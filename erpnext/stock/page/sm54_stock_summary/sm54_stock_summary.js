frappe.pages['sm54_stock_summary'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'SM54 Stock Summary',
		single_column: true
	});

	new SM54StockSummary(page);
}

class SM54StockSummary {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.init();
	}

	init() {
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
			default: frappe.defaults.get_user_default('company'),
			change: () => this.refresh()
		});

		this.page.add_field({
			fieldname: 'warehouse',
			label: __('Warehouse'),
			fieldtype: 'Link',
			options: 'Warehouse',
			change: () => this.refresh()
		});
	}

	make_layout() {
		this.wrapper.html(`
			<div class="sm54-summary-container">
				<div class="summary-kpi-cards">
					<div class="kpi-card total-stock-card">
						<div class="kpi-icon"><i class="fa fa-cubes"></i></div>
						<div class="kpi-details">
							<span class="kpi-title">TOTAL STOCK</span>
							<span class="kpi-value" id="kpi-total-weight">0.00</span>
							<span class="kpi-unit">Kg</span>
						</div>
					</div>
					<div class="kpi-card nb-stock-card">
						<div class="kpi-icon"><i class="fa fa-arrows-h"></i></div>
						<div class="kpi-details">
							<span class="kpi-title">NB WISE STOCK</span>
							<span class="kpi-value" id="kpi-nb-weight">0.00</span>
							<span class="kpi-unit">Kg</span>
						</div>
					</div>
					<div class="kpi-card od-stock-card">
						<div class="kpi-icon"><i class="fa fa-circle-o"></i></div>
						<div class="kpi-details">
							<span class="kpi-title">OD WISE STOCK</span>
							<span class="kpi-value" id="kpi-od-weight">0.00</span>
							<span class="kpi-unit">Kg</span>
						</div>
					</div>
				</div>

				<div class="summary-tables-wrapper">
					<div class="section-title">NB Wise Stock Summary</div>
					<div class="table-card nb-table-card">
						<div class="table-responsive" id="nb-table-container">
							<!-- Render Table 1 -->
						</div>
					</div>

					<div class="section-title">OD Wise Stock Summary</div>
					<div class="table-card od-table-card">
						<div class="table-responsive" id="od-table-container">
							<!-- Render Table 2 -->
						</div>
					</div>
				</div>
			</div>
		`);
	}

	refresh() {
		const filters = {
			company: this.page.fields_dict.company.get_value(),
			warehouse: this.page.fields_dict.warehouse.get_value()
		};

		frappe.call({
			method: 'erpnext.stock.page.sm54_stock_summary.sm54_stock_summary.get_summary_data',
			args: { filters: filters },
			callback: (r) => {
				if (r.message) {
					this.render(r.message);
				}
			}
		});
	}

	render(res) {
		const { nb_data, od_data, stats } = res;

		// Update KPI stats
		this.wrapper.find('#kpi-total-weight').text(frappe.format(stats.total_weight, { fieldtype: 'Float' }, { only_value: true }) || "0.00");
		this.wrapper.find('#kpi-nb-weight').text(frappe.format(stats.total_nb_weight, { fieldtype: 'Float' }, { only_value: true }) || "0.00");
		this.wrapper.find('#kpi-od-weight').text(frappe.format(stats.total_od_weight, { fieldtype: 'Float' }, { only_value: true }) || "0.00");

		// NB Wise table
		const $nb_container = this.wrapper.find('#nb-table-container');
		if (!nb_data || nb_data.length === 0) {
			$nb_container.html('<div class="no-records-msg">No NB Wise records found</div>');
		} else {
			let nb_rows = '';
			nb_data.forEach(row => {
				nb_rows += `
					<tr>
						<td><span class="badge size-badge">${row.nb || ''}</span></td>
						<td>${row.od || ''}</td>
						<td><span class="grade-text">${row.grade || ''}</span></td>
						<td>${row.thik || ''}</td>
						<td>${row.finish || ''}</td>
						<td class="weight-col">${frappe.format(row.weight, { fieldtype: 'Float' }, { only_value: true })}</td>
					</tr>
				`;
			});

			$nb_container.html(`
				<table class="sm54-summary-table">
					<thead>
						<tr>
							<th>NB SIZE</th>
							<th>OD (mm)</th>
							<th>GRADE</th>
							<th>THICKNESS (mm)</th>
							<th>FINISH</th>
							<th class="weight-col">WT (Kg)</th>
						</tr>
					</thead>
					<tbody>
						${nb_rows}
						<tr class="total-row">
							<td colspan="5">TOTAL NB WISE</td>
							<td class="weight-col">${frappe.format(stats.total_nb_weight, { fieldtype: 'Float' }, { only_value: true })}</td>
						</tr>
					</tbody>
				</table>
			`);
		}

		// OD Wise table
		const $od_container = this.wrapper.find('#od-table-container');
		if (!od_data || od_data.length === 0) {
			$od_container.html('<div class="no-records-msg">No OD Wise records found</div>');
		} else {
			let od_rows = '';
			od_data.forEach(row => {
				od_rows += `
					<tr>
						<td><span class="badge od-size-badge">${row.od || ''}</span></td>
						<td><span class="grade-text">${row.grade || ''}</span></td>
						<td>${row.thik || ''}</td>
						<td>${row.finish || ''}</td>
						<td class="weight-col">${frappe.format(row.weight, { fieldtype: 'Float' }, { only_value: true })}</td>
					</tr>
				`;
			});

			$od_container.html(`
				<table class="sm54-summary-table">
					<thead>
						<tr>
							<th>OD SIZE</th>
							<th>GRADE</th>
							<th>THICKNESS (mm)</th>
							<th>FINISH</th>
							<th class="weight-col">WT (Kg)</th>
						</tr>
					</thead>
					<tbody>
						${od_rows}
						<tr class="total-row">
							<td colspan="4">TOTAL OD WISE</td>
							<td class="weight-col">${frappe.format(stats.total_od_weight, { fieldtype: 'Float' }, { only_value: true })}</td>
						</tr>
					</tbody>
				</table>
			`);
		}
	}
}
