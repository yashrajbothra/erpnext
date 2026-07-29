import re

with open("payment_planning.py", "r") as f:
    content = f.read()

# 1. Remove the line that disables fetch_suppliers when customer_group is selected
content = content.replace('        if filters.get("customer_group"):\n            fetch_suppliers = False\n', '')

# 2. Map customer_group to supplier_group for purchase invoices
content = content.replace('filters.get("supplier_group")', 'filters.get("customer_group")')

with open("payment_planning.py", "w") as f:
    f.write(content)

