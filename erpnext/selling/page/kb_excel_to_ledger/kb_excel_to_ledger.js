frappe.pages['kb-excel-to-ledger'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'KB Excel to Ledger Converter',
		single_column: true
	});

	page.uploaded_file = null;

	$(wrapper).find('.layout-main-section').append(`
		<div class="converter-container" style="padding: 20px; text-align: center;">
			<div id="file-uploader-section"></div>
			<div id="error-display-section" style="margin-top: 30px; text-align: left; display: none;">
				<h5 style="color: var(--error-color);">Conversion Errors</h5>
				<table class="table table-bordered" style="background: var(--bg-color); font-size: 13px;">
					<thead>
						<tr>
							<th style="width: 80px;">Row</th>
							<th style="width: 100px;">Column</th>
							<th>Message</th>
						</tr>
					</thead>
					<tbody id="error-table-body"></tbody>
				</table>
			</div>
		</div>
	`);

	page.set_primary_action('Convert', () => {
		if (!page.uploaded_file) {
			frappe.msgprint(__('Please upload an Excel file first.'));
			return;
		}
		
		let file = page.uploaded_file;
		let $error_section = $(wrapper).find('#error-display-section');
		let $error_body = $(wrapper).find('#error-table-body');
		
		$error_section.hide();
		$error_body.empty();
		
		frappe.call({
			method: 'erpnext.selling.page.kb_excel_to_ledger.kb_excel_to_ledger.convert_excel',
			args: {
				file_url: file.file_url
			},
			freeze: true,
			callback: function(r) {
				if (r.message && r.message.errors) {
					r.message.errors.forEach(err => {
						$error_body.append(`
							<tr>
								<td>${err.row}</td>
								<td>${err.col}</td>
								<td>${err.message}</td>
							</tr>
						`);
					});
					$error_section.slideDown();
					frappe.msgprint({
						title: __('Conversion Incomplete'),
						message: __('Found ' + r.message.errors.length + ' errors in the file. Please check the error table below.'),
						indicator: 'orange'
					});
				} else if (r.message && r.message.file_url) {
					window.open(r.message.file_url);
					frappe.show_alert({message: __('Excel Converted and Download Started'), indicator: 'green'});
				}
			}
		});
	});

	page.file_uploader = new frappe.ui.FileUploader({
		wrapper: $(wrapper).find('#file-uploader-section'),
		make_attachments_public: true,
		on_success: (file) => {
			page.uploaded_file = file;
			frappe.show_alert({message: __('File uploaded successfully'), indicator: 'green'});
		}
	});
}
