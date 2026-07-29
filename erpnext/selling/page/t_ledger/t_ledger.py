import frappe

import json

@frappe.whitelist()
def get_t_ledger(customer, from_date=None, to_date=None):
    if isinstance(customer, str):
        try:
            parsed_customer = json.loads(customer)
            if isinstance(parsed_customer, list):
                customer = parsed_customer
            else:
                customer = [customer]
        except Exception:
            customer = [customer]
    elif not isinstance(customer, list):
        customer = [customer]

    if not customer:
        return {}

    conditions = "AND party IN %(customers)s AND is_cancelled = 0"

    if from_date:
        conditions += " AND posting_date >= %(from_date)s"
    if to_date:
        conditions += " AND posting_date <= %(to_date)s"

    entries = frappe.db.sql(f"""
        SELECT
            posting_date,
            voucher_type,
            voucher_no,
            SUM(debit) as debit,
            SUM(credit) as credit
        FROM `tabGL Entry`
        WHERE party_type = 'Customer'
        {conditions}
        GROUP BY posting_date, voucher_type, voucher_no
        ORDER BY posting_date, min(creation)
    """, {
        "customers": tuple(customer),
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)

    debit = []
    credit = []

    total_debit = 0.0
    total_credit = 0.0

    if from_date:
        opening_balance = frappe.db.sql(f"""
            SELECT sum(debit) - sum(credit)
            FROM `tabGL Entry`
            WHERE party_type = 'Customer'
            AND party IN %(customers)s
            AND is_cancelled = 0
            AND posting_date < %(from_date)s
        """, {
            "customers": tuple(customer),
            "from_date": from_date
        })
        
        total_ob_discount = frappe.db.sql(f"""
            SELECT SUM(i.qty * IFNULL(i.custom_discount_rate, 0))
            FROM `tabSales Invoice Item` i
            JOIN `tabSales Invoice` s ON i.parent = s.name
            WHERE s.customer IN %(customers)s
            AND s.docstatus = 1
            AND s.posting_date < %(from_date)s
        """, {
            "customers": tuple(customer),
            "from_date": from_date
        })

        ob_amount = opening_balance[0][0] if opening_balance and opening_balance[0][0] else 0.0
        discount_amount_ob = total_ob_discount[0][0] if total_ob_discount and total_ob_discount[0][0] else 0.0
        ob_amount += float(discount_amount_ob)
        
        if ob_amount >= 0:
            # DB Debit (Receivable) -> UI Credit
            credit.append({
                "date": from_date,
                "voucher_type": "Opening Balance",
                "voucher_no": "",
                "amount": ob_amount
            })
            # To keep rows perfectly aligned, emit blank opposite
            debit.append({})
            total_credit += ob_amount
        else:
            # DB Credit (Advance) -> UI Debit
            debit.append({
                "date": from_date,
                "voucher_type": "Opening Balance",
                "voucher_no": "",
                "amount": abs(ob_amount)
            })
            credit.append({})
            total_debit += abs(ob_amount)

    pe_data = {}
    pe_vouchers = [e.voucher_no for e in entries if e.voucher_type == 'Payment Entry']
    if pe_vouchers:
        pe_records = frappe.get_all('Payment Entry',
            filters={'name': ('in', pe_vouchers)},
            fields=['name', 'payment_type', 'paid_amount', 'received_amount', 'total_allocated_amount']
        )
        for r in pe_records:
            pe_data[r.name] = r
            pe_data[r.name]["references"] = []
            
        pe_refs = frappe.get_all('Payment Entry Reference',
            filters={'parent': ('in', pe_vouchers)},
            fields=['parent', 'reference_doctype', 'reference_name', 'allocated_amount']
        )
        for ref in pe_refs:
            if ref.parent in pe_data:
                pe_data[ref.parent]["references"].append(ref)

    si_vouchers = [e.voucher_no for e in entries if e.voucher_type == 'Sales Invoice']
    discounts = {}
    if si_vouchers:
        discount_data = frappe.db.sql("""
            SELECT parent, SUM(qty * IFNULL(custom_discount_rate, 0)) as discount
            FROM `tabSales Invoice Item`
            WHERE parent IN %s
            GROUP BY parent
        """, (tuple(si_vouchers),), as_dict=True)
        for d in discount_data:
            if d.discount:
                discounts[d.parent] = float(d.discount)

    for e in entries:
        row = {
            "date": e.posting_date,
            "voucher_type": e.voucher_type,
            "voucher_no": e.voucher_no
        }

        if e.voucher_type == 'Payment Entry' and e.voucher_no in pe_data:
            pe = pe_data[e.voucher_no]
            row["allocated_amount"] = pe.total_allocated_amount
            row["references"] = pe.references

        if e.credit > 0:
            row["amount"] = e.credit
            debit.append(row)
            total_debit += e.credit

        elif e.debit > 0:
            row["amount"] = e.debit
            credit.append(row)
            total_credit += e.debit

        if e.voucher_type == 'Sales Invoice' and e.voucher_no in discounts:
            discount_amt = discounts[e.voucher_no]
            if discount_amt != 0:
                discount_row = {
                    "date": e.posting_date,
                    "voucher_type": e.voucher_type,
                    "voucher_no": e.voucher_no,
                    "is_discount": 1,
                    "amount": discount_amt
                }
                credit.append(discount_row)
                total_credit += discount_amt

    # The balance in standard terms: UI Credit (DB Debit) - UI Debit (DB Credit)
    closing_balance = total_credit - total_debit

    return {
        "debit": debit,
        "credit": credit,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "closing_balance": closing_balance
    }
@frappe.whitelist()
def get_itemised_trading_ledger(from_date=None, to_date=None):
    conditions_pr = "AND pr.docstatus = 1"
    conditions_si = "AND si.docstatus = 1"

    if from_date:
        conditions_pr += " AND pr.posting_date >= %(from_date)s"
        conditions_si += " AND si.posting_date >= %(from_date)s"
    if to_date:
        conditions_pr += " AND pr.posting_date <= %(to_date)s"
        conditions_si += " AND si.posting_date <= %(to_date)s"

    purchases = frappe.db.sql(f"""
        SELECT
            pr.posting_date as date,
            'Purchase Receipt' as voucher_type,
            pr.name as voucher_no,
            pr.supplier as party,
            i.item_code,
            i.item_name,
            i.qty,
            i.rate,
            i.amount,
            i.total_weight as weight,
            i.custom_size,
            i.custom_thickness,
            i.custom_od,
            i.custom_schedule,
            i.custom_nb,
            i.custom_pieces,
            NULL as custom_citi_no,
            0 as custom_discount_rate,
            0 as custom_bill_rate,
            0 as custom_loading_charges,
            0 as custom_gst_amount,
            i.warehouse
        FROM `tabPurchase Receipt Item` i
        JOIN `tabPurchase Receipt` pr ON pr.name = i.parent
        WHERE 1=1 {conditions_pr}
        ORDER BY pr.posting_date, pr.creation
    """, {
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)

    sales = frappe.db.sql(f"""
        SELECT
            si.posting_date as date,
            'Sales Invoice' as voucher_type,
            si.name as voucher_no,
            si.customer as party,
            i.item_code,
            i.item_name,
            i.qty,
            i.rate,
            i.amount,
            i.total_weight as weight,
            i.custom_size,
            i.custom_thickness,
            i.custom_od,
            i.custom_schedule,
            i.custom_nb,
            i.custom_pieces,
            i.custom_citi_no,
            i.custom_discount_rate,
            i.custom_bill_rate,
            si.custom_loading_charges as custom_loading_charges,
            si.custom_gst_amount as custom_gst_amount,
            i.warehouse
        FROM `tabSales Invoice Item` i
        JOIN `tabSales Invoice` si ON si.name = i.parent
        WHERE 1=1 {conditions_si}
        ORDER BY si.posting_date, si.creation
    """, {
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)

    for p in purchases:
        final_rate = p.get("rate") or 0.0
        p["calculated_rate"] = final_rate
        
        calc_weight = p.get("weight") or 0.0
        multiplier = calc_weight if calc_weight > 0 else (p.get("qty") or 0.0)
        p["calculated_amount"] = (final_rate * multiplier)

    for s in sales:
        c_rate = (s.get("custom_discount_rate") or 0.0) + (s.get("custom_bill_rate") or 0.0)
        final_rate = c_rate if c_rate > 0 else (s.get("rate") or 0.0)
        s["calculated_rate"] = final_rate
            
        loading = s.get("custom_loading_charges") or 0.0
        gst = s.get("custom_gst_amount") or 0.0
        
        calc_weight = s.get("weight") or 0.0
        multiplier = calc_weight if calc_weight > 0 else (s.get("qty") or 0.0)
        
        s["calculated_amount"] = (final_rate * multiplier) + loading + gst

    total_purchase = sum(p["calculated_amount"] for p in purchases)
    total_sale = sum(s["calculated_amount"] for s in sales)

    closing_balance = total_sale - total_purchase

    return {
        "debit": purchases,
        "credit": sales,
        "total_debit": total_purchase,
        "total_credit": total_sale,
        "closing_balance": closing_balance
    }

@frappe.whitelist()
def get_general_t_ledger(account, from_date=None, to_date=None, use_entry_date=0, party=None, filter_account=None):
    if isinstance(account, str):
        try:
            parsed_account = json.loads(account)
            if isinstance(parsed_account, list):
                account = parsed_account
            else:
                account = [account]
        except Exception:
            account = [account]
    elif not isinstance(account, list):
        account = [account]

    if not account:
        return {}

    if party:
        if isinstance(party, str):
            try:
                parsed_party = json.loads(party)
                if isinstance(parsed_party, list):
                    party = parsed_party
                else:
                    party = [party]
            except Exception:
                party = [party]
        elif not isinstance(party, list):
            party = [party]

    if filter_account:
        if isinstance(filter_account, str):
            try:
                parsed_filter_account = json.loads(filter_account)
                if isinstance(parsed_filter_account, list):
                    filter_account = parsed_filter_account
                else:
                    filter_account = [parsed_filter_account]
            except Exception:
                filter_account = [filter_account]
        elif not isinstance(filter_account, list):
            filter_account = [filter_account]

    use_entry_date = frappe.utils.cint(use_entry_date)

    gle_conditions = "AND gle.account IN %(accounts)s AND gle.is_cancelled = 0"
    if party:
        gle_conditions += " AND EXISTS (SELECT 1 FROM `tabGL Entry` g2 WHERE g2.voucher_no = gle.voucher_no AND g2.party IN %(parties)s)"
    if filter_account:
        gle_conditions += " AND EXISTS (SELECT 1 FROM `tabGL Entry` g2 WHERE g2.voucher_no = gle.voucher_no AND g2.account IN %(filter_accounts)s)"

    if use_entry_date:
        # Filter on Payment Entry's custom_entry_date if available, else posting_date
        if from_date:
            gle_conditions += " AND COALESCE(pe.custom_entry_date, gle.posting_date) >= %(from_date)s"
        if to_date:
            gle_conditions += " AND COALESCE(pe.custom_entry_date, gle.posting_date) <= %(to_date)s"
    else:
        if from_date:
            gle_conditions += " AND gle.posting_date >= %(from_date)s"
        if to_date:
            gle_conditions += " AND gle.posting_date <= %(to_date)s"

    order_by = "COALESCE(pe.custom_entry_date, gle.posting_date)" if use_entry_date else "gle.posting_date"

    entries = frappe.db.sql(f"""
        SELECT
            gle.posting_date,
            COALESCE(pe.custom_entry_date, gle.posting_date) as entry_date,
            gle.voucher_type,
            gle.voucher_no,
            gle.party_type,
            gle.party,
            gle.account,
            MAX(gle.against) as against,
            MAX(pe.paid_to) as paid_to,
            MAX(pe.paid_from) as paid_from,
            MAX(gle.remarks) as remarks,
            SUM(gle.debit) as db_debit,
            SUM(gle.credit) as db_credit
        FROM `tabGL Entry` gle
        LEFT JOIN `tabPayment Entry` pe
            ON pe.name = gle.voucher_no AND gle.voucher_type = 'Payment Entry'
        WHERE 1=1
        {gle_conditions}
        GROUP BY gle.posting_date, COALESCE(pe.custom_entry_date, gle.posting_date),
                 gle.voucher_type, gle.voucher_no, gle.party_type, gle.party, gle.account
        ORDER BY {order_by}, min(gle.creation)
    """, {
        "accounts": tuple(account),
        "parties": tuple(party) if party else None,
        "filter_accounts": tuple(filter_account) if filter_account else None,
        "from_date": from_date,
        "to_date": to_date
    }, as_dict=True)

    debit_arr = []
    credit_arr = []

    total_debit = 0.0
    total_credit = 0.0

    opening_balance_val = 0.0
    if from_date:
        ob_conditions = "AND gle.account IN %(accounts)s AND gle.is_cancelled = 0"
        if party:
            ob_conditions += " AND EXISTS (SELECT 1 FROM `tabGL Entry` g2 WHERE g2.voucher_no = gle.voucher_no AND g2.party IN %(parties)s)"
        if filter_account:
            ob_conditions += " AND EXISTS (SELECT 1 FROM `tabGL Entry` g2 WHERE g2.voucher_no = gle.voucher_no AND g2.account IN %(filter_accounts)s)"

        if use_entry_date:
            ob_where = "AND COALESCE(pe.custom_entry_date, gle.posting_date) < %(from_date)s"
        else:
            ob_where = "AND gle.posting_date < %(from_date)s"

        opening_balance_query = frappe.db.sql(f"""
            SELECT sum(gle.debit) - sum(gle.credit)
            FROM `tabGL Entry` gle
            LEFT JOIN `tabPayment Entry` pe
                ON pe.name = gle.voucher_no AND gle.voucher_type = 'Payment Entry'
            WHERE 1=1 {ob_conditions}
            {ob_where}
        """, {
            "accounts": tuple(account),
            "parties": tuple(party) if party else None,
            "filter_accounts": tuple(filter_account) if filter_account else None,
            "from_date": from_date
        })
        
        opening_balance_val = opening_balance_query[0][0] if opening_balance_query and opening_balance_query[0][0] else 0.0

    missing_vouchers = [e.voucher_no for e in entries if (not e.party or not e.party_type) and e.voucher_no]
    if missing_vouchers:
        voucher_parties = frappe.db.sql("""
            SELECT voucher_no, MAX(party_type) as ptype, MAX(party) as pty
            FROM `tabGL Entry`
            WHERE voucher_no IN %s AND party IS NOT NULL
            GROUP BY voucher_no
        """, (tuple(missing_vouchers),), as_dict=True)
        
        vp_map = {vp.voucher_no: {"party_type": vp.ptype, "party": vp.pty} for vp in voucher_parties if vp.pty}
        for e in entries:
            if not e.party and e.voucher_no in vp_map:
                e.party_type = vp_map[e.voucher_no]["party_type"]
                e.party = vp_map[e.voucher_no]["party"]

    parties = {}
    for e in entries:
        if e.party_type and e.party:
            if e.party_type not in parties:
                parties[e.party_type] = set()
            parties[e.party_type].add(e.party)

    party_names = {}
    for p_type, names in parties.items():
        if not names: continue
        name_field = "name"
        if p_type == "Customer":
            name_field = "customer_name"
        elif p_type == "Supplier":
            name_field = "supplier_name"
        elif p_type == "Employee":
            name_field = "employee_name"

        try:
            p_data = frappe.get_all(p_type, filters={"name": ("in", list(names))}, fields=["name", name_field])
            for d in p_data:
                party_names[f"{p_type}:{d.name}"] = d.get(name_field) or d.name
        except Exception:
            pass

    for e in entries:
        party_key = f"{e.party_type}:{e.party}" if e.party_type and e.party else None
        p_name = party_names.get(party_key, e.party) if party_key else e.party

        row = {
            "date": e.entry_date if (use_entry_date and e.entry_date) else e.posting_date,
            "posting_date": e.posting_date,  # explicit alias for clarity
            "entry_date": str(e.entry_date) if e.entry_date else None,  # creation date, for display when use_entry_date
            "voucher_type": e.voucher_type,
            "voucher_no": e.voucher_no,
            "party": p_name,
            "account": e.account,
            "against": e.against,
            "paid_to": e.paid_to,
            "paid_from": e.paid_from,
            "remarks": e.remarks
        }

        if e.db_debit > 0:
            row_dr = row.copy()
            row_dr["amount"] = e.db_debit
            debit_arr.append(row_dr)
            total_debit += e.db_debit

        if e.db_credit > 0:
            row_cr = row.copy()
            row_cr["amount"] = e.db_credit
            credit_arr.append(row_cr)
            total_credit += e.db_credit

    closing_balance = opening_balance_val + total_debit - total_credit

    return {
        "debit": debit_arr,
        "credit": credit_arr,
        "opening_balance": opening_balance_val,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "closing_balance": closing_balance
    }


@frappe.whitelist(allow_guest=True)
def get_customer_names():
    customers = frappe.get_all(
        "Customer",
        fields=["name"],
        order_by="name asc",
        limit_page_length=0
    )
    
    return [c["name"] for c in customers]

@frappe.whitelist(allow_guest=True)
def get_supplier_names():
    suppliers = frappe.get_all(
        "Supplier",
        fields=["name"],
        order_by="name asc",
        limit_page_length=0
    )
    
    return [c["name"] for c in suppliers]

@frappe.whitelist()
def get_paper_summary_data(account, party=None, filter_account=None, from_date=None, to_date=None, cutoff_date=None, interest_rate=0.0, use_entry_date=0):
    from erpnext.api import get_general_t_ledger
    from frappe.utils import getdate, flt
    
    # 1. Fetch all transactions (from the beginning of time if we want to calculate Opening Balance accurately, 
    # but wait, get_general_t_ledger already handles Opening Balance for the WHOLE account if from_date is provided.
    # We cannot use get_general_t_ledger to get OB per party if from_date is set.
    # Therefore, we fetch EVERYTHING (from_date=None) to calculate both OB and Period per party!)
    
    # Fetch all transactions up to to_date
    res = get_general_t_ledger(account, from_date=None, to_date=to_date, use_entry_date=use_entry_date, party=party, filter_account=filter_account)
    
    interest_rate = flt(interest_rate)
    
    if cutoff_date:
        cutoff_date = getdate(cutoff_date)
        
    if from_date:
        from_date = getdate(from_date)
        
    summary = {}
    
    # helper to aggregate
    def add_to_summary(p, key, amount):
        if not p:
            p = "No Party"
        if p not in summary:
            summary[p] = {"party": p, "opening_balance": 0.0, "total_debit": 0.0, "total_credit": 0.0, "interest": 0.0, "closing_balance": 0.0}
        summary[p][key] += flt(amount)
        
    # Helper to calculate interest
    def calc_interest(row_date, amount):
        if not cutoff_date or not row_date: return 0.0
        row_date = getdate(row_date)
        days = (cutoff_date - row_date).days
        if days > 0 and interest_rate > 0:
            return (amount * interest_rate / 100.0) * (days / 30.0)
        return 0.0

    # debit entries
    for d in res.get("debit", []):
        if not d.get("amount"): continue
        d_date = getdate(d.get("date")) # posting_date or entry_date depending on use_entry_date
        
        if from_date and d_date < from_date:
            # DB Credit -> UI Debit -> means it adds to OB debit side
            add_to_summary(d.get("party"), "opening_balance", d["amount"])
        else:
            add_to_summary(d.get("party"), "total_debit", d["amount"])
            add_to_summary(d.get("party"), "interest", calc_interest(d_date, d["amount"]))
            
    # credit entries
    for c in res.get("credit", []):
        if not c.get("amount"): continue
        c_date = getdate(c.get("date"))
        
        if from_date and c_date < from_date:
            add_to_summary(c.get("party"), "opening_balance", -c["amount"])
        else:
            add_to_summary(c.get("party"), "total_credit", c["amount"])
            # In paper.js, credit interest is also positive, but for net interest it would be subtracted
            # Wait, in paper.js, total_debit_interest and total_credit_interest are separated.
            # Let's keep them separated or net? Let's keep net for summary or separate.
            if c.get("party") not in summary:
                add_to_summary(c.get("party"), "total_credit", 0.0) # initialize
            if "total_credit_interest" not in summary[c.get("party") or "No Party"]:
                summary[c.get("party") or "No Party"]["total_credit_interest"] = 0.0
                summary[c.get("party") or "No Party"]["total_debit_interest"] = 0.0
            
            summary[c.get("party") or "No Party"]["total_credit_interest"] += calc_interest(c_date, c["amount"])

    # Fix the interest keys for debits
    for p in summary:
        if "total_debit_interest" not in summary[p]:
            summary[p]["total_debit_interest"] = summary[p].get("interest", 0.0)
            summary[p]["total_credit_interest"] = summary[p].get("total_credit_interest", 0.0)
        else:
            summary[p]["total_debit_interest"] += summary[p].get("interest", 0.0)
            
        # Calculate closing balance: OB + Debit - Credit
        summary[p]["closing_balance"] = summary[p]["opening_balance"] + summary[p]["total_debit"] - summary[p]["total_credit"]

    result = list(summary.values())
    result.sort(key=lambda x: x["party"])
    return result

@frappe.whitelist()
def get_stock_balance_report(company=None, from_date=None, to_date=None, warehouse=None, custom_size=None, custom_schedule=None, segregate_serial_batch_bundle=None):
    from erpnext.stock.report.stock_balance.stock_balance import execute
    
    if isinstance(warehouse, str):
        try:
            parsed_warehouse = json.loads(warehouse)
            if isinstance(parsed_warehouse, list):
                warehouse = parsed_warehouse
            else:
                warehouse = [warehouse]
        except Exception:
            warehouse = [warehouse]

    filters = frappe._dict({
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "show_stock_ageing_data": 0,
        "segregate_serial_batch_bundle": 1 if (segregate_serial_batch_bundle or custom_size or custom_schedule) else 0
    })
    
    if warehouse:
        filters["warehouse"] = warehouse

    if custom_size:
        if isinstance(custom_size, str):
            try:
                parsed_size = json.loads(custom_size)
                if isinstance(parsed_size, list):
                    custom_size = parsed_size
            except Exception:
                pass
        filters["custom_size"] = custom_size

    if custom_schedule:
        if isinstance(custom_schedule, str):
            try:
                parsed_schedule = json.loads(custom_schedule)
                if isinstance(parsed_schedule, list):
                    custom_schedule = parsed_schedule
            except Exception:
                pass
        filters["custom_schedule"] = custom_schedule
        
    columns, data = execute(filters)
    return data

