import frappe

def update_server_script():
    script_name = "Auto Create Accounts for Payment Entry"
    if not frappe.db.exists("Server Script", script_name):
        doc = frappe.new_doc("Server Script")
        doc.name = script_name
        doc.script_type = "DocType Event"
        doc.reference_doctype = "Payment Entry"
        doc.doctype_event = "Before Validate"
    else:
        doc = frappe.get_doc("Server Script", script_name)

    script_code = """
import re

def fix_account_name(account_name, company):
    if not account_name:
        return account_name
    
    company_abbr = frappe.get_cached_value('Company', company, 'abbr') or company
    # Replace the wrong company suffix (like - SM54) with the correct one
    # This regex looks for - <ANY WORD> at the end of the string
    fixed_name = re.sub(r' - [A-Za-z0-9]+$', f' - {company_abbr}', str(account_name).strip())
    return fixed_name

def ensure_account(account_name, company):
    if not account_name or not company:
        return
    if frappe.db.exists("Account", account_name):
        return
    
    # Try to find a suitable parent account
    parent = frappe.db.get_value("Account", {"company": company, "is_group": 1, "account_type": "Expense Account"})
    if not parent:
        parent = frappe.db.get_value("Account", {"company": company, "is_group": 1, "account_type": "Asset"})
    if not parent:
        parent = frappe.db.get_value("Account", {"company": company, "is_group": 1})
        
    if parent:
        acc_doc = frappe.new_doc("Account")
        company_abbr = frappe.get_cached_value('Company', company, 'abbr') or company
        
        base_account_name = account_name
        if base_account_name.endswith(f" - {company_abbr}"):
            base_account_name = base_account_name.replace(f" - {company_abbr}", "").strip()
            
        acc_doc.account_name = base_account_name
        acc_doc.company = company
        acc_doc.parent_account = parent
        acc_doc.is_group = 0
        try:
            acc_doc.insert(ignore_permissions=True)
            frappe.db.commit()
        except Exception as e:
            pass

if doc.company:
    if doc.paid_from:
        doc.paid_from = fix_account_name(doc.paid_from, doc.company)
        ensure_account(doc.paid_from, doc.company)
    if doc.paid_to:
        doc.paid_to = fix_account_name(doc.paid_to, doc.company)
        ensure_account(doc.paid_to, doc.company)
"""
    doc.script = script_code
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    print("Server Script updated successfully.")

def run():
    update_server_script()
