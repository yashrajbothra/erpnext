import frappe
from frappe.utils.file_manager import save_file
import openpyxl
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
import os
import csv
import re
from collections import defaultdict


# ── helpers ───────────────────────────────────────────────────────────────────

STOP_WORDS = {"IMPEX", "OVERSEAS", "STEEL", "METALS", "METAL", "CORP", "CORPORATION", "LTD", "LIMITED", "PVT", "PRIVATE", "ENTERPRISES", "ALLOYS", "TRADERS", "INDIA", "LLP", "CO", "AND", "SONS", "STAINLESS", "INDUSTRIES", "ISPAT", "UDYOG", "AGENCY", "AGENCIES", "BROS", "BROTHERS", "IMP", "EXP", "GLOBAL", "TRADE", "TUBES", "TUBE", "PIPE", "PIPES", "COIL", "SHEET", "PLATES", "CIRCLE"}

def safe_float(val, default=0.0):
    try:
        v = str(val).replace(",", "").strip()
        return float(v) if v else default
    except (ValueError, TypeError):
        return default


def extract_citi_num(citi_str):
    if not citi_str: return float('inf')
    m = re.search(r'\d+', str(citi_str))
    return int(m.group()) if m else float('inf')


def normalize_date(d):
    return str(d).strip().lower()


def normalize_party(p):
    """Keep only alphanumeric uppercase for fuzzy matching."""
    return "".join(c for c in str(p).upper() if c.isalnum())


def get_significant_tokens(p):
    tokens = set(re.findall(r'[A-Z0-9]+', str(p).upper()))
    return tokens - STOP_WORDS


def _normalize_tokens(s):
    """Normalise common spelling variants before tokenising."""
    s = s.upper()
    # name variants
    s = re.sub(r'\bRANJEET\b', 'RANJIT', s)
    s = re.sub(r'\bSAWASTINOX\b', 'SWASTINOX', s)
    s = re.sub(r'\bRATANMANI\b', 'RATNAMANI', s)
    s = re.sub(r'\bSHUBHLAXMI\b', 'SUBHLAXMI', s)
    s = re.sub(r'\bMETALLOYS\b', 'METAL', s)
    s = re.sub(r'\bSUBHLAXMI\b', 'SUBHLAXMI', s)
    return s


def party_match(a, b):
    """Return True if party strings refer to the same entity."""
    na, nb = normalize_party(a), normalize_party(b)
    if not na or not nb:
        return False
    if na in nb or nb in na:
        return True

    # normalise spelling variants then check significant token overlap
    sig_a = get_significant_tokens(_normalize_tokens(a))
    sig_b = get_significant_tokens(_normalize_tokens(b))

    if sig_a and sig_b and sig_a.intersection(sig_b):
        return True

    return False


def find_best_subset(available_indices, target_wt, inout_data, max_diff=10):
    """
    Finds a subset of available_indices whose sum of inout_data[i]['wt'] 
    is closest to target_wt within max_diff.
    Returns (best_subset_indices, best_diff).
    """
    import itertools
    best_subset = None
    best_diff = float('inf')
    best_k = float('inf')
    
    n = len(available_indices)
    
    # Strategy 1: Check contiguous slices of available_indices first.
    # Physical ledger entries are almost always entered consecutively.
    # O(N^2) is highly efficient and scales well, bypassing combinatorial limits.
    for start in range(n):
        for end in range(start + 1, n + 1):
            combo = tuple(available_indices[start:end])
            total_wt = sum(inout_data[i]["wt"] for i in combo)
            diff = abs(total_wt - target_wt)
            if diff <= max_diff:
                k = len(combo)
                if (diff < best_diff) or (diff == best_diff and k < best_k):
                    best_subset = combo
                    best_diff = diff
                    best_k = k
                    
    if best_subset is not None:
        return best_subset, best_diff
        
    # Strategy 2: Fallback to combinatorial subset search on the pool.
    if n <= 18:
        k_range = range(1, n + 1)
    else:
        # Safeguard to prevent combinatorial explosion on exceptionally large pools
        k_range = [1, 2, 3, n]
        
    for k in k_range:
        if k > n:
            continue
        for combo in itertools.combinations(available_indices, k):
            total_wt = sum(inout_data[i]["wt"] for i in combo)
            diff = abs(total_wt - target_wt)
            if diff <= max_diff:
                if (diff < best_diff) or (diff == best_diff and k < best_k):
                    best_subset = combo
                    best_diff = diff
                    best_k = k
                    
    return best_subset, best_diff


