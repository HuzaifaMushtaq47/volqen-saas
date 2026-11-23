frappe.ui.form.on("Customer", {
  refresh(frm) {
    if (frm.is_new() || !frm.doc.volqen_subdomain) return;
    const status = frm.doc.volqen_site_status;
    const colours = { Active: "green", Failed: "red", Provisioning: "orange", Queued: "blue" };
    if (status) frm.dashboard.set_headline_alert(`Volqen site: <b>${status}</b>`, colours[status] || "blue");

    if (status === "Active" && frm.doc.volqen_site_url) {
      frm.add_custom_button(__("Open ERP site"), () => window.open(frm.doc.volqen_site_url, "_blank"), __("Volqen"));
    }
    if (status !== "Provisioning") {
      const label = status === "Active" ? __("Re-provision site") : __("Provision ERP site");
      frm.add_custom_button(label, () => {
        frappe.confirm(
          status === "Active"
            ? __("The site already exists. Run the setup steps again?")
            : __("Create the ERP site and database for this customer?"),
          () => frappe.call({
            method: "volqen_saas.api.provision_now",
            args: { customer: frm.doc.name, force: status === "Active" ? 1 : 0 },
            freeze: true,
            freeze_message: __("Queuing site creation..."),
            callback: () => { frappe.show_alert({ message: __("Queued. Watch the provisioning log."), indicator: "blue" }); frm.reload_doc(); },
          })
        );
      }, __("Volqen"));
    }
  },
});
