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
from frappe.query_builder.functions import Sum
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
            "label": _("Party Name"),
            "fieldname": "party_name",
            "fieldtype": "Data",
            "width": 200,
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
    report_date = getdate(filters.get("report_date") or nowdate())
    company = filters.get("company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )
    company_currency = (
        frappe.get_cached_value("Company", company, "default_currency")
        if company
        else frappe.db.get_default("currency")
    )

    # ------------------------------------------------------------------
    # 1. Identify the Debtors (Receivable) and Creditors (Payable) accounts for this company
    debtor_accounts = frappe.get_all(
        "Account",
        filters={"account_type": ["in", ["Receivable", "Payable"]], "company": company, "disabled": 0},
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
            _("No Receivable or Payable accounts found for company {0}").format(company),
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
        party_vouchers = frappe.get_all(
            "GL Entry",
            filters={
                "party": ["in", parties],
                "company": company,
                "is_cancelled": 0,
                "posting_date": ["<=", report_date],
                "account": ["in", debtor_accounts],
            },
            pluck="voucher_no",
        )
        if not party_vouchers:
            return []
        base_query = base_query.where(gle.voucher_no.isin(list(set(party_vouchers))))

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

    # 4. Aggregate per party
    debtor_set = set(debtor_accounts)
    discount_set = set(discount_accounts) if discount_accounts else set()
    party_map = {}

    for gle_row in gl_entries:
        party = gle_row.party
        if not party:
            continue

        # Skip non-Customer/Supplier parties unless no party_type filter
        if gle_row.party_type and gle_row.party_type not in ("Customer", "Supplier"):
            continue

        if party not in party_map:
            party_map[party] = frappe._dict(
                party_type=gle_row.party_type,
                party=party,
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

        if gle_row.voucher_type in ("Sales Invoice", "Purchase Invoice"):
            if account in debtor_set:
                party_map[party].invoice_debtors_debit += debit
                party_map[party].invoice_debtors_credit += credit
            elif account in discount_set:
                party_map[party].invoice_discount_debit += debit
                party_map[party].invoice_discount_credit += credit
        else:
            if account in debtor_set:
                party_map[party].payment_debtors_debit += debit
                party_map[party].payment_debtors_credit += credit
            elif account in discount_set:
                party_map[party].payment_discount_debit += debit
                party_map[party].payment_discount_credit += credit

    if not party_map:
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
        party_map = {k: v for k, v in party_map.items() if k in valid_set}

    if not party_map:
        return []

    # 6. Fetch customer and supplier names
    parties_list = list(party_map.keys())
    customer_names = frappe._dict(
        frappe.get_all(
            "Customer",
            filters={"name": ["in", parties_list]},
            fields=["name", "customer_name"],
            as_list=1,
        )
    )
    supplier_names = frappe._dict(
        frappe.get_all(
            "Supplier",
            filters={"name": ["in", parties_list]},
            fields=["name", "supplier_name"],
            as_list=1,
        )
    )

    # 7. Build final rows — only show parties with non-zero outstanding
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
                party_type=row.party_type,
                party=party,
                party_name=customer_names.get(party) or supplier_names.get(party) or party,
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
        grand.out_bill = flt(grand.out_bill, 2)
        grand.out_discount = flt(grand.out_discount, 2)
        grand.paid_bill = flt(grand.paid_bill, 2)
        grand.paid_discount = flt(grand.paid_discount, 2)
        grand.total_bill = flt(grand.total_bill, 2)
        grand.total_discount = flt(grand.total_discount, 2)
        grand.total_outstanding = flt(grand.total_outstanding, 2)
        data.append(grand)

    return data