def load_any_sheet(file_path):
    """Loads either XLSX or CSV and returns a list of tuples/lists representing rows."""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == ".csv":
        with open(file_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            return list(reader)
    else:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb.active
        return list(ws.iter_rows(values_only=True))


GST_TOLERANCE = 50          # ± ₹ accepted when checking full-rate GST
WT_TOLERANCE_PCT = 0.02     # ± 2 % for weight matching


# ── main whitelisted endpoint ─────────────────────────────────────────────────

@frappe.whitelist()
def merge_sheets(sale_file_url, inout_file_url):
    """
    Merge sale + inout sheets.

    Matching key  : Date  +  Party (fuzzy)  +  total weight (±2 %)
    CITI NO.      : filled FROM sale INTO each matched inout row
    Bill Rate     : filled per GST-split logic
    Discount Rate : remainder after GST-split
    Loading / GST : distributed proportionally by weight across inout rows
    """

    def get_path(url):
        p = frappe.get_site_path(url.strip("/"))
        if not os.path.exists(p):
            p = frappe.get_site_path("public", "files", os.path.basename(url))
        return p

    sale_path  = get_path(sale_file_url)
    inout_path = get_path(inout_file_url)

    # ── load sheets ──────────────────────────────────────────────────────────
    sale_rows  = load_any_sheet(sale_path)
    inout_rows = load_any_sheet(inout_path)

    if not sale_rows or not inout_rows:
        frappe.throw("One of the uploaded files is empty or invalid.")

    # ── process sale sheet ────────────────────────────────────────────────────
    sale_hdrs  = [str(c).strip() if c is not None else "" for c in sale_rows[0]]

    def sale_col(name):
        try:
            return sale_hdrs.index(name)
        except ValueError:
            frappe.throw(f"Column '{name}' not found in Sale sheet. Found: {', '.join(sale_hdrs)}")

    sc = {
        "citi"    : sale_col("CITI NO."),
        "date"    : sale_col("DATE"),
        "party"   : sale_col("PARTY"),
        "wt"      : sale_col("WT"),
        "rate"    : sale_col("RATE"),
        "loading" : sale_col("LOADING+TRANS."),
        "gst"     : sale_col("GST"),
    }

    # ── Group Sale Data by CITI NO ──
    sale_data = []
    for row in sale_rows[1:]:
        if not any(row):
            continue
        padded_row = list(row) + [None] * (len(sale_hdrs) - len(row))
        sale_data.append({
            "citi"    : padded_row[sc["citi"]],
            "date"    : normalize_date(padded_row[sc["date"]]),
            "party"   : str(padded_row[sc["party"]] or "").strip(),
            "wt"      : safe_float(padded_row[sc["wt"]]),
            "rate"    : safe_float(padded_row[sc["rate"]]),
            "loading" : safe_float(padded_row[sc["loading"]]),
            "gst"     : safe_float(padded_row[sc["gst"]]),
        })

    sale_groups = []
    sale_by_citi = defaultdict(list)
    fake_citi_idx = 0
    for s in sale_data:
        c_no = str(s["citi"]).strip() if s["citi"] is not None else ""
        if not c_no:
            c_no = f"__FAKE_{fake_citi_idx}__"
            fake_citi_idx += 1
        key = (s["date"], c_no)
        sale_by_citi[key].append(s)

    def citi_sort_key(item):
        key = item[0]
        c_no = key[1]
        if c_no.startswith("__FAKE_"):
            return float("inf")
        return extract_citi_num(c_no)

    for key, s_list in sorted(sale_by_citi.items(), key=citi_sort_key):
        sale_groups.append({
            "date": key[0],
            "citi_no": key[1],
            "s_list": s_list,
            "total_wt": sum(s["wt"] for s in s_list),
            "party": s_list[0]["party"]
        })

    # ── process inout sheet ──────────────────────────────────────────────────
    inout_hdrs = [str(c).strip() if c is not None else "" for c in inout_rows[0]]

    def inout_col(name):
        try:
            return inout_hdrs.index(name)
        except ValueError:
            return None

    ic = {
        "citi"     : inout_col("CITI NO. (Items)"),
        "date"     : inout_col("Date"),
        "party"    : inout_col("Party"),
        "wt"       : inout_col("Weight (Items)"),
        "bill_r"   : inout_col("Bill Rate (Items)"),
        "disc_r"   : inout_col("Discount Rate (Items)"),
        "loading"  : inout_col("Loading Charges"),
        "gst_amt"  : inout_col("GST Amount"),
    }

    if ic["date"] is None or ic["party"] is None:
         frappe.throw("Required columns (Date, Party) missing from Inout sheet.")

    inout_data = []
    for row in inout_rows[1:]:
        if not any(row):
            continue
        padded_row = list(row) + [None] * (len(inout_hdrs) - len(row))
        inout_data.append({
            "orig"    : padded_row,
            "date"    : normalize_date(padded_row[ic["date"]]),
            "party"   : str(padded_row[ic["party"]] or "").strip(),
            "wt"      : safe_float(padded_row[ic["wt"]]) if ic["wt"] is not None else 0.0,
            "citi"    : padded_row[ic["citi"]] if ic["citi"] is not None else None,
            "bill_r"  : padded_row[ic["bill_r"]] if ic["bill_r"] is not None else None,
            "disc_r"  : padded_row[ic["disc_r"]] if ic["disc_r"] is not None else None,
            "loading" : padded_row[ic["loading"]] if ic["loading"] is not None else None,
            "gst_amt" : padded_row[ic["gst_amt"]] if ic["gst_amt"] is not None else None,
            "matched" : False,
        })

    warnings = []
    matched = 0

    # ── rate helpers ──────────────────────────────────────────────────────────

    def calc_rates(s_rate, s_loading, s_gst, s_wt):
        loading_per_kg = s_loading / s_wt if s_wt > 0 else 0.0
        if s_gst == 0:
            return 0.0, s_rate
        gst_if_full = (s_rate + loading_per_kg) * s_wt * 18 / 100
        if abs(gst_if_full - s_gst) <= GST_TOLERANCE:
            return s_rate, 0.0
        denom = s_wt * 18 / 100
        br = (s_gst / denom - loading_per_kg) if denom > 0 else 0.0
        if br <= 0:   return 0.0, s_rate
        if br >= s_rate: return s_rate, 0.0
        return br, s_rate - br

    def assign_rates(inout_idx, sale_row, frac=1.0):
        s = sale_row
        br, dr = calc_rates(s["rate"], s["loading"], s["gst"], s["wt"])
        inout_data[inout_idx]["citi"]    = s["citi"]
        inout_data[inout_idx]["bill_r"]  = round(br, 2)           if br > 0 else None
        inout_data[inout_idx]["disc_r"]  = round(dr, 2)           if dr > 0 else None
        inout_data[inout_idx]["loading"] = round(s["loading"] * frac, 2) if s["loading"] > 0 else None
        inout_data[inout_idx]["gst_amt"] = round(s["gst"]     * frac, 2) if s["gst"]     > 0 else None
        inout_data[inout_idx]["matched"] = True

    # ── core matching loop ────────────────────────────────────────────────────
    # Group contiguous inout rows into blocks if they share the same date and party
    inout_blocks = []
    current_block = []
    for idx, d in enumerate(inout_data):
        if not d["wt"] > 0:
            continue
        
        if not current_block:
            current_block = [idx]
        else:
            prev_idx = current_block[-1]
            prev_d = inout_data[prev_idx]
            if d["date"] == prev_d["date"] and d["party"].upper() == prev_d["party"].upper():
                current_block.append(idx)
            else:
                inout_blocks.append(current_block)
                current_block = [idx]
    if current_block:
        inout_blocks.append(current_block)

    valid_sale_groups = [g for g in sale_groups if not g["citi_no"].startswith("__FAKE_") and g["total_wt"] > 0]
    sale_idx = 0
    num_sales = len(valid_sale_groups)

    for block in inout_blocks:
        block_party = inout_data[block[0]]["party"]
        block_date = inout_data[block[0]]["date"]
        
        available = list(block)
        
        while available:
            found_sub_match = False
            
            for s_i in range(sale_idx, num_sales):
                s_group = valid_sale_groups[s_i]
                
                # Require a fuzzy party match to avoid false coincidence alignments
                if not party_match(block_party, s_group["party"]):
                    continue
                
                target_wt = s_group["total_wt"]
                
                # Use combinatorial subset search within the remaining block pool!
                subset, diff = find_best_subset(available, target_wt, inout_data)
                
                if subset:
                    # Found a matching subset!
                    acc_wt = sum(inout_data[i]["wt"] for i in subset)
                    s_list = s_group["s_list"]
                    
                    # Record skipped sequential CITIs
                    for skipped_i in range(sale_idx, s_i):
                        sc = valid_sale_groups[skipped_i]["citi_no"]
                        warnings.append(f"Skipped Sale CITI {sc} (no sequential weight match)")
                    
                    matched += 1
                    
                    # Distribute rates proportionally across the matched subset
                    if len(s_list) == 1:
                        s = s_list[0]
                        for idx in subset:
                            frac = inout_data[idx]["wt"] / acc_wt if acc_wt > 0 else 0.0
                            assign_rates(idx, s, frac)
                    else:
                        rem_sale = list(s_list)
                        for idx in sorted(subset, key=lambda i: inout_data[i]["wt"], reverse=True):
                            if not rem_sale:
                                assign_rates(idx, s_list[0], inout_data[idx]["wt"] / max(target_wt, 1))
                                continue
                            row_wt = inout_data[idx]["wt"]
                            best_s = min(rem_sale, key=lambda s: abs(s["wt"] - row_wt) / max(s["wt"], row_wt, 1))
                            frac = row_wt / max(best_s["wt"], 1)
                            assign_rates(idx, best_s, frac)
                            rem_sale.remove(best_s)
                    
                    # Consume these indices from the pool
                    for item in subset:
                        available.remove(item)
                        
                    sale_idx = s_i + 1
                    found_sub_match = True
                    break
            
            if not found_sub_match:
                remaining_wt = sum(inout_data[i]["wt"] for i in available)
                warnings.append(f"No CITI match for Inout sub-segment: date={block_date}, party={block_party}, wt={remaining_wt:.1f}")
                break

    for s_i in range(sale_idx, num_sales):
        sc = valid_sale_groups[s_i]["citi_no"]
        warnings.append(f"Skipped Sale CITI {sc} (reached end of Inout blocks)")

    # ── build output workbook ─────────────────────────────────────────────────

    out_wb = Workbook()
    out_ws = out_wb.active
    out_ws.title = "Merged Data"

    # header style
    hdr_fill   = PatternFill("solid", fgColor="1F4E79")
    hdr_font   = Font(bold=True, color="FFFFFF", size=10)
    hdr_align  = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_side  = Side(style="thin", color="D0D0D0")
    thin_bdr   = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
    filled_fill= PatternFill("solid", fgColor="E8F5E9")   # light green for filled cells

    # Write header row (only once)
    out_ws.append(inout_hdrs)
    for cell in out_ws[1]:
        cell.fill      = hdr_fill
        cell.font      = hdr_font
        cell.alignment = hdr_align
        cell.border    = thin_bdr

    # col_map for fields to overwrite
    col_map = {
        "citi"    : ic["citi"],
        "bill_r"  : ic["bill_r"],
        "disc_r"  : ic["disc_r"],
        "loading" : ic["loading"],
        "gst_amt" : ic["gst_amt"],
    }

    # Maintain original inout row order.
    for d in inout_data:
        row_vals = list(d["orig"])    # start from original values

        # overwrite filled columns
        for field, col_idx in col_map.items():
            if col_idx is not None and d[field] is not None:
                row_vals[col_idx] = d[field]

        out_ws.append(row_vals)

        # highlight filled cells green
        excel_row = out_ws.max_row
        for field, col_idx in col_map.items():
            if col_idx is not None and d[field] is not None:
                c = out_ws.cell(row=excel_row, column=col_idx + 1)
                c.fill = filled_fill

        # border for all cells
        for cell in out_ws[excel_row]:
            cell.border = thin_bdr

    # auto-width columns (cap at 40)
    for col in out_ws.columns:
        max_len = max((len(str(c.value or "")) for c in col), default=8)
        out_ws.column_dimensions[col[0].column_letter].width = min(max_len + 4, 40)

    out_ws.freeze_panes = "A2"

    # ── save ──────────────────────────────────────────────────────────────────
    fname = f"merged_inout_{frappe.generate_hash(length=8)}.xlsx"
    fpath = frappe.get_site_path("public", "files", fname)
    out_wb.save(fpath)

    with open(fpath, "rb") as fh:
        file_doc = save_file(fname, fh.read(), "Page", "ss-merge-sheets", is_private=0)

    return {
        "file_url"   : file_doc.file_url,
        "matched"    : matched,
        "total_groups": len(inout_data),
        "warnings"   : warnings,
    }
