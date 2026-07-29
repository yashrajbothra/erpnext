import re

with open("payment_planning.py", "r") as f:
    content = f.read()

content = content.replace("filters.get('supplier_group')", "filters.get('customer_group')")

with open("payment_planning.py", "w") as f:
    f.write(content)

