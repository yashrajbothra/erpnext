import frappe
from frappe import _

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	
	modulated_data = []
	item_sequence = [
		'410 GRADE', 'TRIPLY CIRCLE', '304 BA/2B (COIL & SHEET) (>800)', '316L BA/2B (COIL & SHEET) (>800)', 'Coil (1250+)', 'Coil (1240)', 'Coil (Other Sizes)', 
		'NO 4 PVC (COIL & SHEET)', 'J3 NO 8 PVC SHEET', '304 NO 8 PVC SHEET', 'J3 SHEET', '304 SHEET',
		'BABY COIL', 'Circle', 'Sheet', 'Scrap'
	]
	
	# Group data
	item_groups = {}
	for row in data:
		itype = row.get("item_type") or "Other"
		finish = (row.get("finish") or "").upper()
		grade = (row.get("grade") or "").upper()
		
		# Priority Group: 410 Grade
		if '410' in grade:
			itype = '410 GRADE'
		elif itype.lower() == 'circle' and ('TRIPLY' in grade or 'TRIPLY' in finish):
			itype = 'TRIPLY CIRCLE'
		else:
			try:
				import re
				size_val = frappe.utils.flt(re.search(r'(\d+\.?\d*)', str(row.get("size"))).group(1))
				if finish in ['BA', '2B'] and size_val > 800:
					if '316L' in grade:
						itype = '316L BA/2B (COIL & SHEET) (>800)'
					else:
						itype = '304 BA/2B (COIL & SHEET) (>800)'
			except:
				size_val = 0

		if itype in ['304 BA/2B (COIL & SHEET) (>800)', '316L BA/2B (COIL & SHEET) (>800)']:
			pass # already set
		elif itype == 'TRIPLY CIRCLE':
			pass
		elif finish == 'NO 4 PVC':
			itype = 'NO 4 PVC (COIL & SHEET)'
		elif itype.lower() == 'coil' and row.get("size"):
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
	
	conditions = ["sle.docstatus < 2"]
	if filters.get("item_group"):
		conditions.append("i.item_group = %(item_group)s")
	
	conditions.append("LOWER(i.item_group) != 'pipe'")

	where_clause = " AND ".join(conditions)
	
	db_columns = [c[0] for c in frappe.db.sql("SHOW COLUMNS FROM `tabStock Ledger Entry`")]
	has_party = "custom_party" in db_columns
	has_by = "custom_by" in db_columns
	
	party_select = "MAX(sle.custom_party) as party," if has_party else "'' as party,"
	by_select = "MAX(sle.custom_by) as by_col," if has_by else "'' as by_col,"

	query = f"""
		SELECT
			MAX(sle.custom_specification_key) as goto,
			MAX(sle.posting_date) as date,
			i.item_group as item_type,
			g.attribute_value AS grade,
			t.attribute_value AS type,
			f.attribute_value AS finish,
			SUBSTRING_INDEX(sle.warehouse, ' - ', 1) as plot,
			sle.custom_pkt_no as pkt_no,
			MAX(sle.custom_hsn_code) as hsn,
			MAX(sle.custom_code) as code,
			MAX(sle.custom_size) as size,
			{party_select}
			{by_select}
			MAX(CASE 
				WHEN sle.custom_nb IS NOT NULL AND sle.custom_nb != '' 
				THEN sle.custom_nb 
				ELSE sle.custom_od 
			END) AS od,
			MAX(CASE 
				WHEN sle.custom_schedule IS NOT NULL AND sle.custom_schedule != '' 
				THEN sle.custom_schedule 
				ELSE sle.custom_thickness 
			END) AS thickness,
			SUM(sle.custom_pieces) as pieces,
			SUM(sle.actual_qty) as weight,
			DATEDIFF(CURDATE(), MAX(sle.posting_date)) AS l_days

		FROM `tabItem` i
		JOIN `tabStock Ledger Entry` sle ON sle.item_code = i.name
		LEFT JOIN `tabItem Variant Attribute` g
			ON g.parent = i.name AND g.attribute = 'Grade'
		LEFT JOIN `tabItem Variant Attribute` t
			ON t.parent = i.name AND t.attribute = 'Type'
		LEFT JOIN `tabItem Variant Attribute` f
			ON f.parent = i.name AND f.attribute = 'Finish'

		WHERE {where_clause}

		GROUP BY 
			sle.item_code,
			sle.warehouse,
			sle.custom_pkt_no,
			i.item_group,
			g.attribute_value,
			t.attribute_value,
			f.attribute_value

		HAVING ROUND(SUM(sle.actual_qty), 4) != 0

		ORDER BY MAX(sle.posting_date) ASC, MAX(sle.posting_time) ASC
	"""
	return frappe.db.sql(query, filters, as_dict=1)
