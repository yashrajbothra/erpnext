# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

"""
Outstanding Ledger Report
=========================
Columns
-------
Posting Date   : Posting date of the voucher
Voucher Type   : Type of voucher (Sales Invoice, Payment Entry, Journal Entry, etc.)
Voucher No     : Number of the voucher
Party          : Customer ID
Party Name     : Customer Name
Out Bill       : Outstanding amount in Debtors account (receivable)
Out Discount   : Outstanding amount in Debtors Discount account
Paid Bill      : Total received / settled against Debtors
Paid Discount  : Total received / settled against Debtors Discount
Total Bill     : Out Bill - Paid Bill
Total Discount : Out Discount - Paid Discount
Total Outstanding : Total Bill + Total Discount
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
            "label": _("Posting Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Voucher Type"),
            "fieldname": "voucher_type",
            "fieldtype": "Link",
            "options": "DocType",
            "width": 130,
        },
        {
            "label": _("Voucher No"),
            "fieldname": "voucher_no",
            "fieldtype": "Dynamic Link",
            "options": "voucher_type",
            "width": 160,
        },
        {
            "label": _("Party"),
            "fieldname": "party",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 130,
        },
        {
            "label": _("Party Name"),
            "fieldname": "party_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Out Bill"),
            "fieldname": "out_bill",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Out Discount"),
            "fieldname": "out_discount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Paid Bill"),
            "fieldname": "paid_bill",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Paid Discount"),
            "fieldname": "paid_discount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Total Bill"),
            "fieldname": "total_bill",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Total Discount"),
            "fieldname": "total_discount",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
        },
        {
            "label": _("Total Outstanding"),
            "fieldname": "total_outstanding",
            "fieldtype": "Currency",
            "options": "currency",
            "width": 130,
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
    report_date = getdate(filters.get("report_date") or nowdate())
    company = filters.get("company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )
    company_currency = (
        frappe.get_cached_value("Company", company, "default_currency")
        if company
        else frappe.db.get_default("currency")
    )

    # 1. Identify the Debtors (Receivable) accounts for this company
    debtor_accounts = frappe.get_all(
        "Account",
        filters={"account_type": "Receivable", "company": company, "disabled": 0},
        pluck="name",
    )

    # 2. Identify the Debtors Discount accounts for this company
    discount_accounts = frappe.get_all(
        "Account",
        filters={
            "account_name": ["like", "%Debtors Discount%"],
            "company": company,
            "disabled": 0,
        },
        pluck="name",
    )

    if not debtor_accounts:
        frappe.msgprint(
            _("No Receivable accounts found for company {0}").format(company),
            alert=True,
        )
        return []

    # 3. Fetch GL Entries for both account sets in a single query
    gle = frappe.qb.DocType("GL Entry")

    base_query = (
        frappe.qb.from_(gle)
        .select(
            gle.party,
            gle.party_type,
            gle.account,
            gle.debit,
            gle.credit,
            gle.voucher_no,
            gle.voucher_type,
            gle.posting_date,
        )
        .where(gle.is_cancelled == 0)
        .where(gle.posting_date <= report_date)
        .where(gle.company == company)
        .where(
            gle.account.isin(debtor_accounts + (discount_accounts or []))
        )
    )

    if filters.get("party"):
        parties = filters.party if isinstance(filters.party, (list, tuple)) else [filters.party]
        base_query = base_query.where(gle.party.isin(parties))

    gl_entries = base_query.run(as_dict=True)

    if not gl_entries:
        return []

    # Resolve missing party details from other GL Entries in the same voucher
    vp_map = {}
    for e in gl_entries:
        if e.party:
            vp_map[e.voucher_no] = {"party_type": e.party_type, "party": e.party}

    for e in gl_entries:
        if not e.party and e.voucher_no in vp_map:
            e.party_type = vp_map[e.voucher_no]["party_type"]
            e.party = vp_map[e.voucher_no]["party"]

    # Only if still missing after local mapping, we query the DB for the remainder
    still_missing = list({e.voucher_no for e in gl_entries if not e.party and e.voucher_no})
    if still_missing:
        # Standard query to resolve party details from the DB, chunked for safety
        voucher_parties = []
        for i in range(0, len(still_missing), 500):
            chunk = still_missing[i : i + 500]
            chunk_parties = frappe.get_all(
                "GL Entry",
                filters={
                    "voucher_no": ["in", chunk],
                    "party": ["is", "set"],
                },
                fields=["voucher_no", "party_type", "party"],
            )
            voucher_parties.extend(chunk_parties)

        for vp in voucher_parties:
            if vp.party:
                vp_map[vp.voucher_no] = {"party_type": vp.party_type, "party": vp.party}

        for e in gl_entries:
            if not e.party and e.voucher_no in vp_map:
                e.party_type = vp_map[e.voucher_no]["party_type"]
                e.party = vp_map[e.voucher_no]["party"]

    # 4. Group GL Entries by (party, voucher_no)
    debtor_set = set(debtor_accounts)
    discount_set = set(discount_accounts) if discount_accounts else set()
    group_map = {}

    for gle_row in gl_entries:
        party = gle_row.party
        if not party:
            continue

        # Skip non-Customer parties unless no party_type filter
        if gle_row.party_type and gle_row.party_type != "Customer":
            continue

        voucher_no = gle_row.voucher_no
        if not voucher_no:
            continue

        key = (party, voucher_no)
        if key not in group_map:
            group_map[key] = frappe._dict(
                party=party,
                voucher_no=voucher_no,
                voucher_type=gle_row.voucher_type,
                posting_date=gle_row.posting_date,
                invoice_debtors_debit=0.0,
                invoice_debtors_credit=0.0,
                invoice_discount_debit=0.0,
                invoice_discount_credit=0.0,
                payment_debtors_debit=0.0,
                payment_debtors_credit=0.0,
                payment_discount_debit=0.0,
                payment_discount_credit=0.0,
                currency=company_currency,
            )

        debit = flt(gle_row.debit)
        credit = flt(gle_row.credit)
        account = gle_row.account
        row = group_map[key]

        # Use the latest posting date found for safety
        if gle_row.posting_date:
            row.posting_date = gle_row.posting_date

        if gle_row.voucher_type == "Sales Invoice":
            if account in debtor_set:
                row.invoice_debtors_debit += debit
                row.invoice_debtors_credit += credit
            elif account in discount_set:
                row.invoice_discount_debit += debit
                row.invoice_discount_credit += credit
        else:
            if account in debtor_set:
                row.payment_debtors_debit += debit
                row.payment_debtors_credit += credit
            elif account in discount_set:
                row.payment_discount_debit += debit
                row.payment_discount_credit += credit

    if not group_map:
        return []

    # 5. Optionally filter by customer_group / territory
    if filters.get("customer_group") or filters.get("territory"):
        cust_filters = {}
        if filters.get("customer_group"):
            cust_filters["customer_group"] = filters.customer_group
        if filters.get("territory"):
            cust_filters["territory"] = filters.territory

        valid_customers = frappe.get_all(
            "Customer",
            filters=cust_filters,
            pluck="name",
        )
        valid_set = set(valid_customers)
        group_map = {k: v for k, v in group_map.items() if k[0] in valid_set}

    if not group_map:
        return []

    # 6. Fetch customer names
    customer_names = frappe._dict(
        frappe.get_all(
            "Customer",
            filters={"name": ["in", list({k[0] for k in group_map.keys()})]},
            fields=["name", "customer_name"],
            as_list=1,
        )
    )

    # 7. Build final rows — only show vouchers with non-zero metrics
    data = []
    grand = frappe._dict(
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

    # Sort data by customer ID, then posting date, then voucher_no
    sorted_keys = sorted(
        group_map.keys(),
        key=lambda x: (
            x[0],
            getdate(group_map[x].posting_date or '1970-01-01'),
            group_map[x].voucher_no or '',
        )
    )

    for key in sorted_keys:
        row = group_map[key]
        out_bill = flt((row.invoice_debtors_debit - row.invoice_debtors_credit) - (row.invoice_discount_credit - row.invoice_discount_debit), 2)
        out_discount = flt(row.invoice_discount_credit - row.invoice_discount_debit, 2)
        paid_bill = flt(row.payment_debtors_credit - row.payment_debtors_debit, 2)
        paid_discount = flt(row.payment_discount_credit - row.payment_discount_debit, 2)
        total_bill = flt(out_bill - paid_bill, 2)
        total_discount = flt(out_discount - paid_discount, 2)
        total_outstanding = flt(total_bill + total_discount, 2)

        # Skip if nothing outstanding and no paid amounts
        if out_bill == 0 and out_discount == 0 and paid_bill == 0 and paid_discount == 0 and total_bill == 0 and total_discount == 0 and total_outstanding == 0:
            continue

        data.append(
            frappe._dict(
                posting_date=row.posting_date,
                voucher_type=row.voucher_type,
                voucher_no=row.voucher_no,
                party=row.party,
                party_name=customer_names.get(row.party, row.party),
                out_bill=out_bill,
                out_discount=out_discount,
                paid_bill=paid_bill,
                paid_discount=paid_discount,
                total_bill=total_bill,
                total_discount=total_discount,
                total_outstanding=total_outstanding,
                currency=company_currency,
            )
        )

        grand.out_bill += out_bill
        grand.out_discount += out_discount
        grand.paid_bill += paid_bill
        grand.paid_discount += paid_discount
        grand.total_bill += total_bill
        grand.total_discount += total_discount
        grand.total_outstanding += total_outstanding

    if data:
        data.append({})  # blank separator
        grand.out_bill = flt(grand.out_bill, 2)
        grand.out_discount = flt(grand.out_discount, 2)
        grand.paid_bill = flt(grand.paid_bill, 2)
        grand.paid_discount = flt(grand.paid_discount, 2)
        grand.total_bill = flt(grand.total_bill, 2)
        grand.total_discount = flt(grand.total_discount, 2)
        grand.total_outstanding = flt(grand.total_outstanding, 2)
        data.append(grand)

    return data
