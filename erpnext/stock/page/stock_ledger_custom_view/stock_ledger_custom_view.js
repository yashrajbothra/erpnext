frappe.pages['stock-ledger-custom-view'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Stock Ledger Custom View',
		single_column: true
	});

	new StockLedgerDashboard(page);
}

class StockLedgerDashboard {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.filters = {};
		this.init();
	}

	init() {
		this.page.add_inner_button(__('Summary'), () => {
			frappe.set_route('stock-balance-summary');
		});

		this.page.add_inner_button(__('Export'), () => {
			this.export_to_excel();
		});

		this.page.set_primary_action(__('Save'), () => {
			this.save_data();
		});

		this.make_filters();
		this.make_layout();
		this.refresh();
	}

	make_filters() {
		this.page.add_field({
			fieldname: 'item_group',
			label: __('Item Group'),
			fieldtype: 'Link',
			options: 'Item Group',
			change: () => this.refresh()
		});

		this.page.add_field({
			fieldname: 'to_date',
			label: __('To Date'),
			fieldtype: 'Date',
			change: () => this.refresh()
		});
	}

	make_layout() {
		this.wrapper.html(`
			<div class="stock-dashboard">
				<!-- Packet boxes will be rendered here -->
			</div>
		`);
	}

	refresh() {
		const filters = {
			item_group: this.page.fields_dict.item_group.get_value(),
			to_date: this.page.fields_dict.to_date.get_value()
		};

		frappe.call({
			method: 'erpnext.stock.page.stock_ledger_custom_view.stock_ledger_custom_view.get_dashboard_data',
			args: { filters: filters },
			callback: (r) => {
				if (r.message) {
					this.render(r.message);
				}
			}
		});

		// Bind change event for custom edit fields to mark them dirty
		this.wrapper.off('change', '.custom-edit');
		this.wrapper.on('change', '.custom-edit', (e) => {
			$(e.currentTarget).addClass('dirty');
		});
	}

	save_data() {
		const updates = [];
		this.wrapper.find('.custom-edit.dirty').each((i, el) => {
			const $el = $(el);
			updates.push({
				pkt_no: $el.attr('data-pkt'),
				field: $el.attr('data-field'),
				value: $el.val()
			});
		});

		if (updates.length > 0) {
			frappe.call({
				method: 'erpnext.stock.page.stock_ledger_custom_view.stock_ledger_custom_view.update_custom_fields_batch',
				args: {
					updates: updates
				},
				callback: (r) => {
					if (!r.exc) {
						this.wrapper.find('.custom-edit.dirty').removeClass('dirty');
						frappe.show_alert({ message: __('Saved successfully'), indicator: 'green' });
						this.refresh();
					}
				}
			});
		} else {
			frappe.show_alert({ message: __('No changes to save'), indicator: 'orange' });
		}
	}

	export_to_excel() {
		const filters = {
			item_group: this.page.fields_dict.item_group.get_value(),
			to_date: this.page.fields_dict.to_date.get_value()
		};

		open_url_post(
			'/api/method/erpnext.stock.page.stock_ledger_custom_view.stock_ledger_custom_view.export_to_excel',
			{ filters: JSON.stringify(filters) },
			true
		);
	}

	render(res) {
		const { data } = res;
		this.wrapper.find('.stock-dashboard').empty();

		if (data.length === 0) {
			this.wrapper.find('.stock-dashboard').append('<div style="text-align: center; padding: 20px;">No records found</div>');
			return;
		}

		if (this.datatables) {
			this.datatables.forEach(dt => {
				try {
					dt.destroy();
				} catch (e) {
					console.error(e);
				}
			});
		}
		this.datatables = [];

		// Group all data by item type
		const item_groups = new Map();
		data.forEach(row => {
			let type = row.item_type || 'Other';
			const finish = (row.finish || '').toUpperCase();
			const grade = (row.grade || '').toUpperCase();
			const size_val = row.size ? flt(row.size.split(/[*xX]/)[0]) : 0;

			// Priority Groups
			if (grade.includes('410')) {
				type = '410 GRADE';
			} else if (type.toLowerCase() === 'circle' && (grade.includes('TRIPLY') || finish.includes('TRIPLY'))) {
				type = 'TRIPLY CIRCLE';
			} else if ((finish === 'BA' || finish === '2B') && size_val > 800) {
				if (grade.includes('316L')) {
					type = '316L BA/2B (COIL & SHEET) (>800)';
				} else {
					type = '304 BA/2B (COIL & SHEET) (>800)';
				}
			} else if (finish === 'NO 4 PVC') {
				type = 'NO 4 PVC (COIL & SHEET)';
			} else if (type.toLowerCase() === 'coil' && row.size) {
				if (size_val >= 1250) {
					type = 'Coil (1250+)';
				} else if (size_val === 1240) {
					type = 'Coil (1240)';
				} else {
					type = 'Coil (Other Sizes)';
				}
			} else if (type.toLowerCase() === 'sheet' && (finish === 'NO 8 PVC' || finish === 'NO - 8 PVC')) {
				if (grade.includes('304')) {
					type = '304 NO 8 PVC SHEET';
				} else {
					type = 'J3 NO 8 PVC SHEET';
				}
			} else if (type.toLowerCase() === 'sheet' && grade.includes('J3')) {
				type = 'J3 SHEET';
			} else if (type.toLowerCase() === 'sheet' && grade.includes('304')) {
				type = '304 SHEET';
			}

			if (!item_groups.has(type)) item_groups.set(type, []);
			item_groups.get(type).push(row);
		});

		// Define item group sequence
		const item_sequence = [
			'410 GRADE', 'TRIPLY CIRCLE', '304 BA/2B (COIL & SHEET) (>800)', '316L BA/2B (COIL & SHEET) (>800)', 'Coil (1250+)', 'Coil (1240)', 'Coil (Other Sizes)',
			'NO 4 PVC (COIL & SHEET)', 'J3 NO 8 PVC SHEET', '304 NO 8 PVC SHEET', 'J3 SHEET', '304 SHEET',
			'BABY COIL', 'Circle', 'Sheet', 'Scrap'
		];
		// Sort rows within each group by date ascending (Older first)
		item_groups.forEach((rows, type) => {
			rows.sort((a, b) => {
				const date_a = a.date || '';
				const date_b = b.date || '';
				return date_a.localeCompare(date_b);
			});
		});

		const rendered_groups = new Set();
		console.log("Stock Ledger Data:", data);

		// Helper to render group datatable
		const render_group = (item_type, rows) => {
			const sanitized_type = item_type.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
			const container_id = `datatable-wrapper-${sanitized_type}`;

			const group_html = `
				<div class="item-group-container" style="margin-bottom: 40px; background: #fff; padding: 15px; border-radius: 8px; border: 1px solid var(--pipe-border);">
					<h4 style="margin-bottom: 15px; font-weight: bold; color: var(--pipe-primary); font-size: 16px;">${item_type}</h4>
					<div id="${container_id}"></div>
				</div>
			`;
			this.wrapper.find('.stock-dashboard').append(group_html);

			// Prepare data with totals
			let total_pieces = 0;
			let total_weight = 0;
			const datatable_rows = [];

			rows.forEach(row => {
				total_pieces += flt(row.pieces);
				total_weight += flt(row.weight);
				datatable_rows.push(row);
			});

			datatable_rows.push({
				pkt_no: 'TOTAL',
				thickness: '',
				size: '',
				grade: '',
				finish: '',
				pieces: total_pieces,
				weight: total_weight,
				plot: '',
				code: '',
				hsn: '',
				date: '',
				l_days: '',
				party: '',
				by_col: ''
			});

			const columns = [
				{ id: 'pkt_no', name: 'PKT/COIL NO.', editable: false, width: 100, format: (val) => val === 'TOTAL' ? '<strong>TOTAL</strong>' : (val || '') },
				{ id: 'thickness', name: 'THIK', editable: false, width: 80 },
				{ id: 'size', name: 'SIZE', editable: false, width: 100 },
				{ id: 'grade', name: 'GRADE', editable: false, width: 100 },
				{ id: 'finish', name: 'FINISH', editable: false, width: 100 },
				{
					id: 'pieces', name: 'PCS/PKT', editable: false, width: 90, align: 'right', format: (val, row, col, data) => {
						const is_total = data && data.pkt_no === 'TOTAL';
						const formatted = val !== undefined ? val : '';
						return is_total ? `<strong>${formatted}</strong>` : formatted;
					}
				},
				{
					id: 'weight', name: 'N. WEIGHT', editable: false, width: 110, align: 'right', format: (val, row, col, data) => {
						const is_total = data && data.pkt_no === 'TOTAL';
						const formatted = val !== undefined ? frappe.format(val, { fieldtype: 'Float' }, { only_value: true }) : '';
						return is_total ? `<strong>${formatted}</strong>` : formatted;
					}
				},
				{ id: 'plot', name: 'PLOT', editable: false, width: 100 },
				{ id: 'code', name: 'CODE', editable: false, width: 80 },
				{ id: 'hsn', name: 'HSN CODE', editable: false, width: 120 },
				{
					id: 'date', name: 'R. DATE', editable: false, width: 100, format: (val) => {
						if (!val) return '';
						try {
							const d = frappe.datetime.str_to_obj(val);
							const current_year = new Date().getFullYear();
							if (d.getFullYear() < current_year) {
								return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit', year: 'numeric' });
							}
							return d.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
						} catch (e) {
							return val;
						}
					}
				},
				{ id: 'l_days', name: 'L. DAY', editable: false, width: 80, align: 'right' },
				{
					id: 'party', name: 'PARTY', editable: false, width: 120, format: (value, row, column, data) => {
						let pkt = '';
						if (data && data.pkt_no) pkt = data.pkt_no;
						else if (row && row.pkt_no) pkt = row.pkt_no;
						else if (Array.isArray(row)) {
							const cell = row.find(c => c.column && c.column.id === 'pkt_no');
							if (cell) pkt = cell.content;
						}
						if (pkt === 'TOTAL' || !pkt) return '';
						return `<input type="text" class="custom-edit form-control input-xs" data-pkt="${pkt || ''}" data-field="party" value="${value || ''}" style="width: 100px; height: 24px; padding: 2px 4px;">`;
					}
				},
				{
					id: 'by_col', name: 'BY', editable: false, width: 120, format: (value, row, column, data) => {
						let pkt = '';
						if (data && data.pkt_no) pkt = data.pkt_no;
						else if (row && row.pkt_no) pkt = row.pkt_no;
						else if (Array.isArray(row)) {
							const cell = row.find(c => c.column && c.column.id === 'pkt_no');
							if (cell) pkt = cell.content;
						}
						if (pkt === 'TOTAL' || !pkt) return '';
						return `<input type="text" class="custom-edit form-control input-xs" data-pkt="${pkt || ''}" data-field="by_col" value="${value || ''}" style="width: 100px; height: 24px; padding: 2px 4px;">`;
					}
				}
			];

			const dt = new frappe.DataTable(`#${container_id}`, {
				columns: columns,
				data: datatable_rows,
				layout: 'fluid',
				serialNoColumn: false,
				checkboxColumn: false,
				cellHeight: 35,
				dynamicRowHeight: true
			});

			this.datatables.push(dt);
		};

		// 1. Render sequenced groups
		item_sequence.forEach(item_type => {
			const matched_key = Array.from(item_groups.keys()).find(k => k.toLowerCase() === item_type.toLowerCase());
			if (!matched_key) return;

			const rows = item_groups.get(matched_key);
			if (!rows || rows.length === 0) return;

			rendered_groups.add(matched_key);
			render_group(item_type, rows);
		});

		// 2. Render any remaining groups
		item_groups.forEach((rows, type) => {
			if (!rendered_groups.has(type) && type.toLowerCase() !== 'pipe') {
				render_group(type, rows);
			}
		});
	}
}
