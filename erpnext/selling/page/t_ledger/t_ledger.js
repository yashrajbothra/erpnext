frappe.pages['t-ledger'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'T Ledger',
		single_column: true
	});

	page.add_field({
		fieldname: 'customer',
		label: __('Customer'),
		fieldtype: 'MultiSelectList',
		options: 'Customer',
		get_data: function (txt) {
			return frappe.db.get_link_options('Customer', txt);
		}
	});

	page.add_field({
		fieldname: 'from_date',
		label: __('From Date'),
		fieldtype: 'Date',
		default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)
	});

	page.add_field({
		fieldname: 'to_date',
		label: __('To Date'),
		fieldtype: 'Date',
		default: frappe.datetime.get_today()
	});

	page.set_primary_action(__('Load Ledger'), () => {
		load_ledger();
	});

	let current_data = null;

	page.add_menu_item(__('Export to Excel'), () => {
		export_to_excel();
	});

	page.add_menu_item(__('Export to PDF'), () => {
		export_to_pdf();
	});

	const $ledger_container = $(`
		<div class="ledger-container" style="margin: 15px;">
			<div id="ledger-body">
				<div class="text-muted text-center" style="margin-top: 50px;">
					${__("Please select filters and click on Load Ledger")}
				</div>
			</div>
		</div>
	`).appendTo(page.main);

	function load_ledger() {
		let customer = page.fields_dict.customer.get_value();
		let from_date = page.fields_dict.from_date.get_value();
		let to_date = page.fields_dict.to_date.get_value();

		if (!customer || customer.length === 0) {
			frappe.msgprint(__('Please select at least one Customer'));
			return;
		}

		frappe.call({
			method: "erpnext.selling.page.t_ledger.t_ledger.get_t_ledger",
			args: {
				customer: customer,
				from_date: from_date,
				to_date: to_date
			},
			callback: function (r) {
				if (r.message) {
					current_data = r.message;
					render_ledger(r.message);
				}
			}
		});
	}

	function render_ledger(data) {
		let debit = data.debit || [];
		let credit = data.credit || [];
		let max_len = Math.max(debit.length, credit.length);

		let html = `
			<div class="t-ledger-table" style="border: 1px solid #d1d8dd; border-radius: 4px; background-color: #ffffff; font-family: sans-serif;">
				<div class="row" style="margin: 0; border-bottom: 1px solid #d1d8dd; background-color: #f8f9fa;">
					<div class="col-xs-6 text-center" style="border-right: 1px solid #d1d8dd; padding: 12px; font-weight: bold; color: #36414c; width: 50%; float: left; box-sizing: border-box;">
						${__('Debit')}
					</div>
					<div class="col-xs-6 text-center" style="padding: 12px; font-weight: bold; color: #36414c; width: 50%; float: left; box-sizing: border-box;">
						${__('Credit')}
					</div>
					<div style="clear: both;"></div>
				</div>
		`;

		if (max_len === 0) {
			html += `
				<div class="text-center text-muted" style="padding: 30px;">
					${__("No entries found for the selected criteria.")}
				</div>
			`;
		}

		for (let i = 0; i < max_len; i++) {
			let d = debit[i] || {};
			let c = credit[i] || {};

			html += `
			<div class="row" style="margin: 0; border-bottom: 1px solid #d1d8dd;">
				<div class="col-xs-6" style="border-right: 1px solid #d1d8dd; padding: 10px; width: 50%; float: left; box-sizing: border-box;">
					${format_row(d)}
				</div>
				<div class="col-xs-6" style="padding: 10px; width: 50%; float: left; box-sizing: border-box;">
					${format_row(c)}
				</div>
				<div style="clear: both;"></div>
			</div>
			`;
		}

		// Totals
		html += `
				<div class="row" style="margin: 0; font-weight: bold; background-color: #f8f9fa; border-bottom: 1px solid #d1d8dd;">
					<div class="col-xs-6" style="border-right: 1px solid #d1d8dd; padding: 12px; font-size: 14px; width: 50%; float: left; box-sizing: border-box;">
						<div class="text-right text-danger" style="text-align: right; color: #e74c3c;">
							<div>${__('Total: ')} ${format_currency(data.total_debit, frappe.boot.sysdefaults.currency)}</div>
						</div>
					</div>
					<div class="col-xs-6" style="padding: 12px; font-size: 14px; width: 50%; float: left; box-sizing: border-box;">
						<div class="text-right text-success" style="text-align: right; color: #2ecc71;">
							<div>${__('Total: ')} ${format_currency(data.total_credit, frappe.boot.sysdefaults.currency)}</div>
						</div>
					</div>
					<div style="clear: both;"></div>
				</div>
		`;

		let closing_bal = data.closing_balance || 0;
		let bal_color = closing_bal >= 0 ? '#2ecc71' : '#e74c3c';
		let bal_text = closing_bal >= 0 ? __('Closing Balance (Credit)') : __('Closing Balance (Debit)');
		let bal_abs = Math.abs(closing_bal);

		html += `
				<div class="row" style="margin: 0; font-weight: bold; background-color: #eaf1f8; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; padding: 15px; border-top: 2px solid #d1d8dd; font-size: 15px;">
					<div style="text-align: right; color: ${bal_color}; width: 100%; box-sizing: border-box;">
						${bal_text}: ${format_currency(bal_abs, frappe.boot.sysdefaults.currency)}
					</div>
				</div>
			</div>
		`;

		$('#ledger-body').html(html);
	}

	function format_row(row) {
		if (!row || row.amount === undefined || row.amount === null || row.amount === "") {
			return "";
		}

		let link_html = "";
		if (row.voucher_type === "Opening Balance") {
			link_html = `<span style="font-weight: bold;">${row.voucher_type}</span>`;
		} else {
			link_html = `<a href="/app/${frappe.router.slug(row.voucher_type)}/${row.voucher_no}" style="text-decoration: none; font-weight: bold;">
				${row.voucher_type} - ${row.voucher_no}
			</a>`;
		}

		let extra_info_html = "";
		if (row.is_discount) {
			extra_info_html = `<div style="font-size: 11px; color: #e74c3c; margin-top: 2px;">${__('Custom Discount')}</div>`;
		}

		if (row.references && row.references.length > 0) {
			let ref_links = row.references.map(ref => {
				return `<span style="color: #6c7680;">${ref.reference_doctype} ${ref.reference_name} (${format_currency(ref.allocated_amount, frappe.boot.sysdefaults.currency)})</span>`;
			}).join('<br>');
			extra_info_html += `
				<div style="font-size: 11px; margin-top: 6px; line-height: 1.4;">
					<strong>${__('References:')}</strong><br>${ref_links}
				</div>
			`;
		}

		let html = `
			<table style="width: 100%; border-collapse: collapse;">
				<tr>
					<td style="vertical-align: top;">
						<div class="text-muted" style="font-size: 11px; color: #8d99a6;">
							${frappe.datetime.str_to_user(row.date)}
						</div>
						<div style="font-size: 13px;">
							${link_html}
						</div>
						${extra_info_html}
					</td>
					<td style="text-align: right; font-weight: 500; vertical-align: top; width: 120px;">
						<div>${format_currency(row.amount, frappe.boot.sysdefaults.currency)}</div>
					</td>
				</tr>
			</table>
		`;

		return html;
	}

	function export_to_excel() {
		if (!current_data) {
			frappe.msgprint(__('Please load the ledger first'));
			return;
		}

		let debit = current_data.debit || [];
		let credit = current_data.credit || [];
		let max_len = Math.max(debit.length, credit.length);

		let html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
		<head>
			<!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet><x:Name>T Ledger</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->
			<style>
				table { border-collapse: collapse; font-family: sans-serif; }
				th, td { border: 1px solid #000000; padding: 5px; font-size: 11pt; }
				.header { background-color: #d9edf7; font-weight: bold; text-align: center; }
				.divider { background-color: #ffe699; border: 1px solid #000000; width: 25px; text-align: center; }
				.num { text-align: right; }
				.date-col { text-align: center; }
				.totals-row td { font-weight: bold; background-color: #f2f2f2; }
				.closing-row td { font-weight: bold; background-color: #dff0d8; text-align: right;}
			</style>
		</head>
		<body>
			<table>
				<tr>
					<th class="header">Date</th>
					<th class="header">Debit Voucher</th>
					<th class="header">Debit Amount</th>
					<th class="divider"></th>
					<th class="header">Date</th>
					<th class="header">Credit Voucher</th>
					<th class="header">Credit Amount</th>
				</tr>`;

		for (let i = 0; i < max_len; i++) {
			let d = debit[i] || {};
			let c = credit[i] || {};

			let d_voucher = d.voucher_no ? `${d.voucher_type} - ${d.voucher_no}` : (d.voucher_type || "");
			let c_voucher = c.voucher_no ? `${c.voucher_type} - ${c.voucher_no}` : (c.voucher_type || "");
			if (c.is_discount) {
				c_voucher += " (Discount)";
			}

			html += `
				<tr>
					<td class="date-col">${d.date ? frappe.datetime.str_to_user(d.date) : ""}</td>
					<td>${d_voucher}</td>
					<td class="num">${d.amount ? flt(d.amount, 2).toFixed(2) : ""}</td>
					<td class="divider"></td>
					<td class="date-col">${c.date ? frappe.datetime.str_to_user(c.date) : ""}</td>
					<td>${c_voucher}</td>
					<td class="num">${c.amount ? flt(c.amount, 2).toFixed(2) : ""}</td>
				</tr>
			`;
		}

		html += `
				<tr class="totals-row">
					<td class="header" style="text-align: right;" colspan="2">Total:</td>
					<td class="num">${flt(current_data.total_debit || 0, 2).toFixed(2)}</td>
					<td class="divider"></td>
					<td class="header" style="text-align: right;" colspan="2">Total:</td>
					<td class="num">${flt(current_data.total_credit || 0, 2).toFixed(2)}</td>
				</tr>
		`;

		let closing_bal = current_data.closing_balance || 0;
		let bal_text = closing_bal >= 0 ? 'Closing Balance (Credit)' : 'Closing Balance (Debit)';

		html += `
				<tr class="closing-row">
					<td colspan="3"></td>
					<td class="divider"></td>
					<td class="header" colspan="2" style="text-align: right;">${bal_text}:</td>
					<td class="num">${flt(Math.abs(closing_bal), 2).toFixed(2)}</td>
				</tr>
			</table>
		</body>
		</html>`;

		let blob = new Blob([html], { type: 'application/vnd.ms-excel' });
		let url = URL.createObjectURL(blob);
		let a = document.createElement('a');
		a.href = url;
		a.download = `T_Ledger_${page.fields_dict.customer.get_value().join('_')}.xls`;
		document.body.appendChild(a);
		a.click();
		setTimeout(() => {
			document.body.removeChild(a);
			URL.revokeObjectURL(url);
		}, 100);
	}

	function export_to_pdf() {
		if (!current_data) {
			frappe.msgprint(__('Please load the ledger first'));
			return;
		}

		let header_html = `
			<h2 style="text-align: center; font-family: sans-serif;">T Ledger</h2>
			<div style="text-align: center; font-family: sans-serif; font-size: 14px; margin-bottom: 20px; color: #555;">
				${__('Customers')}: <strong>${page.fields_dict.customer.get_value().join(', ')}</strong>
			</div>
		`;
		let content_html = $('#ledger-body').html();

		frappe.render_pdf(header_html + content_html, {
			orientation: 'Portrait',
			report_name: `T_Ledger`
		});
	}
};
