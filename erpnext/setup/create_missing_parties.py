import re
import frappe


def run():
	# 1. Extract all party names that caused LinkValidationError
	logs = frappe.db.sql(
		"""
		SELECT exception
		FROM `tabData Import Log`
		WHERE data_import LIKE '%Journal Entry Import on 2026-06-20 17%'
		  AND success = 0
		""",
		as_list=True,
	)

	missing_names = set()
	for (exc,) in logs:
		if not exc:
			continue
		for line in exc.split("\n"):
			if line.startswith("frappe.exceptions.LinkValidationError:") or line.startswith("LinkValidationError:"):
				msg_part = line.split("LinkValidationError:", 1)[-1].strip()
				clean_msg = re.sub(r"^Could not find ", "", msg_part).strip()
				parts = re.split(r",\s*Row #\d+:\s*Party:\s*|,\s*Party:\s*", clean_msg)
				parts[0] = re.sub(r"^(?:Row #\d+:\s*)?Party:\s*", "", parts[0])
				for name in parts:
					name = name.strip()
					if name:
						missing_names.add(name)

	print(f"\nFound {len(missing_names)} unique missing party names:")
	for n in sorted(missing_names):
		print(f"  {n}")

	# 2. Create each as both Customer AND Supplier (if not already existing)
	created_customers = []
	created_suppliers = []
	skipped = []

	for party_name in sorted(missing_names):
		# Customer
		exists_cust = (
			frappe.db.get_value("Customer", {"customer_name": party_name}, "name")
			or frappe.db.get_value("Customer", party_name, "name")
		)
		if not exists_cust:
			try:
				doc = frappe.get_doc({
					"doctype": "Customer",
					"customer_name": party_name,
					"customer_group": "Commercial",
					"customer_type": "Company",
					"territory": "All Territories",
				})
				doc.insert(ignore_permissions=True)
				frappe.db.commit()
				created_customers.append(f"  + Customer: {doc.name}")
			except Exception as e:
				frappe.db.rollback()
				created_customers.append(f"  ERR Customer: {party_name} => {e}")
		else:
			skipped.append(f"  - Customer exists: {exists_cust}")

		# Supplier
		exists_supp = (
			frappe.db.get_value("Supplier", {"supplier_name": party_name}, "name")
			or frappe.db.get_value("Supplier", party_name, "name")
		)
		if not exists_supp:
			try:
				doc = frappe.get_doc({
					"doctype": "Supplier",
					"supplier_name": party_name,
					"supplier_group": "All Supplier Groups",
					"supplier_type": "Company",
				})
				doc.insert(ignore_permissions=True)
				frappe.db.commit()
				created_suppliers.append(f"  + Supplier: {doc.name}")
			except Exception as e:
				frappe.db.rollback()
				created_suppliers.append(f"  ERR Supplier: {party_name} => {e}")
		else:
			skipped.append(f"  - Supplier exists: {exists_supp}")

	print(f"\nCustomers created ({len(created_customers)}):")
	for line in created_customers:
		print(line)

	print(f"\nSuppliers created ({len(created_suppliers)}):")
	for line in created_suppliers:
		print(line)

	if skipped:
		print(f"\nAlready existing ({len(skipped)}):")
		for line in skipped:
			print(line)

	print("\nDone. You can now retry the Journal Entry import.")
