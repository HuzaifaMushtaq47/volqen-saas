"""Customer document events: keep the signup data tidy, create the portal user,
and start provisioning the customer's own ERP site."""

import frappe

from volqen_saas import provisioner, settings, utils


def _ready_to_provision(doc):
    return bool(doc.get("volqen_subdomain")) and doc.get("volqen_site_status") in (None, "", "Pending")


def after_insert(doc, method=None):
    _fill_defaults(doc)
    create_portal_user(doc)
    if settings.as_bool("volqen_auto_provision") and _ready_to_provision(doc):
        provisioner.enqueue(doc.name)


def on_update(doc, method=None):
    before = doc.get_doc_before_save()
    if not before:
        return
    changed = (before.get("volqen_subdomain") or "") != (doc.get("volqen_subdomain") or "")
    if changed and doc.get("volqen_subdomain"):
        _fill_defaults(doc)
    if not before.get("volqen_portal_user"):
        create_portal_user(doc)
    if settings.as_bool("volqen_auto_provision") and _ready_to_provision(doc) and doc.get("volqen_subdomain"):
        provisioner.enqueue(doc.name)


def _fill_defaults(doc):
    values = {}
    if doc.get("volqen_subdomain"):
        sub = utils.validate_subdomain(doc.get("volqen_subdomain"))
        values["volqen_subdomain"] = sub
        values["volqen_site_name"] = utils.site_name(sub)
        values["volqen_site_url"] = utils.site_url(sub)
    if not doc.get("volqen_site_status"):
        values["volqen_site_status"] = "Pending"
    if not doc.get("volqen_signup_date"):
        values["volqen_signup_date"] = frappe.utils.now_datetime()
    if values:
        frappe.db.set_value("Customer", doc.name, values, update_modified=False)
        doc.reload()


def create_portal_user(doc):
    """A login on THIS ERP so the customer can see their own invoices."""
    if not settings.as_bool("volqen_create_portal_user"):
        return None
    email = doc.get("volqen_admin_email")
    if not email or doc.get("volqen_portal_user"):
        return doc.get("volqen_portal_user")

    first, last = utils.split_name(doc.get("volqen_admin_name") or doc.customer_name)
    if frappe.db.exists("User", email):
        user = frappe.get_doc("User", email)
    else:
        user = frappe.new_doc("User")
        user.email = email
        user.first_name = first
        user.last_name = last
        user.user_type = "Website User"
        user.send_welcome_email = 0
    user.mobile_no = doc.get("volqen_admin_phone") or user.get("mobile_no")
    role = settings.get("volqen_portal_user_role")
    if role and frappe.db.exists("Role", role) and role not in [r.role for r in user.get("roles", [])]:
        user.append("roles", {"role": role})
    user.flags.ignore_permissions = True
    user.save(ignore_permissions=True)

    _link_contact(doc, user, first, last)
    frappe.db.set_value("Customer", doc.name, "volqen_portal_user", user.name, update_modified=False)
    utils.log(doc.name, f"portal user {user.name} linked to this customer")
    return user.name


def _link_contact(doc, user, first, last):
    existing = frappe.get_all(
        "Contact Email", filters={"email_id": user.name}, fields=["parent"], limit=1
    )
    if existing:
        contact = frappe.get_doc("Contact", existing[0].parent)
    else:
        contact = frappe.new_doc("Contact")
        contact.first_name = first
        contact.last_name = last
        contact.user = user.name
        contact.append("email_ids", {"email_id": user.name, "is_primary": 1})
        if doc.get("volqen_admin_phone"):
            contact.append("phone_nos", {"phone": doc.get("volqen_admin_phone"), "is_primary_mobile_no": 1})
    links = [(l.link_doctype, l.link_name) for l in contact.get("links", [])]
    if ("Customer", doc.name) not in links:
        contact.append("links", {"link_doctype": "Customer", "link_name": doc.name})
    contact.flags.ignore_permissions = True
    contact.save(ignore_permissions=True)
    if not doc.get("customer_primary_contact"):
        frappe.db.set_value("Customer", doc.name, "customer_primary_contact", contact.name, update_modified=False)
    return contact.name
