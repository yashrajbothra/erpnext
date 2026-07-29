import frappe
def run():
    for acc in ["LC - SM54", "ADV AC - SM54"]:
        print(f"{acc}: {frappe.db.exists('Account', acc)}")
