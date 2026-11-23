"""Creates one ERPNext site (with its own database) per Customer.

Every step runs `bench` on this server as a subprocess. Nothing is passed through a
shell, and the database root password and the new site's admin password travel on
stdin or in a file that is deleted straight after, so they never reach the process list.
"""

import json
import os
import subprocess
import tempfile

import frappe

from volqen_saas import emails, plans, settings, utils

STEPS = ("create_site", "install_app", "bootstrap", "finalise", "notify")


# --------------------------------------------------------------------------- bench

def bench_path():
    path = settings.get("volqen_bench_path")
    if not path or not os.path.isdir(os.path.join(path, "sites")):
        frappe.throw(
            f"volqen_bench_path ({path!r}) does not look like a bench directory. "
            "Set it with: bench --site <site> set-config volqen_bench_path /path/to/frappe-bench"
        )
    return path


def run_bench(args, timeout=None, stdin_text=None):
    """Run one bench command and return its output. Raises on a non-zero exit."""
    cmd = ["bench"] + [str(a) for a in args]
    if settings.as_bool("volqen_dry_run"):
        return f"DRY RUN: {' '.join(cmd)}"
    try:
        proc = subprocess.run(
            cmd,
            cwd=bench_path(),
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout or int(settings.get("volqen_bench_timeout")),
            shell=False,
            check=False,
        )
    except FileNotFoundError:
        frappe.throw("`bench` was not found on this server. Volqen SaaS must run on the bench host.")
    except subprocess.TimeoutExpired:
        frappe.throw(f"Timed out running: {' '.join(cmd[:3])}")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        raise ProvisioningError(f"`{' '.join(cmd[:4])}` failed ({proc.returncode}): {out.strip()[-1200:]}")
    return out.strip()


class ProvisioningError(Exception):
    pass


def site_exists(site):
    return os.path.isdir(os.path.join(bench_path(), "sites", site))


def database_name(site):
    """Read the database bench generated for the site."""
    cfg = os.path.join(bench_path(), "sites", site, "site_config.json")
    try:
        with open(cfg, encoding="utf-8") as f:
            return json.load(f).get("db_name") or ""
    except OSError:
        return ""


# --------------------------------------------------------------------------- steps

def _payload(doc, plan, admin_password, user_password):
    return {
        "company_name": doc.customer_name,
        "country": doc.get("volqen_country") or "",
        "currency": doc.get("volqen_base_currency") or "",
        "fy_start_month": doc.get("volqen_fy_start") or "01",
        "full_name": doc.get("volqen_admin_name") or doc.customer_name,
        "email": doc.get("volqen_admin_email") or "",
        "password": user_password,
        "phone": doc.get("volqen_admin_phone") or "",
        "plan": plan,
        "host_name": utils.site_url(doc.get("volqen_subdomain")),
        "admin_password": admin_password,
    }


def _create_site(doc, plan, admin_password):
    site = utils.site_name(doc.get("volqen_subdomain"))
    if site_exists(site):
        return f"site {site} already exists, reusing it"
    db_root = settings.get("volqen_db_root_password")
    if not db_root and not settings.as_bool("volqen_dry_run"):
        frappe.throw(
            "The MariaDB root password is not set. Run: "
            "bench --site <this site> set-config volqen_db_root_password '<password>'"
        )
    apps = list(settings.default_apps())
    for app in plan.get("apps", []):
        if app not in apps:
            apps.append(app)
    args = ["new-site", site, "--admin-password", admin_password, "--db-root-password", db_root or "x"]
    for app in apps:
        args += ["--install-app", app]
    run_bench(args, timeout=int(settings.get("volqen_bench_timeout")))
    return f"created site {site} with apps: {', '.join(apps)}"


def _install_app(doc, site):
    if not settings.as_bool("volqen_install_app_on_tenant"):
        return "skipped (volqen_install_app_on_tenant is off)"
    run_bench(["--site", site, "install-app", "volqen_saas"], timeout=600)
    return "installed volqen_saas on the customer site"


