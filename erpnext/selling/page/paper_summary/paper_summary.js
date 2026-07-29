frappe.pages['paper-summary'].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: 'Paper Summary',
        single_column: true
    });

    let fixed_account = 'ADV AC - SM55';
    let company = frappe.defaults.get_default('company') || frappe.boot.sysdefaults.company;
    if (company) {
        frappe.db.get_value('Company', company, 'abbr').then(r => {
            if (r && r.message && r.message.abbr) {
                fixed_account = `ADV AC - ${r.message.abbr}`;
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
        default: '2026-03-31'
    });

    page.add_field({
        fieldname: 'interest_rate',
        label: __('Interest Rate (%)'),
        fieldtype: 'Float',
        default: 0.9
    });

    page.add_field({
        fieldname: 'use_entry_date',
        label: __('As per Entry Date'),
        fieldtype: 'Check',
        default: 1
    });

    page.add_field({
        fieldname: 'merge_similar',
        label: __('Merge Similar'),
        fieldtype: 'Check',
        default: 0
    });

    page.add_field({
        fieldname: 'hide_zero_balances',
        label: __('Hide Zero Balances'),
        fieldtype: 'Check',
        default: 0
    });

    page.set_primary_action(__('Load Summary'), () => {
        load_summary();
    });

    let current_data = null;

    page.add_menu_item(__('Export to Excel'), () => {
        export_to_excel();
    });

    page.add_menu_item(__('Export to PDF'), () => {
        export_to_pdf();
    });

    const $summary_container = $(`
        <div class="summary-container" style="margin: 15px;">
            <div id="summary-body">
                <div class="text-muted text-center" style="margin-top: 50px;">
                    ${__("Please select filters and click on Load Summary")}
                </div>
            </div>
        </div>
    `).appendTo(page.main);

    function load_summary() {
        let filter_account = page.fields_dict.filter_account.get_value();
        let party = page.fields_dict.party.get_value();
        let from_date = page.fields_dict.from_date.get_value();
        let to_date = page.fields_dict.to_date.get_value();
        let cutoff_date = page.fields_dict.cutoff_date.get_value();
        let interest_rate = page.fields_dict.interest_rate.get_value() || 0;
        let use_entry_date = page.fields_dict.use_entry_date.get_value() ? 1 : 0;
        let merge_similar = page.fields_dict.merge_similar.get_value() ? 1 : 0;
        let hide_zero_balances = page.fields_dict.hide_zero_balances.get_value() ? 1 : 0;

        if (!cutoff_date) {
            frappe.msgprint(__('Please select a Cutoff Date'));
            return;
        }

        let account, counterpart_filter;
        if (filter_account && filter_account.length > 0) {
            account = filter_account;
            counterpart_filter = null;
        } else {
            account = fixed_account;
            counterpart_filter = null;
        }

        frappe.call({
            method: "erpnext.api.get_paper_summary_data",
            args: {
                account: account,
                party: party,
                filter_account: counterpart_filter,
                from_date: from_date,
                to_date: to_date,
                cutoff_date: cutoff_date,
                interest_rate: interest_rate,
                use_entry_date: use_entry_date
            },
            callback: function (r) {
                if (r.message) {
                    current_data = r.message;
                    if (merge_similar) {
                        current_data = merge_similar_rows(current_data);
                    }
                    if (hide_zero_balances) {
                        current_data = current_data.filter(row => Math.abs(row.closing_balance) >= 0.01);
                    }
                    render_summary(current_data);
                }
            }
        });
    }

    function render_summary(data) {
        if (!data || data.length === 0) {
            $('#summary-body').html(`
                <div class="text-center text-muted" style="padding: 30px;">
                    ${__("No data found for the selected criteria.")}
                </div>
            `);
            return;
        }

        let total_ob = 0;
        let total_dr = 0;
        let total_cr = 0;
        let total_dr_int = 0;
        let total_cr_int = 0;
        let total_cl = 0;

        let rows_html = data.map(row => {
            total_ob += row.opening_balance;
            total_dr += row.total_debit;
            total_cr += row.total_credit;
            total_dr_int += row.total_debit_interest;
            total_cr_int += row.total_credit_interest;
            total_cl += row.closing_balance;

            let ob_color = row.opening_balance >= 0 ? '#2ecc71' : '#e74c3c';
            let cl_color = row.closing_balance >= 0 ? '#2ecc71' : '#e74c3c';

            return `
                <tr style="border-bottom: 1px solid #d1d8dd;">
                    <td style="padding: 10px;">${row.party}</td>
                    <td style="padding: 10px; text-align: right; color: ${ob_color};">${format_currency(Math.abs(row.opening_balance), frappe.boot.sysdefaults.currency)} ${row.opening_balance >= 0 ? 'Dr' : 'Cr'}</td>
                    <td style="padding: 10px; text-align: right; color: #e74c3c;">${format_currency(row.total_debit, frappe.boot.sysdefaults.currency)}</td>
                    <td style="padding: 10px; text-align: right; color: #2ecc71;">${format_currency(row.total_credit, frappe.boot.sysdefaults.currency)}</td>
                    <td style="padding: 10px; text-align: right; color: #e74c3c; font-size: 11px;">${format_currency(row.total_debit_interest, frappe.boot.sysdefaults.currency)}</td>
                    <td style="padding: 10px; text-align: right; color: #2ecc71; font-size: 11px;">${format_currency(row.total_credit_interest, frappe.boot.sysdefaults.currency)}</td>
                    <td style="padding: 10px; text-align: right; font-weight: bold; color: ${cl_color};">${format_currency(Math.abs(row.closing_balance), frappe.boot.sysdefaults.currency)} ${row.closing_balance >= 0 ? 'Dr' : 'Cr'}</td>
                </tr>
            `;
        }).join('');

        let total_ob_color = total_ob >= 0 ? '#2ecc71' : '#e74c3c';
        let total_cl_color = total_cl >= 0 ? '#2ecc71' : '#e74c3c';

        let html = `
            <div style="background-color: #ffffff; border: 1px solid #d1d8dd; border-radius: 4px; overflow-x: auto;">
                <table style="width: 100%; border-collapse: collapse; min-width: 800px;">
                    <thead>
                        <tr style="background-color: #f8f9fa; border-bottom: 1px solid #d1d8dd; text-align: left;">
                            <th style="padding: 12px 10px;">${__('Customer')}</th>
                            <th style="padding: 12px 10px; text-align: right;">${__('Opening Bal')}</th>
                            <th style="padding: 12px 10px; text-align: right;">${__('Debit')}</th>
                            <th style="padding: 12px 10px; text-align: right;">${__('Credit')}</th>
                            <th style="padding: 12px 10px; text-align: right; font-size: 11px;">${__('Dr. Interest')}</th>
                            <th style="padding: 12px 10px; text-align: right; font-size: 11px;">${__('Cr. Interest')}</th>
                            <th style="padding: 12px 10px; text-align: right;">${__('Closing Bal')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows_html}
                    </tbody>
                    <tfoot>
                        <tr style="background-color: #f8f9fa; border-top: 2px solid #d1d8dd; font-weight: bold;">
                            <td style="padding: 12px 10px;">${__('Total')}</td>
                            <td style="padding: 12px 10px; text-align: right; color: ${total_ob_color};">${format_currency(Math.abs(total_ob), frappe.boot.sysdefaults.currency)} ${total_ob >= 0 ? 'Dr' : 'Cr'}</td>
                            <td style="padding: 12px 10px; text-align: right; color: #e74c3c;">${format_currency(total_dr, frappe.boot.sysdefaults.currency)}</td>
                            <td style="padding: 12px 10px; text-align: right; color: #2ecc71;">${format_currency(total_cr, frappe.boot.sysdefaults.currency)}</td>
                            <td style="padding: 12px 10px; text-align: right; color: #e74c3c; font-size: 11px;">${format_currency(total_dr_int, frappe.boot.sysdefaults.currency)}</td>
                            <td style="padding: 12px 10px; text-align: right; color: #2ecc71; font-size: 11px;">${format_currency(total_cr_int, frappe.boot.sysdefaults.currency)}</td>
                            <td style="padding: 12px 10px; text-align: right; color: ${total_cl_color};">${format_currency(Math.abs(total_cl), frappe.boot.sysdefaults.currency)} ${total_cl >= 0 ? 'Dr' : 'Cr'}</td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        `;

        $('#summary-body').html(html);
    }

    function export_to_excel() {
        if (!current_data) {
            frappe.msgprint(__('Please load the summary first'));
            return;
        }

        let export_data = [
            ["Customer", "Opening Balance", "Debit", "Credit", "Dr. Interest", "Cr. Interest", "Closing Balance"]
        ];

        let total_ob = 0;
        let total_dr = 0;
        let total_cr = 0;
        let total_dr_int = 0;
        let total_cr_int = 0;
        let total_cl = 0;

        current_data.forEach(row => {
            total_ob += flt(row.opening_balance);
            total_dr += flt(row.total_debit);
            total_cr += flt(row.total_credit);
            total_dr_int += flt(row.total_debit_interest);
            total_cr_int += flt(row.total_credit_interest);
            total_cl += flt(row.closing_balance);

            export_data.push([
                row.party,
                flt(row.opening_balance, 2),
                flt(row.total_debit, 2),
                flt(row.total_credit, 2),
                flt(row.total_debit_interest, 2),
                flt(row.total_credit_interest, 2),
                flt(row.closing_balance, 2)
            ]);
        });

        export_data.push([
            "Total",
            flt(total_ob, 2),
            flt(total_dr, 2),
            flt(total_cr, 2),
            flt(total_dr_int, 2),
            flt(total_cr_int, 2),
            flt(total_cl, 2)
        ]);

        frappe.tools.downloadify(export_data, null, `Paper_Summary`);
    }

    function export_to_pdf() {
        if (!current_data) {
            frappe.msgprint(__('Please load the summary first'));
            return;
        }

        let account = fixed_account;
        let cutoff_date = page.fields_dict.cutoff_date.get_value();
        let interest_rate = page.fields_dict.interest_rate.get_value() || 0;

        let header_html = `
            <h2 style="text-align: center; font-family: sans-serif;">Paper Summary</h2>
            <div style="text-align: center; font-family: sans-serif; font-size: 14px; margin-bottom: 20px; color: #555;">
                ${__('Account')}: <strong>${account}</strong> | ${__('Interest Rate')}: <strong>${interest_rate}%</strong> | ${__('Cutoff Date')}: <strong>${frappe.datetime.str_to_user(cutoff_date)}</strong>
            </div>
        `;
        let content_html = $('#summary-body').html();

        frappe.render_pdf(header_html + content_html, {
            orientation: 'Landscape',
            report_name: `Paper_Summary`
        });
    }

    function merge_similar_rows(data) {
        let merged_data = [];
        let used_indices = new Set();

        for (let i = 0; i < data.length; i++) {
            if (used_indices.has(i)) continue;

            let row1 = data[i];
            let matched = false;

            for (let j = i + 1; j < data.length; j++) {
                if (used_indices.has(j)) continue;
                let row2 = data[j];

                if (Math.abs(row1.closing_balance) === Math.abs(row2.closing_balance) &&
                    Math.abs(row1.closing_balance) > 0 &&
                    (row1.closing_balance + row2.closing_balance === 0)) {

                    let merged_row = {
                        party: row1.party + ' & ' + row2.party,
                        opening_balance: row1.opening_balance + row2.opening_balance,
                        total_debit: row1.total_debit + row2.total_debit,
                        total_credit: row1.total_credit + row2.total_credit,
                        total_debit_interest: row1.total_debit_interest + row2.total_debit_interest,
                        total_credit_interest: row1.total_credit_interest + row2.total_credit_interest,
                        closing_balance: row1.closing_balance + row2.closing_balance
                    };
                    merged_data.push(merged_row);
                    used_indices.add(i);
                    used_indices.add(j);
                    matched = true;
                    break;
                }
            }

            if (!matched) {
                merged_data.push(row1);
            }
        }
        return merged_data;
    }
};