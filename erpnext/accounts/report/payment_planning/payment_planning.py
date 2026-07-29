import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("S. O. DATE"), "fieldname": "s_o_date", "fieldtype": "Date", "width": 100},
        {"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "hidden": 1},
        {"label": _("PARTY"), "fieldname": "party", "fieldtype": "Dynamic Link", "options": "party_type", "width": 150},
        {"label": _("Customer Group"), "fieldname": "customer_group", "fieldtype": "Data", "width": 120},
        {"label": _("VIA"), "fieldname": "via", "fieldtype": "Data", "width": 80},
        {"label": _("COM"), "fieldname": "com", "fieldtype": "Data", "width": 100},
        {"label": _("INV. NO"), "fieldname": "inv_no", "fieldtype": "Data", "width": 120},
        {"label": _("Actual Inv No"), "fieldname": "actual_inv_no", "fieldtype": "Data", "hidden": 1},
        {"label": _("Payment Entry"), "fieldname": "payment_entry", "fieldtype": "Data", "hidden": 1},
        {"label": _("DUE DAYS"), "fieldname": "due_days", "fieldtype": "Int", "width": 90},
        {"label": _("DUE DATE"), "fieldname": "due_date", "fieldtype": "Date", "width": 100},
        {"label": _("BILL AMT"), "fieldname": "bill_amt", "fieldtype": "Currency", "width": 120},
        {"label": _("RECEIVED"), "fieldname": "received", "fieldtype": "Currency", "width": 120},
        {"label": _("RECD ON"), "fieldname": "recd_on", "fieldtype": "Date", "width": 100},
        {"label": _("DUE AMT."), "fieldname": "due_amt", "fieldtype": "Currency", "width": 120},
        {"label": _("LATE"), "fieldname": "late", "fieldtype": "Int", "width": 80},
        {"label": _("Rate (%)"), "fieldname": "rate", "fieldtype": "Data", "width": 80},
        {"label": _("Interest"), "fieldname": "interest", "fieldtype": "Currency", "width": 100},
    ]

