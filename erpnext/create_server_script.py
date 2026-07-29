import frappe

def create_server_script():
    frappe.init(site="ss54.aitoolx.io", sites_path="sites")
    frappe.connect()

    script_name = "Auto Create Accounts for Payment Entry"
    if frappe.db.exists("Server Script", script_name):
        frappe.delete_doc("Server Script", script_name)

    script_code = """
def ensure_account(account_name, company):
    if not account_name or not company:
        return
    if frappe.db.exists("Account", account_name):
        return
    
    # Try to find a suitable parent account
    parent = frappe.db.get_value("Account", {"company": company, "is_group": 1, "account_type": "Expense Account"})
    if not parent:
        parent = frappe.db.get_value("Account", {"company": company, "is_group": 1})
        
    if parent:
        doc = frappe.new_doc("Account")
        
        company_abbr = frappe.get_cached_value('Company', company, 'abbr') or company
        base_account_name = account_name
        if base_account_name.endswith(f" - {company_abbr}"):
            base_account_name = base_account_name.replace(f" - {company_abbr}", "").strip()
            
        doc.account_name = base_account_name
        doc.company = company
        doc.parent_account = parent
        doc.is_group = 0
        doc.insert(ignore_permissions=True)
        frappe.db.commit()

if doc.paid_from:
    ensure_account(doc.paid_from, doc.company)
if doc.paid_to:
    ensure_account(doc.paid_to, doc.company)
"""

    doc = frappe.new_doc("Server Script")
    doc.name = script_name
    doc.script_type = "DocType Event"
    doc.reference_doctype = "Payment Entry"
    doc.doctype_event = "Before Validate"
    doc.script = script_code
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print("Server Script created successfully.")

if __name__ == "__main__":
    create_server_script()
