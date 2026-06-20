import frappe
from frappe import _

def execute(filters=None):
    if not filters:
        filters = frappe._dict()

    from erpnext.stock.page.sm54_stock_summary.sm54_stock_summary import get_summary_data
    res = get_summary_data(filters)
    
    summary_data = res.get("summary_data") or []
    
    columns = [
        _("Grade") + ":Data:120",
        _("Size") + ":Data:120",
        _("OD / Schedule") + ":Data:150",
        _("Warehouse") + ":Link/Warehouse:180",
        _("Pcs") + ":Float:100",
        _("Weight (Kg)") + ":Float:120"
    ]
    
    rows = []
    for row in summary_data:
        for wh_entry in row.get("warehouses") or []:
            rows.append([
                row.get("grade"),
                row.get("size"),
                row.get("schedule"),
                wh_entry.get("warehouse"),
                wh_entry.get("pcs"),
                wh_entry.get("weight")
            ])
            
    total_pcs = sum(float(r[4] or 0) for r in rows)
    total_weight = sum(float(r[5] or 0) for r in rows)

    rows.append([
        _("Total"),
        "",
        "",
        "",
        total_pcs,
        total_weight
    ])

    return columns, rows, None, None
