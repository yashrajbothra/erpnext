import re

with open("payment_planning.py", "r") as f:
    content = f.read()

# Make sure supplier_group filter is fixed (it should have been fixed in the previous script)
content = content.replace("filters.get('supplier_group')", "filters.get('customer_group')")

# Now inject the PUR formatting logic
target = """            for i, r in enumerate(inv_rows):
                if i > 0:
                    r.bill_amt = ""
                data.append(r)"""

replacement = """            for i, r in enumerate(inv_rows):
                if i > 0:
                    r.bill_amt = ""
                
                if r.invoice_doctype == 'Purchase Invoice':
                    if not r.inv_no or str(r.inv_no).strip() == '':
                        r.inv_no = f'<a href="/app/purchase-invoice/{r.actual_inv_no}" style="color:var(--primary)">PUR</a>'
                    elif '<a ' not in str(r.inv_no):
                        r.inv_no = f'<a href="/app/purchase-invoice/{r.actual_inv_no}" style="color:var(--primary)">{r.inv_no}</a>'
                
                data.append(r)"""

content = content.replace(target, replacement)

with open("payment_planning.py", "w") as f:
    f.write(content)
