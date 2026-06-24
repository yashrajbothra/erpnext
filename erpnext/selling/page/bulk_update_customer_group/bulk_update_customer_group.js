frappe.pages['bulk-update-customer-group'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Bulk Update Customer Group',
		single_column: true
	});

    page.set_indicator('Ready', 'blue');

    let body = $(`
        <div class="margin-top">
            <div class="text-muted margin-bottom">
                Upload a CSV or Excel file to bulk update Customer Groups. <br>
                The file must have the first column as the <b>Customer</b> (Name/ID) and the second column as the <b>Customer Group</b>.<br>
                If the specified Customer Group does not exist, it will be automatically created under "All Customer Groups".
            </div>
            <div id="upload-area" class="margin-bottom">
                <button class="btn btn-primary btn-sm" id="btn-upload">Upload File</button>
            </div>
            <div id="update-log" style="display: none; margin-top: 30px;">
                <h4>Update Results <small id="update-progress-text" class="text-muted"></small></h4>
                <div class="table-responsive">
                    <table class="table table-bordered table-hover">
                        <thead>
                            <tr>
                                <th>Customer</th>
                                <th>Customer Group</th>
                                <th>Status</th>
                                <th>Message</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>
    `).appendTo(page.main);

    // Setup realtime event listeners
    frappe.realtime.on('bulk_update_customer_group_progress', function(log) {
        let tbody = body.find('#update-log tbody');
        let status_class = log.status === 'Success' ? 'text-success' : 'text-danger';
        tbody.append(`
            <tr>
                <td>${frappe.utils.escape_html(log.customer)}</td>
                <td>${frappe.utils.escape_html(log.customer_group)}</td>
                <td class="${status_class}"><b>${log.status}</b></td>
                <td>${frappe.utils.escape_html(log.message || '')}</td>
            </tr>
        `);
    });

    frappe.realtime.on('bulk_update_customer_group_complete', function(data) {
        page.set_indicator('Completed', 'green');
        body.find('#update-progress-text').text('(Completed)');
        frappe.show_alert({message: __('Customer group update completed.'), indicator: 'green'});
    });

    frappe.realtime.on('bulk_update_customer_group_error', function(data) {
        page.set_indicator('Error', 'red');
        body.find('#update-progress-text').text('(Error)');
        frappe.msgprint({
            title: __('Error'),
            indicator: 'red',
            message: data.message || data
        });
    });

    body.find('#btn-upload').on('click', () => {
        new frappe.ui.FileUploader({
            allow_multiple: false,
            on_success: (file_doc) => {
                let file_url = file_doc.file_url;
                page.set_indicator('Queuing job...', 'orange');
                
                // Clear previous logs
                body.find('#update-log tbody').empty();
                body.find('#update-log').show();
                body.find('#update-progress-text').text('(Processing...)');

                frappe.call({
                    method: 'erpnext.selling.page.bulk_update_customer_group.bulk_update_customer_group.process_update',
                    args: {
                        file_url: file_url
                    },
                    callback: function(r) {
                        if(r.message) {
                            page.set_indicator('Processing in background...', 'orange');
                            frappe.show_alert({message: __('Update job added to background queue. Please wait...'), indicator: 'blue'});
                        }
                    },
                    error: function(r) {
                        page.set_indicator('Error', 'red');
                    }
                });
            }
        });
    });
}