def get_data(filters):
    fetch_customers = True
    fetch_suppliers = True
    
    if filters:
        party_type = filters.get("party_type")
        if party_type == "Customer":
            fetch_suppliers = False
        elif party_type == "Supplier":
            fetch_customers = False
            

    invoices = []
    payments_data = []

    if fetch_customers:
        conditions = " AND (IFNULL(si.custom_inv_no, '') != ''"
        if frappe.db.has_column("Sales Invoice Item", "custom_bill_rate"):
            conditions += " OR EXISTS (SELECT name FROM `tabSales Invoice Item` sii WHERE sii.parent = si.name AND IFNULL(sii.custom_bill_rate, 0) != 0))"
        else:
            conditions += ")"
        party_cond = ""
        if filters and filters.get("party"):
            parties = filters.get("party")
            if isinstance(parties, str):
                parties = [parties]
            party_cond = " IN ({})".format(", ".join(frappe.db.escape(c) for c in parties))

        if filters and filters.get("company"):
            conditions += f" AND si.company = {frappe.db.escape(filters.get('company'))}"
        if party_cond:
            conditions += f" AND si.customer {party_cond}"
        if filters and filters.get("customer_group"):
            conditions += f" AND si.customer_group = {frappe.db.escape(filters.get('customer_group'))}"
        
        c_invoices = frappe.db.sql(f"""
            SELECT 
                si.name as actual_inv_no,
                si.custom_inv_no as inv_no, 
                si.posting_date as s_o_date,
                si.customer,
                'Customer' as party_type,
                si.customer_name,
                si.customer_group,
            si.custom_via,
            si.custom_com as com,
            si.custom_payment_terms,
            si.posting_date as original_due_date,
            si.base_grand_total as bill_amt,
            si.outstanding_amount,
            (SELECT SUM(tax_amount) FROM `tabSales Taxes and Charges` WHERE parent = si.name AND account_head LIKE 'Debtors Discount%') as discount_amount,
            'Sales Invoice' as invoice_doctype
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 {conditions}
    """, as_dict=True)

        invoices.extend(c_invoices)

        je_cond = ""
        if filters and filters.get("company"):
            je_cond += f" AND je.company = {frappe.db.escape(filters.get('company'))}"
        if party_cond:
            je_cond += f" AND jea.party {party_cond}"
        if filters and filters.get("customer_group"):
            je_cond += f" AND c.customer_group = {frappe.db.escape(filters.get('customer_group'))}"

        jv_invoices = frappe.db.sql(f"""
            SELECT 
                je.name as actual_inv_no,
                'OPP' as inv_no, 
                je.posting_date as s_o_date,
                jea.party as customer,
                'Customer' as party_type,
                c.customer_name,
            c.customer_group,
            '' as custom_via,
            je.mode_of_payment as com,
            0 as custom_payment_terms,
            je.posting_date as original_due_date,
            SUM(jea.debit_in_account_currency) as bill_amt,
            SUM(jea.debit_in_account_currency) as outstanding_amount,
            'Journal Entry' as invoice_doctype
        FROM `tabJournal Entry` je
        JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
        JOIN `tabCustomer` c ON jea.party = c.name
        JOIN `tabAccount` a ON jea.account = a.name
        WHERE je.docstatus = 1 
          AND jea.party_type = 'Customer' 
          AND a.account_type = 'Receivable'
          AND jea.debit_in_account_currency > 0
          {je_cond}
        GROUP BY je.name, jea.party
        """, as_dict=True)

        invoices.extend(jv_invoices)

        pe_cond = ""
        if filters and filters.get("company"):
            pe_cond += f" AND pe.company = {frappe.db.escape(filters.get('company'))}"
        if party_cond:
            pe_cond += f" AND pe.party {party_cond}"
        if filters and filters.get("customer_group"):
            pe_cond += f" AND c.customer_group = {frappe.db.escape(filters.get('customer_group'))}"
            
        c_payments_data = frappe.db.sql(f"""
            SELECT 
                pe.name,
                pe.posting_date as recd_on,
                pe.paid_amount as received,
                c.customer_group,
                c.customer_name,
                pe.party as customer,
                'Customer' as party_type,
            pe.mode_of_payment,
            'Payment Entry' as payment_doctype
        FROM `tabPayment Entry` pe
        JOIN `tabCustomer` c ON pe.party = c.name
        WHERE pe.docstatus = 1 
          AND pe.party_type = 'Customer' 
          AND IFNULL(pe.mode_of_payment, '') != 'CQ'
          AND (pe.paid_from IN (SELECT name FROM `tabAccount` WHERE account_type = 'Receivable') 
               OR pe.paid_to IN (SELECT name FROM `tabAccount` WHERE account_type = 'Receivable'))
          {pe_cond}
        ORDER BY pe.posting_date ASC
        """, as_dict=True)
        payments_data.extend(c_payments_data)

        je_cond = ""
        if filters and filters.get("company"):
            je_cond += f" AND je.company = {frappe.db.escape(filters.get('company'))}"
        if party_cond:
            je_cond += f" AND jea.party {party_cond}"
        if filters and filters.get("customer_group"):
            je_cond += f" AND c.customer_group = {frappe.db.escape(filters.get('customer_group'))}"

        jv_data = frappe.db.sql(f"""
            SELECT 
                je.name,
                je.posting_date as recd_on,
                SUM(jea.credit_in_account_currency) as received,
                c.customer_group,
                c.customer_name,
                jea.party as customer,
                'Customer' as party_type,
            je.mode_of_payment,
            'Journal Entry' as payment_doctype
        FROM `tabJournal Entry` je
        JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
        JOIN `tabCustomer` c ON jea.party = c.name
        JOIN `tabAccount` a ON jea.account = a.name
        WHERE je.docstatus = 1 
          AND jea.party_type = 'Customer' 
          AND a.account_type = 'Receivable'
          AND jea.credit_in_account_currency > 0 
          {je_cond}
        GROUP BY je.name, jea.party
        """, as_dict=True)

        payments_data.extend(jv_data)

    if fetch_suppliers:
        conditions = ""
        
        party_cond = ""
        if filters and filters.get("party"):
            parties = filters.get("party")
            if isinstance(parties, str):
                parties = [parties]
            party_cond = " IN ({})".format(", ".join(frappe.db.escape(c) for c in parties))

        if filters and filters.get("company"):
            conditions += f" AND pi.company = {frappe.db.escape(filters.get('company'))}"
        if party_cond:
            conditions += f" AND pi.supplier {party_cond}"
        if filters and filters.get("customer_group"):
            conditions += f" AND pi.supplier_group = {frappe.db.escape(filters.get('customer_group'))}"
        
        p_invoices = frappe.db.sql(f"""
            SELECT 
                pi.name as actual_inv_no,
                pi.custom_inv_no as inv_no, 
                pi.posting_date as s_o_date,
                pi.supplier as customer,
                'Supplier' as party_type,
                pi.supplier_name as customer_name,
                pi.supplier_group as customer_group,
                pi.custom_via,
                pi.custom_com as com,
                pi.custom_cr_day as custom_payment_terms,
                pi.posting_date as original_due_date,
                pi.base_grand_total as bill_amt,
                pi.outstanding_amount,
                0 as discount_amount,
                'Purchase Invoice' as invoice_doctype
            FROM `tabPurchase Invoice` pi
            WHERE pi.docstatus = 1 {conditions}
        """, as_dict=True)
        invoices.extend(p_invoices)

        je_cond = ""
        if filters and filters.get("company"):
            je_cond += f" AND je.company = {frappe.db.escape(filters.get('company'))}"
        if party_cond:
            je_cond += f" AND jea.party {party_cond}"
        if filters and filters.get("customer_group"):
            je_cond += f" AND c.supplier_group = {frappe.db.escape(filters.get('customer_group'))}"

        jv_invoices = frappe.db.sql(f"""
            SELECT 
                je.name as actual_inv_no,
                'OPP' as inv_no, 
                je.posting_date as s_o_date,
                jea.party as customer,
                'Supplier' as party_type,
                c.supplier_name as customer_name,
                c.supplier_group as customer_group,
                '' as custom_via,
                je.mode_of_payment as com,
                0 as custom_payment_terms,
                je.posting_date as original_due_date,
                SUM(jea.credit_in_account_currency) as bill_amt,
                SUM(jea.credit_in_account_currency) as outstanding_amount,
                'Journal Entry' as invoice_doctype
            FROM `tabJournal Entry` je
            JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
            JOIN `tabSupplier` c ON jea.party = c.name
            JOIN `tabAccount` a ON jea.account = a.name
            WHERE je.docstatus = 1 
              AND jea.party_type = 'Supplier' 
              AND a.account_type = 'Payable'
              AND jea.credit_in_account_currency > 0
              {je_cond}
            GROUP BY je.name, jea.party
        """, as_dict=True)
        invoices.extend(jv_invoices)

        pe_cond = ""
        if filters and filters.get("company"):
            pe_cond += f" AND pe.company = {frappe.db.escape(filters.get('company'))}"
        if party_cond:
            pe_cond += f" AND pe.party {party_cond}"
        if filters and filters.get("customer_group"):
            pe_cond += f" AND c.supplier_group = {frappe.db.escape(filters.get('customer_group'))}"
            
        p_payments_data = frappe.db.sql(f"""
            SELECT 
                pe.name,
                pe.posting_date as recd_on,
                pe.paid_amount as received,
                c.supplier_group as customer_group,
                c.supplier_name as customer_name,
                pe.party as customer,
                'Supplier' as party_type,
                pe.mode_of_payment,
                'Payment Entry' as payment_doctype
            FROM `tabPayment Entry` pe
            JOIN `tabSupplier` c ON pe.party = c.name
            WHERE pe.docstatus = 1 
              AND pe.party_type = 'Supplier' 
              AND IFNULL(pe.mode_of_payment, '') != 'CQ'
              AND (pe.paid_from IN (SELECT name FROM `tabAccount` WHERE account_type = 'Payable') 
                   OR pe.paid_to IN (SELECT name FROM `tabAccount` WHERE account_type = 'Payable'))
              {pe_cond}
            ORDER BY pe.posting_date ASC
        """, as_dict=True)
        payments_data.extend(p_payments_data)

        je_cond = ""
        if filters and filters.get("company"):
            je_cond += f" AND je.company = {frappe.db.escape(filters.get('company'))}"
        if party_cond:
            je_cond += f" AND jea.party {party_cond}"
        if filters and filters.get("customer_group"):
            je_cond += f" AND c.supplier_group = {frappe.db.escape(filters.get('customer_group'))}"

        jv_data = frappe.db.sql(f"""
            SELECT 
                je.name,
                je.posting_date as recd_on,
                SUM(jea.debit_in_account_currency) as received,
                c.supplier_group as customer_group,
                c.supplier_name as customer_name,
                jea.party as customer,
                'Supplier' as party_type,
                je.mode_of_payment,
                'Journal Entry' as payment_doctype
            FROM `tabJournal Entry` je
            JOIN `tabJournal Entry Account` jea ON je.name = jea.parent
            JOIN `tabSupplier` c ON jea.party = c.name
            JOIN `tabAccount` a ON jea.account = a.name
            WHERE je.docstatus = 1 
              AND jea.party_type = 'Supplier' 
              AND a.account_type = 'Payable'
              AND jea.debit_in_account_currency > 0 
              {je_cond}
            GROUP BY je.name, jea.party
        """, as_dict=True)
        payments_data.extend(jv_data)

    invoices = [inv for inv in invoices if inv.customer != 'OPENING']
    payments_data = [pay for pay in payments_data if pay.customer != 'OPENING']

    payments_data.sort(key=lambda x: frappe.utils.getdate(x.recd_on) if x.recd_on else frappe.utils.getdate('1900-01-01'))

    clubbed_invoices = {}
    for inv in invoices:
        discount = inv.discount_amount or 0
        inv.bill_amt = (inv.bill_amt or 0) - discount
        inv.outstanding_amount = (inv.outstanding_amount or 0) - discount
        
        if inv.inv_no == 'OPP':
            club_key = ('OPP', inv.actual_inv_no)
        elif not inv.inv_no:
            club_key = ('NA', inv.actual_inv_no)
        else:
            club_key = (inv.com, inv.inv_no)
        if club_key not in clubbed_invoices:
            clubbed_invoices[club_key] = inv
        else:
            clubbed_invoices[club_key].bill_amt = (clubbed_invoices[club_key].bill_amt or 0) + (inv.bill_amt or 0)
            clubbed_invoices[club_key].outstanding_amount = (clubbed_invoices[club_key].outstanding_amount or 0) + (inv.outstanding_amount or 0)
            
    invoices = list(clubbed_invoices.values())

    grouped_invoices = {}
    for inv in invoices:
        party_key = inv.customer_group or inv.customer
        
        cr_days = frappe.utils.cint(inv.custom_payment_terms)
        if inv.s_o_date:
            inv.due_date = frappe.utils.add_days(inv.s_o_date, cr_days)
            inv.due_days = cr_days
        else:
            inv.due_date = inv.original_due_date
            inv.due_days = 0
            
        inv.party_key = party_key
        inv.remaining_balance = inv.bill_amt or 0
        
        if party_key not in grouped_invoices:
            grouped_invoices[party_key] = []
        grouped_invoices[party_key].append(inv)
        
    for pk in grouped_invoices:
        grouped_invoices[pk].sort(key=lambda x: frappe.utils.getdate(x.due_date) if x.due_date else frappe.utils.getdate('1900-01-01'))

    grouped_payments = {}
    for p in payments_data:
        party_key = p.customer_group or p.customer
        p.remaining = p.received or 0
        if party_key not in grouped_payments:
            grouped_payments[party_key] = []
        grouped_payments[party_key].append(p)

    data = []
    today = frappe.utils.nowdate()
    processed_pks = set()
    
    for party_key, inv_list in grouped_invoices.items():
        processed_pks.add(party_key)
        pays = grouped_payments.get(party_key, [])
        
        for inv in inv_list:
            inv_rows = []
            
            for pay in pays:
                if inv.remaining_balance <= 0:
                    break
                    
                if pay.remaining <= 0:
                    continue
                    
                pay_mode = (pay.get('mode_of_payment') or '').strip().upper()
                inv_com = (inv.get('com') or '').strip().upper()
                
                if pay_mode != inv_com:
                    if not pay_mode and inv_com == 'OPP':
                        pass
                    elif not inv_com and pay_mode == 'OPP':
                        pass
                    else:
                        continue
                    
                allocate = min(inv.remaining_balance, pay.remaining)
                inv.remaining_balance -= allocate
                pay.remaining -= allocate
                
                row = frappe._dict(inv)
                row.party = inv.customer
                row.party_type = inv.party_type
                row.via = inv.custom_via or ""
                row.rate = "1.25%"
                
                row.received = -allocate if inv.party_type == 'Customer' else allocate
                row.recd_on = pay.recd_on
                row.payment_entry = pay.name
                row.payment_doctype = pay.payment_doctype
                row.due_amt = ""
                
                if row.recd_on and row.due_date:
                    late_days = frappe.utils.date_diff(row.recd_on, row.due_date)
                    if late_days > 0:
                        row.late = late_days
                        row.interest = (allocate * 0.0125 * (late_days / 30.0))
                    else:
                        row.late = 0
                        row.interest = 0
                else:
                    row.late = 0
                    row.interest = 0
                    
                inv_rows.append(row)
            
            if inv.remaining_balance > 0:
                row = frappe._dict(inv)
                row.party = inv.customer
                row.party_type = inv.party_type
                row.via = inv.custom_via or ""
                row.rate = "1.25%"
                
                row.received = 0
                row.recd_on = None
                row.due_amt = inv.remaining_balance
                
                if row.due_date and frappe.utils.getdate(today) > frappe.utils.getdate(row.due_date):
                    late_days = frappe.utils.date_diff(today, row.due_date)
                    row.late = late_days
                    row.interest = (row.due_amt * 0.0125 * (late_days / 30.0))
                else:
                    row.late = 0
                    row.interest = 0
                
                inv_rows.append(row)
            else:
                if inv_rows:
                    inv_rows[-1].due_amt = 0
                    
            if filters and filters.get("hide_non_due") and inv.remaining_balance <= 0:
                continue
                
            for i, r in enumerate(inv_rows):
                if i > 0:
                    r.bill_amt = ""
                
                if r.invoice_doctype == 'Purchase Invoice':
                    if not r.inv_no or str(r.inv_no).strip() == '':
                        r.inv_no = 'PUR'
                elif r.invoice_doctype == 'Sales Invoice':
                    if not r.inv_no or str(r.inv_no).strip() == '':
                        r.inv_no = 'SAL'
                
                data.append(r)

        for pay in pays:
            if pay.remaining > 0:
                row = frappe._dict()
                row.actual_inv_no = pay.name
                row.inv_no = "ADV"
                row.invoice_doctype = pay.payment_doctype
                row.customer = pay.customer
                row.customer_name = pay.customer_name
                row.customer_group = pay.customer_group
                row.party = pay.customer
                row.party_type = pay.party_type
                row.s_o_date = pay.recd_on
                row.original_due_date = pay.recd_on
                row.due_date = pay.recd_on
                row.bill_amt = ""
                row.outstanding_amount = ""
                row.due_amt = -pay.remaining
                row.received = -pay.remaining if pay.party_type == 'Customer' else pay.remaining
                row.recd_on = pay.recd_on
                row.payment_entry = pay.name
                row.payment_doctype = pay.payment_doctype
                row.late = 0
                row.interest = 0
                row.via = ""
                row.rate = ""
                data.append(row)

    for party_key, pays in grouped_payments.items():
        if party_key not in processed_pks:
            for pay in pays:
                if pay.remaining > 0:
                    row = frappe._dict()
                    row.actual_inv_no = pay.name
                    row.inv_no = "ADV"
                    row.invoice_doctype = pay.payment_doctype
                    row.customer = pay.customer
                    row.customer_name = pay.customer_name
                    row.customer_group = pay.customer_group
                    row.party = pay.customer
                    row.s_o_date = pay.recd_on
                    row.original_due_date = pay.recd_on
                    row.due_date = pay.recd_on
                    row.bill_amt = ""
                    row.outstanding_amount = ""
                    row.due_amt = -pay.remaining
                    row.received = -pay.remaining if pay.party_type == 'Customer' else pay.remaining
                    row.recd_on = pay.recd_on
                    row.payment_entry = pay.name
                    row.payment_doctype = pay.payment_doctype
                    row.late = 0
                    row.interest = 0
                    row.via = ""
                    row.rate = ""
                    data.append(row)

    return data
