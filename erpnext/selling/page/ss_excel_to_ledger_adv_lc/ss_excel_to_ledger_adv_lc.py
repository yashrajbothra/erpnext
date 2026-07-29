import frappe
from frappe import _
import openpyxl
from openpyxl import Workbook
import os
import datetime
import re
from frappe.utils.file_manager import save_file
from frappe.utils import getdate, formatdate

@frappe.whitelist()
def convert_excel(file_url, owner=None):
    # Load the uploaded file
    file_path = frappe.get_site_path(file_url.strip('/'))
    if not os.path.exists(file_path):
        file_path = frappe.get_site_path('public', 'files', os.path.basename(file_url))

    wb = openpyxl.load_workbook(file_path, data_only=True)
    sheet = wb.active
    
    header_date = None
    errors = []
    
    # New workbook for output
    out_wb = Workbook()
    out_sheet = out_wb.active
    
    # Headers based on user request (Mode of Payment removed)
    headers = [
        "Payment Type", "Posting Date", "Entry Date", "Company", "Party Type", "Party (Custom)", 
        "Account Paid From", "Paid From Account Type", "Account Paid To" , "Paid Amount", "Received Amount", "Remarks", "Owner"
    ]
    out_sheet.append(headers)
    
    company_name = "SS54"
    company_abbr = frappe.get_cached_value('Company', company_name, 'abbr') or company_name
    current_user = owner or frappe.session.user
    
    def is_numeric(val):
        if val is None: return False
        try:
            float(str(val).replace(',', '').strip())
            return True
        except:
            return False

    def is_nonzero_numeric(val):
        if val is None: return False
        try:
            f = float(str(val).replace(',', '').strip())
            return f != 0
        except:
            return False

    # Default column indices (will be automatically updated if header row is found)
    l_amt_idx, l_party_idx, l_company_idx, l_bank_idx, l_date_idx = 1, 2, 3, 4, 5
    r_amt_idx, r_party_idx, r_company_idx, r_bank_idx, r_date_idx = 8, 9, 10, 11, 12

    # Process rows
    for row_idx, row in enumerate(sheet.iter_rows(min_row=1, values_only=True), start=1):
        row_strs = " ".join([str(v).upper() for v in row if v is not None])
        
        # Dynamic Header Detection: Automatically discover layout shifts
        if "AMT.CR" in row_strs and "AMT.DR" in row_strs:
             normalized_row = [str(c).upper().strip() if c is not None else "" for c in row]
             try:
                 l_amt_idx = normalized_row.index("AMT.CR")
                 r_amt_idx = normalized_row.index("AMT.DR")
                 for i in range(l_amt_idx + 1, r_amt_idx):
                     val = normalized_row[i]
                     if "PARTY" in val: l_party_idx = i
                     elif "COMP" in val: l_company_idx = i
                     elif "BANK" in val: l_bank_idx = i
                     elif "DATE" in val: l_date_idx = i
                 for i in range(r_amt_idx + 1, len(normalized_row)):
                     val = normalized_row[i]
                     if "PARTY" in val: r_party_idx = i
                     elif "COMP" in val: r_company_idx = i
                     elif "BANK" in val: r_bank_idx = i
                     elif "DATE" in val: r_date_idx = i
                 continue # Skip actual header row from processing as transactions
             except ValueError:
                 pass

        has_amt_left = len(row) > l_amt_idx and is_nonzero_numeric(row[l_amt_idx])
        has_amt_right = len(row) > r_amt_idx and is_nonzero_numeric(row[r_amt_idx])
        is_transaction_row = has_amt_left or has_amt_right

        # Check for header date row (e.g. "1-1 TO 31-1-2026" or "PORPOSEL")
        # Use word boundary for 'TO' to avoid matching 'MILTON', 'TON', etc.
        is_date_row = any(re.search(fr'\b{x}\b', row_strs) for x in ["TO", "PORPOSEL", "PROPOSAL", "PORPOSAL", "PURPOSEL"])
        
        # Try to parse a date from Column 3 (Index 2) first, as it is the primary header date location
        col_3_parsed = None
        if not is_transaction_row and len(row) > 2 and row[2]:
            cell = row[2]
            if isinstance(cell, (datetime.date, datetime.datetime)):
                col_3_parsed = cell
            elif isinstance(cell, str):
                cell_val = cell.strip()
                all_matches = re.findall(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})', cell_val)
                if all_matches:
                    g1, g2, y = all_matches[-1]
                    if len(y) == 2:
                        y = "20" + y
                    try:
                        # Try DD.MM.YYYY first (g1=day, g2=month)
                        col_3_parsed = datetime.datetime(int(y), int(g2), int(g1))
                    except ValueError:
                        try:
                            # Fallback to MM.DD.YYYY (g1=month, g2=day)
                            col_3_parsed = datetime.datetime(int(y), int(g1), int(g2))
                        except ValueError: pass
                if not col_3_parsed:
                    try:
                        if re.search(r'\d{2,4}', cell_val):
                            d = getdate(cell_val)
                            if d and d.year > 1900:
                                col_3_parsed = d
                    except: pass

        if col_3_parsed:
            header_date = col_3_parsed
            continue

        # We only try to set/update header_date if it's a date row OR if we don't have one yet.
        if not is_transaction_row and (is_date_row or header_date is None):
            new_header_date = None
            
            # Prioritize Column 3 (Index 2) per user request
            cells_to_check = []
            if len(row) > 2 and row[2]:
                cells_to_check.append(row[2])
            for cell in row:
                if cell and cell not in cells_to_check:
                    cells_to_check.append(cell)
            
            for cell in cells_to_check:
                parsed = None
                if isinstance(cell, (datetime.date, datetime.datetime)):
                    parsed = cell
                elif isinstance(cell, str):
                    cell_val = cell.strip()
                    all_matches = re.findall(r'(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})', cell_val)
                    if all_matches:
                        g1, g2, y = all_matches[-1]
                        if len(y) == 2:
                            y = "20" + y
                        try:
                            # Try DD.MM.YYYY first (g1=day, g2=month)
                            parsed = datetime.datetime(int(y), int(g2), int(g1))
                        except ValueError:
                            try:
                                # Fallback to MM.DD.YYYY (g1=month, g2=day)
                                parsed = datetime.datetime(int(y), int(g1), int(g2))
                            except ValueError: pass
                    
                    if not parsed:
                        try:
                            if re.search(r'\d{2,4}', cell_val):
                                d = getdate(cell_val)
                                if d and d.year > 1900:
                                    parsed = d
                        except: pass
                
                if parsed:
                    if re.search(r'\d{2,4}', str(cell)) or (isinstance(cell, datetime.date) and cell.year > 2000):
                        new_header_date = parsed
                        if len(row) > 2 and cell == row[2]:
                            break
                
            if new_header_date:
                header_date = new_header_date
                continue 
        
        if not header_date:
            continue
        
        # skip header rows, summary rows, and empty rows
        if not any(v is not None for v in row): continue
        if "AMOUNT" in row_strs and "AMT" in row_strs:
            continue
        if "TOTAL" in row_strs:
            continue
        if "OPP.BAL." in row_strs or "OP. BAL" in row_strs:
            continue
            
        # Left side (Receive)
        l_amt     = row[l_amt_idx] if len(row) > l_amt_idx else None
        l_party   = row[l_party_idx] if len(row) > l_party_idx else None
        l_company = row[l_company_idx] if l_company_idx is not None and len(row) > l_company_idx else None
        l_bank    = row[l_bank_idx] if l_bank_idx is not None and len(row) > l_bank_idx else None
        l_date    = row[l_date_idx] if len(row) > l_date_idx else None
        
        # Right side (Pay)
        r_amt     = row[r_amt_idx] if len(row) > r_amt_idx else None
        r_party   = row[r_party_idx] if len(row) > r_party_idx else None
        r_company = row[r_company_idx] if r_company_idx is not None and len(row) > r_company_idx else None
        r_bank    = row[r_bank_idx] if r_bank_idx is not None and len(row) > r_bank_idx else None
        r_date    = row[r_date_idx] if len(row) > r_date_idx else None

        def build_remark(comp, bank):
            parts = []
            if comp: parts.append(str(comp).strip())
            if bank: parts.append(str(bank).strip())
            return " ".join([p for p in parts if p])

        l_remark = build_remark(l_company, l_bank)
        r_remark = build_remark(r_company, r_bank)
        
        def parse_row_date(val, h_date):
            if not val: return None
            if isinstance(val, (datetime.date, datetime.datetime)):
                return val.replace(year=h_date.year)
            if isinstance(val, str):
                val = val.strip()
                if not val: return None
                try:
                    # Handle "Jan 01" style by appending year
                    if not re.search(r'\d{4}', val):
                        val_with_year = f"{val} {h_date.year}"
                        return getdate(val_with_year)
                    return getdate(val)
                except:
                    pass
            return None

        def get_final_amt(val):
            try:
                if val is None: return 0
                return float(str(val).replace(',', '').strip() or 0)
            except (ValueError, TypeError):
                return 0

        def is_numeric(val):
            if val is None: return False
            try:
                float(str(val).replace(',', '').strip())
                return True
            except:
                return False

        # Date Logic:
        # Posting Date = Row Date (e.g. "Jan 01")
        # Entry Date = Header Date (from Column 5, e.g. "01/31/2026")
        f_header_date = header_date.strftime('%Y-%m-%d')

        # Left side (Receive)
        if is_numeric(l_amt) and l_party and str(l_party).strip():
            row_date_obj = parse_row_date(l_date, header_date)
            f_posting_date = row_date_obj.strftime('%Y-%m-%d') if row_date_obj else f_header_date
            
            final_amt = get_final_amt(l_amt)
            
            acc_paid_from = f"ADV AC - {company_abbr}"
            final_l_party = str(l_party).strip() if l_party else l_party
            acc_paid_to = f"LC - {company_abbr}"
            
            out_sheet.append([
                "Receive", f_posting_date, f_header_date, company_name, "Customer", final_l_party ,
                acc_paid_from, "Receivable", acc_paid_to, final_amt, final_amt, l_remark, current_user
            ])
        
        # Right side (Pay)
        if is_numeric(r_amt) and r_party and str(r_party).strip():
            row_r_date_obj = parse_row_date(r_date, header_date)
            f_posting_r_date = row_r_date_obj.strftime('%Y-%m-%d') if row_r_date_obj else f_header_date

            final_amt = get_final_amt(r_amt)
            
            acc_paid_from =f"LC - {company_abbr}"
            final_r_party = str(r_party).strip() if r_party else r_party
            acc_paid_from_row = f"ADV AC - {company_abbr}"

            out_sheet.append([
                "Pay", f_posting_r_date, f_header_date, company_name, "Customer", final_r_party ,
                acc_paid_from, "Cash", acc_paid_from_row, final_amt, final_amt, r_remark, current_user
            ])


    if errors:
        return {"errors": errors}

    # Save output
    output_filename = f"converted_ledger_{frappe.generate_hash(length=8)}.xlsx"
    output_path = frappe.get_site_path('public', 'files', output_filename)
    out_wb.save(output_path)
    
    # Register file in database
    with open(output_path, 'rb') as f:
        file_doc = save_file(output_filename, f.read(), 'Page', 'ss-excel-to-ledger-adv-lc', is_private=0)
    
    return {
        "file_url": file_doc.file_url
    }
