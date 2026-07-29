import frappe
from erpnext.accounts.report.payment_planning.payment_planning import get_data

frappe.init(site="sm55.aitoolx.io")
frappe.connect()

filters = frappe._dict({
    "customer_group": "MONTEX TUBES LLP",
    "hide_non_due": 1
})

data = get_data(filters)
print(f"Total rows: {len(data)}")
for d in data:
    if d.get("actual_inv_no") == "ACC-PINV-2026-01364":
        print("FOUND IT:", d.get('actual_inv_no'), "due_amt:", d.get('due_amt'), "remaining_balance (internal):", getattr(d, 'remaining_balance', None))

