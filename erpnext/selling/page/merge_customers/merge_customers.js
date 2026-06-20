frappe.pages['merge-customers'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Merge Customers',
		single_column: true
	});

    page.set_indicator('Ready', 'blue');

    let body = $(`
        <div class="margin-top">
            <div class="text-muted margin-bottom">
                Upload a CSV or Excel file to bulk merge customers. The file must have the first column as the <b>Original Name</b> and the second column as the <b>New Name</b>.
            </div>
            <div id="upload-area" class="margin-bottom">
                <button class="btn btn-primary btn-sm" id="btn-upload">Upload File</button>
            </div>
            <div id="merge-log" style="display: none; margin-top: 30px;">
                <h4>Merge Results <small id="merge-progress-text" class="text-muted"></small></h4>
                <div class="table-responsive">
                    <table class="table table-bordered table-hover">
                        <thead>
                            <tr>
                                <th>Original Name</th>
                                <th>New Name</th>
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
    frappe.realtime.on('merge_customers_progress', function(log) {
        let tbody = body.find('#merge-log tbody');
        let status_class = log.status === 'Success' ? 'text-success' : 'text-danger';
        tbody.append(`
            <tr>
                <td>${frappe.utils.escape_html(log.old_name)}</td>
                <td>${frappe.utils.escape_html(log.new_name)}</td>
                <td class="${status_class}"><b>${log.status}</b></td>
                <td>${frappe.utils.escape_html(log.message || '')}</td>
            </tr>
        `);
    });

    frappe.realtime.on('merge_customers_complete', function(data) {
        page.set_indicator('Completed', 'green');
        body.find('#merge-progress-text').text('(Completed)');
        frappe.show_alert({message: __('Customer merge completed.'), indicator: 'green'});
    });

    frappe.realtime.on('merge_customers_error', function(data) {
        page.set_indicator('Error', 'red');
        body.find('#merge-progress-text').text('(Error)');
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
                body.find('#merge-log tbody').empty();
                body.find('#merge-log').show();
                body.find('#merge-progress-text').text('(Processing...)');

                frappe.call({
                    method: 'erpnext.selling.page.merge_customers.merge_customers.process_merge',
                    args: {
                        file_url: file_url
                    },
                    callback: function(r) {
                        if(r.message) {
                            page.set_indicator('Processing in background...', 'orange');
                            frappe.show_alert({message: __('Merge job added to background queue. Please wait...'), indicator: 'blue'});
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