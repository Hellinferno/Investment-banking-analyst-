"""
fix_financial_statements.py
Fixes all 6 critical errors in financial_statements.xlsx identified in the v2 audit.
"""
import os
import glob
import openpyxl
from openpyxl.styles import Font

blue_font = Font(name='Arial', color='0000FF')
green_font = Font(name='Arial', color='008000')


def fix_financial_statements(filepath):
    print(f"Loading {filepath}...")
    wb = openpyxl.load_workbook(filepath)

    pl = wb['Profit & Loss']
    cfs = wb['Cash Flow Statement']
    bs = wb['Balance Sheet']

    # =====================================================================
    # ERROR 6 (Audit) — PBT formula: Interest Expense ADDED instead of SUBTRACTED
    # Row 27: was =B22+SUM(B24:B26) which adds IntExp as positive
    # Correct: =B22+B24-B25+B26  (EBIT + IntIncome - IntExpense + Other)
    # =====================================================================
    print("FIX: PBT formula — subtract Interest Expense")
    for col in ['B', 'C']:
        pl[f'{col}27'] = f'={col}22+{col}24-{col}25+{col}26'
        pl[f'{col}27'].font = blue_font

    # =====================================================================
    # ERROR 7 — Tax is hardcoded (21000/24800) instead of =PBT*0.30
    # Row 28
    # =====================================================================
    print("FIX: Tax — replace hardcoded with =PBT*0.30")
    for col in ['B', 'C']:
        pl[f'{col}28'] = f'={col}27*0.30'
        pl[f'{col}28'].font = blue_font

    # =====================================================================
    # ERROR 7b — Net Income formula adds Tax instead of subtracting
    # Row 29: was =B27+B28, should be =B27-B28
    # =====================================================================
    print("FIX: Net Income — subtract tax from PBT")
    for col in ['B', 'C']:
        pl[f'{col}29'] = f'={col}27-{col}28'
        pl[f'{col}29'].font = blue_font

    # =====================================================================
    # ERROR 8 — CFS Net Income is hardcoded, not linked to P&L
    # Row 6: was 49000/57600, should link to P&L Net Income (Row 29)
    # =====================================================================
    print("FIX: CFS Net Income — link to P&L")
    cfs['B6'] = "='Profit & Loss'!B29"
    cfs['B6'].font = green_font
    cfs['C6'] = "='Profit & Loss'!C29"
    cfs['C6'].font = green_font

    # =====================================================================
    # ERROR 9 — CFI and CFF outflows stored as positive (wrong sign)
    # Investing outflows that should be NEGATIVE:
    #   R21 Purchase of PP&E, R23 Acquisition, R24 Purchase of Investments, R26 Cap Dev Costs
    # Financing outflows that should be NEGATIVE:
    #   R31 Repayment of LT Debt, R33 Repayment of ST Borrowings, R34 Dividends, R35 Treasury
    # =====================================================================
    print("FIX: CFI/CFF sign conventions — negate outflows")
    investing_outflow_rows = [21, 23, 24, 26]
    financing_outflow_rows = [31, 33, 34, 35]

    for row in investing_outflow_rows + financing_outflow_rows:
        for col in ['B', 'C']:
            cell = cfs[f'{col}{row}']
            val = cell.value
            if val is not None and isinstance(val, (int, float)) and val > 0:
                cell.value = -val
                cell.font = blue_font

    # =====================================================================
    # ERROR 10 — FY2024 beginning cash not rolled from FY2023 ending
    # Row 40, C40 is hardcoded 45200, should be =B41
    # =====================================================================
    print("FIX: FY2024 beginning cash — roll from FY2023 ending")
    cfs['C40'] = '=B41'
    cfs['C40'].font = green_font

    # =====================================================================
    # ERROR 5 (BS) — Link BS Cash to CFS Ending Cash
    # Row 7 Cash should reflect CFS ending cash
    # =====================================================================
    print("FIX: BS Cash — link to CFS Ending Cash")
    bs['B7'] = "='Cash Flow Statement'!B41"
    bs['B7'].font = green_font
    bs['C7'] = "='Cash Flow Statement'!C41"
    bs['C7'].font = green_font

    # Save
    out_path = filepath.replace('.xlsx', '_fixed.xlsx')
    wb.save(out_path)
    print(f"Saved fixed file to: {out_path}")
    return out_path


if __name__ == "__main__":
    upload_dir = os.path.join(os.path.dirname(__file__), 'uploads')
    targets = glob.glob(os.path.join(upload_dir, '**', '*financial_statements*.xlsx'), recursive=True)
    # Skip already-fixed files
    targets = [t for t in targets if '_fixed' not in t]

    if not targets:
        print("No financial_statements.xlsx found in uploads.")
    for t in targets:
        fix_financial_statements(t)
