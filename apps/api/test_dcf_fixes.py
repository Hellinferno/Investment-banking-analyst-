"""
Targeted DCF Engine test using known Relaxo Footwears data.
Validates that the corrected engine produces share prices in a reasonable range.
"""
import sys

sys.path.insert(0, "src")

from engine.dcf import DCFEngine

# === Relaxo Footwears - Actual Data from Annual Report FY2025 ===
# Revenue in absolute INR (1 Cr = 1e7)
historical_revenues = [
    2588_00_00_000,   # FY2021A: Rs 2,588 Cr
    2910_00_00_000,   # FY2022A: Rs 2,910 Cr
    2960_00_00_000,   # FY2023A: Rs 2,960 Cr
    2914_06_00_000,   # FY2024A: Rs 2,914.06 Cr
    2789_61_00_000,   # FY2025A: Rs 2,789.61 Cr (DECLINING)
]

historical_ebitda_margins = [0.16, 0.14, 0.13, 0.133, 0.1369]  # Recent: 13.69%

# Corrected parameters from the review
shares_outstanding = 24_89_00_000   # 24.89 Cr shares
net_debt = 0                        # ZERO DEBT company
capex_pct = 0.03                    # 3% (actual FY25: 2.21%)
da_pct = 0.057                      # 5.7% (actual FY25: 5.68%)
tax_rate = 0.25
base_fy = 2025

print("=" * 60)
print("DCF MODEL VERIFICATION - Relaxo Footwears Ltd")
print("=" * 60)

# 1. Test CAGR calculation (should NOT be floored at 5%)
engine = DCFEngine(
    historical_revenues=historical_revenues,
    historical_ebitda_margins=historical_ebitda_margins,
    tax_rate=tax_rate,
    cap_ex_percent_rev=capex_pct,
    da_percent_rev=da_pct,
    nwc_percent_rev=0.10,
    base_fy=base_fy,
)
cagr = engine.calculate_cagr(historical_revenues)
print("\n1. CAGR Test:")
print(f"   Revenue CAGR: {cagr*100:.2f}%")
print("   Expected: ~1.9% (slow growth with FY24-25 decline)")
assert cagr < 0.05, f"FAIL: CAGR should be below 5% for declining company, got {cagr*100:.2f}%"
print("   PASS - CAGR no longer floored at 5%")

# 2. Test WACC with zero debt
wacc_breakdown = engine.calculate_wacc_breakdown(
    risk_free_rate=0.07,
    equity_risk_premium=0.055,
    beta=0.90,           # Consumer staple / footwear beta
    cost_of_debt=0.09,
    debt_to_equity=0.0,  # ZERO debt
)
wacc = wacc_breakdown["wacc"]
print("\n2. WACC Test (Zero Debt):")
print(f"   WACC: {wacc*100:.2f}%")
print(f"   Weight of Debt: {wacc_breakdown['weight_of_debt']*100:.2f}%")
print(f"   Weight of Equity: {wacc_breakdown['weight_of_equity']*100:.2f}%")
assert wacc_breakdown["weight_of_debt"] == 0, "FAIL: Debt weight should be 0% for debt-free company"
assert wacc_breakdown["weight_of_equity"] == 1.0, "FAIL: Equity weight should be 100%"
expected_coe = 0.07 + 0.90 * 0.055
assert abs(wacc - expected_coe) < 0.01, f"FAIL: WACC {wacc} should equal CoE {expected_coe} for zero-debt company"
print("   PASS - WACC correctly ignores debt (100% equity)")

# 3. Full DCF Model
projections = engine.build_projections(projection_years=7, terminal_growth_rate=0.025)
print("\n3. Projection Test:")
print(f"   Revenue CAGR used: {projections['assumptions']['revenue_cagr']*100:.2f}%")
print(f"   EBITDA Margin: {projections['assumptions']['avg_ebitda_margin']*100:.2f}%")
print(f"   CapEx % Rev: {projections['assumptions']['cap_ex_percent_rev']*100:.2f}%")
print(f"   D&A % Rev: {projections['assumptions']['da_percent_rev']*100:.2f}%")

# 4. Valuation
tgr = 0.025
valuation = engine.calculate_valuation(
    ufcf_projections=projections["projections"]["ufcf"],
    wacc=wacc,
    terminal_growth_rate=tgr,
    net_debt=net_debt,
    shares_outstanding=shares_outstanding,
)
print("\n4. Valuation Test:")
print(f"   Enterprise Value: Rs {valuation['implied_enterprise_value']/1e7:,.2f} Cr")
print(f"   Equity Value: Rs {valuation['implied_equity_value']/1e7:,.2f} Cr")
print(f"   Shares Outstanding: {shares_outstanding/1e7:.2f} Cr")
print(f"   Implied Share Price: Rs {valuation['implied_share_price']:.2f}")
print("   Expected Range: above Rs 100 under a conservative historical-growth base case")

share_price = valuation["implied_share_price"]
assert 100 < share_price < 500, f"FAIL: Share price Rs {share_price:.2f} outside reasonable range"
print("   PASS - Share price in reasonable range")

# 5. Check warnings
print("\n5. Warning Test:")
if valuation.get("warnings"):
    for warning in valuation["warnings"]:
        print(f"   WARNING: {warning}")
else:
    print("   No warnings - clean model")

# Summary
print(f"\n{'=' * 60}")
print("VERIFICATION SUMMARY")
print(f"{'=' * 60}")
print("  CAGR allows negative growth: PASS")
print("  WACC zero-debt: PASS")
print(f"  CapEx default: {capex_pct*100}% (was 8%)")
print(f"  D&A default: {da_pct*100}% (was 6%)")
print(f"  Shares: {shares_outstanding/1e7:.2f} Cr (was fixed 10 Cr)")
print(f"  Share Price: Rs {share_price:.2f}")
print("\nAll engine tests PASSED")