def _bootstrap(doc, site, payload):
    """Hand the setup details to the new site through a one-shot file."""
    if not settings.as_bool("volqen_install_app_on_tenant"):
        return "skipped: the customer site needs volqen_saas to run its setup"
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=bench_path(), encoding="utf-8")
    try:
        json.dump(payload, tmp)
        tmp.close()
        os.chmod(tmp.name, 0o600)
        out = run_bench(
            ["--site", site, "execute", "volqen_saas.tenant.bootstrap_from_file", "--args", json.dumps([tmp.name])],
            timeout=int(settings.get("volqen_bench_timeout")),
        )
        return (out or "setup finished").strip()[-800:]
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def _finalise(doc, site):
    notes = []
    run_bench(["--site", site, "set-config", "server_script_enabled", "1"], timeout=120)
    run_bench(["--site", site, "set-config", "-p", "host_name", utils.site_url(doc.get("volqen_subdomain"))], timeout=120)
    run_bench(["--site", site, "enable-scheduler"], timeout=120)
    notes.append("scheduler enabled, server scripts allowed")
    if settings.as_bool("volqen_setup_nginx"):
        run_bench(["setup", "nginx", "--yes"], timeout=300)
        notes.append("nginx config regenerated (reload nginx to serve the new domain)")
    return "; ".join(notes)


# --------------------------------------------------------------------------- entry points

def provision(customer, force=False):
    """Create the site for one Customer. Safe to call again after a failure."""
    doc = frappe.get_doc("Customer", customer)
    status = doc.get("volqen_site_status")
    if status == "Active" and not force:
        return {"ok": True, "status": status, "message": "already active"}
    if status == "Provisioning" and not force:
        return {"ok": False, "status": status, "message": "already running"}

    subdomain = utils.validate_subdomain(doc.get("volqen_subdomain"))
    plan = plans.plan_or_throw(doc.get("volqen_plan"))
    site = utils.site_name(subdomain)

    admin_password = doc.get_password("volqen_site_admin_password", raise_exception=False) or utils.generate_password()
    user_password = utils.generate_password(14)

    frappe.db.set_value("Customer", customer, {
        "volqen_site_status": "Provisioning",
        "volqen_site_name": site,
        "volqen_site_url": utils.site_url(subdomain),
    }, update_modified=False)
    frappe.db.commit()
    utils.log(customer, f"provisioning started for {site} on the {plan['name']} plan")

    try:
        utils.log(customer, "1/5 " + _create_site(doc, plan, admin_password))
        utils.log(customer, "2/5 " + _install_app(doc, site))
        utils.log(customer, "3/5 " + _bootstrap(doc, site, _payload(doc, plan, admin_password, user_password)))
        utils.log(customer, "4/5 " + _finalise(doc, site))
    except Exception as exc:
        frappe.db.set_value("Customer", customer, "volqen_site_status", "Failed", update_modified=False)
        utils.log(customer, f"FAILED: {exc}")
        frappe.log_error(frappe.get_traceback(), f"Volqen provisioning failed: {customer}")
        emails.notify_support(doc, f"Provisioning failed for {site}", str(exc))
        return {"ok": False, "status": "Failed", "message": str(exc)}

    doc.reload()
    doc.db_set("volqen_site_admin_password", admin_password, update_modified=False)
    frappe.db.set_value("Customer", customer, {
        "volqen_site_status": "Active",
        "volqen_database_name": database_name(site),
        "volqen_provisioned_on": frappe.utils.now_datetime(),
    }, update_modified=False)
    frappe.db.commit()

    sent = emails.send_welcome(customer, user_password)
    utils.log(customer, "5/5 " + sent)
    return {"ok": True, "status": "Active", "site": site, "url": utils.site_url(subdomain)}


def enqueue(customer, force=False):
    frappe.db.set_value("Customer", customer, "volqen_site_status", "Queued", update_modified=False)
    frappe.enqueue(
        "volqen_saas.provisioner.provision",
        queue="long",
        timeout=int(settings.get("volqen_bench_timeout")) + 600,
        job_name=f"volqen-provision-{customer}",
        customer=customer,
        force=force,
    )
    utils.log(customer, "queued for provisioning")


def retry_stuck_customers():
    """Scheduled: pick up anything left Queued by a restart."""
    stuck = frappe.get_all(
        "Customer",
        filters={"volqen_site_status": "Queued", "volqen_subdomain": ["is", "set"]},
        fields=["name", "modified"],
        limit=20,
    )
    for row in stuck:
        if frappe.utils.time_diff_in_seconds(frappe.utils.now_datetime(), row.modified) > 900:
            enqueue(row.name)
