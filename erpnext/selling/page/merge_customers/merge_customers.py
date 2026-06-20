import frappe
from frappe.utils.file_manager import get_file
from frappe.utils.csvutils import read_csv_content
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

@frappe.whitelist()
def process_merge(file_url):
    user = frappe.session.user
    # Enqueue the background task
    frappe.enqueue(
        'erpnext.selling.page.merge_customers.merge_customers.run_merge_background',
        file_url=file_url,
        user=user,
        queue='long',
        timeout=1500
    )
    return "Merge job has been queued in the background."

def run_merge_background(file_url, user):
    try:
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        
        if file_url.endswith(".csv"):
            file_content = file_doc.get_content()
            rows = read_csv_content(file_content)
        elif file_url.endswith(".xlsx"):
            rows = read_xlsx_file_from_attached_file(file_url=file_url)
        else:
            frappe.publish_realtime('merge_customers_error', message="Unsupported file format.", user=user)
            return
            
        if not rows:
            frappe.publish_realtime('merge_customers_error', message="The uploaded file is empty.", user=user)
            return
            
        # Assuming first row is header
        total_rows = len(rows) - 1
        
        for i, row in enumerate(rows):
            if i == 0:
                continue
                
            if len(row) < 2:
                continue
                
            old_name = str(row[0]).strip() if row[0] else ""
            new_name = str(row[1]).strip() if row[1] else ""
            
            if not old_name or not new_name:
                continue
                
            try:
                if not frappe.db.exists("Customer", new_name):
                    # If the target customer doesn't exist, we can simply rename the old one
                    # which effectively "creates" the new customer and moves everything over.
                    frappe.rename_doc("Customer", old_name, new_name, merge=False)
                    message = "Renamed successfully (new customer created)."
                else:
                    # If it exists, we merge the old one into the new one.
                    frappe.rename_doc("Customer", old_name, new_name, merge=True)
                    message = "Merged successfully."
                    
                frappe.db.commit() # Commit after each successful merge
                
                # Notify frontend of success
                frappe.publish_realtime(
                    'merge_customers_progress',
                    message={
                        "old_name": old_name,
                        "new_name": new_name,
                        "status": "Success",
                        "message": message
                    },
                    user=user
                )
            except Exception as e:
                frappe.db.rollback()
                # Notify frontend of failure
                frappe.publish_realtime(
                    'merge_customers_progress',
                    message={
                        "old_name": old_name,
                        "new_name": new_name,
                        "status": "Failed",
                        "message": str(e)
                    },
                    user=user
                )
                
        # Clean up the uploaded file to save space
        try:
            file_doc.delete()
        except Exception:
            pass
            
        # Notify completion
        frappe.publish_realtime('merge_customers_complete', message="All rows processed.", user=user)
        
    except Exception as e:
        frappe.publish_realtime('merge_customers_error', message=f"An error occurred: {str(e)}", user=user)
