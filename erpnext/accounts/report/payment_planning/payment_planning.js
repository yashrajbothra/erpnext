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
        }
    ],
    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname == "inv_no" && data && data.actual_inv_no) {
            value = `<a href="/app/sales-invoice/${data.actual_inv_no}" data-doctype="Sales Invoice" data-name="${data.actual_inv_no}">${value}</a>`;
        }
        return value;
    }
};
