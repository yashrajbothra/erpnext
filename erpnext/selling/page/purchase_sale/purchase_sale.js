frappe.pages['purchase-sale'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Purchase / Sale',
		single_column: true
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
					${__("Please select dates and click on Load Ledger")}
				</div>
			</div>
		</div>
	`).appendTo(page.main);

	function load_ledger() {
		let from_date = page.fields_dict.from_date.get_value();
		let to_date = page.fields_dict.to_date.get_value();

		frappe.call({
			method: "erpnext.api.get_itemised_trading_ledger",
			args: {
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
						${__('Purchases')}
					</div>
					<div class="col-xs-6 text-center" style="padding: 12px; font-weight: bold; color: #36414c; width: 50%; float: left; box-sizing: border-box;">
						${__('Sales')}
					</div>
					<div style="clear: both;"></div>
				</div>
		`;

		if (max_len === 0) {
			html += `
				<div class="text-center text-muted" style="padding: 30px;">
					${__("No items found for the selected dates.")}
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
				<div class="row" style="margin: 0; font-weight: bold; background-color: #f8f9fa;">
					<div class="col-xs-6" style="border-right: 1px solid #d1d8dd; padding: 12px; font-size: 14px; width: 50%; float: left; box-sizing: border-box;">
						<div class="text-right text-danger" style="text-align: right; color: #e74c3c;">${__('Total: ')} ${format_currency(data.total_debit, frappe.boot.sysdefaults.currency)}</div>
					</div>
					<div class="col-xs-6" style="padding: 12px; font-size: 14px; width: 50%; float: left; box-sizing: border-box;">
						<div class="text-right text-success" style="text-align: right; color: #2ecc71;">${__('Total: ')} ${format_currency(data.total_credit, frappe.boot.sysdefaults.currency)}</div>
					</div>
					<div style="clear: both;"></div>
				</div>
		`;

		let closing_bal = data.closing_balance || 0;
		let bal_color = closing_bal >= 0 ? '#2ecc71' : '#e74c3c';
		let bal_text = closing_bal >= 0 ? __('Gross Margin (Profit)') : __('Gross Margin (Loss)');
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
		if (!row || row.amount === undefined || row.amount === null || row.amount === "") return "";

		let link_html = `<a href="/app/${frappe.router.slug(row.voucher_type)}/${row.voucher_no}" style="text-decoration: none; font-weight: bold;">
				${row.voucher_type} - ${row.voucher_no}
			</a>`;

		let details = [];
		if (row.custom_size) details.push(`Size: ${row.custom_size}`);
		if (row.weight) details.push(`Wt: ${row.weight}`);
		if (row.custom_thickness) details.push(`Thick: ${row.custom_thickness}`);
		if (row.custom_od) details.push(`OD: ${row.custom_od}`);
		if (row.custom_citi_no) details.push(`Citi No: ${row.custom_citi_no}`);

		let details_html = details.length > 0
			? `<div style="font-size: 11px; color: #8d99a6; margin-top: 2px;">${details.join(' | ')}</div>`
			: '';

		let extra_info_html = `
            <div style="font-size: 11px; color: #8d99a6; margin-top: 4px;">
                ${__('Party')}: <span style="color: #36414c;">${row.party || ''}</span>
            </div>
            <div style="font-size: 11px; color: #8d99a6; margin-top: 2px;">
                ${__('Warehouse')}: <span style="color: #36414c;">${row.warehouse || ''}</span>
            </div>
			<div style="font-size: 11px; color: #8d99a6; margin-top: 2px;">
				${__('Item')}: <span style="color: #36414c;">${row.item_name}</span>
			</div>
            ${details_html}
			<div style="font-size: 11px; color: #8d99a6; margin-top: 2px;">
				${row.weight || row.qty} x ${format_currency(row.calculated_rate, frappe.boot.sysdefaults.currency)}
			</div>
		`;

		let raw_amt = (row.calculated_rate || 0.0) * (row.weight || row.qty);
		let amount_breakdown = `
			<div style="font-size: 12px; color: #8d99a6;">
				${format_currency(raw_amt, frappe.boot.sysdefaults.currency)}
			</div>
		`;

		if (row.custom_loading_charges) {
			amount_breakdown += `<div style="font-size: 11px; color: #8d99a6;">+ L: ${format_currency(row.custom_loading_charges, frappe.boot.sysdefaults.currency)}</div>`;
		}
		if (row.custom_gst_amount) {
			amount_breakdown += `<div style="font-size: 11px; color: #8d99a6;">+ GST: ${format_currency(row.custom_gst_amount, frappe.boot.sysdefaults.currency)}</div>`;
		}

		let total_amount_html = `
			${amount_breakdown}
			<div style="font-weight: 600; font-size: 14px; margin-top: 4px; border-top: 1px dashed #d1d8dd; padding-top: 2px;">
				${format_currency(row.calculated_amount, frappe.boot.sysdefaults.currency)}
			</div>
		`;

		return `
			<table style="width: 100%; border-collapse: collapse;">
				<tr>
					<td style="vertical-align: top;">
						<div class="text-muted" style="font-size: 11px; color: #8d99a6;">${frappe.datetime.str_to_user(row.date)}</div>
						<div style="font-size: 13px;">
							${link_html}
						</div>
						${extra_info_html}
					</td>
					<td style="text-align: right; vertical-align: top;">
						${total_amount_html}
					</td>
				</tr>
			</table>
		`;
	}

	function export_to_excel() {
		if (!current_data) {
			frappe.msgprint(__('Please load the ledger first'));
			return;
		}

		let export_data = [
			["Citi No", "Purchase Date", "Supplier", "Purchase Warehouse", "Purchase Item", "Size", "Thickness", "OD", "Purchase Qty", "Purchase Weight", "Purchase Rate", "Purchase Loading", "Purchase GST", "Purchase Total", "Citi No", "Sale Date", "Customer", "Sale Warehouse", "Sale Item", "Size", "Thickness", "OD", "Sale Qty", "Sale Weight", "Sale Rate", "Sale Loading", "Sale GST", "Sales Total"]
		];

		let debit = current_data.debit || [];
		let credit = current_data.credit || [];
		let max_len = Math.max(debit.length, credit.length);

		for (let i = 0; i < max_len; i++) {
			let d = debit[i] || {};
			let c = credit[i] || {};

			export_data.push([
				d.custom_citi_no || "",
				d.date ? frappe.datetime.str_to_user(d.date) : "",
				d.party || "",
				d.warehouse || "",
				(d.item_name || ""),
				d.custom_size || "",
				d.custom_schedule || d.custom_thickness || "",
				d.custom_nb || d.custom_od || "",
				d.custom_pieces || "",
				d.qty || "",
				d.calculated_rate || 0.0,
				d.custom_loading_charges || 0.0,
				d.custom_gst_amount || 0.0,
				d.calculated_amount || 0.0,
				c.custom_citi_no || "",
				c.date ? frappe.datetime.str_to_user(c.date) : "",
				c.party || "",
				c.warehouse || "",
				(c.item_name || ""),
				c.custom_size || "",
				c.custom_schedule || c.custom_thickness || "",
				c.custom_nb || c.custom_od || "",
				c.custom_pieces || "",
				c.qty || "",
				c.calculated_rate || 0.0,
				c.custom_loading_charges || 0.0,
				c.custom_gst_amount || 0.0,
				c.calculated_amount || 0.0
			]);
		}

		export_data.push([
			"", "", "", "", "", "", "", "", "", "", "", "", "", "Total:", current_data.total_debit || 0,
			"", "", "", "", "", "", "", "", "", "", "", "", "", "Total:", current_data.total_credit || 0
		]);

		let closing_bal = current_data.closing_balance || 0;
		let bal_text = closing_bal >= 0 ? 'Gross Margin (Profit)' : 'Gross Margin (Loss)';

		export_data.push([
			"", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", bal_text + ":", Math.abs(closing_bal)
		]);

		frappe.tools.downloadify(export_data, null, `Itemised_Trading_Ledger`);
	}

	function export_to_pdf() {
		if (!current_data) {
			frappe.msgprint(__('Please load the ledger first'));
			return;
		}

		let header_html = `<h2 style="text-align: center; font-family: sans-serif;">Itemised Trading Ledger</h2><br>`;
		let content_html = $('#ledger-body').html();

		frappe.render_pdf(header_html + content_html, {
			orientation: 'Portrait',
			report_name: `Itemised_Trading_Ledger`
		});
	}
};