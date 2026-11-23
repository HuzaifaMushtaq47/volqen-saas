"""A small fake `frappe` so the Volqen SaaS logic can be tested without a bench."""
import sys, types, html
from datetime import datetime, timedelta


class ValidationError(Exception):
    pass


class DoesNotExistError(Exception):
    pass


class Doc(dict):
    def __init__(self, doctype="", **kw):
        super().__init__(**kw)
        self.doctype = doctype
        self.flags = types.SimpleNamespace(ignore_permissions=False)
        self._saved = 0

    def __getattr__(self, k):
        if k.startswith("_"):
            raise AttributeError(k)
        return self.get(k)

    def __setattr__(self, k, v):
        if k in ("doctype", "flags", "_saved"):
            object.__setattr__(self, k, v)
        else:
            self[k] = v

    def get(self, k, default=None):
        return dict.get(self, k, default)

    def set(self, k, v):
        if isinstance(v, list):
            v = [types.SimpleNamespace(**i) if isinstance(i, dict) else i for i in v]
        self[k] = v

    def append(self, k, v):
        self.setdefault(k, []).append(types.SimpleNamespace(**v) if isinstance(v, dict) else v)

    def update(self, d):
        dict.update(self, d)
        return self

    def save(self, **kw):
        self._saved += 1
        FR.saved.append((self.doctype, dict(self)))
        if not self.get("name"):
            self["name"] = self.get("email") or self.get("customer_name") or f"{self.doctype}-1"
        return self

    def insert(self, **kw):
        if not self.get("name"):
            self["name"] = self.get("email") or self.get("customer_name") or f"{self.doctype}-1"
        FR.inserted.append((self.doctype, dict(self)))
        FR.docs[(self.doctype, self["name"])] = self
        return self

    def reload(self):
        stored = FR.docs.get((self.doctype, self.get("name")))
        if stored:
            dict.update(self, stored)
        return self

    def db_set(self, field, value, **kw):
        self[field] = value
        FR.db_sets.append((self.get("name"), {field: value}))

    def get_password(self, field, raise_exception=True):
        return self.get(field)

    def get_doc_before_save(self):
        return self.get("_before")

    def add_comment(self, kind, text):
        FR.comments.append((self.get("name"), kind, text))


class DB:
    def get_value(self, doctype, name, fieldname=None, as_dict=False, **kw):
        key = name if isinstance(name, str) else None
        doc = FR.docs.get((doctype, key)) if key else None
        if doc is None and isinstance(name, dict):
            for (dt, nm), d in FR.docs.items():
                if dt == doctype and all(d.get(k) == v for k, v in name.items()):
                    doc = d
                    break
        if doc is None:
            return None
        if isinstance(fieldname, list):
            out = Doc(doctype, **{f: doc.get(f) for f in fieldname})
            out["name"] = doc.get("name")
            return out if as_dict else list(out.values())
        return doc.get(fieldname) if fieldname else doc.get("name")

    def set_value(self, doctype, name, field, value=None, update_modified=True):
        doc = FR.docs.setdefault((doctype, name), Doc(doctype, name=name))
        changes = field if isinstance(field, dict) else {field: value}
        doc.update(changes)
        FR.db_sets.append((name, changes))

    def exists(self, doctype, filters=None):
        if isinstance(filters, dict):
            for (dt, nm), d in FR.docs.items():
                if dt == doctype and all(d.get(k) == v for k, v in filters.items()):
                    return nm
            return None
        return filters if (doctype, filters) in FR.docs else None

    def count(self, doctype, filters=None):
        return FR.user_count

    def get_single_value(self, doctype, field):
        return FR.singles.get((doctype, field))

    def set_single_value(self, doctype, field, value):
        FR.singles[(doctype, field)] = value

    def commit(self):
        FR.commits += 1


