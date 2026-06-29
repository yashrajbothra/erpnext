# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import copy
from collections import defaultdict

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt, get_datetime

from erpnext.stock.doctype.inventory_dimension.inventory_dimension import get_inventory_dimensions
from erpnext.stock.doctype.serial_no.serial_no import get_serial_nos
from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import get_stock_balance_for
from erpnext.stock.doctype.warehouse.warehouse import apply_warehouse_filter
from erpnext.stock.utils import (
	is_reposting_item_valuation_in_progress,
	update_included_uom_in_report,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	is_reposting_item_valuation_in_progress()
	include_uom = filters.get("include_uom")
	columns = get_columns(filters)
	items = get_items(filters)
	sl_entries = get_stock_ledger_entries(filters, items)
	item_details = get_item_details(items, sl_entries, include_uom)

	inv_dimension_key = []
	inv_dimension_wise_value = get_inv_dimension_wise_value(filters)
	if inv_dimension_wise_value:
		for key in inv_dimension_wise_value:
			value = inv_dimension_wise_value[key]
			if isinstance(value, list):
				inv_dimension_key.extend(value)
			else:
				inv_dimension_key.append(value)

	if filters.get("batch_no"):
		opening_row = get_opening_balance_from_batch(filters, columns, sl_entries)
	elif inv_dimension_wise_value:
		opening_row = get_opening_balance_for_inv_dimension(filters, inv_dimension_wise_value)
	else:
		opening_row = get_opening_balance(filters, columns, sl_entries, inv_dimension_wise_value)

	precision = cint(frappe.db.get_single_value("System Settings", "float_precision"))
	bundle_details = {}

	if filters.get("segregate_serial_batch_bundle"):
		bundle_details = get_serial_batch_bundle_details(sl_entries, filters)

	data = []
	conversion_factors = []
	if opening_row:
		data.append(opening_row)
		conversion_factors.append(0)

	actual_qty = stock_value = 0
	if opening_row:
		actual_qty = opening_row.get("qty_after_transaction")
		stock_value = opening_row.get("stock_value")

	available_serial_nos = {}

	batch_balances = {}
	items_list = list(set(sle.item_code for sle in sl_entries))
	warehouses_list = list(set(sle.warehouse for sle in sl_entries))

	if items_list and warehouses_list:
		q1_sql = f"""
			SELECT
				item_code, warehouse, batch_no,
				SUM(actual_qty) as qty,
				SUM(stock_value_difference) as stock_value,
				SUM(CASE WHEN actual_qty > 0 THEN custom_pieces WHEN actual_qty < 0 THEN -custom_pieces ELSE 0 END) as pieces
			FROM `tabStock Ledger Entry`
			WHERE docstatus = 1 AND is_cancelled = 0
			AND posting_date < %s AND company = %s
			AND item_code IN ({', '.join(['%s'] * len(items_list))})
			AND warehouse IN ({', '.join(['%s'] * len(warehouses_list))})
			GROUP BY item_code, warehouse, batch_no
		"""
		for row in frappe.db.sql(q1_sql, [filters.from_date, filters.company] + items_list + warehouses_list, as_dict=True):
			b_key = (row.item_code, row.warehouse, row.batch_no or "")
			batch_balances[b_key] = [flt(row.qty), flt(row.stock_value), flt(row.pieces)]

		sle_t = frappe.qb.DocType("Stock Ledger Entry")
		sbe_t = frappe.qb.DocType("Serial and Batch Entry")
		q2 = (
			frappe.qb.from_(sle_t)
			.inner_join(sbe_t)
			.on(sle_t.serial_and_batch_bundle == sbe_t.parent)
			.select(
				sle_t.item_code,
				sle_t.warehouse,
				sbe_t.batch_no,
				sbe_t.qty,
				sle_t.actual_qty,
				sle_t.custom_pieces,
				sle_t.voucher_type,
				sbe_t.stock_value_difference.as_("stock_value"),
			)
			.where(
				(sle_t.docstatus == 1)
				& (sle_t.is_cancelled == 0)
				& (sle_t.posting_date < filters.from_date)
				& (sle_t.company == filters.company)
				& (sle_t.item_code.isin(items_list))
				& (sle_t.warehouse.isin(warehouses_list))
			)
		)
		for row in q2.run(as_dict=True):
			b_key = (row.item_code, row.warehouse, row.batch_no or "")
			if b_key not in batch_balances:
				batch_balances[b_key] = [0.0, 0.0, 0.0]
			batch_balances[b_key][0] += flt(row.qty)
			batch_balances[b_key][1] += flt(row.stock_value)

			# Calculate pieces proportionally for bundle entries
			pieces = flt(row.custom_pieces) * (flt(row.qty) / flt(row.actual_qty)) if row.actual_qty else 0.0
			if flt(row.qty) < 0:
				pieces = -abs(pieces)
			elif flt(row.qty) > 0:
				pieces = abs(pieces)
			else:
				pieces = 0.0
			batch_balances[b_key][2] += pieces

	if opening_row and filters.get("batch_no"):
		for b_key in list(batch_balances.keys()):
			if b_key[2] == filters.batch_no:
				batch_balances[b_key] = [flt(opening_row.get("qty_after_transaction")), flt(opening_row.get("stock_value")), flt(opening_row.get("balance_pieces"))]

	inv_dimension_wise_dict = frappe._dict({})
	set_opening_row_for_inv_dimension(
		inv_dimension_wise_dict, filters, inv_dimension_key=inv_dimension_key, opening_row=opening_row
	)

	for sle in sl_entries:
		item_detail = item_details[sle.item_code]

		sle.update(item_detail)
		if bundle_info := bundle_details.get(sle.serial_and_batch_bundle):
			data.extend(get_segregated_bundle_entries(sle, bundle_info, batch_balances, filters))
			continue

		if inv_dimension_key:
			set_balance_value_for_inv_dimesion(inv_dimension_key, inv_dimension_wise_dict, sle)

		b_key = (sle.item_code, sle.warehouse, sle.batch_no or "")
		if b_key not in batch_balances:
			batch_balances[b_key] = [0.0, 0.0, 0.0]

		if sle.voucher_type == "Stock Reconciliation" and not sle.actual_qty:
			# Zero-target SLE: reset the balance to the new reconciled pieces value
			batch_balances[b_key][0] = flt(sle.qty_after_transaction)
			batch_balances[b_key][1] = flt(sle.stock_value)
			# Do not reset pieces here because custom_pieces is a delta, not absolute
		else:
			pieces_diff = flt(sle.custom_pieces)
			if sle.actual_qty < 0:
				pieces_diff = -abs(pieces_diff)
			elif sle.actual_qty > 0:
				pieces_diff = abs(pieces_diff)
			else:
				pieces_diff = 0.0

			batch_balances[b_key][0] += flt(sle.actual_qty, precision)
			batch_balances[b_key][1] += flt(sle.stock_value_difference)
			batch_balances[b_key][2] += pieces_diff

		sle.update({"qty_after_transaction": batch_balances[b_key][0], "stock_value": batch_balances[b_key][1], "balance_pieces": batch_balances[b_key][2]})

		# For all voucher types including Stock Reconciliation: use actual_qty direction to determine in/out display
		in_pieces = flt(sle.custom_pieces) if sle.actual_qty > 0 else 0.0
		out_pieces = -abs(flt(sle.custom_pieces)) if sle.actual_qty < 0 else 0.0

		sle.update({
			"in_qty": max(sle.actual_qty, 0), "out_qty": min(sle.actual_qty, 0),
			"in_pieces": in_pieces, "out_pieces": out_pieces
		})

		if sle.serial_no:
			update_available_serial_nos(available_serial_nos, sle)

		if sle.actual_qty:
			sle["in_out_rate"] = flt(sle.stock_value_difference / sle.actual_qty, precision)

		elif sle.voucher_type == "Stock Reconciliation":
			sle["in_out_rate"] = sle.valuation_rate

		data.append(sle)

		if include_uom:
			conversion_factors.append(item_detail.conversion_factor)

	filtered_data = []
	filtered_conversion_factors = []
	import re

	for idx, row in enumerate(data):
		item_code = row.get("item_code")
		if item_code == _("'Opening'"):
			if filters.get("item_code"):
				if isinstance(filters.item_code, list | tuple):
					item_code = filters.item_code[0] if filters.item_code else None
				else:
					item_code = filters.item_code

		batch_no = row.get("batch_no")
		
		if cint(filters.get("segregate_serial_batch_bundle")) and not batch_no and item_code and item_code != _("'Opening'"):
			continue

		if not batch_no and item_code and item_code != _("'Opening'"):
			if not row.get("serial_and_batch_bundle"):
				batch_no = frappe.db.get_value("Batch", {"item": item_code}, "name", order_by="creation desc")
			elif filters.get("batch_no"):
				batch_no = filters.batch_no
				
		if filters.get("batch_no") and batch_no != filters.get("batch_no"):
			continue

		size = row.get("custom_size") or ""
		schedule = row.get("custom_schedule") or ""

		if (not size or not schedule) and batch_no:
			if "MIX" in str(batch_no).upper():
				if not size: size = "MIX"
				if not schedule: schedule = "MIX"
			else:
				od_match = re.search(r"OD\s*:\s*([0-9\.]+)", batch_no, re.IGNORECASE)
				thk_match = re.search(r"THK\s*:\s*([0-9\.]+)", batch_no, re.IGNORECASE)

				od = flt(od_match.group(1)) if od_match else None
				thk = flt(thk_match.group(1)) if thk_match else None

				if od:
					if thk:
						pipe_dim = frappe.db.get_value(
							"Pipe Dimension Master",
							{"od_mm": od, "thickness_mm": thk},
							["nb", "schedule"],
							as_dict=True,
						)
						if pipe_dim:
							if not size: size = pipe_dim.nb
							if not schedule: schedule = pipe_dim.schedule

					if not size:
						pipe_dim = frappe.db.get_value(
							"Pipe Dimension Master",
							{"od_mm": od},
							["nb", "schedule"],
							as_dict=True,
						)
						if pipe_dim:
							if not size: size = pipe_dim.nb
							if not schedule: schedule = f"{thk} MM" if thk else None

				if not size:
					if od:
						size = f"{od} MM"
					if thk:
						schedule = f"{thk} MM"

		row["custom_size"] = size
		row["custom_schedule"] = schedule

		filter_size = filters.get("custom_size")
		if filter_size:
			if isinstance(filter_size, str):
				filter_size = [s.strip() for s in filter_size.split(",") if s.strip()]
			if isinstance(filter_size, list):
				if not any(str(s).strip().lower() == str(row.get("custom_size", "")).strip().lower() for s in filter_size):
					continue

		filter_schedule = filters.get("custom_schedule")
		if filter_schedule:
			if isinstance(filter_schedule, str):
				filter_schedule = [s.strip() for s in filter_schedule.split(",") if s.strip()]
			if isinstance(filter_schedule, list):
				if not any(str(s).strip().lower() == str(row.get("custom_schedule", "")).strip().lower() for s in filter_schedule):
					continue

		filtered_data.append(row)
		if conversion_factors and idx < len(conversion_factors):
			filtered_conversion_factors.append(conversion_factors[idx])

	data = filtered_data
	conversion_factors = filtered_conversion_factors

	update_included_uom_in_report(columns, data, include_uom, conversion_factors)
	return columns, data



def set_opening_row_for_inv_dimension(
	inv_dimension_wise_dict, filters, inv_dimension_key=None, opening_row=None
):
	if (
		not inv_dimension_key
		or not opening_row
		or not filters.get("item_code")
		or not filters.get("warehouse")
	):
		return

	if len(filters.get("item_code")) > 1 or len(filters.get("warehouse")) > 1:
		return

	if inv_dimension_key and opening_row and filters.get("item_code") and filters.get("warehouse"):
		new_key = copy.deepcopy(inv_dimension_key)
		new_key.extend([filters.item_code[0], filters.warehouse[0]])

		opening_key = tuple(new_key)
		inv_dimension_wise_dict[opening_key] = {
			"qty_after_transaction": flt(opening_row.get("qty_after_transaction")),
			"dimension_stock_value": flt(opening_row.get("stock_value")),
		}


def set_balance_value_for_inv_dimesion(inv_dimension_key, inv_dimension_wise_dict, sle):
	new_key = copy.deepcopy(inv_dimension_key)
	new_key.extend([sle.item_code, sle.warehouse])
	new_key = tuple(new_key)

	if new_key not in inv_dimension_wise_dict:
		inv_dimension_wise_dict[new_key] = {"qty_after_transaction": 0, "dimension_stock_value": 0}

	inv_dimesion_value = inv_dimension_wise_dict[new_key]
	inv_dimesion_value["qty_after_transaction"] += sle.actual_qty
	inv_dimesion_value["dimension_stock_value"] += sle.stock_value_difference
	sle.update(
		{
			"qty_after_transaction": inv_dimesion_value["qty_after_transaction"],
			"stock_value": inv_dimesion_value["dimension_stock_value"],
		}
	)


def get_segregated_bundle_entries(sle, bundle_details, batch_balances, filters):
	segregated_entries = []
	qty_before_transaction = sle.qty_after_transaction - sle.actual_qty
	stock_value_before_transaction = sle.stock_value - sle.stock_value_difference

	for row in bundle_details:
		new_sle = copy.deepcopy(sle)
		new_sle.update(row)

		b_key = (new_sle.item_code, new_sle.warehouse, row.batch_no or "")
		if b_key not in batch_balances:
			batch_balances[b_key] = [0.0, 0.0, 0.0]

		row_pieces = flt(sle.custom_pieces) * (flt(row.qty) / flt(sle.actual_qty)) if sle.actual_qty else 0.0
		if row.qty < 0:
			row_pieces = -abs(row_pieces)
		elif row.qty > 0:
			row_pieces = abs(row_pieces)
		else:
			row_pieces = 0.0

		batch_balances[b_key][0] += flt(row.qty)
		batch_balances[b_key][1] += flt(new_sle.stock_value_difference)
		batch_balances[b_key][2] += row_pieces

		in_pieces = row_pieces if row.qty > 0 else 0.0
		out_pieces = -abs(row_pieces) if row.qty < 0 else 0.0

		new_sle.update(
			{
				"in_out_rate": flt(new_sle.stock_value_difference / row.qty) if row.qty else 0,
				"in_qty": row.qty if row.qty > 0 else 0,
				"out_qty": row.qty if row.qty < 0 else 0,
				"qty_after_transaction": batch_balances[b_key][0],
				"stock_value": batch_balances[b_key][1],
				"balance_pieces": batch_balances[b_key][2],
				"in_pieces": in_pieces,
				"out_pieces": out_pieces,
				"incoming_rate": row.incoming_rate if row.qty > 0 else 0,
			}
		)

		qty_before_transaction += row.qty
		stock_value_before_transaction += new_sle.stock_value_difference

		new_sle.valuation_rate = (
			stock_value_before_transaction / qty_before_transaction if qty_before_transaction else 0
		)

		segregated_entries.append(new_sle)

	return segregated_entries


def get_serial_batch_bundle_details(sl_entries, filters=None):
	bundle_details = []
	for sle in sl_entries:
		if sle.serial_and_batch_bundle:
			bundle_details.append(sle.serial_and_batch_bundle)

	if not bundle_details:
		return frappe._dict({})

	query_filers = {"parent": ("in", bundle_details)}
	if filters.get("batch_no"):
		query_filers["batch_no"] = filters.batch_no

	_bundle_details = frappe._dict({})
	batch_entries = frappe.get_all(
		"Serial and Batch Entry",
		filters=query_filers,
		fields=["parent", "qty", "incoming_rate", "stock_value_difference", "batch_no", "serial_no"],
		order_by="parent, idx",
	)
	for entry in batch_entries:
		_bundle_details.setdefault(entry.parent, []).append(entry)

	return _bundle_details


def update_available_serial_nos(available_serial_nos, sle):
	serial_nos = get_serial_nos(sle.serial_no)
	key = (sle.item_code, sle.warehouse)
	if key not in available_serial_nos:
		stock_balance = get_stock_balance_for(
			sle.item_code, sle.warehouse, sle.posting_date, sle.posting_time
		)
		serials = get_serial_nos(stock_balance["serial_nos"]) if stock_balance["serial_nos"] else []
		available_serial_nos.setdefault(key, serials)

	existing_serial_no = available_serial_nos[key]
	for sn in serial_nos:
		if sle.actual_qty > 0:
			if sn in existing_serial_no:
				existing_serial_no.remove(sn)
			else:
				existing_serial_no.append(sn)
		else:
			if sn in existing_serial_no:
				existing_serial_no.remove(sn)
			else:
				existing_serial_no.append(sn)

	sle.balance_serial_no = "\n".join(existing_serial_no)


def get_columns(filters):
	columns = [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Datetime", "width": 130},
	]

	for dimension in get_inventory_dimensions():
		columns.append(
			{
				"label": _(dimension.doctype),
				"fieldname": dimension.fieldname,
				"fieldtype": "Link",
				"options": dimension.doctype,
				"width": 110,
			}
		)

	columns.extend(
		[
			{
				"label": _("Citi No."),
				"fieldname": "custom_citi_no",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("Size"),
				"fieldname": "custom_size",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("OD/Schedule"),
				"fieldname": "custom_schedule",
				"fieldtype": "Data",
				"width": 100,
			},
			{
				"label": _("In Pieces"),
				"fieldname": "in_pieces",
				"fieldtype": "Float",
				"width": 80,
			},
			{
				"label": _("Out Pieces"),
				"fieldname": "out_pieces",
				"fieldtype": "Float",
				"width": 80,
			},
			{
				"label": _("Balance Pieces"),
				"fieldname": "balance_pieces",
				"fieldtype": "Float",
				"width": 100,
			},
			{
				"label": _("Warehouse"),
				"fieldname": "warehouse",
				"fieldtype": "Link",
				"options": "Warehouse",
				"width": 150,
			},
			{
				"label": _("In Qty"),
				"fieldname": "in_qty",
				"fieldtype": "Float",
				"width": 80,
				"convertible": "qty",
			},
			{
				"label": _("Out Qty"),
				"fieldname": "out_qty",
				"fieldtype": "Float",
				"width": 80,
				"convertible": "qty",
			},
			{
				"label": _("Balance Qty"),
				"fieldname": "qty_after_transaction",
				"fieldtype": "Float",
				"width": 100,
				"convertible": "qty",
			},
			{"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 110},
			{
				"label": _("Voucher #"),
				"fieldname": "voucher_no",
				"fieldtype": "Dynamic Link",
				"options": "voucher_type",
				"width": 100,
			},
				{
				"label": _("Batch"),
				"fieldname": "batch_no",
				"fieldtype": "Link",
				"options": "Batch",
				"width": 300,
				"hidden": not filters.get("segregate_serial_batch_bundle"),
			},
			{
			"label": _("Item"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 100,
		},
			{
				"label": _("Balance Value"),
				"fieldname": "stock_value",
				"fieldtype": "Currency",
				"width": 110,
				"options": "Company:company:default_currency",
			},
			{
				"label": _("Value Change"),
				"fieldname": "stock_value_difference",
				"fieldtype": "Currency",
				"width": 110,
				"options": "Company:company:default_currency",
			},
			{
				"label": _("Project"),
				"fieldname": "project",
				"fieldtype": "Link",
				"options": "Project",
				"width": 100,
			},
			{
				"label": _("Company"),
				"fieldname": "company",
				"fieldtype": "Link",
				"options": "Company",
				"width": 110,
			},
		{"label": _("Item Name"), "fieldname": "item_name", "width": 100},
		{
			"label": _("Stock UOM"),
			"fieldname": "stock_uom",
			"fieldtype": "Link",
			"options": "UOM",
			"width": 90,
		},
		]
	)

	return columns


def get_stock_ledger_entries(filters, items):
	from_date = get_datetime(filters.from_date + " 00:00:00")
	to_date = get_datetime(filters.to_date + " 23:59:59")

	sle = frappe.qb.DocType("Stock Ledger Entry")
	query = (
		frappe.qb.from_(sle)
		.select(
			sle.item_code,
			sle.posting_datetime.as_("date"),
			sle.warehouse,
			sle.posting_date,
			sle.posting_time,
			sle.actual_qty,
			sle.incoming_rate,
			sle.valuation_rate,
			sle.company,
			sle.voucher_type,
			sle.qty_after_transaction,
			sle.stock_value_difference,
			sle.serial_and_batch_bundle,
			sle.voucher_no,
			sle.stock_value,
			sle.batch_no,
			sle.serial_no,
			sle.custom_pieces,
			sle.custom_citi_no,
			sle.custom_size,
			sle.custom_schedule,
		)
		.where((sle.docstatus < 2) & (sle.is_cancelled == 0) & (sle.posting_datetime[from_date:to_date]))
		.orderby(sle.posting_datetime)
		.orderby(sle.creation)
	)

	inventory_dimension_fields = get_inventory_dimension_fields()
	if inventory_dimension_fields:
		for fieldname in inventory_dimension_fields:
			query = query.select(fieldname)
			if fieldname in filters and filters.get(fieldname):
				query = query.where(sle[fieldname].isin(filters.get(fieldname)))

	if items:
		query = query.where(sle.item_code.isin(items))

	for field in ["voucher_no", "project", "company"]:
		if filters.get(field) and field not in inventory_dimension_fields:
			query = query.where(sle[field] == filters.get(field))

	if filters.get("batch_no"):
		bundles = get_serial_and_batch_bundles(filters)

		if bundles:
			query = query.where(
				(sle.serial_and_batch_bundle.isin(bundles)) | (sle.batch_no == filters.batch_no)
			)
		else:
			query = query.where(sle.batch_no == filters.batch_no)

	query = apply_warehouse_filter(query, sle, filters)

	return query.run(as_dict=True)


def get_serial_and_batch_bundles(filters):
	SBB = frappe.qb.DocType("Serial and Batch Bundle")
	SBE = frappe.qb.DocType("Serial and Batch Entry")

	query = (
		frappe.qb.from_(SBE)
		.inner_join(SBB)
		.on(SBE.parent == SBB.name)
		.select(SBE.parent)
		.where(
			(SBB.docstatus == 1)
			& (SBB.has_batch_no == 1)
			& (SBB.voucher_no.notnull())
			& (SBE.batch_no == filters.batch_no)
		)
	)

	return query.run(pluck=SBE.parent)


def get_inventory_dimension_fields():
	return [dimension.fieldname for dimension in get_inventory_dimensions()]


def get_items(filters):
	item = frappe.qb.DocType("Item")
	query = frappe.qb.from_(item).select(item.name)
	conditions = []

	if item_codes := filters.get("item_code"):
		conditions.append(item.name.isin(item_codes))

	else:
		if brand := filters.get("brand"):
			conditions.append(item.brand == brand)

		if filters.get("item_group") and (
			condition := get_item_group_condition(filters.get("item_group"), item)
		):
			conditions.append(condition)

	items = []
	if conditions:
		for condition in conditions:
			query = query.where(condition)

		items = [r[0] for r in query.run()]

	return items


def get_item_details(items, sl_entries, include_uom):
	item_details = {}
	if not items:
		items = list(set(d.item_code for d in sl_entries))

	if not items:
		return item_details

	item = frappe.qb.DocType("Item")
	query = (
		frappe.qb.from_(item)
		.select(item.name, item.item_name, item.description, item.item_group, item.brand, item.stock_uom)
		.where(item.name.isin(items))
	)

	if include_uom:
		ucd = frappe.qb.DocType("UOM Conversion Detail")
		query = (
			query.left_join(ucd)
			.on((ucd.parent == item.name) & (ucd.uom == include_uom))
			.select(ucd.conversion_factor)
		)

	res = query.run(as_dict=True)

	for item in res:
		item_details.setdefault(item.name, item)

	return item_details


# TODO: THIS IS NOT USED
def get_sle_conditions(filters):
	conditions = []
	if filters.get("warehouse"):
		warehouse_condition = get_warehouse_condition(filters.get("warehouse"))
		if warehouse_condition:
			conditions.append(warehouse_condition)
	if filters.get("voucher_no"):
		conditions.append("voucher_no=%(voucher_no)s")
	if filters.get("batch_no"):
		conditions.append("batch_no=%(batch_no)s")
	if filters.get("project"):
		conditions.append("project=%(project)s")

	for dimension in get_inventory_dimensions():
		if filters.get(dimension.fieldname):
			conditions.append(f"{dimension.fieldname} in %({dimension.fieldname})s")

	return "and {}".format(" and ".join(conditions)) if conditions else ""


def get_opening_balance_from_batch(filters, columns, sl_entries):
	conditions = []
	values = []
	for field in ["item_code", "warehouse"]:
		if value := filters.get(field):
			if isinstance(value, list | tuple):
				conditions.append(f"{field} IN ({', '.join(['%s'] * len(value))})")
				values.extend(value)
			else:
				conditions.append(f"{field} = %s")
				values.append(value)

	condition_str = f"AND {' AND '.join(conditions)}" if conditions else ""

	opening_data = frappe.db.sql(f"""
		SELECT 
			SUM(actual_qty) as qty_after_transaction,
			SUM(stock_value_difference) as stock_value,
			SUM(CASE WHEN actual_qty > 0 THEN custom_pieces WHEN actual_qty < 0 THEN -custom_pieces ELSE 0 END) as balance_pieces
		FROM `tabStock Ledger Entry`
		WHERE batch_no = %s AND docstatus = 1 AND is_cancelled = 0
		AND posting_date < %s AND company = %s
		{condition_str}
	""", [filters.batch_no, filters.from_date, filters.company] + values, as_dict=True)[0]

	for field in ["qty_after_transaction", "stock_value", "valuation_rate", "balance_pieces"]:
		if opening_data.get(field) is None:
			opening_data[field] = 0.0

	table = frappe.qb.DocType("Stock Ledger Entry")
	sabb_table = frappe.qb.DocType("Serial and Batch Entry")
	query = (
		frappe.qb.from_(table)
		.inner_join(sabb_table)
		.on(table.serial_and_batch_bundle == sabb_table.parent)
		.select(
			sabb_table.qty,
			table.actual_qty,
			table.custom_pieces,
			sabb_table.stock_value_difference.as_("stock_value"),
		)
		.where(
			(sabb_table.batch_no == filters.batch_no)
			& (sabb_table.docstatus == 1)
			& (table.posting_date < filters.from_date)
			& (table.is_cancelled == 0)
		)
	)

	for field in ["item_code", "warehouse", "company"]:
		value = filters.get(field)

		if not value:
			continue

		if isinstance(value, list | tuple):
			query = query.where(table[field].isin(value))

		else:
			query = query.where(table[field] == value)

	bundle_data = query.run(as_dict=True)

	if bundle_data:
		for row in bundle_data:
			opening_data.qty_after_transaction += flt(row.qty)
			opening_data.stock_value += flt(row.stock_value)

			# Calculate pieces proportionally
			pieces = flt(row.custom_pieces) * (flt(row.qty) / flt(row.actual_qty)) if row.actual_qty else 0.0
			if flt(row.qty) < 0:
				pieces = -abs(pieces)
			elif flt(row.qty) > 0:
				pieces = abs(pieces)
			else:
				pieces = 0.0
			opening_data.balance_pieces += pieces

		if opening_data.qty_after_transaction:
			opening_data.valuation_rate = flt(opening_data.stock_value) / flt(
				opening_data.qty_after_transaction
			)

	return {
		"item_code": _("'Opening'"),
		"qty_after_transaction": opening_data.qty_after_transaction,
		"valuation_rate": opening_data.valuation_rate,
		"stock_value": opening_data.stock_value,
		"balance_pieces": opening_data.balance_pieces,
		"batch_no": filters.get("batch_no"),
	}


def get_opening_balance(filters, columns, sl_entries, inv_dimension_wise_value=None):
	if not (filters.item_code and filters.warehouse and filters.from_date):
		return

	from erpnext.stock.stock_ledger import get_previous_sle

	project = None
	if filters.get("project") and not frappe.get_all(
		"Inventory Dimension", filters={"reference_document": "Project"}
	):
		project = filters.get("project")

	last_entry = get_previous_sle(
		{
			"item_code": filters.item_code,
			"warehouse_condition": get_warehouse_condition(filters.warehouse),
			"posting_date": filters.from_date,
			"posting_time": "00:00:00",
			"project": project,
		},
		for_report=True,
	)

	# check if any SLEs are actually Opening Stock Reconciliation
	for sle in list(sl_entries):
		if (
			sle.get("voucher_type") == "Stock Reconciliation"
			and sle.posting_date == filters.from_date
			and frappe.db.get_value("Stock Reconciliation", sle.voucher_no, "purpose") == "Opening Stock"
		):
			last_entry = sle
			sl_entries.remove(sle)

	row = {
		"item_code": _("'Opening'"),
		"qty_after_transaction": last_entry.get("qty_after_transaction", 0),
		"valuation_rate": last_entry.get("valuation_rate", 0),
		"stock_value": last_entry.get("stock_value", 0),
		"balance_pieces": last_entry.get("custom_pieces", 0),
	}

	return row


def get_warehouse_condition(warehouses):
	if not warehouses:
		return ""

	if isinstance(warehouses, str):
		warehouses = [warehouses]

	warehouse_range = frappe.get_all(
		"Warehouse",
		filters={
			"name": ("in", warehouses),
		},
		fields=["lft", "rgt"],
		as_list=True,
	)

	if not warehouse_range:
		return ""

	alias = "wh"
	conditions = []
	for lft, rgt in warehouse_range:
		conditions.append(f"({alias}.lft >= {lft} and {alias}.rgt <= {rgt})")

	conditions = " or ".join(conditions)

	return f" exists (select name from `tabWarehouse` {alias} \
		where ({conditions}) and warehouse = {alias}.name)"


def get_item_group_condition(item_group, item_table=None):
	item_group_details = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"], as_dict=1)
	if item_group_details:
		if item_table:
			ig = frappe.qb.DocType("Item Group")
			return item_table.item_group.isin(
				frappe.qb.from_(ig)
				.select(ig.name)
				.where(
					(ig.lft >= item_group_details.lft)
					& (ig.rgt <= item_group_details.rgt)
					& (item_table.item_group == ig.name)
				)
			)
		else:
			return f"item.item_group in (select ig.name from `tabItem Group` ig \
				where ig.lft >= {item_group_details.lft} and ig.rgt <= {item_group_details.rgt} and item.item_group = ig.name)"


def get_opening_balance_for_inv_dimension(filters, inv_dimension_wise_value):
	if not filters.item_code or not filters.warehouse or not filters.from_date:
		return

	if len(filters.get("item_code")) > 1 or len(filters.get("warehouse")) > 1:
		return

	sl_doctype = frappe.qb.DocType("Stock Ledger Entry")

	query = (
		frappe.qb.from_(sl_doctype)
		.select(
			sl_doctype.item_code,
			sl_doctype.warehouse,
			Sum(sl_doctype.actual_qty).as_("qty_after_transaction"),
			Sum(sl_doctype.stock_value_difference).as_("stock_value"),
		)
		.where(
			(sl_doctype.posting_date < filters.from_date)
			& (sl_doctype.docstatus < 2)
			& (sl_doctype.is_cancelled == 0)
		)
	)

	if filters.get("item_code"):
		if isinstance(filters.item_code, list | tuple):
			query = query.where(sl_doctype.item_code.isin(filters.item_code))
		else:
			query = query.where(sl_doctype.item_code == filters.item_code)

	if filters.get("warehouse"):
		if isinstance(filters.warehouse, list | tuple):
			query = query.where(sl_doctype.warehouse.isin(filters.warehouse))
		else:
			query = query.where(sl_doctype.warehouse == filters.warehouse)

	for key, value in inv_dimension_wise_value.items():
		if isinstance(value, list | tuple):
			query = query.where(sl_doctype[key].isin(value))
		else:
			query = query.where(sl_doctype[key] == value)

	opening_data = query.run(as_dict=True)

	if opening_data:
		return frappe._dict(
			{
				"item_code": _("'Opening'"),
				"qty_after_transaction": opening_data[0].qty_after_transaction,
				"stock_value": opening_data[0].stock_value,
				"valuation_rate": flt(opening_data[0].stock_value)
				/ flt(opening_data[0].qty_after_transaction)
				if opening_data[0].qty_after_transaction
				else 0,
			}
		)

	return frappe._dict({})


def get_inv_dimension_wise_value(filters) -> list:
	inv_dimension_key = frappe._dict({})
	for dimension in get_inventory_dimensions():
		if dimension.fieldname in filters and filters.get(dimension.fieldname):
			inv_dimension_key[dimension.fieldname] = filters.get(dimension.fieldname)

	if filters.get("project") and not frappe.get_all(
		"Inventory Dimension", filters={"reference_document": "Project"}
	):
		inv_dimension_key["project"] = filters.get("project")

	return inv_dimension_key


@frappe.whitelist()
def get_pipe_size_filter_data(txt=None):
	"""Return unique 'size' (NB) values computed from batch_no, for use in filter dropdown.
	Includes fallback values like '19.05 MM' that are not in Pipe Dimension Master."""
	import re

	# Get all distinct batch_no values from SLE that have OD or MIX info
	batch_nos = frappe.db.sql(
		"SELECT DISTINCT batch_no FROM `tabStock Ledger Entry` WHERE (batch_no LIKE %s OR batch_no LIKE %s) AND docstatus < 2 AND is_cancelled = 0 LIMIT 500",
		["%OD%", "%MIX%"],
		as_dict=False,
	)

	sizes = set()
	for (batch_no,) in batch_nos:
		if not batch_no:
			continue
		if "MIX" in str(batch_no).upper():
			size = "MIX"
		else:
			od_match = re.search(r"OD\s*:\s*([0-9\.]+)", batch_no, re.IGNORECASE)
			thk_match = re.search(r"THK\s*:\s*([0-9\.]+)", batch_no, re.IGNORECASE)
			od = frappe.utils.flt(od_match.group(1)) if od_match else None
			thk = frappe.utils.flt(thk_match.group(1)) if thk_match else None

			size = ""
			if od:
				if thk:
					pipe_dim = frappe.db.get_value(
						"Pipe Dimension Master",
						{"od_mm": od, "thickness_mm": thk},
						["nb", "schedule"],
						as_dict=True,
					)
					if pipe_dim:
						size = pipe_dim.nb

				if not size:
					pipe_dim = frappe.db.get_value(
						"Pipe Dimension Master",
						{"od_mm": od},
						["nb", "schedule"],
						as_dict=True,
					)
					if pipe_dim:
						size = pipe_dim.nb

				if not size:
					size = f"{od} MM"

		if size:
			sizes.add(size)

	# Also include values from Pipe Dimension Master for items that do have a match
	pdm_nbs = frappe.db.sql(
		"SELECT DISTINCT nb FROM `tabPipe Dimension Master` WHERE nb IS NOT NULL AND nb != ''",
		as_dict=False,
	)
	for (nb,) in pdm_nbs:
		if nb:
			sizes.add(nb)

	all_sizes = sorted(sizes)
	if txt:
		txt_lower = txt.lower()
		all_sizes = [s for s in all_sizes if txt_lower in s.lower()]

	return [{"value": s, "description": s} for s in all_sizes[:50]]


@frappe.whitelist()
def get_pipe_schedule_filter_data(txt=None):
	"""Return unique 'schedule' (OD/Schedule) values computed from batch_no, for use in filter dropdown.
	Includes fallback values like '19.05 MM' that are not in Pipe Dimension Master."""
	import re

	batch_nos = frappe.db.sql(
		"SELECT DISTINCT batch_no FROM `tabStock Ledger Entry` WHERE (batch_no LIKE %s OR batch_no LIKE %s) AND docstatus < 2 AND is_cancelled = 0 LIMIT 500",
		["%THK%", "%MIX%"],
		as_dict=False,
	)

	schedules = set()
	for (batch_no,) in batch_nos:
		if not batch_no:
			continue
		if "MIX" in str(batch_no).upper():
			schedule = "MIX"
		else:
			od_match = re.search(r"OD\s*:\s*([0-9\.]+)", batch_no, re.IGNORECASE)
			thk_match = re.search(r"THK\s*:\s*([0-9\.]+)", batch_no, re.IGNORECASE)
			od = frappe.utils.flt(od_match.group(1)) if od_match else None
			thk = frappe.utils.flt(thk_match.group(1)) if thk_match else None

			schedule = ""
			if od:
				if thk:
					pipe_dim = frappe.db.get_value(
						"Pipe Dimension Master",
						{"od_mm": od, "thickness_mm": thk},
						["nb", "schedule"],
						as_dict=True,
					)
					if pipe_dim:
						schedule = pipe_dim.schedule

				if not schedule:
					pipe_dim = frappe.db.get_value(
						"Pipe Dimension Master",
						{"od_mm": od},
						["nb", "schedule"],
						as_dict=True,
					)
					if pipe_dim:
						schedule = f"{thk} MM" if thk else ""

			if not schedule and thk:
				schedule = f"{thk} MM"

		if schedule:
			schedules.add(schedule)

	# Also include values from Pipe Dimension Master
	pdm_schedules = frappe.db.sql(
		"SELECT DISTINCT schedule FROM `tabPipe Dimension Master` WHERE schedule IS NOT NULL AND schedule != ''",
		as_dict=False,
	)
	for (sched,) in pdm_schedules:
		if sched:
			schedules.add(sched)

	all_schedules = sorted(schedules)
	if txt:
		txt_lower = txt.lower()
		all_schedules = [s for s in all_schedules if txt_lower in s.lower()]

	return [{"value": s, "description": s} for s in all_schedules[:50]]
