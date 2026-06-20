frappe.pages['interest-planning'].on_page_load = function (wrapper) {

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Interest Planning',
		single_column: true
	});

	const fixed_account = 'SSPL - GT';

	page.add_field({
		fieldname: 'party',
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

	page.add_field({
		fieldname: 'interest_rate',
		label: __('Interest Rate (%)'),
		fieldtype: 'Float',
		default: 0,
		reqd: 1
	});

	page.add_field({
		fieldname: 'till_date',
		label: __('Till Date'),
		fieldtype: 'Date',
		default: frappe.datetime.get_today(),
		reqd: 1
	});

	page.add_field({
		fieldname: 'use_entry_date',
		label: __('As per Entry Date'),
		fieldtype: 'Check',
		default: 0
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
		let account = fixed_account;
		let party = page.fields_dict.party.get_value();
		let from_date = page.fields_dict.from_date.get_value();
		let to_date = page.fields_dict.to_date.get_value();
		let interest_rate = page.fields_dict.interest_rate.get_value();
		let till_date = page.fields_dict.till_date.get_value();
		let use_entry_date = page.fields_dict.use_entry_date.get_value() ? 1 : 0;

		// Account is fixed to SSPL - GT

		if (interest_rate === undefined || interest_rate === null || interest_rate === '') {
			frappe.msgprint(__('Please enter an Interest Rate'));
			return;
		}

		if (!till_date) {
			frappe.msgprint(__('Please select a Till Date'));
			return;
		}

		frappe.call({
			method: "erpnext.api.get_general_t_ledger",
			args: {
				account: account,
				party: party,
				from_date: from_date,
				to_date: to_date,
				use_entry_date: use_entry_date
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
		let interest_rate = page.fields_dict.interest_rate.get_value() || 0;
		let till_date = page.fields_dict.till_date.get_value();

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

		let total_debit_interest = 0;
		let total_credit_interest = 0;


		for (let i = 0; i < max_len; i++) {
			let d = debit[i] || {};
			let c = credit[i] || {};
			let dr_res = format_row(d, interest_rate, till_date);
			let cr_res = format_row(c, interest_rate, till_date);

			// Accumulate interest totals
			total_debit_interest += dr_res.interest;
			total_credit_interest += cr_res.interest;

			// Append row HTML
			html += `
			<div class="row" style="margin: 0; border-bottom: 1px solid #d1d8dd;">
				<div class="col-xs-6" style="border-right: 1px solid #d1d8dd; padding: 10px; width: 50%; float: left; box-sizing: border-box;">
					${dr_res.html}
				</div>
				<div class="col-xs-6" style="padding: 10px; width: 50%; float: left; box-sizing: border-box;">
					${cr_res.html}
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
							<div style="font-size: 12px; margin-top: 4px;">${__('Total Interest: ')} ${format_currency(total_debit_interest, frappe.boot.sysdefaults.currency)}</div>
						</div>
					</div>
					<div class="col-xs-6" style="padding: 12px; font-size: 14px; width: 50%; float: left; box-sizing: border-box;">
						<div class="text-right text-success" style="text-align: right; color: #2ecc71;">
							<div>${__('Total: ')} ${format_currency(data.total_credit, frappe.boot.sysdefaults.currency)}</div>
							<div style="font-size: 12px; margin-top: 4px;">${__('Total Interest: ')} ${format_currency(total_credit_interest, frappe.boot.sysdefaults.currency)}</div>
						</div>
					</div>
					<div style="clear: both;"></div>
				</div>
		`;

		let closing_bal = data.closing_balance || 0;
		let bal_color = closing_bal >= 0 ? '#2ecc71' : '#e74c3c';
		let bal_text = closing_bal >= 0 ? __('Closing Balance (You owe us)') : __('Closing Balance (We owe you)');
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

	function format_row(row, interest_rate, till_date) {
		if (!row || row.amount === undefined || row.amount === null || row.amount === "") {
			return { html: "", interest: 0 };
		}

		let link_html = "";
		if (row.voucher_type === "Opening Balance") {
			link_html = `<span style="font-weight: bold;">${row.voucher_type}</span>`;
		}

		let extra_info_html = "";
		if (row.party || row.remarks || row.voucher_type === "Opening Balance") {
			let details = [];
			if (row.party) details.push(`<span style="font-weight: 600; color: #36414c;">${row.party}</span>`);
			if (row.voucher_type === "Opening Balance") { }
			else if (row.remarks) {
				let safe_remarks = String(row.remarks).replace(/\n/g, '<br>');
				details.push(`<span style="color: #6c7680;">${safe_remarks}</span>`);
			}
			extra_info_html = `
				<div style="font-size: 11px; margin-top: 6px; line-height: 1.4;">
					${details.join('<br>')}
				</div>
			`;
		}

		let interest = 0;
		let days_display = 0;
		// Always use posting_date for interest and days calculation (never entry_date)
		let calc_date = row.posting_date || row.date;
		if (calc_date && till_date) {
			let days = moment(till_date).diff(moment(calc_date), 'days');
			if (row.voucher_type === "Opening Balance") {
				days += 1;
			}
			if (days > 0) {
				days_display = days;
				if (interest_rate > 0) {
					interest = (row.amount * interest_rate / 100) * (days / 30);
				}
			}
		}

		// Show entry_date if available (when use_entry_date is active), posting_date otherwise
		let display_date = row.custom_entry_date ? row.custom_entry_date : row.date;
		let entry_date_suffix = row.custom_entry_date ? ` <span style="font-size:10px; color:#aaa;">(E: ${frappe.datetime.str_to_user(row.custom_entry_date)})</span>` : '';

		let html = `
			<table style="width: 100%; border-collapse: collapse;">
				<tr>
					<td style="vertical-align: top;">
						<div class="text-muted" style="font-size: 11px; color: #8d99a6;">
							${frappe.datetime.str_to_user(display_date)}${entry_date_suffix}
						</div>
						<div style="font-size: 13px;">
							${link_html}
						</div>
						${extra_info_html}
					</td>
					<td style="text-align: right; font-weight: 500; vertical-align: top;">
						<div>${format_currency(row.amount, frappe.boot.sysdefaults.currency)}</div>
						<div class="text-muted" style="font-size: 11px; margin-top: 4px;">
							${days_display > 0 ? `Days: ${days_display}<br>` : ''}
							Int: ${format_currency(interest, frappe.boot.sysdefaults.currency)}
						</div>
					</td>
				</tr>
			</table>
		`;

		return { html: html, interest: interest };
	}

	function export_to_excel() {
		if (!current_data) {
			frappe.msgprint(__('Please load the ledger first'));
			return;
		}

		let account = fixed_account;
		let interest_rate = page.fields_dict.interest_rate.get_value() || 0;
		let till_date = page.fields_dict.till_date.get_value();

		let debit = current_data.debit || [];
		let credit = current_data.credit || [];
		let max_len = Math.max(debit.length, credit.length);

		let total_debit_interest = 0;
		let total_credit_interest = 0;

		let html = `<html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
		<head>
			<!--[if gte mso 9]><xml><x:ExcelWorkbook><x:ExcelWorksheets><x:ExcelWorksheet><x:Name>Interest Planning</x:Name><x:WorksheetOptions><x:DisplayGridlines/></x:WorksheetOptions></x:ExcelWorksheet></x:ExcelWorksheets></x:ExcelWorkbook></xml><![endif]-->
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
					<th class="header">Debit Amount</th>
					<th class="header">Debit Days</th>
					<th class="header">Debit Interest</th>
					<th class="header">Party / Remarks</th>
					<th class="divider"></th>
					<th class="header">Date</th>
					<th class="header">Credit Amount</th>
					<th class="header">Credit Days</th>
					<th class="header">Credit Interest</th>
					<th class="header">Party / Remarks</th>
				</tr>`;

		for (let i = 0; i < max_len; i++) {
			let d = debit[i] || {};
			let c = credit[i] || {};

			let dr_info = [d.party || "", d.voucher_type === "Opening Balance" ? "Opening Balance" : (d.remarks || "")].filter(Boolean).join(" - ");
			let cr_info = [c.party || "", c.voucher_type === "Opening Balance" ? "Opening Balance" : (c.remarks || "")].filter(Boolean).join(" - ");

			let d_interest = 0;
			let d_days = 0;
			// Always use posting_date for days/interest
			let d_calc_date = d.posting_date || d.date;
			if (d.amount && d_calc_date && till_date) {
				d_days = moment(till_date).diff(moment(d_calc_date), 'days');
				if (d.voucher_type === "Opening Balance") d_days += 1;
				if (d_days > 0 && interest_rate > 0) d_interest = (d.amount * interest_rate / 100) * (d_days / 30);
				total_debit_interest += d_interest;
			}

			let c_interest = 0;
			let c_days = 0;
			let c_calc_date = c.posting_date || c.date;
			if (c.amount && c_calc_date && till_date) {
				c_days = moment(till_date).diff(moment(c_calc_date), 'days');
				if (c.voucher_type === "Opening Balance") c_days += 1;
				if (c_days > 0 && interest_rate > 0) c_interest = (c.amount * interest_rate / 100) * (c_days / 30);
				total_credit_interest += c_interest;
			}

			html += `
				<tr>
					<td class="date-col">${d.date ? frappe.datetime.str_to_user(d.date) : ""}</td>
					<td class="num">${d.amount ? flt(d.amount, 2).toFixed(2) : ""}</td>
					<td style="text-align: right;">${d_days > 0 ? d_days : ""}</td>
					<td class="num">${d_interest ? flt(d_interest, 2).toFixed(2) : ""}</td>
					<td>${dr_info}</td>
					<td class="divider"></td>
					<td class="date-col">${c.date ? frappe.datetime.str_to_user(c.date) : ""}</td>
					<td class="num">${c.amount ? flt(c.amount, 2).toFixed(2) : ""}</td>
					<td style="text-align: right;">${c_days > 0 ? c_days : ""}</td>
					<td class="num">${c_interest ? flt(c_interest, 2).toFixed(2) : ""}</td>
					<td>${cr_info}</td>
				</tr>
			`;
		}

		html += `
				<tr class="totals-row">
					<td class="header" style="text-align: right;">Total:</td>
					<td class="num">${flt(current_data.total_debit || 0, 2).toFixed(2)}</td>
					<td></td>
					<td class="num">${flt(total_debit_interest, 2).toFixed(2)}</td>
					<td></td>
					<td class="divider"></td>
					<td class="header" style="text-align: right;">Total:</td>
					<td class="num">${flt(current_data.total_credit || 0, 2).toFixed(2)}</td>
					<td></td>
					<td class="num">${flt(total_credit_interest, 2).toFixed(2)}</td>
					<td></td>
				</tr>
		`;

		let closing_bal = current_data.closing_balance || 0;
		let bal_text = closing_bal >= 0 ? 'Closing Balance (Debit)' : 'Closing Balance (Credit)';

		html += `
				<tr class="closing-row">
					<td colspan="5"></td>
					<td class="divider"></td>
					<td class="header" colspan="2" style="text-align: right;">${bal_text}:</td>
					<td class="num" colspan="3">${flt(Math.abs(closing_bal), 2).toFixed(2)}</td>
				</tr>
			</table>
		</body>
		</html>`;

		let blob = new Blob([html], { type: 'application/vnd.ms-excel' });
		let url = URL.createObjectURL(blob);
		let a = document.createElement('a');
		a.href = url;
		a.download = `Interest_Planning_${account}.xls`;
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

		let account = fixed_account;
		let interest_rate = page.fields_dict.interest_rate.get_value() || 0;
		let till_date = page.fields_dict.till_date.get_value();

		let header_html = `
			<h2 style="text-align: center; font-family: sans-serif;">Interest Planning: ${account}</h2>
			<div style="text-align: center; font-family: sans-serif; font-size: 14px; margin-bottom: 20px; color: #555;">
				${__('Interest Rate')}: <strong>${interest_rate}%</strong> | ${__('Till Date')}: <strong>${frappe.datetime.str_to_user(till_date)}</strong>
			</div>
		`;
		let content_html = $('#ledger-body').html();

		frappe.render_pdf(header_html + content_html, {
			orientation: 'Portrait',
			report_name: `Interest_Planning_${account}`
		});
	}
};