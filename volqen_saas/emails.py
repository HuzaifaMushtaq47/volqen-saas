"""Emails sent to the customer and to the Volqen team."""

import frappe

from volqen_saas import settings, utils


def _shell(title, rows_html, intro, button=None):
    btn = (
        f'<a href="{button[0]}" style="display:inline-block;margin-top:8px;background:#38B6F4;'
        f'color:#04102B;text-decoration:none;font-weight:700;padding:12px 22px;border-radius:999px">{button[1]}</a>'
        if button else ""
    )
    return f"""<div style="background:#050A18;padding:28px 18px;font-family:Segoe UI,Arial,sans-serif">
<div style="max-width:560px;margin:0 auto">
<div style="font-size:22px;font-weight:800;color:#fff">Volqen <span style="color:#38B6F4">ERP</span></div>
<div style="margin-top:18px;background:#0C1838;border:1px solid #1E2F5C;border-radius:16px;padding:26px">
<h1 style="margin:0 0 14px;font-size:21px;color:#fff">{frappe.utils.escape_html(title)}</h1>
<p style="color:#C3D0EC;line-height:1.6;margin:0 0 14px">{intro}</p>
{rows_html}{btn}</div></div></div>"""


def _rows(pairs):
    cells = "".join(
        f'<tr><td style="padding:9px 14px;color:#8E9EC2;font-size:13px">{frappe.utils.escape_html(k)}</td>'
        f'<td style="padding:9px 14px;color:#fff;font-family:Consolas,monospace;font-size:13px">'
        f'{frappe.utils.escape_html(str(v))}</td></tr>'
        for k, v in pairs if v
    )
    return f'<table style="width:100%;border-collapse:collapse;margin:12px 0;background:#050A18;border-radius:10px">{cells}</table>'


def send_welcome(customer, user_password):
    """Tell the customer their ERP is ready, with the login details."""
    if not settings.as_bool("volqen_send_welcome_email"):
        return "welcome email skipped (volqen_send_welcome_email is off)"
    doc = frappe.get_doc("Customer", customer)
    to = doc.get("volqen_admin_email")
    if not to:
        return "no admin email on the Customer, welcome email not sent"
    url = doc.get("volqen_site_url")
    first = (doc.get("volqen_admin_name") or doc.customer_name).split()[0]
    html = _shell(
        "Your ERP is ready",
        _rows([
            ("ERP address", url),
            ("Username", to),
            ("Temporary password", user_password),
            ("Plan", doc.get("volqen_plan")),
            ("Order", doc.get("volqen_order_id")),
        ]),
        f"Hi {frappe.utils.escape_html(first)}, your Volqen ERP for "
        f"<b>{frappe.utils.escape_html(doc.customer_name)}</b> has been created with its own private database. "
        "Please change your password after the first login.",
        button=(url, "Open my ERP"),
    )
    frappe.sendmail(
        recipients=[to],
        subject=f"Your Volqen ERP is ready - {doc.get('volqen_site_name')}",
        message=html,
        reference_doctype="Customer",
        reference_name=customer,
        now=True,
    )
    frappe.db.set_value("Customer", customer, "volqen_welcome_email_sent", 1, update_modified=False)
    frappe.db.commit()
    return f"welcome email sent to {to}"


def notify_support(doc, subject, body):
    to = settings.get("volqen_support_email")
    if not to:
        return
    try:
        frappe.sendmail(
            recipients=[to],
            subject=f"[Volqen] {subject}",
            message=_shell(subject, _rows([
                ("Customer", doc.customer_name),
                ("Order", doc.get("volqen_order_id")),
                ("Site", doc.get("volqen_site_name")),
            ]), frappe.utils.escape_html(str(body)[:900])),
            now=True,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Volqen: support notification failed")
