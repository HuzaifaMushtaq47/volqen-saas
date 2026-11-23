app_name = "volqen_saas"
app_title = "Volqen SaaS"
app_publisher = "Volqen"
app_description = (
    "Volqen ERP SaaS control plane: website signups land on the Customer doctype, "
    "each Customer gets its own ERPNext site and database, an admin user, and a welcome email."
)
# TODO: set your support address before publishing the app anywhere public.
app_email = ""
app_license = "mit"

# Customer -> user + site provisioning
doc_events = {
    "Customer": {
        "after_insert": "volqen_saas.customer.after_insert",
        "on_update": "volqen_saas.customer.on_update",
    }
}

after_install = "volqen_saas.install.after_install"
after_migrate = "volqen_saas.install.after_install"

# Retry provisioning that was interrupted (server restart, crashed worker)
scheduler_events = {
    "cron": {
        "*/10 * * * *": ["volqen_saas.provisioner.retry_stuck_customers"],
    }
}

# Adds a "Provision ERP site" button on the Customer form
doctype_js = {"Customer": "public/js/customer.js"}

fixtures = []
