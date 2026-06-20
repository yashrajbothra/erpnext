frappe.pages['paper'].on_page_load = function (wrapper) {

	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Paper',
		single_column: true
	});

	let fixed_account = 'LC - SM55';
	let company = frappe.defaults.get_default('company') || frappe.boot.sysdefaults.company;
	if (company) {
		frappe.db.get_value('Company', company, 'abbr').then(r => {
			if (r && r.message && r.message.abbr) {
				fixed_account = `LC - ${r.message.abbr}`;
			}
		});
	}

	page.add_field({
		fieldname: 'filter_account',
		label: __('Account'),
		fieldtype: 'MultiSelectList',
		options: 'Account',
		get_data: function (txt) {
			return frappe.db.get_link_options('Account', txt);
		}
	});

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
		fieldname: 'cutoff_date',
		label: __('Cutoff Date'),
		fieldtype: 'Date',
		default: frappe.datetime.get_today()
	});

	page.add_field({
		fieldname: 'interest_rate',
		label: __('Interest Rate (%)'),
		fieldtype: 'Float',
		default: 0
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
		let filter_account = page.fields_dict.filter_account.get_value();
		let party = page.fields_dict.party.get_value();
		let from_date = page.fields_dict.from_date.get_value();
		let to_date = page.fields_dict.to_date.get_value();
		let cutoff_date = page.fields_dict.cutoff_date.get_value();
		let interest_rate = page.fields_dict.interest_rate.get_value() || 0;
		let use_entry_date = page.fields_dict.use_entry_date.get_value() ? 1 : 0;

		if (!cutoff_date) {
			frappe.msgprint(__('Please select a Cutoff Date'));
			return;
		}

		// If user selected a specific account filter, query that account directly
		// (not the fixed LC account). This lets accounts like "Debtors Discount"
		// show their own GL entries.
		let account, counterpart_filter;
		if (filter_account && filter_account.length > 0) {
			account = filter_account;
			counterpart_filter = null;
		} else {
			account = fixed_account;
			counterpart_filter = null;
		}

		frappe.call({
			method: "erpnext.api.get_general_t_ledger",
			args: {
				account: account,
				party: party,
				filter_account: counterpart_filter,
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

		let debit = data.debit || [];
		let credit = data.credit || [];
		let use_entry_date = page.fields_dict.use_entry_date.get_value() ? 1 : 0;
		let cutoff_date = page.fields_dict.cutoff_date.get_value();
		let interest_rate = page.fields_dict.interest_rate.get_value() || 0;

		let total_debit_interest = 0;
		let total_credit_interest = 0;

		if (use_entry_date) {
			let grouped = {};

			debit.forEach(d => {
				if (!d.amount) return;
				let date = d.entry_date || d.date;
				if (!grouped[date]) grouped[date] = { debit: [], credit: [] };
				grouped[date].debit.push(d);
			});

			credit.forEach(c => {
				if (!c.amount) return;
				let date = c.entry_date || c.date;
				if (!grouped[date]) grouped[date] = { debit: [], credit: [] };
				grouped[date].credit.push(c);
			});

			let sorted_dates = Object.keys(grouped).sort();
			let opening_bal = data.opening_balance || 0;
			let op_bal_color = opening_bal >= 0 ? '#2ecc71' : '#e74c3c';
			let op_bal_text = opening_bal >= 0 ? __('Opening Balance (Dr)') : __('Opening Balance (Cr)');

			let html = `
				<div style="margin-bottom: 25px; background-color: #f8f9fa; border: 1px solid #d1d8dd; border-radius: 4px; padding: 15px; display: flex; justify-content: space-between; align-items: center; font-weight: bold; font-size: 14px;">
					<span style="color: #1f2937;">${op_bal_text}</span>
					<span style="color: ${op_bal_color};">${format_currency(Math.abs(opening_bal), frappe.boot.sysdefaults.currency)}</span>
				</div>
			`;

			if (sorted_dates.length === 0) {
				html += `
					<div class="text-center text-muted" style="padding: 30px;">
						${__("No entries found for the selected criteria.")}
					</div>
				`;
			}

			let running_balance = opening_bal;

			sorted_dates.forEach(date => {
				let day_data = grouped[date];
				let d_rows = day_data.debit;
				let c_rows = day_data.credit;
				let max_len = Math.max(d_rows.length, c_rows.length);

				let day_total_debit = d_rows.reduce((s, r) => s + (r.amount || 0), 0);
				let day_total_credit = c_rows.reduce((s, r) => s + (r.amount || 0), 0);

				let day_opening = running_balance;
				let day_closing = running_balance + day_total_debit - day_total_credit;
				running_balance = day_closing;

				html += `
					<div class="date-box" style="margin-bottom: 25px; border: 1px solid #d1d8dd; border-radius: 4px; background-color: #ffffff; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
						<div style="padding: 10px 15px; background-color: #f8f9fa; border-bottom: 1px solid #d1d8dd; font-weight: bold; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap;">
							<div style="font-size: 14px; color: #1f2937; margin-bottom: 5px;">${frappe.datetime.str_to_user(date)}</div>
							<div style="font-size: 12px; display: flex; gap: 15px;">
								<span style="color: #6c7680;">${__('Op: ')} ${format_currency(Math.abs(day_opening), frappe.boot.sysdefaults.currency)} ${day_opening >= 0 ? 'Dr' : 'Cr'}</span>
								<span class="text-danger">${__('Dr: ')} ${format_currency(day_total_debit, frappe.boot.sysdefaults.currency)}</span>
								<span class="text-success">${__('Cr: ')} ${format_currency(day_total_credit, frappe.boot.sysdefaults.currency)}</span>
								<span style="color: #1f2937;">${__('Cl: ')} ${format_currency(Math.abs(day_closing), frappe.boot.sysdefaults.currency)} ${day_closing >= 0 ? 'Dr' : 'Cr'}</span>
							</div>
						</div>
						<div class="row" style="margin: 0; border-bottom: 1px solid #d1d8dd; background-color: #fcfcfc;">
							<div class="col-xs-6 text-center" style="border-right: 1px solid #d1d8dd; padding: 8px; font-weight: 600; width: 50%; float: left; box-sizing: border-box;">${__('Debit')}</div>
							<div class="col-xs-6 text-center" style="padding: 8px; font-weight: 600; width: 50%; float: left; box-sizing: border-box;">${__('Credit')}</div>
							<div style="clear: both;"></div>
						</div>
				`;


				for (let i = 0; i < max_len; i++) {
					let d = d_rows[i] || {};
					let c = c_rows[i] || {};
					let dr_res = format_row(d, cutoff_date, interest_rate);
					let cr_res = format_row(c, cutoff_date, interest_rate);

					total_debit_interest += dr_res.interest;
					total_credit_interest += cr_res.interest;

					html += `
						<div class="row" style="margin: 0; border-bottom: 1px solid #f0f0f0;">
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
				html += `</div>`; // End of date-box
			});

			// Summary Totals
			let closing_bal = data.closing_balance || 0;
			let bal_color = closing_bal >= 0 ? '#2ecc71' : '#e74c3c';
			let bal_text = closing_bal >= 0 ? __('Closing Balance (You owe us)') : __('Closing Balance (We owe you)');
			let bal_abs = Math.abs(closing_bal);

			html += `
				<div style="margin-top: 30px; border-top: 1px solid #d1d8dd; padding-top: 20px;">
					<div class="row" style="margin: 0; font-weight: bold; background-color: #f8f9fa; border: 1px solid #d1d8dd; border-radius: 4px;">
						<div class="col-xs-12" style="padding: 15px; font-size: 14px; width: 100%; box-sizing: border-box;">
							<table style="width: 100%; border-collapse: collapse;">
								<tr>
									<td style="padding: 5px 0; color: ${op_bal_color};">${op_bal_text}</td>
									<td style="text-align: right; padding: 5px 0; color: ${op_bal_color};">${format_currency(Math.abs(opening_bal), frappe.boot.sysdefaults.currency)}</td>
								</tr>
								<tr>
									<td style="padding: 5px 0; color: #e74c3c;">${__('Total Period Debit')}</td>
									<td style="text-align: right; padding: 5px 0; color: #e74c3c;">${format_currency(data.total_debit, frappe.boot.sysdefaults.currency)}</td>
								</tr>
								${cutoff_date ? `
								<tr>
									<td style="padding: 5px 0; color: #e74c3c; font-size: 12px; padding-left: 15px;">${__('Total Period Debit Interest')}</td>
									<td style="text-align: right; padding: 5px 0; color: #e74c3c; font-size: 12px;">${format_currency(total_debit_interest, frappe.boot.sysdefaults.currency)}</td>
								</tr>
								` : ''}
								<tr>
									<td style="padding: 5px 0; color: #2ecc71;">${__('Total Period Credit')}</td>
									<td style="text-align: right; padding: 5px 0; color: #2ecc71;">${format_currency(data.total_credit, frappe.boot.sysdefaults.currency)}</td>
								</tr>
								${cutoff_date ? `
								<tr>
									<td style="padding: 5px 0; color: #2ecc71; font-size: 12px; padding-left: 15px;">${__('Total Period Credit Interest')}</td>
									<td style="text-align: right; padding: 5px 0; color: #2ecc71; font-size: 12px;">${format_currency(total_credit_interest, frappe.boot.sysdefaults.currency)}</td>
								</tr>
								` : ''}
								<tr style="border-top: 1px solid #d1d8dd; font-size: 16px;">
									<td style="padding: 15px 0; color: ${bal_color};">${bal_text}</td>
									<td style="text-align: right; padding: 15px 0; color: ${bal_color};">${format_currency(bal_abs, frappe.boot.sysdefaults.currency)}</td>
								</tr>
							</table>
						</div>
					</div>
				</div>
			`;


			$('#ledger-body').html(html);
			return;
		}

		let max_len = Math.max(debit.length, credit.length);

		let opening_bal = data.opening_balance || 0;
		let op_bal_color = opening_bal >= 0 ? '#2ecc71' : '#e74c3c';
		let op_bal_text = opening_bal >= 0 ? __('Opening Balance (Dr)') : __('Opening Balance (Cr)');

		let html = `
			<div style="margin-bottom: 25px; background-color: #f8f9fa; border: 1px solid #d1d8dd; border-radius: 4px; padding: 15px; display: flex; justify-content: space-between; align-items: center; font-weight: bold; font-size: 14px;">
				<span style="color: #1f2937;">${op_bal_text}</span>
				<span style="color: ${op_bal_color};">${format_currency(Math.abs(opening_bal), frappe.boot.sysdefaults.currency)}</span>
			</div>
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
			let dr_res = format_row(d, cutoff_date, interest_rate);
			let cr_res = format_row(c, cutoff_date, interest_rate);

			total_debit_interest += dr_res.interest;
			total_credit_interest += cr_res.interest;

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
		let closing_bal = data.closing_balance || 0;
		let bal_color = closing_bal >= 0 ? '#2ecc71' : '#e74c3c';
		let bal_text = closing_bal >= 0 ? __('Closing Balance (You owe us)') : __('Closing Balance (We owe you)');
		let bal_abs = Math.abs(closing_bal);

		html += `
				<div class="row" style="margin: 0; font-weight: bold; background-color: #f8f9fa;">
					<div class="col-xs-6" style="border-right: 1px solid #d1d8dd; padding: 12px; font-size: 14px; width: 50%; float: left; box-sizing: border-box;">
						<div class="text-right text-danger" style="text-align: right; color: #e74c3c;">
							<div>${__('Total Period: ')} ${format_currency(data.total_debit, frappe.boot.sysdefaults.currency)}</div>
							${cutoff_date ? `<div style="font-size: 12px; margin-top: 4px;">${__('Total Interest: ')} ${format_currency(total_debit_interest, frappe.boot.sysdefaults.currency)}</div>` : ''}
						</div>
					</div>
					<div class="col-xs-6" style="padding: 12px; font-size: 14px; width: 50%; float: left; box-sizing: border-box;">
						<div class="text-right text-success" style="text-align: right; color: #2ecc71;">
							<div>${__('Total Period: ')} ${format_currency(data.total_credit, frappe.boot.sysdefaults.currency)}</div>
							${cutoff_date ? `<div style="font-size: 12px; margin-top: 4px;">${__('Total Interest: ')} ${format_currency(total_credit_interest, frappe.boot.sysdefaults.currency)}</div>` : ''}
						</div>
					</div>
					<div style="clear: both;"></div>
				</div>
				<div class="row" style="margin: 0; font-weight: bold; background-color: #eaf1f8; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px; padding: 15px; border-top: 2px solid #d1d8dd; font-size: 15px;">
					<div style="text-align: right; color: ${bal_color}; width: 100%; box-sizing: border-box;">
						${bal_text}: ${format_currency(bal_abs, frappe.boot.sysdefaults.currency)}
					</div>
				</div>
			</div>
		`;


		$('#ledger-body').html(html);
	}


	function format_row(row, cutoff_date, interest_rate) {
		if (!row || row.amount === undefined || row.amount === null || row.amount === "") {
			return { html: "", interest: 0 };
		}

		let link_html = "";
		if (row.voucher_type === "Opening Balance") {
			link_html = `<span style="font-weight: bold;">${row.voucher_type}</span>`;
		}

		let extra_info_html = "";
		if (row.party || row.remarks) {
			let details = [];
			if (row.party) details.push(`<span style="font-weight: 600; color: #36414c;">${row.party}</span>`);
			if (row.remarks) {
				let safe_remarks = String(row.remarks).replace(/\n/g, '<br>');
				details.push(`<span style="color: #6c7680;">${safe_remarks}</span>`);
			}
			extra_info_html = `
				<div style="font-size: 11px; margin-top: 6px; line-height: 1.4;">
					${details.join('<br>')}
				</div>
			`;
		}

		// Show entry_date if available (when use_entry_date is active), posting_date otherwise
		let display_date = row.entry_date ? row.entry_date : row.date;
		let entry_date_suffix = row.entry_date && row.entry_date !== row.date ? ` <span style="font-size:10px; color:#aaa;">(E: ${frappe.datetime.str_to_user(row.entry_date)})</span>` : '';

		// Determine best account to show
		let account_to_show = row.against || "";
		if (row.voucher_type === "Payment Entry") {
			// If it's a payment, prefer the explicit paid_to or paid_from fields to avoid showing Party Name
			account_to_show = row.paid_to == fixed_account ? row.paid_from : row.paid_to;
		}

		let interest = 0;
		let days_display = 0;
		let calc_date = row.date;
		if (calc_date && cutoff_date) {
			let days = moment(cutoff_date).diff(moment(calc_date), 'days');
			days_display = days;
			if (days > 0 && interest_rate > 0) {
				interest = (row.amount * interest_rate / 100) * (days / 30);
			}
		}

		let interest_display_html = "";
		if (cutoff_date) {
			interest_display_html = `
				<div class="text-muted" style="font-size: 11px; margin-top: 4px; line-height: 1.2;">
					Due Days: ${days_display}<br>
					Int: ${format_currency(interest, frappe.boot.sysdefaults.currency)}
				</div>
			`;
		}

		let html = `
			<table style="width: 100%; border-collapse: collapse;">
				<tr>
					<td style="vertical-align: top;">
						<div class="text-muted" style="font-size: 11px; color: #8d99a6; line-height: 1.2;">
							${frappe.datetime.str_to_user(display_date)}${entry_date_suffix}
						</div>
						<div style="font-size: 11px; color: #8d99a6; margin-bottom: 4px;">
							${account_to_show}
						</div>
						<div style="font-size: 13px;">
							${link_html}
						</div>
						${extra_info_html}
					</td>
					<td style="text-align: right; font-weight: 500; vertical-align: top;">
						<div>${format_currency(row.amount, frappe.boot.sysdefaults.currency)}</div>
						${interest_display_html}
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
		let cutoff_date = page.fields_dict.cutoff_date.get_value();
		let interest_rate = page.fields_dict.interest_rate.get_value() || 0;

		let opening_bal = current_data.opening_balance || 0;
		let op_bal_text = opening_bal >= 0 ? 'Opening Balance (Debit)' : 'Opening Balance (Credit)';

		let export_data = [
			[op_bal_text, "", "", Math.abs(opening_bal), "", "", "", "", "", "", "", "", "", ""],
			[
				"Date", "Debit Voucher Type", "Debit Voucher No", "Debit Amount", "Debit Due Days", "Debit Interest", "Party / Remarks",
				"Date", "Credit Voucher Type", "Credit Voucher No", "Credit Amount", "Credit Due Days", "Credit Interest", "Party / Remarks"
			]
		];

		let debit = current_data.debit || [];
		let credit = current_data.credit || [];
		let max_len = Math.max(debit.length, credit.length);

		let use_entry_date = page.fields_dict.use_entry_date.get_value() ? 1 : 0;
		let total_debit_interest = 0;
		let total_credit_interest = 0;

		for (let i = 0; i < max_len; i++) {
			let d = debit[i] || {};
			let c = credit[i] || {};

			let dr_info = [d.party || "", d.remarks || ""].filter(Boolean).join(" - ");
			let cr_info = [c.party || "", c.remarks || ""].filter(Boolean).join(" - ");

			let d_date = (use_entry_date && d.entry_date) ? d.entry_date : d.date;
			let c_date = (use_entry_date && c.entry_date) ? c.entry_date : c.date;

			let d_interest = 0;
			let d_days = "";
			let d_calc_date = d.date;
			if (d_calc_date && cutoff_date && d.amount !== undefined && d.amount !== null && d.amount !== "") {
				let days = moment(cutoff_date).diff(moment(d_calc_date), 'days');
				d_days = days;
				if (days > 0 && interest_rate > 0) {
					d_interest = (d.amount * interest_rate / 100) * (days / 30);
				}
				total_debit_interest += d_interest;
			}

			let c_interest = 0;
			let c_days = "";
			let c_calc_date = c.date;
			if (c_calc_date && cutoff_date && c.amount !== undefined && c.amount !== null && c.amount !== "") {
				let days = moment(cutoff_date).diff(moment(c_calc_date), 'days');
				c_days = days;
				if (days > 0 && interest_rate > 0) {
					c_interest = (c.amount * interest_rate / 100) * (days / 30);
				}
				total_credit_interest += c_interest;
			}

			export_data.push([
				d_date ? frappe.datetime.str_to_user(d_date) : "",
				(d.voucher_type || "") + (d.is_discount ? " (Discount)" : ""),
				d.voucher_no || "",
				d.amount || 0.0,
				d_days,
				d_interest,
				dr_info,
				c_date ? frappe.datetime.str_to_user(c_date) : "",
				(c.voucher_type || "") + (c.is_discount ? " (Discount)" : ""),
				c.voucher_no || "",
				c.amount || 0.0,
				c_days,
				c_interest,
				cr_info
			]);
		}

		export_data.push([
			"", "", "Total Period Debit:", current_data.total_debit || 0, "", total_debit_interest, "",
			"", "", "Total Period Credit:", current_data.total_credit || 0, "", total_credit_interest, ""
		]);

		let closing_bal = current_data.closing_balance || 0;
		let bal_text = closing_bal >= 0 ? 'Closing Balance (Debit)' : 'Closing Balance (Credit)';

		export_data.push([
			"", "", "", "", "", "", "",
			"", "", "", bal_text + ":", "", Math.abs(closing_bal), ""
		]);

		frappe.tools.downloadify(export_data, null, `General_T_Ledger_${account}`);
	}

	function export_to_pdf() {
		if (!current_data) {
			frappe.msgprint(__('Please load the ledger first'));
			return;
		}

		let account = fixed_account;
		let cutoff_date = page.fields_dict.cutoff_date.get_value();
		let interest_rate = page.fields_dict.interest_rate.get_value() || 0;

		let header_html = `
			<h2 style="text-align: center; font-family: sans-serif;">General T-Ledger: ${account}</h2>
			<div style="text-align: center; font-family: sans-serif; font-size: 14px; margin-bottom: 20px; color: #555;">
				${__('Interest Rate')}: <strong>${interest_rate}%</strong> | ${__('Cutoff Date')}: <strong>${frappe.datetime.str_to_user(cutoff_date)}</strong>
			</div>
		`;
		let content_html = $('#ledger-body').html();

		frappe.render_pdf(header_html + content_html, {
			orientation: 'Portrait',
			report_name: `General_T_Ledger_${account}`
		});
	}
};