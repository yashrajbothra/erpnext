import frappe
def run():
    print(frappe.get_all("Account", filters={"company": "SM54", "is_group": 1}, fields=["name", "account_name"]))
