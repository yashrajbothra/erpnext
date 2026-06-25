# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""
Outstanding Summary Report
==========================
Columns
-------
Party Name     : Customer name
Out Bill       : Outstanding amount in Debtors account (receivable)
Out Discount   : Outstanding amount in Debtors Discount account
Paid Bill      : Total received / settled against Debtors
Paid Discount  : Total received / settled against Debtors Discount
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
    if not filters:
        filters = {}
    filters = frappe._dict(filters)
    columns = get_columns(filters)
    data = get_data(filters)
    return columns, data


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def get_columns(filters):
    columns = [
        {
            "label": _("Party"),
            "fieldname": "party",
            "fieldtype": "Dynamic Link",
            "options": "party_type",
            "width": 450,
        }
    ]
        
    columns.extend([
        {
            "label": _("Total Bill"),
            "fieldname": "total_bill",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 175,
        },
        {
            "label": _("Total Discount"),
            "fieldname": "total_discount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 175,
        },
        {
            "label": _("Total Outstanding"),
            "fieldname": "total_outstanding",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 200,
        },
        {
            "label": _("Currency"),
            "fieldname": "currency",
            "fieldtype": "Data",
            "width": 80,
            "hidden": 1,
        },
    ])
    return columns


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def get_data(filters):
    from erpnext.accounts.report.outstanding_ledger.outstanding_ledger import get_data as get_ledger_data
    
    ledger_data = get_ledger_data(filters)
    if not ledger_data:
        return []

    party_map = {}
    company_currency = None

    parties = list({row.party for row in ledger_data if row.get("party") and row.party != "Grand Total"})
    
    party_to_group = {}
    if parties:
        customer_groups = frappe.get_all("Customer", filters={"name": ["in", parties]}, fields=["name", "customer_group"])
        supplier_groups = frappe.get_all("Supplier", filters={"name": ["in", parties]}, fields=["name", "supplier_group"])
        
        for c in customer_groups:
            if c.customer_group and c.customer_group != "All Customer Groups":
                party_to_group[("Customer", c.name)] = c.customer_group
        for s in supplier_groups:
            if s.supplier_group and s.supplier_group != "All Supplier Groups":
                party_to_group[("Supplier", s.name)] = s.supplier_group

    for row in ledger_data:
        if not row.get("party") or row.get("party") == "Grand Total":
            continue

        party_type = row.get("party_type", "")
        party = row.party

        group = party_to_group.get((party_type, party))
        if group:
            key = ('Merged Group', 'group', group)
            final_party_type = "Customer Group" if party_type == "Customer" else "Supplier Group"
        else:
            final_party_type = party_type
            key = (final_party_type, 'party', party)

        if key not in party_map:
            party_map[key] = frappe._dict(
                party_type=final_party_type,
                party=group if key[1] == 'group' else party,
                is_group=1 if key[1] == 'group' else 0,
                out_bill=0.0,
                out_discount=0.0,
                paid_bill=0.0,
                paid_discount=0.0,
                total_bill=0.0,
                total_discount=0.0,
                total_outstanding=0.0,
                currency=row.get("currency"),
            )

        if not company_currency:
            company_currency = row.get("currency")

        p = party_map[key]
        p.out_bill += flt(row.get("out_bill", 0), 2)
        p.out_discount += flt(row.get("out_discount", 0), 2)
        p.paid_bill += flt(row.get("paid_bill", 0), 2)
        p.paid_discount += flt(row.get("paid_discount", 0), 2)
        p.total_bill += flt(row.get("total_bill", 0), 2)
        p.total_discount += flt(row.get("total_discount", 0), 2)
        p.total_outstanding += flt(row.get("total_outstanding", 0), 2)

    show_zero_values = filters.get("show_zero_values")

    data = []
    for key, row in sorted(party_map.items(), key=lambda x: x[0]):
        if row.out_bill == 0 and row.out_discount == 0 and row.paid_bill == 0 and row.paid_discount == 0 and row.total_bill == 0 and row.total_discount == 0 and row.total_outstanding == 0:
            continue
            
        if not show_zero_values and -9 <= flt(row.total_outstanding) <= 9:
            continue
            
        d = frappe._dict(
            party=row.party,
            is_group=row.is_group,
            out_bill=flt(row.out_bill, 2),
            out_discount=flt(row.out_discount, 2),
            paid_bill=flt(row.paid_bill, 2),
            paid_discount=flt(row.paid_discount, 2),
            total_bill=flt(row.total_bill, 2),
            total_discount=flt(row.total_discount, 2),
            total_outstanding=flt(row.total_outstanding, 2),
            currency=row.currency,
        )
        data.append(d)

    return data
