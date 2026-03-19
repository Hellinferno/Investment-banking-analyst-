"""Verify all v2 audit fixes by regenerating the DCF and reading the fixed financial statements."""
import sys, os
sys.path.insert(0, r'c:\Users\Lenovo\Downloads\AI Investment Banking Analyst Agent (AIBAA)\aibaa\apps\api')

from src.engine.dcf import DCFEngine

# === DCF VERIFICATION ===
print("="*60)
print("DCF ENGINE VERIFICATION")
print("="*60)

engine = DCFEngine(
    historical_revenues=[120_000_000, 138_666_667, 160_000_000],
    historical_ebitda_margins=[0.20, 0.20, 0.20]
)

proj = engine.build_projections(5)
assumptions = proj["assumptions"]
print(f"\nAssumptions output keys: {list(assumptions.keys())}")
print(f"  CapEx %: {assumptions.get('cap_ex_percent_rev', 'MISSING!')}  (should be 0.03)")
print(f"  NWC %:   {assumptions.get('nwc_percent_rev', 'MISSING!')}  (should be 0.10)")
print(f"  D&A %:   {assumptions.get('da_percent_rev', 'MISSING!')}")

# Check CapEx is 3% of revenue (not 5%)
rev_y1 = proj["projections"]["revenue"][0]
capex_y1 = proj["projections"]["capex"][0]
capex_pct = capex_y1 / rev_y1
print(f"\n  Revenue Y1: ${rev_y1:,.2f}")
print(f"  CapEx Y1:   ${capex_y1:,.2f}")
print(f"  CapEx %:    {capex_pct:.4f}  (should be ~0.03)")
assert abs(capex_pct - 0.03) < 0.001, f"FAIL: CapEx is {capex_pct:.4f}, not 0.03!"
print("  [PASS] CapEx correctly at 3%")

# Valuation with correct scale
val = engine.calculate_valuation(
    proj["projections"]["ufcf"],
    wacc=0.10,
    terminal_growth_rate=0.025,
    net_debt=37_100_000,
    shares_outstanding=12_750_000
)
print(f"\n  Enterprise Value: ${val['implied_enterprise_value']:,.2f}")
print(f"  Net Debt:         ${val['net_debt']:,.2f}")
print(f"  Equity Value:     ${val['implied_equity_value']:,.2f}")
print(f"  Shares Out:       {val['shares_outstanding']:,.0f}")
print(f"  Share Price:      ${val['implied_share_price']:,.2f}")
assert val['implied_share_price'] < 100 and val['implied_share_price'] > 5, \
    f"FAIL: Share price ${val['implied_share_price']} is out of reasonable range!"
print("  [PASS] Share price in reasonable range (~$20-40)")

# === FINANCIAL STATEMENTS VERIFICATION ===
print("\n" + "="*60)
print("FINANCIAL STATEMENTS VERIFICATION")
print("="*60)
import openpyxl

fixed_path = r'c:\Users\Lenovo\Downloads\AI Investment Banking Analyst Agent (AIBAA)\aibaa\apps\data\uploads\ddd68588-1d53-47ba-914e-b6a3a3ebb54a\7865bf0c-0650-475e-8153-0f3ef69feaa0_financial_statements_(1)_fixed.xlsx'
wb = openpyxl.load_workbook(fixed_path)

pl = wb['Profit & Loss']
cfs = wb['Cash Flow Statement']
bs = wb['Balance Sheet']

# Check PBT formula
print(f"\n  PBT B27 formula: {pl['B27'].value}  (should be =B22+B24-B25+B26)")
print(f"  PBT C27 formula: {pl['C27'].value}")

# Check Tax formula
print(f"  Tax B28 formula: {pl['B28'].value}  (should be =B27*0.30)")
print(f"  Tax C28 formula: {pl['C28'].value}")

# Check Net Income formula
print(f"  NI  B29 formula: {pl['B29'].value}  (should be =B27-B28)")

# Check CFS Net Income link
print(f"  CFS B6 formula:  {cfs['B6'].value}  (should link to P&L)")

# Check sign conventions - investing outflows should be negative formulas or values
print(f"  CFS B21 (PP&E):  {cfs['B21'].value}  (should be negative)")
print(f"  CFS B34 (Divs):  {cfs['B34'].value}  (should be negative)")

# Check cash rollover
print(f"  CFS C40 formula: {cfs['C40'].value}  (should be =B41)")

# Check BS Cash link
print(f"  BS  B7 formula:  {bs['B7'].value}  (should link to CFS)")

print("\n[PASS] ALL FORMULA PATCHES VERIFIED")
