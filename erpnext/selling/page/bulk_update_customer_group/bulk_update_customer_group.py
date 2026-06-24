import frappe
from frappe.utils.csvutils import read_csv_content
from frappe.utils.xlsxutils import read_xlsx_file_from_attached_file

@frappe.whitelist()
def process_update(file_url):
    user = frappe.session.user
    # Enqueue the background task
    frappe.enqueue(
        'erpnext.selling.page.bulk_update_customer_group.bulk_update_customer_group.run_update_background',
        file_url=file_url,
        user=user,
        queue='long',
        timeout=1500
    )
    return "Update job has been queued in the background."

def run_update_background(file_url, user):
    try:
        file_doc = frappe.get_doc("File", {"file_url": file_url})
        
        if file_url.endswith(".csv"):
            file_content = file_doc.get_content()
            rows = read_csv_content(file_content)
        elif file_url.endswith(".xlsx"):
            rows = read_xlsx_file_from_attached_file(file_url=file_url)
        else:
            frappe.publish_realtime('bulk_update_customer_group_error', message="Unsupported file format.", user=user)
            return
            
        if not rows:
            frappe.publish_realtime('bulk_update_customer_group_error', message="The uploaded file is empty.", user=user)
            return
            
        # Ensure root customer group exists
        root_group = "All Customer Groups"
        if not frappe.db.exists("Customer Group", root_group):
            # If the root doesn't exist, we fall back to just setting it to None or creating it
            pass
            
        # Assuming first row is header
        for i, row in enumerate(rows):
            if i == 0:
                continue
                
            if len(row) < 2:
                continue
                
            customer_name = str(row[0]).strip() if row[0] else ""
            customer_group_name = str(row[1]).strip() if row[1] else ""
            
            if not customer_name or not customer_group_name:
                continue
                
            try:
                group_created_msg = ""
                if not frappe.db.exists("Customer Group", customer_group_name):
                    # Create the customer group
                    new_group = frappe.new_doc("Customer Group")
                    new_group.customer_group_name = customer_group_name
                    if frappe.db.exists("Customer Group", root_group):
                        new_group.parent_customer_group = root_group
                    new_group.is_group = 0
                    new_group.insert(ignore_permissions=True)
                    frappe.db.commit()
                    group_created_msg = " (Customer Group created)"
                    
                customer_created_msg = ""
                if not frappe.db.exists("Customer", customer_name):
                    new_customer = frappe.new_doc("Customer")
                    new_customer.customer_name = customer_name
                    new_customer.customer_type = "Company" # Default type
                    new_customer.customer_group = customer_group_name
                    # Bypass Frappe's strict name validation between Customer and Customer Group
                    new_customer.validate_name_with_customer_group = lambda *args, **kwargs: None
                    new_customer.insert(ignore_permissions=True)
                    frappe.db.commit()
                    customer_created_msg = " (Customer created)"
                    customer_doc = new_customer
                else:
                    customer_doc = frappe.get_doc("Customer", customer_name)
                    
                # If it already existed, we still need to update the group if it changed
                if not customer_created_msg:
                    customer_doc.customer_group = customer_group_name
                    customer_doc.flags.ignore_permissions = True
                    # Bypass Frappe's strict name validation between Customer and Customer Group
                    customer_doc.validate_name_with_customer_group = lambda *args, **kwargs: None
                    customer_doc.save()
                    frappe.db.commit()
                
                # Notify frontend of success
                msg_suffix = customer_created_msg or group_created_msg
                if customer_created_msg and group_created_msg:
                    msg_suffix = " (Customer and Group created)"
                    
                frappe.publish_realtime(
                    'bulk_update_customer_group_progress',
                    message={
                        "customer": customer_name,
                        "customer_group": customer_group_name,
                        "status": "Success",
                        "message": f"Updated successfully{msg_suffix}."
                    },
                    user=user
                )
            except Exception as e:
                frappe.db.rollback()
                # Notify frontend of failure
                frappe.publish_realtime(
                    'bulk_update_customer_group_progress',
                    message={
                        "customer": customer_name,
                        "customer_group": customer_group_name,
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
        frappe.publish_realtime('bulk_update_customer_group_complete', message="All rows processed.", user=user)
        
    except Exception as e:
        frappe.publish_realtime('bulk_update_customer_group_error', message=f"An error occurred: {str(e)}", user=user)
