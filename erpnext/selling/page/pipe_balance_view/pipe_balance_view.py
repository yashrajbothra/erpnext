import frappe
from erpnext.stock.report.pipe_balance.pipe_balance import get_data as get_report_data

@frappe.whitelist()
def get_dashboard_data(filters=None):
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)
    
    data = get_report_data(filters)
    
    # Calculate summary stats
    total_weight = sum(d.get("weight", 0) for d in data)
    total_nos = sum(d.get("nos", 0) for d in data)
    unique_packets = len(set(d.get("pkt_no") for d in data if d.get("pkt_no")))
    
    # Oldest received date
    dates = [d.get("r_date") for d in data if d.get("r_date")]
    oldest_date = min(dates) if dates else None
    
    return {
        "data": data,
        "stats": {
            "total_weight": total_weight,
            "total_nos": total_nos,
            "unique_packets": unique_packets,
            "oldest_date": oldest_date
        }
    }

@frappe.whitelist()
def export_to_excel(filters=None):
    if isinstance(filters, str):
        import json
        filters = json.loads(filters)
    
    data = get_report_data(filters)
    
    from collections import OrderedDict
    groups = OrderedDict()
    for row in data:
        pkt_no = row.get("pkt_no")
        if not pkt_no: continue
        if pkt_no not in groups:
            groups[pkt_no] = []
        groups[pkt_no].append(row)
    
    xlsx_data = []
    columns = [
        "R DATE", "GRADE", "FINISH", "TYPE", "OD", "THIK", "LENGTH", "NOS", "WEIGHT", "PLOT", "L DAY"
    ]
    
    for pkt_no, rows in groups.items():
        if sum(float(r.get("weight") or 0) for r in rows) <= 0.001 and sum(float(r.get("nos") or 0) for r in rows) <= 0.001:
            continue

        # Packet Header
        xlsx_data.append([f"PACKET: {pkt_no}"])
        # Table Headers
        xlsx_data.append(columns)
        
        total_nos = 0
        total_weight = 0
        
        for row in rows:
            xlsx_data.append([
                row.get("r_date"),
                row.get("grade"),
                row.get("finish"),
                row.get("type"),
                row.get("od"),
                row.get("thik"),
                row.get("length"),
                row.get("nos"),
                row.get("weight"),
                row.get("warehouse"),
                row.get("l_days")
            ])
            total_nos += float(row.get("nos") or 0)
            total_weight += float(row.get("weight") or 0)
        
        # Total row
        xlsx_data.append(["", "", "", "", "", "", "TOTAL:", total_nos, total_weight, "", ""])
        # Blank rows for separation
        xlsx_data.append([])
        xlsx_data.append([])

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from io import BytesIO

    wb = Workbook()
    ws = wb.active
    ws.title = "Pipe Balance"
    
    bold_font = Font(bold=True)
    yellow_fill = PatternFill(start_color='FFFF00', end_color='FFFF00', fill_type='solid')

    for row_data in xlsx_data:
        ws.append(row_data)
        if not row_data:
            continue
        
        current_row = ws.max_row
        is_packet_header = str(row_data[0]).startswith("PACKET:")
        is_table_header = row_data[0] == "R DATE"
        is_total_row = len(row_data) > 6 and row_data[6] == "TOTAL:"
        
        # Bold formatting
        if is_packet_header or is_table_header or is_total_row:
            for cell in ws[current_row]:
                cell.font = bold_font
        
        # Yellow background for sold rows (Weight <= 0.001)
        # Skip headers and total rows
        elif not is_packet_header and not is_table_header and not is_total_row:
            if len(row_data) > 8 and isinstance(row_data[8], (int, float)) and row_data[8] <= 0.001:
                for cell in ws[current_row]:
                    cell.fill = yellow_fill

    xlsx_file = BytesIO()
    wb.save(xlsx_file)
    
    frappe.response['filename'] = f"Pipe_Balance.xlsx"
    frappe.response['filecontent'] = xlsx_file.getvalue()
    frappe.response['type'] = 'download'
