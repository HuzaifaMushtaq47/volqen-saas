"""Offline tests for Volqen SaaS: every bench command and ERP write is captured, not run.

    cd volqen-saas && python3 tests/test_logic.py
"""
import json, os, sys, types

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import frappe_stub  # noqa: F401  (installs the fake frappe)
from frappe_stub import FR, Doc

import frappe
from volqen_saas import api, customer, emails, install, plans, provisioner, settings, tenant, utils

RESULTS = []
def check(name, ok, info=""):
    RESULTS.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  - {info}" if info else ""))

BENCH = []
def fake_run(cmd, **kw):
    BENCH.append(cmd)
    return types.SimpleNamespace(returncode=0, stdout="ok", stderr="")

def setup_env(tmp):
    FR.reset()
    BENCH.clear()
    frappe.conf = {
        "volqen_tenant_domain": "localhost",
        "volqen_tenant_scheme": "http",
        "volqen_tenant_port": "8000",
        "volqen_bench_path": tmp,
        "volqen_db_root_password": "rootpw",
        "volqen_support_email": "ops@example.test",
    }
    os.makedirs(os.path.join(tmp, "sites"), exist_ok=True)

def make_customer(**over):
    data = {
        "name": "Orbit Foods Ltd", "customer_name": "Orbit Foods Ltd",
        "volqen_order_id": "VQO-TEST01", "volqen_plan": "Growth", "volqen_subdomain": "orbitfoods",
        "volqen_country": "Pakistan", "volqen_base_currency": "PKR", "volqen_fy_start": "07",
        "volqen_admin_name": "Ali Raza", "volqen_admin_email": "ali@orbitfoods.test",
        "volqen_admin_phone": "+92 300 1234567", "volqen_site_status": "Pending",
        "volqen_users": 12,
    }
    data.update(over)
    doc = Doc("Customer", **data)
    FR.docs[("Customer", doc["name"])] = doc
    return doc


