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
			method: 'erpnext.selling.page.pipe_balance_view.pipe_balance_view.get_dashboard_data',
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
			'/api/method/erpnext.selling.page.pipe_balance_view.pipe_balance_view.export_to_excel',
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
			const spec_groups = new Map();
			rows.forEach(row => {
				let normalized_thk = (row.thickness || '').trim();
				const parsed_thk = parseFloat(normalized_thk);
				if (!isNaN(parsed_thk)) {
					normalized_thk = String(parsed_thk);
				} else {
					normalized_thk = normalized_thk.toLowerCase();
				}

				const spec_key = `${row.grade || ''}_${row.finish || ''}_${row.type || ''}_${row.od || ''}_${normalized_thk}_${row.size || ''}`;
				if (!spec_groups.has(spec_key)) {
					spec_groups.set(spec_key, []);
				}
				spec_groups.get(spec_key).push(row);
			});

			let total_nos = 0;
			let total_weight = 0;
			const balance_rows = [];

			spec_groups.forEach((spec_rows, spec_key) => {
				// Sort by date ascending to find oldest
				spec_rows.sort((a, b) => {
					const date_a = a.date || '';
					const date_b = b.date || '';
					return date_a.localeCompare(date_b);
				});

				const oldest_row = spec_rows[0];

				// Find latest positive weight row for warehouse
				let latest_active_row = null;
				for (let i = spec_rows.length - 1; i >= 0; i--) {
					if (flt(spec_rows[i].weight) > 0) {
						latest_active_row = spec_rows[i];
						break;
					}
				}
				if (!latest_active_row) {
					latest_active_row = oldest_row;
				}

				const schedule_row = spec_rows.find(r => r.schedule && r.schedule.trim() !== '');
				const schedule = schedule_row ? schedule_row.schedule : '';

				let net_nos = 0;
				let net_weight = 0;
				spec_rows.forEach(row => {
					const weight = flt(row.weight);
					net_nos += weight < 0 ? -flt(row.pieces) : flt(row.pieces);
					net_weight += weight;
				});

				const finish_val = (oldest_row.finish || '').trim().toUpperCase();
				const is_2b_od = finish_val === '2B OD SIZE';
				const is_sold = is_2b_od ? (net_weight <= 0.001) : (net_weight <= 0.001 && net_nos <= 0.001);

				if (!this.show_sold_stock && is_sold) {
					return;
				}

				total_nos += net_nos;
				total_weight += net_weight;

				balance_rows.push({
					oldest_row: oldest_row,
					latest_active_row: latest_active_row,
					schedule: schedule,
					net_nos: net_nos,
					net_weight: net_weight
				});
			});

			if (balance_rows.length === 0) {
				return;
			}

			const rows_html = balance_rows.map(({ oldest_row, latest_active_row, schedule, net_nos, net_weight }) => {
				const row_class = net_weight <= 0.001 ? 'row-empty' : '';

				let date_str = '';
				if (oldest_row.date) {
					const date = frappe.datetime.str_to_obj(oldest_row.date);
					date_str = date.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
				}

				const l_days = oldest_row.date ? frappe.datetime.get_diff(frappe.datetime.get_today(), oldest_row.date) : 0;

				let thickness_display = schedule || oldest_row.thickness || '';
				if (thickness_display && !/sch/i.test(thickness_display)) {
					const val = parseFloat(thickness_display);
					if (!isNaN(val)) {
						thickness_display = `${val} mm`;
					} else if (!thickness_display.endsWith('mm')) {
						thickness_display = `${thickness_display} mm`;
					}
				}

				return `
					<tr class="${row_class}">
						<td style="font-weight: 700; color: var(--pipe-primary)">${pkt_no}</td>
						<td>${date_str}</td>
						<td>${oldest_row.grade || ''}</td>
						<td>${oldest_row.finish || ''}</td>
						<td>${oldest_row.type || ''}</td>
						<td>${oldest_row.od || ''}</td>
						<td>${thickness_display}</td>
						<td>${oldest_row.size || ''}</td>
						<td style="text-align: right">${net_nos}</td>
						<td style="text-align: right">${frappe.format(net_weight, { fieldtype: 'Float' }, { only_value: true })}</td>
						<td>${latest_active_row.plot || ''}</td>
						<td>${l_days}</td>
					</tr>
				`;
			}).join('');

			const box_html = `
				<div class="pkt-box" style="margin-bottom: 25px;">
					<div class="pipe-table-container">
						<table class="pipe-table">
							<thead>
								<tr>
									<th>PKT NO</th>
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
									<td colspan="8">TOTAL</td>
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
