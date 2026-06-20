import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = frappe._dict()

    from erpnext.stock.page.sm54_stock_summary.sm54_stock_summary import get_summary_data
    res = get_summary_data(filters)
    
    summary_data = res.get("summary_data") or []
    
    columns = [
        {"label": _("Grade"), "fieldname": "grade", "fieldtype": "Data", "width": 120},
        {"label": _("Size"), "fieldname": "size", "fieldtype": "Data", "width": 120},
        {"label": _("OD / Schedule"), "fieldname": "schedule", "fieldtype": "Data", "width": 150},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 180},
        {"label": _("Pcs"), "fieldname": "pcs", "fieldtype": "Float", "width": 100},
        {"label": _("Weight (Kg)"), "fieldname": "weight", "fieldtype": "Float", "width": 120},
    ]
    
    rows = []
    for row in summary_data:
        for wh_entry in row.get("warehouses") or []:
            rows.append({
                "grade": row.get("grade"),
                "size": row.get("size"),
                "schedule": row.get("schedule"),
                "warehouse": wh_entry.get("warehouse"),
                "pcs": wh_entry.get("pcs"),
                "weight": wh_entry.get("weight")
            })
            
    total_pcs = sum(float(r["pcs"] or 0) for r in rows)
    total_weight = sum(float(r["weight"] or 0) for r in rows)

    rows.append({
        "grade": f"<b>{_('Total')}</b>",
        "size": "",
        "schedule": "",
        "warehouse": "",
        "pcs": total_pcs,
        "weight": total_weight,
        "is_subtotal": True,
        "is_total": True,
        "is_total_row": True
    })

    return columns, rows, None, None
