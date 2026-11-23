"""Endpoints the Volqen website calls.

Authenticate with an ERPNext API key and secret:
    Authorization: token <api_key>:<api_secret>

    POST /api/method/volqen_saas.api.signup
    GET  /api/method/volqen_saas.api.signup_status?order_id=VQO-...
    POST /api/method/volqen_saas.api.website_lead
"""

import json

import frappe

from volqen_saas import plans, provisioner, settings, utils

MODULE_LABELS = {
    "accounting-finance": "Accounting & Finance",
    "inventory-warehouse": "Inventory & Warehouse",
    "procurement": "Procurement & Purchasing",
    "sales-crm": "Sales & CRM",
    "manufacturing": "Manufacturing & Production",
    "quality": "Quality Management",
    "hr-payroll": "HR & Payroll",
    "projects": "Project Management",
    "assets-maintenance": "Assets & Maintenance",
    "business-intelligence": "Business Intelligence",
    "workflow-controls": "Workflow, Roles & Permissions",
}


def _data(payload=None):
    if isinstance(payload, str):
        return json.loads(payload)
    if isinstance(payload, dict):
        return payload
    return frappe.local.form_dict


def _clean(value, limit=200):
    if isinstance(value, (list, tuple)):
        value = ", ".join(str(v) for v in value)
    return str(value or "").strip()[:limit]


@frappe.whitelist()
def check_subdomain(subdomain):
    """Used by the website while the visitor types."""
    sub = (subdomain or "").strip().lower()
    if not utils.SUBDOMAIN_RE.match(sub):
        return {"available": False, "reason": "Use 3-30 lowercase letters, numbers or hyphens, starting with a letter."}
    if sub in utils.RESERVED_SUBDOMAINS:
        return {"available": False, "reason": "This address is reserved. Please choose another."}
    if frappe.db.exists("Customer", {"volqen_subdomain": sub}):
        return {"available": False, "reason": "This address is already taken. Try another."}
    if provisioner.site_exists(utils.site_name(sub)):
        return {"available": False, "reason": "This address is already taken. Try another."}
    return {"available": True}


@frappe.whitelist()
def signup(payload=None):
    """Create the Customer for a paid website signup. Provisioning starts on its own."""
    data = _data(payload)
    order_id = _clean(data.get("orderId") or data.get("volqen_order_id"), 40)
    company = _clean(data.get("companyName") or data.get("customer_name"), 140)
    email = _clean(data.get("email") or data.get("volqen_admin_email"), 160).lower()
    plan = plans.plan_or_throw(data.get("plan"))

    if not company:
        frappe.throw("companyName is required")
    if not email:
        frappe.throw("email is required")

    existing = order_id and frappe.db.exists("Customer", {"volqen_order_id": order_id})
    if existing:
        return _status_payload(existing)

    subdomain = utils.validate_subdomain(data.get("subdomain") or utils.suggest_subdomain(company))
    modules = data.get("modules") or []
    if isinstance(modules, str):
        modules = [m.strip() for m in modules.split(",") if m.strip()]

    doc = frappe.new_doc("Customer")
    doc.customer_name = company
    doc.customer_type = "Company"
    doc.customer_group = settings.get("volqen_customer_group") or frappe.db.get_single_value(
        "Selling Settings", "customer_group"
    ) or "All Customer Groups"
    doc.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
    doc.tax_id = _clean(data.get("taxId"), 40) or None
    doc.update({
        "volqen_order_id": order_id or None,
        "volqen_plan": plan["name"],
        "volqen_billing_cycle": "Annual" if str(data.get("cycle")).lower() == "annual" else "Monthly",
        "volqen_users": frappe.utils.cint(data.get("users")) or None,
        "volqen_industry": _clean(data.get("industry"), 80),
        "volqen_company_size": _clean(data.get("companySize"), 40),
        "volqen_country": _clean(data.get("country"), 60),
        "volqen_base_currency": _clean(data.get("currency"), 3).upper(),
        "volqen_fy_start": _clean(data.get("fyStart"), 2) or "01",
        "volqen_modules": ", ".join(MODULE_LABELS.get(m, m) for m in modules),
        "volqen_subdomain": subdomain,
        "volqen_admin_name": _clean(data.get("fullName"), 120),
        "volqen_admin_email": email,
        "volqen_admin_phone": _clean(data.get("phone"), 30),
        "volqen_payment_provider": _clean(data.get("paymentMethod"), 30),
        "volqen_payment_status": "Paid" if data.get("paid") else "Pending",
        "volqen_payment_ref": _clean(data.get("paymentRef"), 80),
        "volqen_amount": _clean(data.get("amount"), 40),
        "volqen_site_status": "Pending",
    })
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return _status_payload(doc.name)


