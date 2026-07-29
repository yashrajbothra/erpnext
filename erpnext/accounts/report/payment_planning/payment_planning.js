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
            "fieldname": "party_type",
            "label": __("Party Type"),
            "fieldtype": "Link",
            "options": "DocType",
            "get_query": function () {
                return {
                    filters: {
                        "name": ["in", ["Customer", "Supplier"]]
                    }
                };
            }
        },
        {
            "fieldname": "party",
            "label": __("Party"),
            "fieldtype": "MultiSelectList",
            "get_data": function (txt) {
                if (!frappe.query_report.filters) return;
                let party_type = frappe.query_report.get_filter_value("party_type");
                if (!party_type) return [];
                return frappe.db.get_link_options(party_type, txt);
            }
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
