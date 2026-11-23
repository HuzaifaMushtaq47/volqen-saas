"""Configuration for Volqen SaaS.

Everything lives in the site's own site_config.json so no extra DocType is needed:

    bench --site volqen.localhost set-config volqen_tenant_domain localhost
    bench --site volqen.localhost set-config volqen_bench_path /home/frappe/frappe-bench
    bench --site volqen.localhost set-config volqen_db_root_password '<mariadb root password>'

Read the README for the full list.
"""

import frappe

DEFAULTS = {
    # where customer sites live: <subdomain>.<volqen_tenant_domain>
    "volqen_tenant_domain": "localhost",
    "volqen_tenant_scheme": "http",
    # port to put in the customer's URL; "" for standard 80/443, "8000" for `bench start`
    "volqen_tenant_port": "8000",
    "volqen_bench_path": "/home/frappe/frappe-bench",
    "volqen_db_root_password": None,
    # apps installed on every customer site (plans may add more, e.g. hrms)
    "volqen_default_apps": ["erpnext"],
    "volqen_install_app_on_tenant": 1,
    # create the site automatically when a Customer is saved with a subdomain
    "volqen_auto_provision": 1,
    # also create a portal User on this ERP for the customer's admin contact
    "volqen_create_portal_user": 1,
    "volqen_portal_user_role": "Customer",
    "volqen_send_welcome_email": 1,
    # run `bench setup nginx` + reload after creating a site (production servers only)
    "volqen_setup_nginx": 0,
    # log the bench commands but do not run them (safe dry run for a first test)
    "volqen_dry_run": 0,
    "volqen_bench_timeout": 1800,
    "volqen_support_email": "",
}


def get(key, default=None):
    """Read one setting from site_config.json, falling back to the default above.

    An explicit empty value in site_config wins: setting volqen_tenant_port to ""
    means "no port in the URL", not "use the default".
    """
    if key in frappe.conf:
        return frappe.conf.get(key)
    if default is not None:
        return default
    return DEFAULTS.get(key)


def all_settings():
    data = {key: get(key) for key in DEFAULTS}
    data["volqen_db_root_password"] = "***" if data.get("volqen_db_root_password") else None
    return data


def as_bool(key):
    return str(get(key)) not in ("0", "False", "false", "None", "")


def default_apps():
    apps = get("volqen_default_apps")
    if isinstance(apps, str):
        apps = [a.strip() for a in apps.replace(",", " ").split() if a.strip()]
    return list(apps or ["erpnext"])
