frappe.pages['stock-balance-summary'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Stock Balance Summary'),
		single_column: true
	});

	page.main.html(`<div class="stock-balance-summary-wrapper"></div>`);
    
	// Add filters
	let item_group_filter = page.add_field({
		fieldname: 'item_group',
		label: __('Item Group'),
		fieldtype: 'Link',
		options: 'Item Group',
		change: function() {
			load_data(page);
		}
	});

	page.set_primary_action(__('Refresh'), function() {
		load_data(page);
	}, 'refresh');

	load_data(page);
}

function load_data(page) {
	let item_group = page.fields_dict.item_group.get_value();
	frappe.call({
		method: 'erpnext.stock.page.stock_balance_summary.stock_balance_summary.get_summary_data',
		args: {
			filters: {
				item_group: item_group
			}
		},
		callback: function(r) {
			if (r.message) {
				render_data(page, r.message);
			}
		}
	});
}

function render_data(page, data) {
	let wrapper = page.main.find('.stock-balance-summary-wrapper');
	wrapper.empty();

	if (!data || !data.length) {
		wrapper.html(`<div class="text-muted text-center" style="margin-top: 50px;">
			<h4>${__('No Data Found')}</h4>
		</div>`);
		return;
	}

	let html = `<div class="table-responsive" style="padding: 15px;">`;
	
	let grand_total_weight = 0;
	let grand_total_amount = 0;

	data.forEach(group => {
		grand_total_weight += group.total_weight;
		grand_total_amount += group.total_amount;

		html += `
			<h4 style="margin-top: 20px; margin-bottom: 10px;">${group.category}</h4>
			<table class="table table-bordered table-hover" style="background-color: var(--card-bg);">
				<thead>
					<tr>
						<th style="width: 20%">${__('Grade')}</th>
						<th style="width: 30%">${__('Finish')}</th>
						<th style="width: 15%" class="text-right">${__('Weight (Kg)')}</th>
						<th style="width: 15%" class="text-right">${__('Amount')}</th>
						<th style="width: 20%" class="text-right">${__('Rate')}</th>
					</tr>
				</thead>
				<tbody>
		`;

		group.rows.forEach(row => {
			html += `
				<tr>
					<td>${row.grade || ''}</td>
					<td>${row.finish || ''}</td>
					<td class="text-right">${format_number(row.weight, null, 3)}</td>
					<td class="text-right">${format_currency(row.amount)}</td>
					<td class="text-right">${format_currency(row.rate)}</td>
				</tr>
			`;
		});

		// Group Total
		html += `
				<tr style="font-weight: bold; background-color: var(--highlight-color);">
					<td colspan="2" class="text-right">${__('Total')}</td>
					<td class="text-right">${format_number(group.total_weight, null, 3)}</td>
					<td class="text-right">${format_currency(group.total_amount)}</td>
					<td class="text-right">${group.total_weight ? format_currency(group.total_amount / group.total_weight) : 0}</td>
				</tr>
		`;

		html += `
				</tbody>
			</table>
		`;
	});

	// Grand Total
	html += `
		<table class="table table-bordered" style="margin-top: 20px; background-color: var(--card-bg);">
			<tbody>
				<tr style="font-size: 16px; font-weight: bold; background-color: var(--bg-light-gray);">
					<td style="width: 50%" class="text-right">${__('Grand Total')}</td>
					<td style="width: 15%" class="text-right">${format_number(grand_total_weight, null, 3)}</td>
					<td style="width: 15%" class="text-right">${format_currency(grand_total_amount)}</td>
					<td style="width: 20%" class="text-right">${grand_total_weight ? format_currency(grand_total_amount / grand_total_weight) : 0}</td>
				</tr>
			</tbody>
		</table>
	</div>`;

	wrapper.html(html);
}