@frappe.whitelist()
def signup_status(order_id=None, customer=None):
    name = customer or (order_id and frappe.db.get_value("Customer", {"volqen_order_id": order_id}, "name"))
    if not name:
        frappe.throw("Order not found", frappe.DoesNotExistError)
    return _status_payload(name)


def _status_payload(customer):
    doc = frappe.db.get_value(
        "Customer",
        customer,
        ["name", "volqen_order_id", "volqen_site_status", "volqen_site_url", "volqen_site_name",
         "volqen_plan", "volqen_welcome_email_sent"],
        as_dict=True,
    )
    return {
        "customer": doc.name,
        "orderId": doc.volqen_order_id,
        "status": doc.volqen_site_status,
        "siteUrl": doc.volqen_site_url if doc.volqen_site_status == "Active" else None,
        "siteName": doc.volqen_site_name,
        "plan": doc.volqen_plan,
        "welcomeEmailSent": bool(doc.volqen_welcome_email_sent),
    }


@frappe.whitelist()
def website_lead(payload=None):
    """Demo and contact forms from the website."""
    data = _data(payload)
    name = _clean(data.get("name"), 120)
    email = _clean(data.get("email"), 160).lower()
    if not name or not email:
        frappe.throw("name and email are required")
    first, last = utils.split_name(name)
    lead = frappe.new_doc("Lead")
    lead.update({
        "first_name": first,
        "last_name": last,
        "lead_name": name,
        "company_name": _clean(data.get("company"), 140) or None,
        "email_id": email,
        "mobile_no": _clean(data.get("phone"), 30) or None,
        "city": _clean(data.get("city"), 80) or None,
        "status": "Lead",
        "volqen_form_type": _clean(data.get("formType"), 30),
    })
    lead.flags.ignore_permissions = True
    lead.insert(ignore_permissions=True)

    details = [
        ("Form", data.get("formType")), ("Subject", data.get("subject")), ("Job title", data.get("jobTitle")),
        ("Industry", data.get("industry")), ("Company size", data.get("companySize")), ("Users", data.get("users")),
        ("Deployment", data.get("deployment")), ("Current system", data.get("currentSystem")),
        ("Timeline", data.get("timeline")), ("Modules", data.get("modules")), ("Message", data.get("message")),
        ("Reference", data.get("id")),
    ]
    body = "<br>".join(
        f"{frappe.utils.escape_html(k)}: {frappe.utils.escape_html(_clean(v, 2000))}" for k, v in details if v
    )
    if body:
        lead.add_comment("Comment", body)
    frappe.db.commit()
    return {"lead": lead.name}


@frappe.whitelist()
def provision_now(customer, force=0):
    """Called by the button on the Customer form."""
    frappe.only_for(("System Manager", "Sales Manager"))
    provisioner.enqueue(customer, force=bool(frappe.utils.cint(force)))
    return {"queued": True, "customer": customer}


@frappe.whitelist()
def diagnostics():
    """Quick check that the bench settings are right, without creating anything."""
    frappe.only_for("System Manager")
    result = {"settings": settings.all_settings(), "plans": [p["id"] for p in plans.all_plans()]}
    try:
        result["bench_path_ok"] = bool(provisioner.bench_path())
        result["bench_version"] = provisioner.run_bench(["--version"], timeout=60)
    except Exception as exc:
        result["bench_path_ok"] = False
        result["error"] = str(exc)
    return result
