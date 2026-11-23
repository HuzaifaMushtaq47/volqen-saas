"""Runs ON a customer's own site, called once by the provisioner through `bench execute`.

Sets the company up, creates the customer's admin user and limits the site to the
modules, roles and user count their plan allows.
"""

import json
import os
from datetime import date, timedelta

import frappe

from volqen_saas import plans

MONTHS = 12
ALL_APPS = ("erpnext", "hrms")


def _fiscal_year(fy_start_month):
    try:
        month = int(fy_start_month or 1)
    except (TypeError, ValueError):
        month = 1
    month = min(max(month, 1), MONTHS)
    today = date.today()
    year = today.year if today.month >= month else today.year - 1
    start = date(year, month, 1)
    end_year, end_month = (year + 1, month - 1) if month > 1 else (year, 12)
    next_month_start = date(end_year + 1, 1, 1) if end_month == 12 else date(end_year, end_month + 1, 1)
    last_day = next_month_start - timedelta(days=1)
    return start.isoformat(), last_day.isoformat()


def _abbr(name):
    initials = "".join(word[0] for word in str(name).split() if word)
    return (initials or "CO").upper()[:5]


def run_setup_wizard(payload):
    if frappe.db.get_single_value("System Settings", "setup_complete"):
        return "setup wizard already completed"
    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    fy_start, fy_end = _fiscal_year(payload.get("fy_start_month"))
    country = payload.get("country") or "United States"
    args = {
        "language": "English",
        "country": country,
        "timezone": payload.get("timezone") or frappe.utils.get_time_zone(),
        "currency": payload.get("currency") or "USD",
        "full_name": payload.get("full_name"),
        "email": payload.get("email"),
        "password": payload.get("password"),
        "company_name": payload.get("company_name"),
        "company_abbr": _abbr(payload.get("company_name")),
        "chart_of_accounts": "Standard",
        "fy_start_date": fy_start,
        "fy_end_date": fy_end,
        "setup_demo": 0,
    }
    setup_complete(args)
    return f"company {payload.get('company_name')} created ({country}, {args['currency']}, FY {fy_start})"


def ensure_admin_user(payload):
    """The setup wizard normally creates this user; make sure it exists either way."""
    email = payload.get("email")
    if not email:
        return "no admin email supplied"
    first, _, last = (payload.get("full_name") or "").partition(" ")
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
        created = False
    else:
        user = frappe.new_doc("User")
        user.email = email
        user.send_welcome_email = 0
        created = True
    user.first_name = first or payload.get("company_name")
    user.last_name = last or ""
    user.mobile_no = payload.get("phone") or user.get("mobile_no")
    user.user_type = "System User"
    user.enabled = 1
    user.flags.ignore_permissions = True
    user.save(ignore_permissions=True)
    if created and payload.get("password"):
        from frappe.utils.password import update_password

        update_password(email, payload["password"])
    return f"admin user {email} {'created' if created else 'updated'}"


def apply_plan(plan_id, admin_email=None):
    """Block modules outside the plan, build a role profile, cap the user count."""
    plan = plans.plan_or_throw(plan_id)
    notes = []

    installed = frappe.get_installed_apps()
    module_defs = frappe.get_all(
        "Module Def", filters={"app_name": ["in", [a for a in ALL_APPS if a in installed]]}, pluck="name"
    )
    blocked = [m for m in module_defs if m not in plan["erpModules"]]
    profile_name = f"Volqen {plan['name']}"
    mp = (
        frappe.get_doc("Module Profile", profile_name)
        if frappe.db.exists("Module Profile", profile_name)
        else frappe.new_doc("Module Profile")
    )
    mp.module_profile_name = profile_name
    mp.set("block_modules", [{"module": m} for m in blocked])
    mp.flags.ignore_permissions = True
    mp.save(ignore_permissions=True)
    notes.append(f"module profile '{profile_name}' blocks {len(blocked)} modules")

    existing_roles = frappe.get_all("Role", filters={"name": ["in", plan["roles"]]}, pluck="name")
    rp = (
        frappe.get_doc("Role Profile", profile_name)
        if frappe.db.exists("Role Profile", profile_name)
        else frappe.new_doc("Role Profile")
    )
    rp.role_profile = profile_name
    rp.set("roles", [{"role": r} for r in ["System Manager"] + existing_roles])
    rp.flags.ignore_permissions = True
    rp.save(ignore_permissions=True)
    notes.append(f"role profile with {len(existing_roles) + 1} roles")

    if admin_email and frappe.db.exists("User", admin_email):
        user = frappe.get_doc("User", admin_email)
        user.role_profile_name = profile_name
        user.module_profile = profile_name
        user.flags.ignore_permissions = True
        user.save(ignore_permissions=True)
        notes.append(f"profiles assigned to {admin_email}")

    notes.append(set_user_limit(plan["maxUsers"]))
    return "; ".join(notes)


def set_user_limit(max_users):
    """A Server Script that refuses a new system user past the plan's limit."""
    if not frappe.conf.get("server_script_enabled"):
        return f"user limit of {max_users} NOT enforced (server_script_enabled is off)"
    script = "\n".join([
        f"limit = {int(max_users)}",
        'if doc.user_type == "System User" and doc.enabled:',
        '    count = frappe.db.count("User", {"user_type": "System User", "enabled": 1,'
        '        "name": ["not in", ["Administrator", "Guest"]]})',
        "    if count >= limit:",
        '        frappe.throw("Your Volqen plan allows " + str(limit) + " users. '
        'Please upgrade your plan to add more users.")',
    ])
    name = "Volqen User Limit"
    doc = (
        frappe.get_doc("Server Script", name)
        if frappe.db.exists("Server Script", name)
        else frappe.new_doc("Server Script")
    )
    if not doc.get("name"):
        doc.name = name
    doc.script_type = "DocType Event"
    doc.reference_doctype = "User"
    doc.doctype_event = "Before Insert"
    doc.script = script
    doc.disabled = 0
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    return f"user limit set to {max_users}"


def bootstrap(payload):
    """Everything a brand-new customer site needs, in one call."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    notes = [run_setup_wizard(payload), ensure_admin_user(payload)]
    frappe.db.commit()
    notes.append(apply_plan(payload.get("plan", {}).get("id") or payload.get("plan"), payload.get("email")))
    frappe.db.commit()
    return " | ".join(n for n in notes if n)


def bootstrap_from_file(path):
    """Entry point used by `bench execute`; the file holds the signup details."""
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    try:
        result = bootstrap(payload)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    print(result)
    return result
