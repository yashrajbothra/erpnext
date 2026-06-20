def execute():
    import frappe
    if frappe.db.exists("Page", "ss-purchase-merge-sh"):
        p = frappe.get_doc("Page", "ss-purchase-merge-sh")
        if not p.roles:
            p.append("roles", {"role": "System Manager"})
            p.append("roles", {"role": "Accounts User"})
            p.append("roles", {"role": "Accounts Manager"})
            p.save(ignore_permissions=True)
            frappe.db.commit()
            print("Added roles to ss-purchase-merge-sh")
        else:
            print("Roles already exist:", [r.role for r in p.roles])
