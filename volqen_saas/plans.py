"""Plan catalogue (modules, apps, roles and limits per tier)."""

import json
import os

import frappe

_CACHE = {}


def all_plans():
    if "plans" not in _CACHE:
        path = os.path.join(os.path.dirname(__file__), "plans.json")
        with open(path, encoding="utf-8") as f:
            _CACHE["plans"] = json.load(f)["plans"]
    return _CACHE["plans"]


def get_plan(name_or_id):
    """Accepts 'growth', 'Growth' or 'Volqen Growth' and returns the plan dict."""
    if not name_or_id:
        return None
    key = str(name_or_id).strip().lower().replace("volqen ", "")
    for plan in all_plans():
        if plan["id"] == key or plan["name"].lower() == key:
            return plan
    return None


def plan_or_throw(name_or_id):
    plan = get_plan(name_or_id)
    if not plan:
        known = ", ".join(p["name"] for p in all_plans())
        frappe.throw(f"Unknown Volqen plan {name_or_id!r}. Known plans: {known}")
    return plan


def plan_options():
    return "\n".join([""] + [p["name"] for p in all_plans()])
