import frappe
from frappe import _
from frappe.utils import flt
import re

@frappe.whitelist()
def get_summary_data(filters=None):
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)
    
    if not filters:
        filters = {}

    item_group = filters.get("item_group") or None
    
    # 1. Get all items with stock from Stock Ledger Entry
    query = """
        SELECT
            sle.item_code,
            SUM(sle.actual_qty) as weight,
            sle.warehouse,
            g.attribute_value as grade,
            f.attribute_value as finish,
            t.attribute_value as type,
            i.item_group as item_type
        FROM `tabStock Ledger Entry` sle
        JOIN `tabItem` i ON i.name = sle.item_code
        LEFT JOIN `tabItem Variant Attribute` g ON g.parent = i.name AND g.attribute = 'Grade'
        LEFT JOIN `tabItem Variant Attribute` f ON f.parent = i.name AND f.attribute = 'Finish'
        LEFT JOIN `tabItem Variant Attribute` t ON t.parent = i.name AND t.attribute = 'Type'
        WHERE sle.is_cancelled = 0
        AND (%(item_group)s IS NULL OR %(item_group)s = '' OR i.item_group = %(item_group)s)
        GROUP BY sle.item_code, sle.warehouse
        HAVING SUM(sle.actual_qty) > 0
    """
    bins = frappe.db.sql(query, {"item_group": item_group}, as_dict=1)

    if not bins:
        return []

    # 2. Get latest SLE info for all bins (Valuation Rate and Size)
    # This avoids the subquery per row which can be slow
    latest_sle_info = frappe.db.sql("""
        SELECT 
            sle.item_code, 
            sle.warehouse, 
            sle.valuation_rate,
            sle.custom_size as size
        FROM `tabStock Ledger Entry` sle
        INNER JOIN (
            SELECT item_code, warehouse, MAX(name) as max_name
            FROM `tabStock Ledger Entry`
            WHERE is_cancelled = 0
            GROUP BY item_code, warehouse
        ) latest ON sle.name = latest.max_name
    """, as_dict=1)
    
    info_map = {(r.item_code, r.warehouse): r for r in latest_sle_info}
    
    # Grouping logic
    item_sequence = [
        '410 GRADE', 'TRIPLY CIRCLE', '304 BA/2B (COIL & SHEET) (>800)', '316L BA/2B (COIL & SHEET) (>800)', 'Coil (1250+)', 'Coil (1240)', 'Coil (Other Sizes)', 
        'NO 4 PVC (COIL & SHEET)', 'J3 NO 8 PVC SHEET', '304 NO 8 PVC SHEET', 'J3 SHEET', '304 SHEET',
        'BABY COIL', 'Circle', 'Sheet', 'Scrap'
    ]

    grouped_data = {}

    for b in bins:
        itype = b.get("item_type") or "Other"
        finish = (b.get("finish") or "").upper()
        grade = (b.get("grade") or "").upper()
        
        if itype.lower() == "pipe":
            pipe_type = (b.get("type") or "").strip().upper()
            pipe_type_full = "WELDED" if pipe_type in ["W", "WELDED"] else "SEAMLESS" if pipe_type in ["S", "SEAMLESS"] else pipe_type
            if pipe_type_full:
                finish = f"{pipe_type_full} {finish}".strip()
        
        info = info_map.get((b.item_code, b.warehouse), {})
        size_str = str(info.get("size") or "")
        
        try:
            match = re.search(r'(\d+\.?\d*)', size_str)
            size_val = flt(match.group(1)) if match else 0
        except:
            size_val = 0

        # Category logic (matching stock_ledger_custom_view.py)
        if '410' in grade:
            itype = '410 GRADE'
        elif itype.lower() == 'circle' and ('TRIPLY' in grade or 'TRIPLY' in finish):
            itype = 'TRIPLY CIRCLE'
        elif (finish == 'BA' or finish == '2B') and size_val > 800:
            if '316L' in grade:
                itype = '316L BA/2B (COIL & SHEET) (>800)'
            else:
                itype = '304 BA/2B (COIL & SHEET) (>800)'
        elif finish == 'NO 4 PVC':
            itype = 'NO 4 PVC (COIL & SHEET)'
        elif itype.lower() == 'coil' and size_str:
            if size_val >= 1250:
                itype = 'Coil (1250+)'
            elif size_val == 1240:
                itype = 'Coil (1240)'
            else:
                itype = 'Coil (Other Sizes)'
        elif itype.lower() == 'sheet' and finish in ['NO 8 PVC', 'NO - 8 PVC']:
            if '304' in grade:
                itype = '304 NO 8 PVC SHEET'
            else:
                itype = 'J3 NO 8 PVC SHEET'
        elif itype.lower() == 'sheet' and 'J3' in grade:
            itype = 'J3 SHEET'
        elif itype.lower() == 'sheet' and '304' in grade:
            itype = '304 SHEET'

        if itype not in grouped_data:
            grouped_data[itype] = {}

        key = (grade, finish)
        if key not in grouped_data[itype]:
            grouped_data[itype][key] = {
                "grade": grade,
                "finish": finish,
                "weight": 0,
                "amount": 0
            }
        
        rate = flt(info.get("valuation_rate", 0))
        weight = flt(b.weight)
        
        grouped_data[itype][key]["weight"] += weight
        grouped_data[itype][key]["amount"] += weight * rate

    result = []
    # Process by sequence
    for category in item_sequence:
        if category in grouped_data:
            rows = []
            cat_weight = 0
            cat_amount = 0
            for key, val in grouped_data[category].items():
                val["rate"] = val["amount"] / val["weight"] if val["weight"] > 0 else 0
                rows.append(val)
                cat_weight += val["weight"]
                cat_amount += val["amount"]
            
            rows.sort(key=lambda x: (x["grade"], x["finish"]))
            result.append({"category": category, "rows": rows, "total_weight": cat_weight, "total_amount": cat_amount})
            del grouped_data[category]

    # Remaining
    remaining_cats = sorted(grouped_data.keys())
    for category in remaining_cats:
        items = grouped_data[category]
        rows = []
        cat_weight = 0
        cat_amount = 0
        for key, val in items.items():
            val["rate"] = val["amount"] / val["weight"] if val["weight"] > 0 else 0
            rows.append(val)
            cat_weight += val["weight"]
            cat_amount += val["amount"]
        
        rows.sort(key=lambda x: (x["grade"], x["finish"]))
        result.append({"category": category, "rows": rows, "total_weight": cat_weight, "total_amount": cat_amount})

    return result
