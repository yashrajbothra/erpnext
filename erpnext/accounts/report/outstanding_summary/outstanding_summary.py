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
    columns = get_columns()
    data = get_data(filters)
    return columns, data


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------

def get_columns():
    return [
        {
            "label": _("Party Type"),
            "fieldname": "party_type",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Party"),
            "fieldname": "party",
            "fieldtype": "Dynamic Link",
            "options": "party_type",
            "width": 160,
        },
        {
            "label": _("Out Bill"),
            "fieldname": "out_bill",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "label": _("Out Discount"),
            "fieldname": "out_discount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "label": _("Paid Bill"),
            "fieldname": "paid_bill",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "label": _("Paid Discount"),
            "fieldname": "paid_discount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "label": _("Total Bill"),
            "fieldname": "total_bill",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "label": _("Total Discount"),
            "fieldname": "total_discount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "label": _("Total Outstanding"),
            "fieldname": "total_outstanding",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 150,
        },
        {
            "label": _("Currency"),
            "fieldname": "currency",
            "fieldtype": "Data",
            "width": 80,
            "hidden": 1,
        },
    ]


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

    for row in ledger_data:
        if not row.get("party") or row.get("party") == "Grand Total":
            continue

        party = row.party
        if party not in party_map:
            party_map[party] = frappe._dict(
                party_type=row.get("party_type", ""),
                party=party,
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

        p = party_map[party]
        p.out_bill += flt(row.get("out_bill", 0), 2)
        p.out_discount += flt(row.get("out_discount", 0), 2)
        p.paid_bill += flt(row.get("paid_bill", 0), 2)
        p.paid_discount += flt(row.get("paid_discount", 0), 2)
        p.total_bill += flt(row.get("total_bill", 0), 2)
        p.total_discount += flt(row.get("total_discount", 0), 2)
        p.total_outstanding += flt(row.get("total_outstanding", 0), 2)

    data = []
    grand = frappe._dict(
        party_type="",
        party="Grand Total",
        party_name="",
        out_bill=0.0,
        out_discount=0.0,
        paid_bill=0.0,
        paid_discount=0.0,
        total_bill=0.0,
        total_discount=0.0,
        total_outstanding=0.0,
        currency=company_currency,
        bold=1,
    )

    for party, row in sorted(party_map.items(), key=lambda x: x[0]):
        if row.out_bill == 0 and row.out_discount == 0 and row.paid_bill == 0 and row.paid_discount == 0 and row.total_bill == 0 and row.total_discount == 0 and row.total_outstanding == 0:
            continue
            
        data.append(
            frappe._dict(
                party_type=row.party_type,
                party=party,
                out_bill=flt(row.out_bill, 2),
                out_discount=flt(row.out_discount, 2),
                paid_bill=flt(row.paid_bill, 2),
                paid_discount=flt(row.paid_discount, 2),
                total_bill=flt(row.total_bill, 2),
                total_discount=flt(row.total_discount, 2),
                total_outstanding=flt(row.total_outstanding, 2),
                currency=row.currency,
            )
        )

        grand.out_bill += row.out_bill
        grand.out_discount += row.out_discount
        grand.paid_bill += row.paid_bill
        grand.paid_discount += row.paid_discount
        grand.total_bill += row.total_bill
        grand.total_discount += row.total_discount
        grand.total_outstanding += row.total_outstanding

    if data:
        grand.out_bill = flt(grand.out_bill, 2)
        grand.out_discount = flt(grand.out_discount, 2)
        grand.paid_bill = flt(grand.paid_bill, 2)
        grand.paid_discount = flt(grand.paid_discount, 2)
        grand.total_bill = flt(grand.total_bill, 2)
        grand.total_discount = flt(grand.total_discount, 2)
        grand.total_outstanding = flt(grand.total_outstanding, 2)
        data.append(grand)

    return data
