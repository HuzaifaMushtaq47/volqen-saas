# Volqen SaaS

A Frappe/ERPNext app that turns one ERPNext site into the control panel for the Volqen ERP
SaaS. A signup from the Volqen website becomes a **Customer** here, and the app then:

1. creates a **portal User** and **Contact** for the customer's admin, linked to the Customer;
2. creates that customer their **own site with its own database** (`<subdomain>.<domain>`);
3. runs the ERPNext setup wizard on the new site (company, country, currency, fiscal year);
4. creates the customer's **admin user** on their site and applies their **plan**
   (modules outside the plan are blocked, roles assigned, user count capped);
5. **emails the customer** their site address, username and temporary password.

Every step is written to a provisioning log on the Customer, and a failed signup can be
retried from a button on the Customer form.

```
Volqen website  ──►  Customer (this ERP)  ──►  bench new-site  ──►  customer's own site + database
                         │                                              │
                         └── portal user + contact                      └── company setup, admin user,
                                                                            plan limits, welcome email
```

## Install

```bash
cd ~/frappe-bench
bench get-app https://github.com/HuzaifaMushtaq47/volqen-saas
bench --site volqen.localhost install-app volqen_saas
```

`bench get-app` + `install-app` also makes the app available to every customer site the
app creates (it installs itself there to run the setup).

## Configure

All settings live in the control site's `site_config.json`:

```bash
cd ~/frappe-bench
bench --site volqen.localhost set-config volqen_bench_path /home/frappe/frappe-bench
bench --site volqen.localhost set-config volqen_db_root_password '<MariaDB root password>'
bench --site volqen.localhost set-config volqen_tenant_domain localhost
bench --site volqen.localhost set-config volqen_tenant_port 8000
bench --site volqen.localhost set-config volqen_support_email ops@yourdomain
```

| Setting | Default | What it does |
|---|---|---|
| `volqen_tenant_domain` | `localhost` | Customer sites become `<subdomain>.<this>` |
| `volqen_tenant_scheme` | `http` | `https` in production |
| `volqen_tenant_port` | `8000` | Port shown in the customer's URL. Set to `""` behind nginx |
| `volqen_bench_path` | `/home/frappe/frappe-bench` | Bench this app runs `bench new-site` in |
| `volqen_db_root_password` | – | MariaDB root password, needed to create databases |
| `volqen_default_apps` | `["erpnext"]` | Installed on every customer site; plans may add `hrms` |
| `volqen_install_app_on_tenant` | `1` | Install this app on the customer site to run its setup |
| `volqen_auto_provision` | `1` | Create the site as soon as a Customer with a subdomain is saved |
| `volqen_create_portal_user` | `1` | Also create a portal login on this ERP |
| `volqen_portal_user_role` | `Customer` | Role for that portal login |
| `volqen_send_welcome_email` | `1` | Email the customer when the site is ready |
| `volqen_setup_nginx` | `0` | Run `bench setup nginx` after each site (production) |
| `volqen_dry_run` | `0` | Log the bench commands without running them |
| `volqen_bench_timeout` | `1800` | Seconds allowed per bench command |
| `volqen_support_email` | – | Gets an email when provisioning fails |

**First run:** set `volqen_dry_run 1`, create a test Customer, and read the provisioning log
to see the exact bench commands before letting it create anything.

## Try it

```bash
bench --site volqen.localhost console
>>> frappe.call("volqen_saas.api.diagnostics")          # checks bench path and settings
```

Or create a Customer by hand: fill **Subdomain**, **Plan**, **Admin Name** and
**Admin Email**, save, and watch *Volqen → Provision ERP site*.

## Website endpoints

Authenticate with an ERPNext API key (User → API Access → Generate Keys):

```
Authorization: token <api_key>:<api_secret>
```

| Method | Purpose |
|---|---|
| `POST /api/method/volqen_saas.api.signup` | Paid signup → Customer → site |
| `GET /api/method/volqen_saas.api.signup_status?order_id=VQO-…` | Progress for the website's status page |
| `GET /api/method/volqen_saas.api.check_subdomain?subdomain=acme` | Live availability check |
| `POST /api/method/volqen_saas.api.website_lead` | Demo and contact forms → Lead |
| `POST /api/method/volqen_saas.api.provision_now` | Retry or re-run provisioning |
| `GET /api/method/volqen_saas.api.diagnostics` | Settings and bench check |

## Plans

`volqen_saas/plans.json` holds the modules, apps, roles and user limit for each tier. It is
a copy of `config/plans.json` in the website repo — keep the two in step.

| Plan | Apps | Users | Extra modules |
|---|---|---|---|
| Starter | erpnext | 5 | – |
| Growth | erpnext, hrms | 25 | Manufacturing, Quality, Projects, Assets, HR, Payroll |
| Enterprise | erpnext, hrms | 100 | + Support, Maintenance, Website, Portal |

## Tests

```bash
python3 tests/test_logic.py
```

50 checks run without a bench: every `bench` command and ERP write is captured instead of
executed, covering subdomain rules, site naming, the full provisioning sequence, failure
handling, plan enforcement, the welcome email and the website endpoints.

## Not yet verified on a live bench

The tests above stub Frappe. Before taking real customers, run one signup on a staging
bench and confirm: `bench new-site` flags for your MariaDB setup, the setup-wizard arguments
for your exact ERPNext version, and Module Profile / Role Profile / Server Script creation.

## Security notes

- The MariaDB root password and site passwords are never put in a shell string; `bench` runs
  through `subprocess` with an argument list, and setup details travel in a `0600` file that
  is deleted straight after use.
- The customer's site `Administrator` password is stored in an encrypted Password field on the
  Customer for support, and is never emailed.
- The customer's own user gets a generated temporary password and is asked to change it.
