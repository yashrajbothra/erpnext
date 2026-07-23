frappe.query_reports["Payment Planning"] = {
    "filters": [
        {
            "fieldname": "company",
            "label": __("Company"),
            "fieldtype": "Link",
            "options": "Company",
            "default": frappe.defaults.get_user_default("Company")
        },
        {
            "fieldname": "customer",
            "label": __("Customer"),
            "fieldtype": "Link",
            "options": "Customer"
        },
        {
            "fieldname": "customer_group",
            "label": __("Customer Group"),
            "fieldtype": "Link",
            "options": "Customer Group"
        },
        {
            "fieldname": "hide_non_due",
            "label": __("Hide Non Due Invoices"),
            "fieldtype": "Check",
            "default": 1,
            "on_change": function (query_report) {
                query_report.refresh();
            }
        }
    ],
    "formatter": function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname == "inv_no" && data && data.actual_inv_no) {
            let inv_doctype = data.invoice_doctype || "Sales Invoice";
            let url_doctype = inv_doctype.toLowerCase().replace(" ", "-");
            value = `<a href="/app/${url_doctype}/${data.actual_inv_no}" data-doctype="${inv_doctype}" data-name="${data.actual_inv_no}">${value}</a>`;
        }
        if (column.fieldname == "received" && data && data.payment_entry) {
            let doctype = data.payment_doctype || "Payment Entry";
            let url_doctype = doctype.toLowerCase().replace(" ", "-");
            value = `<a href="/app/${url_doctype}/${data.payment_entry}" data-doctype="${doctype}" data-name="${data.payment_entry}">${value}</a>`;
        }
        return value;
    }
};