class Utils:
    @staticmethod
    def now_datetime():
        return datetime(2026, 11, 23, 10, 0, 0)

    @staticmethod
    def cint(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def escape_html(v):
        return html.escape(str(v))

    @staticmethod
    def time_diff_in_seconds(a, b):
        return (a - b).total_seconds()

    @staticmethod
    def get_time_zone():
        return "Asia/Karachi"


class FrappeStub(types.ModuleType):
    def __init__(self):
        super().__init__("frappe")
        self.reset()
        self.db = DB()
        self.utils = Utils()
        self.conf = {}
        self.ValidationError = ValidationError
        self.DoesNotExistError = DoesNotExistError
        self.local = types.SimpleNamespace(form_dict={})

    def reset(self):
        self.docs, self.inserted, self.saved, self.db_sets = {}, [], [], []
        self.emails, self.enqueued, self.comments, self.errors = [], [], [], []
        self.commits, self.user_count = 0, 0
        self.singles = {}
        self.installed_apps = ["frappe", "erpnext", "hrms"]
        self.roles = ["System Manager", "Accounts Manager", "Sales Manager", "Stock Manager", "HR Manager"]
        self.module_defs = [
            {"name": m, "app_name": "erpnext"}
            for m in ["Accounts", "Selling", "Buying", "Stock", "CRM", "Setup", "Utilities",
                      "Manufacturing", "Quality Management", "Projects", "Assets", "Subcontracting",
                      "Support", "Maintenance", "Website", "Portal"]
        ] + [{"name": m, "app_name": "hrms"} for m in ["HR", "Payroll"]]

    # --- api used by the app
    def throw(self, msg, exc=None):
        raise (exc or ValidationError)(msg)

    def whitelist(self, *a, **kw):
        def deco(fn):
            return fn
        return deco(a[0]) if a and callable(a[0]) else deco

    def only_for(self, *a, **kw):
        return True

    def get_doc(self, doctype, name=None):
        if isinstance(doctype, dict):
            return Doc(doctype.get("doctype", ""), **doctype)
        doc = self.docs.get((doctype, name))
        if doc is None:
            raise DoesNotExistError(f"{doctype} {name} not found")
        return doc

    def new_doc(self, doctype):
        return Doc(doctype)

    def get_all(self, doctype, filters=None, fields=None, pluck=None, limit=None):
        if doctype == "Module Def":
            names = [m["name"] for m in self.module_defs]
            return names if pluck else [Doc(doctype, name=n) for n in names]
        if doctype == "Role":
            wanted = (filters or {}).get("name", [None, []])[1]
            names = [r for r in self.roles if r in wanted]
            return names if pluck else [Doc(doctype, name=n) for n in names]
        rows = [d for (dt, _), d in self.docs.items() if dt == doctype]
        return [r.get(pluck) for r in rows] if pluck else rows

    def get_installed_apps(self):
        return self.installed_apps

    def enqueue(self, method, **kw):
        self.enqueued.append((method, kw))

    def sendmail(self, **kw):
        self.emails.append(kw)

    def logger(self, name=None):
        return types.SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None)

    def log_error(self, *a, **kw):
        self.errors.append(a)

    def get_traceback(self):
        return "traceback"


FR = FrappeStub()
sys.modules["frappe"] = FR

_cf = types.ModuleType("frappe.custom.doctype.custom_field.custom_field")
_cf.create_custom_fields = lambda fields, **kw: FR.__dict__.setdefault("custom_fields", []).append(fields)
for mod in ("frappe.custom", "frappe.custom.doctype", "frappe.custom.doctype.custom_field"):
    sys.modules[mod] = types.ModuleType(mod)
sys.modules["frappe.custom.doctype.custom_field.custom_field"] = _cf

_pw = types.ModuleType("frappe.utils.password")
_pw.update_password = lambda user, pwd: FR.__dict__.setdefault("passwords", []).append((user, pwd))
_pw.set_encrypted_password = lambda dt, dn, pwd, field: FR.__dict__.setdefault("encrypted", []).append((dt, dn, field, pwd))
sys.modules["frappe.utils.password"] = _pw
sys.modules["frappe.utils"] = FR.utils

_wiz = types.ModuleType("frappe.desk.page.setup_wizard.setup_wizard")
_wiz.setup_complete = lambda args: FR.__dict__.setdefault("wizard", []).append(args)
for mod in ("frappe.desk", "frappe.desk.page", "frappe.desk.page.setup_wizard"):
    sys.modules[mod] = types.ModuleType(mod)
sys.modules["frappe.desk.page.setup_wizard.setup_wizard"] = _wiz
