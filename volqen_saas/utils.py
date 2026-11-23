"""Shared helpers: subdomain rules, site names, passwords."""

import re
import secrets

import frappe

from volqen_saas import settings

SUBDOMAIN_RE = re.compile(r"^[a-z][a-z0-9-]{1,28}[a-z0-9]$")

RESERVED_SUBDOMAINS = {
    "www", "app", "api", "admin", "mail", "smtp", "imap", "pop", "ftp", "erp", "demo", "test",
    "staging", "dev", "support", "help", "docs", "status", "billing", "pay", "login", "account",
    "accounts", "portal", "master", "volqen", "static", "cdn", "assets", "blog", "shop", "store",
    "ns1", "ns2", "webmail", "cpanel", "root", "system", "site", "sites", "new", "signup",
}

PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def validate_subdomain(subdomain):
    """Return the cleaned subdomain or throw a readable error."""
    sub = (subdomain or "").strip().lower()
    if not SUBDOMAIN_RE.match(sub):
        frappe.throw(
            "Subdomain must be 3-30 characters: lowercase letters, numbers and hyphens, starting with a letter."
        )
    if sub in RESERVED_SUBDOMAINS:
        frappe.throw(f"The subdomain {sub!r} is reserved. Please choose another.")
    return sub


def suggest_subdomain(company_name):
    sub = re.sub(r"[^a-z0-9]+", "-", (company_name or "").lower()).strip("-")
    sub = re.sub(r"^[0-9-]+", "", sub)[:30].rstrip("-")
    return sub


def site_name(subdomain):
    return "{}.{}".format(validate_subdomain(subdomain), settings.get("volqen_tenant_domain"))


def site_url(subdomain):
    port = str(settings.get("volqen_tenant_port") or "").strip()
    suffix = f":{port}" if port and port not in ("80", "443") else ""
    return "{}://{}{}".format(settings.get("volqen_tenant_scheme"), site_name(subdomain), suffix)


def generate_password(length=18):
    raw = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(length))
    return "-".join([raw[0:4], raw[4:9], raw[9:14], raw[14:]])


def split_name(full_name):
    parts = [p for p in (full_name or "").strip().split() if p]
    if not parts:
        return "Customer", ""
    return parts[0], " ".join(parts[1:])


def log(customer, message):
    """Append one timestamped line to the Customer's provisioning log."""
    stamp = frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    existing = frappe.db.get_value("Customer", customer, "volqen_provision_log") or ""
    text = (existing + "\n" + line).strip()[-20000:]
    frappe.db.set_value("Customer", customer, "volqen_provision_log", text, update_modified=False)
    frappe.db.commit()
    frappe.logger("volqen_saas").info(f"{customer}: {message}")
    return line