def main():
    import tempfile
    tmp = tempfile.mkdtemp(prefix="bench-")
    setup_env(tmp)

    # ---- subdomain rules
    check("Subdomain: valid name accepted", utils.validate_subdomain("Orbit-Foods") == "orbit-foods")
    bad = []
    for v in ("ab", "1abc", "-abc", "abc-", "a" * 40, "ADMIN", "www"):
        try:
            utils.validate_subdomain(v); bad.append(v)
        except Exception:
            pass
    check("Subdomain: short, reserved and malformed names rejected", not bad, f"accepted {bad}")
    check("Subdomain suggested from company name",
          utils.suggest_subdomain("Orbit Foods Ltd.") == "orbit-foods-ltd", utils.suggest_subdomain("Orbit Foods Ltd."))

    # ---- site naming from settings
    check("Site name uses the configured domain", utils.site_name("orbitfoods") == "orbitfoods.localhost")
    check("Site URL includes the dev port", utils.site_url("orbitfoods") == "http://orbitfoods.localhost:8000",
          utils.site_url("orbitfoods"))
    frappe.conf.update({"volqen_tenant_domain": "volqenerp.com", "volqen_tenant_scheme": "https", "volqen_tenant_port": ""})
    check("Production URL drops the port", utils.site_url("orbitfoods") == "https://orbitfoods.volqenerp.com",
          utils.site_url("orbitfoods"))
    frappe.conf.update({"volqen_tenant_domain": "localhost", "volqen_tenant_scheme": "http", "volqen_tenant_port": "8000"})

    pw = utils.generate_password()
    check("Generated password is long and grouped", len(pw) >= 18 and pw.count("-") == 3, pw)

    # ---- plans
    check("Plan lookup accepts id, name and label",
          all(plans.get_plan(v)["id"] == "growth" for v in ("growth", "Growth", "Volqen Growth")))
    g, s = plans.get_plan("growth"), plans.get_plan("starter")
    check("Growth plan adds HRMS and manufacturing", "hrms" in g["apps"] and "Manufacturing" in g["erpModules"])
    check("Starter plan excludes manufacturing and HR",
          "Manufacturing" not in s["erpModules"] and "hrms" not in s["apps"])

    # ---- custom fields cover every signup field
    fields = install.custom_fields()
    names = {f["fieldname"] for f in fields["Customer"]}
    needed = {"volqen_order_id", "volqen_plan", "volqen_subdomain", "volqen_site_url", "volqen_site_status",
              "volqen_admin_email", "volqen_database_name", "volqen_provision_log", "volqen_site_admin_password"}
    check("Customer fields cover plan, site, admin and log", needed <= names, str(sorted(needed - names)))
    check("Lead carries the website form type", fields["Lead"][0]["fieldname"] == "volqen_form_type")

    # ---- provisioning, happy path
    import subprocess
    real_run = subprocess.run
    subprocess.run = fake_run
    try:
        doc = make_customer()
        out = provisioner.provision("Orbit Foods Ltd")
        cmds = [" ".join(c) for c in BENCH]
        new_site = next((c for c in cmds if "new-site" in c), "")
        check("Provision: result is Active with the right URL",
              out["ok"] and out["status"] == "Active" and out["url"] == "http://orbitfoods.localhost:8000", str(out))
        check("Provision: bench creates the site with its own database",
              "new-site orbitfoods.localhost" in new_site and "--db-root-password rootpw" in new_site, new_site[:120])
        check("Provision: plan apps installed (erpnext + hrms)",
              "--install-app erpnext" in new_site and "--install-app hrms" in new_site)
        check("Provision: volqen_saas installed on the customer site",
              any("install-app volqen_saas" in c for c in cmds))
        check("Provision: tenant bootstrap executed", any("volqen_saas.tenant.bootstrap_from_file" in c for c in cmds))
        check("Provision: scheduler and server scripts enabled",
              any("enable-scheduler" in c for c in cmds) and any("server_script_enabled 1" in c for c in cmds))
        check("Provision: host_name set on the new site", any("host_name http://orbitfoods.localhost:8000" in c for c in cmds))
        status = FR.docs[("Customer", "Orbit Foods Ltd")]
        check("Provision: Customer marked Active with site name and URL",
              status["volqen_site_status"] == "Active" and status["volqen_site_name"] == "orbitfoods.localhost")
        check("Provision: steps written to the provisioning log",
              str(status.get("volqen_provision_log", "")).count("\n") >= 4)
        check("Provision: temporary password never written to the log",
              "Temporary" not in str(status.get("volqen_provision_log", "")))

        # ---- welcome email
        mail = FR.emails[-1] if FR.emails else {}
        body = mail.get("message", "")
        check("Welcome email sent to the customer admin", mail.get("recipients") == ["ali@orbitfoods.test"])
        check("Welcome email carries site, username and password",
              "orbitfoods.localhost" in body and "ali@orbitfoods.test" in body and "Temporary password" in body)
        enc = FR.__dict__.get("encrypted", [])
        check("Provision: site Administrator password saved in Frappe's encrypted store",
              enc and enc[-1][0] == "Customer" and enc[-1][2] == "volqen_site_admin_password" and len(enc[-1][3]) >= 18)
        check("Welcome email does not leak the Administrator password", enc[-1][3] not in body)

        # ---- idempotence
        BENCH.clear()
        again = provisioner.provision("Orbit Foods Ltd")
        check("Provision: running again on an active customer does nothing",
              again["message"] == "already active" and not BENCH, str(again))

        # ---- failure path
        FR.reset(); BENCH.clear()
        make_customer(name="Broken Co", customer_name="Broken Co", volqen_subdomain="brokenco")
        def boom(cmd, **kw):
            BENCH.append(cmd)
            return types.SimpleNamespace(returncode=1, stdout="", stderr="MySQL root password is wrong")
        subprocess.run = boom
        res = provisioner.provision("Broken Co")
        failed = FR.docs[("Customer", "Broken Co")]
        check("Failure: customer marked Failed, reason kept in the log",
              not res["ok"] and failed["volqen_site_status"] == "Failed"
              and "root password" in failed.get("volqen_provision_log", ""), str(res)[:90])
        check("Failure: support notified by email", any("[Volqen]" in m.get("subject", "") for m in FR.emails))
        subprocess.run = fake_run

        # ---- dry run
        FR.reset(); BENCH.clear()
        frappe.conf["volqen_dry_run"] = 1
        make_customer(name="Dry Run Co", customer_name="Dry Run Co", volqen_subdomain="dryrunco")
        provisioner.provision("Dry Run Co")
        check("Dry run: no bench command actually executed", not BENCH)
        frappe.conf["volqen_dry_run"] = 0
    finally:
        subprocess.run = real_run

    # ---- tenant-side plan enforcement
    FR.reset()
    frappe.conf["server_script_enabled"] = 1
    note = tenant.apply_plan("starter")
    mp = next(d for dt, d in FR.saved if dt == "Module Profile")
    blocked = [b.module for b in mp["block_modules"]]
    check("Tenant: Starter blocks Manufacturing, HR and Payroll",
          {"Manufacturing", "HR", "Payroll"} <= set(blocked), f"{len(blocked)} blocked")
    check("Tenant: Starter keeps Accounts, Selling, Stock",
          not ({"Accounts", "Selling", "Stock"} & set(blocked)))
    script = next(d for dt, d in FR.saved if dt == "Server Script")["script"]
    check("Tenant: user limit script matches the plan", "limit = 5" in script, script.splitlines()[0])
    check("Tenant: Growth raises the limit to 25", "limit = 25" in
          next(d for dt, d in FR.saved if dt == "Server Script" and "25" in d["script"])["script"]
          if (tenant.apply_plan("growth") or True) else False)

    FR.reset()
    frappe.conf["server_script_enabled"] = 0
    msg = tenant.set_user_limit(5)
    check("Tenant: limit is reported as NOT enforced when server scripts are off", "NOT enforced" in msg, msg)
    frappe.conf["server_script_enabled"] = 1

    # ---- tenant setup wizard arguments
    FR.reset()
    out = tenant.run_setup_wizard({
        "company_name": "Orbit Foods Ltd", "country": "Pakistan", "currency": "PKR",
        "fy_start_month": "07", "full_name": "Ali Raza", "email": "ali@orbitfoods.test", "password": "x",
    })
    args = FR.__dict__["wizard"][-1]
    check("Tenant: setup wizard gets company, country, currency and fiscal year",
          args["company_name"] == "Orbit Foods Ltd" and args["currency"] == "PKR"
          and args["fy_start_date"] == "2026-07-01" and args["fy_end_date"] == "2027-06-30", str(args)[:110])
    check("Tenant: company abbreviation generated", args["company_abbr"] == "OFL", args["company_abbr"])

    # ---- website API
    FR.reset()
    setup_env(tmp)
    res = api.signup({
        "orderId": "VQO-AAA111", "plan": "growth", "cycle": "annual", "companyName": "Orbit Foods Ltd",
        "country": "PK", "currency": "PKR", "users": 12, "fyStart": "07", "industry": "Manufacturing",
        "modules": ["manufacturing", "accounting-finance"], "fullName": "Ali Raza",
        "email": "ali@orbitfoods.test", "phone": "+92 300 1234567", "subdomain": "orbitfoods",
        "paymentMethod": "bank", "paid": True, "amount": "PKR 11600",
    })
    cust = next(d for dt, d in FR.inserted if dt == "Customer")
    check("API: signup creates the Customer with the signup details",
          cust["volqen_plan"] == "Growth" and cust["volqen_subdomain"] == "orbitfoods"
          and cust["volqen_users"] == 12 and cust["volqen_base_currency"] == "PKR", str(res))
    check("API: module slugs stored as readable names",
          "Manufacturing & Production" in cust["volqen_modules"], cust["volqen_modules"])
    check("API: payment marked paid, billing cycle annual",
          cust["volqen_payment_status"] == "Paid" and cust["volqen_billing_cycle"] == "Annual")
    check("API: status endpoint hides the URL until the site is live", res["siteUrl"] is None and res["status"] == "Pending")

    dupe = api.signup({"orderId": "VQO-AAA111", "plan": "growth", "companyName": "Orbit Foods Ltd",
                       "email": "ali@orbitfoods.test", "subdomain": "orbitfoods"})
    check("API: the same order twice does not create a second Customer",
          len([1 for dt, _ in FR.inserted if dt == "Customer"]) == 1, str(dupe)[:80])

    check("API: taken subdomain reported as unavailable", api.check_subdomain("orbitfoods")["available"] is False)
    check("API: free subdomain reported as available", api.check_subdomain("brandnewco")["available"] is True)
    check("API: reserved subdomain reported as unavailable", api.check_subdomain("admin")["available"] is False)

    FR.reset()
    lead = api.website_lead({"formType": "demo", "name": "Sara Khan", "company": "Acme",
                             "email": "sara@acme.test", "phone": "+971 50 123 4567",
                             "industry": "Retail", "message": "Please call me"})
    inserted_lead = next(d for dt, d in FR.inserted if dt == "Lead")
    check("API: website form creates a Lead with the form type",
          inserted_lead["volqen_form_type"] == "demo" and inserted_lead["email_id"] == "sara@acme.test", str(lead))
    check("API: form answers kept as a comment on the Lead",
          FR.comments and "Retail" in FR.comments[-1][2] and "Please call me" in FR.comments[-1][2])

    # ---- Customer events
    FR.reset()
    setup_env(tmp)
    doc = make_customer(volqen_portal_user=None)
    customer.after_insert(doc)
    check("Customer event: provisioning queued automatically",
          any("provisioner.provision" in m for m, _ in FR.enqueued), str(FR.enqueued)[:90])
    portal = [d for dt, d in FR.saved if dt == "User"]
    check("Customer event: portal user created for the admin contact",
          portal and portal[0]["email"] == "ali@orbitfoods.test", str(portal)[:80])
    contact = [d for dt, d in FR.saved if dt == "Contact"]
    check("Customer event: contact linked back to the Customer",
          contact and contact[0]["links"][0].link_name == "Orbit Foods Ltd")

    FR.reset()
    frappe.conf["volqen_auto_provision"] = 0
    doc = make_customer()
    customer.after_insert(doc)
    check("Customer event: auto-provision can be switched off", not FR.enqueued)
    frappe.conf["volqen_auto_provision"] = 1

    print(f"\n{sum(RESULTS)}/{len(RESULTS)} checks passed")
    return 0 if all(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
