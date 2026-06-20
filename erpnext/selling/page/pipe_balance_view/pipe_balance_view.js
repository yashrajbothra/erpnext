frappe.pages['pipe-balance-view'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Pipe Balance Dashboard',
		single_column: true
	});

	new PipeBalanceDashboard(page);
}

class PipeBalanceDashboard {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.filters = {};
		this.init();
	}

	init() {
		this.page.add_inner_button(__('Export'), () => {
			this.export_to_excel();
		});

		this.show_sold_stock = false;
		this.toggle_btn = this.page.add_inner_button(__('Show Sold Stock'), () => {
			this.show_sold_stock = !this.show_sold_stock;
			$(this.toggle_btn).toggleClass('btn-primary', this.show_sold_stock);
			this.refresh();
		});

		this.make_filters();
		this.make_layout();
		this.refresh();
	}

	make_filters() {
		this.page.add_field({
			fieldname: 'company',
			label: __('Company'),
			fieldtype: 'Link',
			options: 'Company',
			default: frappe.defaults.get_default('company'),
			change: () => this.refresh()
		});

		this.page.add_field({
			fieldname: 'warehouse',
			label: __('Warehouse'),
			fieldtype: 'Link',
			options: 'Warehouse',
			get_query: () => {
				return {
					filters: { 'is_group': 0 }
				}
			},
			change: () => this.refresh()
		});

		this.page.add_field({
			fieldname: 'to_date',
			label: __('To Date'),
			fieldtype: 'Date',
			default: frappe.datetime.get_today(),
			change: () => this.refresh()
		});
	}

	make_layout() {
		this.wrapper.html(`
			<div class="pipe-dashboard">
				<!-- Packet boxes will be rendered here -->
			</div>
		`);
	}

	refresh() {
		const filters = {
			company: this.page.fields_dict.company.get_value(),
			warehouse: this.page.fields_dict.warehouse.get_value(),
			to_date: this.page.fields_dict.to_date.get_value(),
			show_sold_stock: this.show_sold_stock ? 1 : 0
		};

		frappe.call({
			method: 'erpnext.stock.page.pipe_balance_view.pipe_balance_view.get_dashboard_data',
			args: { filters: filters },
			callback: (r) => {
				if (r.message) {
					this.render(r.message);
				}
			}
		});
	}

	export_to_excel() {
		const filters = {
			company: this.page.fields_dict.company.get_value(),
			warehouse: this.page.fields_dict.warehouse.get_value(),
			to_date: this.page.fields_dict.to_date.get_value(),
			show_sold_stock: this.show_sold_stock ? 1 : 0
		};

		open_url_post(
			'/api/method/erpnext.stock.page.pipe_balance_view.pipe_balance_view.export_to_excel',
			{ filters: JSON.stringify(filters) },
			true
		);
	}

	render(res) {
		const { data } = res;
		const body = $('#pipe-data-body');
		this.wrapper.find('.pipe-dashboard').empty();

		if (data.length === 0) {
			this.wrapper.find('.pipe-dashboard').append('<div style="text-align: center; padding: 20px;">No records found</div>');
			return;
		}

		// Group by Pkt No and preserve order
		const groups = new Map();
		data.forEach(row => {
			if (!row.pkt_no) return;
			if (!groups.has(row.pkt_no)) groups.set(row.pkt_no, []);
			groups.get(row.pkt_no).push(row);
		});

		groups.forEach((rows, pkt_no) => {
			const first_row = rows[0];

			let total_nos = 0;
			let total_weight = 0;

			const rows_html = rows.map(row => {
				const weight = flt(row.weight);
				total_nos += flt(row.nos);
				total_weight += weight;

				const row_class = weight <= 0.001 ? 'row-empty' : '';

				let date_str = '';
				if (row.r_date) {
					const date = frappe.datetime.str_to_obj(row.r_date);
					date_str = date.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
				}

				const l_days = row.r_date ? frappe.datetime.get_diff(frappe.datetime.get_today(), row.r_date) : 0;

				return `
					<tr class="${row_class}">
						<td>${date_str}</td>
						<td>${row.grade || ''}</td>
						<td>${row.finish || ''}</td>
						<td>${row.type || ''}</td>
						<td>${row.od || row.nb || ''}</td>
						<td>${row.schedule || row.thik || ''}</td>
						<td>${row.length || ''}</td>
						<td style="text-align: right">${row.nos || 0}</td>
						<td style="text-align: right">${frappe.format(row.weight, { fieldtype: 'Float' }, { only_value: true })}</td>
						<td>${row.warehouse || ''}</td>
						<td>${l_days}</td>
					</tr>
				`;
			}).join('');

			if (total_weight <= 0.001 && total_nos <= 0.001) {
				return;
			}

			const box_html = `
				<div class="pkt-box" style="margin-bottom: 25px;">
					<div style="font-weight: 700; margin-bottom: 5px; color: var(--pipe-primary)">PACKET: ${pkt_no}</div>
					<div class="pipe-table-container">
						<table class="pipe-table">
							<thead>
								<tr>
									<th style="width: 80px">R DATE</th>
									<th>GRADE</th>
									<th>FINISH</th>
									<th>TYPE</th>
									<th>OD</th>
									<th>THIK</th>
									<th>LENGTH</th>
									<th style="text-align: right">NOS</th>
									<th style="text-align: right">WEIGHT</th>
									<th>PLOT</th>
									<th>L DAY</th>
								</tr>
							</thead>
							<tbody>
								${rows_html}
								<tr style="background: #f8fafc; font-weight: 800">
									<td colspan="7"></td>
									<td style="text-align: right">${total_nos}</td>
									<td style="text-align: right">${frappe.format(total_weight, { fieldtype: 'Float' }, { only_value: true })}</td>
									<td colspan="2"></td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			`;
			this.wrapper.find('.pipe-dashboard').append(box_html);
		});
	}
}
