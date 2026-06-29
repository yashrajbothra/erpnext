import frappe
from frappe import _

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	
	modulated_data = []
	item_sequence = [
		'BA/2B COIL (>800)', 'Coil (1250+)', 'Coil (1240)', 'Coil (Other Sizes)', 
		'NO 8 PVC SHEET', 'BABY COIL', 'Circle', 'Sheet', 'Scrap'
	]
	
	# Group data
	item_groups = {}
	for row in data:
		itype = row.get("item_type") or "Other"
		finish = (row.get("finish") or "").upper()
		
		if itype.lower() == 'coil' and row.get("size"):
			try:
				import re
				size_val = frappe.utils.flt(re.search(r'(\d+\.?\d*)', str(row.get("size"))).group(1))
				
				# Priority Group: BA/2B COIL (>800)
				if finish in ['BA', '2B'] and size_val > 800:
					itype = 'BA/2B COIL (>800)'
				elif size_val >= 1250:
					itype = 'Coil (1250+)'
				elif size_val == 1240:
					itype = 'Coil (1240)'
				else:
					itype = 'Coil (Other Sizes)'
			except:
				pass
		elif itype.lower() == 'sheet' and finish in ['NO 8 PVC', 'NO - 8 PVC']:
			itype = 'NO 8 PVC SHEET'
		
		if itype not in item_groups:
			item_groups[itype] = []
		item_groups[itype].append(row)
	
	for itype in item_sequence:
		rows = item_groups.get(itype)
		if not rows:
			continue
		
		# Sort by date ascending (Older first)
		rows.sort(key=lambda x: str(x.get("date") or ""))
		
		total_pcs = 0
		total_weight = 0
		last_date = None
		
		for row in rows:
			# Gap row if date changes
			if last_date and row.get("date") != last_date:
				modulated_data.append({"pkt_no": ""})
			last_date = row.get("date")
			
			modulated_data.append(row)
			total_pcs += float(row.get("pieces") or 0)
			total_weight += float(row.get("weight") or 0)
			
		# Total row
		modulated_data.append({
			"grade": "<b>TOTAL</b>",
			"pieces": total_pcs,
			"weight": total_weight,
		})
		
		# Blank rows as gap
		modulated_data.append({"pkt_no": ""})
		modulated_data.append({"pkt_no": ""})

	return columns, modulated_data

def get_columns():
	return [
		{
			"label": _("PKT/COIL NO."),
			"fieldname": "pkt_no",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("THIK"),
			"fieldname": "thickness",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("SIZE"),
			"fieldname": "size",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("GRADE"),
			"fieldname": "grade",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("FINISH"),
			"fieldname": "finish",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("PCS/PKT"),
			"fieldname": "pieces",
			"fieldtype": "Float",
			"width": 80
		},
		{
			"label": _("N. WEIGHT"),
			"fieldname": "weight",
			"fieldtype": "Float",
			"width": 120
		},
		{
			"label": _("PLOT"),
			"fieldname": "plot",
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 120
		},
		{
			"label": _("CODE"),
			"fieldname": "code",
			"fieldtype": "Data",
			"width": 100
		},
		{
			"label": _("HSN CODE"),
			"fieldname": "hsn",
			"fieldtype": "Data",
			"width": 120
		},
		{
			"label": _("R. DATE"),
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 100
		},
		{
			"label": _("L. DAY"),
			"fieldname": "l_days",
			"fieldtype": "Int",
			"width": 80
		}
	]

def get_data(filters):
	if not filters:
		filters = {}
	
	item_group = filters.get("item_group")
	
	query = """
		SELECT
			sle.custom_specification_key as goto,
			sle.posting_date as date,
			i.item_group as item_type,
			g.attribute_value AS grade,
			t.attribute_value AS type,
			f.attribute_value AS finish,
			sle.warehouse as plot,
			sle.custom_pkt_no as pkt_no,
			sle.custom_hsn_code as hsn,
			sle.custom_code as code,
			sle.custom_size as size,
			CASE 
				WHEN sle.custom_nb IS NOT NULL AND sle.custom_nb != '' 
				THEN sle.custom_nb 
				ELSE sle.custom_od 
			END AS od,
			sle.custom_schedule AS schedule,
			sle.custom_thickness AS thickness,
			sle.custom_pieces as pieces,
			sle.actual_qty as weight,
			DATEDIFF(CURDATE(), sle.posting_date) AS l_days

		FROM `tabItem` i
		JOIN `tabStock Ledger Entry` sle ON sle.item_code = i.name AND sle.docstatus < 2
		LEFT JOIN `tabItem Variant Attribute` g
			ON g.parent = i.name AND g.attribute = 'Grade'
		LEFT JOIN `tabItem Variant Attribute` t
			ON t.parent = i.name AND t.attribute = 'Type'
		LEFT JOIN `tabItem Variant Attribute` f
			ON f.parent = i.name AND f.attribute = 'Finish'

		WHERE (%(item_group)s IS NULL OR i.item_group = %(item_group)s)
		AND LOWER(i.item_group) = 'pipe'

		ORDER BY sle.posting_date ASC, sle.posting_time ASC
	"""
	return frappe.db.sql(query, {"item_group": item_group}, as_dict=1)
