frappe.query_reports["Outstanding Summary"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1
		},
		{
			fieldname: "report_date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Link",
			options: "DocType",
			get_query: function () {
				return {
					filters: {
						"name": ["in", ["Customer", "Supplier"]]
					}
				};
			}
		},

		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Dynamic Link",
			options: "party_type"
		},
		{
			fieldname: "customer_group",
			label: __("Customer Group"),
			fieldtype: "Link",
			options: "Customer Group"
		},
		{
			fieldname: "territory",
			label: __("Territory"),
			fieldtype: "Link",
			options: "Territory"
		},
		{
			fieldname: "show_zero_values",
			label: __("Show Zero Values"),
			fieldtype: "Check",
			default: 0
		}
	],
	formatter: function (value, row, column, data, default_formatter) {
		if (column.fieldname === "party" && data && data.party !== "Grand Total") {
			const doctype = data.party_type;
			if (doctype && value) {
				const href = frappe.utils.get_form_link(doctype, value);
				const link_html = `<a class="grey" href="${href}" data-doctype="${doctype}" data-name="${value}">${value}</a>`;
				if (data.is_group) {
					return `<b><span>${link_html}</span></b>`;
				}
				return link_html;
			}
		}
		return default_formatter(value, row, column, data);
	}
};
