import frappe

def run():
    script = """# ---------------- CUSTOMER/SUPPLIER FROM custom_party_custom ----------------
frappe.log_error(f"Doc: {doc.name}, Parent Custom Party: {doc.get('custom_party_custom')}, Row Custom Parties: {[r.get('custom_party_custom') for r in doc.accounts]}", "JE Add Party Debug")

def get_or_create_customer(c_name):
    if not c_name: return None
    c_name = str(c_name).strip()
    
    existing = frappe.db.get_value('Customer', {'customer_name': c_name}, 'name') or \
               frappe.db.get_value('Customer', c_name, 'name')
               
    if not existing:
        try:
            new_cust = frappe.get_doc({
                'doctype': 'Customer',
                'customer_name': c_name,
                'customer_group': 'Commercial',
                'customer_type': 'Company',
                'territory': 'All Territories'
            })
            new_cust.insert(ignore_permissions=True)
            return new_cust.name
        except Exception as e:
            frappe.log_error(f'Customer creation failed for {c_name}: {str(e)}', 'Journal Entry Add Party Script')
            return None
    return existing

def get_or_create_supplier(s_name):
    if not s_name: return None
    s_name = str(s_name).strip()
    
    existing = frappe.db.get_value('Supplier', {'supplier_name': s_name}, 'name') or \
               frappe.db.get_value('Supplier', s_name, 'name')
               
    if not existing:
        try:
            new_supp = frappe.get_doc({
                'doctype': 'Supplier',
                'supplier_name': s_name,
                'supplier_group': 'All Supplier Groups',
                'supplier_type': 'Company'
            })
            new_supp.insert(ignore_permissions=True)
            return new_supp.name
        except Exception as e:
            frappe.log_error(f'Supplier creation failed for {s_name}: {str(e)}', 'Journal Entry Add Party Script')
            return None
    return existing

parent_party_name = doc.get('custom_party_custom')

for row in doc.accounts:
    if not row.account: continue
    
    party_name = row.get('custom_party_custom') or parent_party_name
    if not party_name: continue
    
    acc_type = frappe.db.get_value('Account', row.account, 'account_type')
    if acc_type not in ('Receivable', 'Payable'):
        # Only clear if we were trying to auto-set a party from custom_party_custom
        # but do NOT clear if the user manually selected an Employee or something valid.
        if not row.party:
            row.party_type = None
            row.party = None
        continue
        
    is_supplier = (acc_type == 'Payable')
            
    if is_supplier:
        supp_id = get_or_create_supplier(party_name)
        if supp_id:
            row.party_type = 'Supplier'
            row.party = supp_id
    else:
        cust_id = get_or_create_customer(party_name)
        if cust_id:
            row.party_type = 'Customer'
            row.party = cust_id
"""
    frappe.db.set_value('Server Script', 'Journal Entry Add Party', 'script', script)
    frappe.db.commit()
    print("Script updated successfully.")
