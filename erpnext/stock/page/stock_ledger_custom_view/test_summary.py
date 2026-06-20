import frappe

def get_test_data():
    query = """
        SELECT
            i.item_group as item_type,
            g.attribute_value AS grade,
            f.attribute_value AS finish,
            sle.actual_qty as weight,
            sle.valuation_rate as rate
        FROM `tabItem` i
        JOIN `tabStock Ledger Entry` sle ON sle.item_code = i.name AND sle.docstatus < 2
        LEFT JOIN `tabItem Variant Attribute` g
            ON g.parent = i.name AND g.attribute = 'Grade'
        LEFT JOIN `tabItem Variant Attribute` f
            ON f.parent = i.name AND f.attribute = 'Finish'
        WHERE sle.is_cancelled = 0
        AND i.item_group != 'Pipe'
    """
    data = frappe.db.sql(query, as_dict=1)
    
    summary = {}
    for d in data:
        key = (d.grade or "N/A", d.finish or "N/A")
        if key not in summary:
            summary[key] = {"weight": 0, "amount": 0}
        
        weight = float(d.weight or 0)
        rate = float(d.rate or 0)
        summary[key]["weight"] += weight
        summary[key]["amount"] += weight * rate
        
    return summary

if __name__ == "__main__":
    res = get_test_data()
    for k, v in res.items():
        if v["weight"] > 0:
            print(f"{k}: {v}")
