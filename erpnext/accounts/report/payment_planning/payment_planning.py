import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": _("S. O. DATE"), "fieldname": "s_o_date", "fieldtype": "Date", "width": 100},
        {"label": _("PARTY"), "fieldname": "party", "fieldtype": "Data", "width": 150},
        {"label": _("VIA"), "fieldname": "via", "fieldtype": "Data", "width": 80},
        {"label": _("COM"), "fieldname": "com", "fieldtype": "Data", "width": 100},
        {"label": _("INV. NO"), "fieldname": "inv_no", "fieldtype": "Data", "width": 120},
        {"label": _("Actual Inv No"), "fieldname": "actual_inv_no", "fieldtype": "Data", "hidden": 1},
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
    conditions = " AND IFNULL(si.custom_inv_no, '') != ''"
    if filters and filters.get("company"):
        conditions += f" AND si.company = {frappe.db.escape(filters.get('company'))}"
    if filters and filters.get("customer"):
        conditions += f" AND si.customer = {frappe.db.escape(filters.get('customer'))}"
    
    invoices = frappe.db.sql(f"""
        SELECT 
            si.name as actual_inv_no,
            si.custom_inv_no as inv_no, 
            si.posting_date as s_o_date,
            si.customer,
            si.customer_name,
            si.customer_group,
            si.custom_via,
            si.custom_com as com,
            si.custom_payment_terms,
            si.due_date as original_due_date,
            si.grand_total as bill_amt,
            si.outstanding_amount
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1 {{conditions}}
        ORDER BY si.posting_date ASC
    """.format(conditions=conditions), as_dict=True)

    data = []
    
    for inv in invoices:
        payments = frappe.db.sql("""
            SELECT 
                pe.name, 
                pe.posting_date as recd_on,
                per.allocated_amount as received
            FROM `tabPayment Entry` pe
            JOIN `tabPayment Entry Reference` per ON pe.name = per.parent
            WHERE pe.docstatus = 1 
              AND per.reference_doctype = 'Sales Invoice'
              AND per.reference_name = %s
            ORDER BY pe.posting_date ASC
        """, (inv.actual_inv_no,), as_dict=True)
        
        cr_days = frappe.utils.cint(inv.custom_payment_terms)
        if inv.s_o_date:
            inv.due_date = frappe.utils.add_days(inv.s_o_date, cr_days)
            due_days = cr_days
        else:
            inv.due_date = inv.original_due_date
            due_days = 0
            
        if payments:
            for i, p in enumerate(payments):
                row = frappe._dict(inv)
                row.party = inv.customer_group if inv.customer_group else (inv.customer_name or inv.customer)
                row.via = inv.custom_via or ""
                row.rate = "1.25%"
                row.due_days = due_days
                
                row.received = p.received
                row.recd_on = p.recd_on
                
                if i == len(payments) - 1:
                    row.due_amt = inv.outstanding_amount
                else:
                    row.due_amt = ""
                
                if row.recd_on and row.due_date:
                    late_days = frappe.utils.date_diff(row.recd_on, row.due_date)
                    if late_days > 0:
                        row.late = late_days
                        row.interest = (row.received * 0.0125 * (late_days / 30.0))
                    else:
                        row.late = 0
                        row.interest = 0
                else:
                    row.late = 0
                    row.interest = 0
                
                data.append(row)
        
        if not payments and inv.outstanding_amount > 0:
            row = frappe._dict(inv)
            row.party = inv.customer_group if inv.customer_group else (inv.customer_name or inv.customer)
            row.via = inv.custom_via or ""
            row.rate = "1.25%"
            row.due_days = due_days
            row.received = 0
            row.recd_on = None
            row.due_amt = inv.outstanding_amount
            
            today = frappe.utils.nowdate()
            if row.due_date and frappe.utils.getdate(today) > frappe.utils.getdate(row.due_date):
                late_days = frappe.utils.date_diff(today, row.due_date)
                row.late = late_days
                row.interest = (row.due_amt * 0.0125 * (late_days / 30.0))
            else:
                row.late = 0
                row.interest = 0
                
            data.append(row)

    return data
