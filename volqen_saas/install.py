"""Creates the Volqen fields on Customer and Lead. Runs on install and on every migrate."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from volqen_saas import plans

SITE_STATUS = "\n".join(["Pending", "Queued", "Provisioning", "Active", "Failed", "Suspended", "Cancelled"])
PAYMENT_STATUS = "\n".join(["Pending", "Awaiting Bank Transfer", "Paid", "Failed", "Refunded"])


def custom_fields():
    return {
        "Customer": [
            {"fieldname": "volqen_sb_plan", "label": "Volqen Subscription", "fieldtype": "Section Break", "insert_after": "tax_id", "collapsible": 0},
            {"fieldname": "volqen_order_id", "label": "Order ID", "fieldtype": "Data", "insert_after": "volqen_sb_plan", "unique": 1, "read_only": 1, "in_standard_filter": 1},
            {"fieldname": "volqen_plan", "label": "Plan", "fieldtype": "Select", "options": plans.plan_options(), "insert_after": "volqen_order_id", "in_list_view": 1, "in_standard_filter": 1, "reqd": 0},
            {"fieldname": "volqen_billing_cycle", "label": "Billing Cycle", "fieldtype": "Select", "options": "\nMonthly\nAnnual", "insert_after": "volqen_plan"},
            {"fieldname": "volqen_users", "label": "Licensed Users", "fieldtype": "Int", "insert_after": "volqen_billing_cycle"},
            {"fieldname": "volqen_industry", "label": "Industry", "fieldtype": "Data", "insert_after": "volqen_users", "in_standard_filter": 1},
            {"fieldname": "volqen_company_size", "label": "Company Size", "fieldtype": "Data", "insert_after": "volqen_industry"},
            {"fieldname": "volqen_cb_plan", "fieldtype": "Column Break", "insert_after": "volqen_company_size"},
            {"fieldname": "volqen_country", "label": "Country (signup)", "fieldtype": "Data", "insert_after": "volqen_cb_plan"},
            {"fieldname": "volqen_base_currency", "label": "ERP Base Currency", "fieldtype": "Data", "insert_after": "volqen_country"},
            {"fieldname": "volqen_fy_start", "label": "Financial Year Start (MM)", "fieldtype": "Data", "insert_after": "volqen_base_currency"},
            {"fieldname": "volqen_modules", "label": "Requested Modules", "fieldtype": "Small Text", "insert_after": "volqen_fy_start"},
            {"fieldname": "volqen_signup_date", "label": "Signup Date", "fieldtype": "Datetime", "insert_after": "volqen_modules"},

            {"fieldname": "volqen_sb_site", "label": "ERP Site", "fieldtype": "Section Break", "insert_after": "volqen_signup_date"},
            {"fieldname": "volqen_subdomain", "label": "Subdomain", "fieldtype": "Data", "insert_after": "volqen_sb_site", "unique": 1, "description": "Customer site becomes &lt;subdomain&gt;.&lt;tenant domain&gt;"},
            {"fieldname": "volqen_site_name", "label": "Site Name", "fieldtype": "Data", "insert_after": "volqen_subdomain", "read_only": 1},
            {"fieldname": "volqen_site_url", "label": "Site URL", "fieldtype": "Data", "options": "URL", "insert_after": "volqen_site_name", "read_only": 1},
            {"fieldname": "volqen_database_name", "label": "Database", "fieldtype": "Data", "insert_after": "volqen_site_url", "read_only": 1},
            {"fieldname": "volqen_cb_site", "fieldtype": "Column Break", "insert_after": "volqen_database_name"},
            {"fieldname": "volqen_site_status", "label": "Site Status", "fieldtype": "Select", "options": SITE_STATUS, "default": "Pending", "insert_after": "volqen_cb_site", "in_list_view": 1, "in_standard_filter": 1, "read_only": 1},
            {"fieldname": "volqen_site_admin_password", "label": "Site Administrator Password", "fieldtype": "Password", "insert_after": "volqen_site_status", "description": "Volqen support login for this customer's site. Never emailed to the customer."},
            {"fieldname": "volqen_provisioned_on", "label": "Provisioned On", "fieldtype": "Datetime", "insert_after": "volqen_site_admin_password", "read_only": 1},

            {"fieldname": "volqen_sb_admin", "label": "Customer Admin", "fieldtype": "Section Break", "insert_after": "volqen_provisioned_on"},
            {"fieldname": "volqen_admin_name", "label": "Admin Name", "fieldtype": "Data", "insert_after": "volqen_sb_admin"},
            {"fieldname": "volqen_admin_email", "label": "Admin Email", "fieldtype": "Data", "options": "Email", "insert_after": "volqen_admin_name"},
            {"fieldname": "volqen_admin_phone", "label": "Admin Phone", "fieldtype": "Data", "insert_after": "volqen_admin_email"},
            {"fieldname": "volqen_cb_admin", "fieldtype": "Column Break", "insert_after": "volqen_admin_phone"},
            {"fieldname": "volqen_portal_user", "label": "Portal User", "fieldtype": "Link", "options": "User", "insert_after": "volqen_cb_admin", "read_only": 1},
            {"fieldname": "volqen_subscription", "label": "Subscription", "fieldtype": "Link", "options": "Subscription", "insert_after": "volqen_portal_user", "read_only": 1},
            {"fieldname": "volqen_welcome_email_sent", "label": "Welcome Email Sent", "fieldtype": "Check", "insert_after": "volqen_subscription", "read_only": 1},

            {"fieldname": "volqen_sb_payment", "label": "Payment", "fieldtype": "Section Break", "insert_after": "volqen_welcome_email_sent", "collapsible": 1},
            {"fieldname": "volqen_payment_provider", "label": "Payment Provider", "fieldtype": "Data", "insert_after": "volqen_sb_payment"},
            {"fieldname": "volqen_payment_status", "label": "Payment Status", "fieldtype": "Select", "options": PAYMENT_STATUS, "default": "Pending", "insert_after": "volqen_payment_provider"},
            {"fieldname": "volqen_cb_payment", "fieldtype": "Column Break", "insert_after": "volqen_payment_status"},
            {"fieldname": "volqen_payment_ref", "label": "Payment Reference", "fieldtype": "Data", "insert_after": "volqen_cb_payment"},
            {"fieldname": "volqen_amount", "label": "Amount", "fieldtype": "Data", "insert_after": "volqen_payment_ref"},

            {"fieldname": "volqen_sb_log", "label": "Provisioning Log", "fieldtype": "Section Break", "insert_after": "volqen_amount", "collapsible": 1},
            {"fieldname": "volqen_provision_log", "label": "Log", "fieldtype": "Code", "options": "Text", "insert_after": "volqen_sb_log", "read_only": 1},
        ],
        "Lead": [
            {"fieldname": "volqen_form_type", "label": "Website Form", "fieldtype": "Data", "insert_after": "source", "read_only": 1, "in_standard_filter": 1},
        ],
    }


def after_install():
    create_custom_fields(custom_fields(), ignore_validate=True)
    frappe.db.commit()
    print("Volqen SaaS: Customer and Lead fields are ready.")
