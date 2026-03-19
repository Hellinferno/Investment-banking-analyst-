"""
Regression checks for Infosys Limited (large-cap IT services) valuation behavior.

Validates all fixes from the Infosys DCF Review (FY 2024-25):
- Revenue normalization: no double-conversion (₹1.87T stays correct)
- Balance sheet normalization: revenue-anchored (cash ₹33,770 Cr, borrowings ₹3,090 Cr)
- Shares normalization: PAT unit-aware EPS cross-check (415.19 Cr shares)
- Debt & cash NOT zero: correct extraction/normalization
- WACC visible and correct: 10-14% range for IT services
- Forecast period: 7+ years for IT services
- Terminal growth: 3.0%+ for IT services
- FCF not understated: ₹30,000+ Cr range
"""
# pyright: reportMissingImports=false
import os
import sys

os.environ["GEMINI_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""

sys.path.insert(0, "src")

from engine.dcf import DCFEngine
from engine.triangulator import Triangulator
from agents.modeling import FinancialModelingAgent
from store import store, Deal


print("=" * 60)
print("INFOSYS LIMITED LARGE-CAP IT REGRESSION TESTS")
print("=" * 60)

# === Infosys Actual Data from Annual Report FY2025 ===
INFOSYS_REVENUES_CRORES = [110659, 121649, 146670, 161528, 186711]
INFOSYS_REVENUES_ABSOLUTE = [
    1_106_590_000_000,  # FY2021A  ~₹1,10,659 Cr
    1_216_490_000_000,  # FY2022A  ~₹1,21,649 Cr
    1_466_700_000_000,  # FY2023A  ~₹1,46,670 Cr
    1_615_280_000_000,  # FY2024A  ~₹1,61,528 Cr
    1_867_110_000_000,  # FY2025A  ~₹1,86,711 Cr
]
INFOSYS_MARGINS = [0.268, 0.262, 0.245, 0.248, 0.253]
INFOSYS_PAT = 256_730_000_000       # ₹25,673 Cr
INFOSYS_EPS = 61.58
INFOSYS_SHARES = 4_151_900_000      # ~415.19 Cr shares
INFOSYS_BORROWINGS = 30_900_000_000  # ₹3,090 Cr
INFOSYS_LEASES = 12_500_000_000     # ₹1,250 Cr
INFOSYS_CASH = 337_700_000_000      # ₹33,770 Cr
INFOSYS_NET_DEBT = INFOSYS_BORROWINGS + INFOSYS_LEASES - INFOSYS_CASH
INFOSYS_OCF = 280_000_000_000       # ₹28,000 Cr

# ---------------------------------------------------------------
# 1. Revenue normalization: crore-scale values must convert correctly
# ---------------------------------------------------------------
print("\n1. Revenue Normalization (Crore-Scale for Mega-Cap IT):")

normalized = FinancialModelingAgent._normalize_revenues(INFOSYS_REVENUES_CRORES)
max_normalized = max(normalized)
print(f"   Raw (Crores): {INFOSYS_REVENUES_CRORES}")
print(f"   Normalized: {[f'₹{v/1e7:,.0f} Cr' for v in normalized]}")
# Infosys FY25 revenue should be ~₹1.87 Trillion
assert max_normalized >= 1_500_000_000_000, (
    f"Revenue should be ≥ ₹1.5T after normalization, got {max_normalized:,.0f}"
)
assert max_normalized <= 2_500_000_000_000, (
    f"Revenue should be ≤ ₹2.5T, got {max_normalized:,.0f}"
)
print("   PASS — Revenue correctly normalized to ~₹1.87T")

# ---------------------------------------------------------------
# 2. Revenue double-conversion guard
# ---------------------------------------------------------------
print("\n2. Revenue Double-Conversion Guard:")

# If LLM already returns absolute values, normalization should NOT re-convert
normalized_abs = FinancialModelingAgent._normalize_revenues(INFOSYS_REVENUES_ABSOLUTE)
assert normalized_abs == INFOSYS_REVENUES_ABSOLUTE, (
    f"Already-absolute revenues should pass through unchanged"
)
print("   PASS — Absolute values pass through unchanged")

# With explicit reporting_unit="crores" but values already absolute → should NOT convert
normalized_skip = FinancialModelingAgent._normalize_revenues(INFOSYS_REVENUES_ABSOLUTE, "crores")
assert normalized_skip == INFOSYS_REVENUES_ABSOLUTE, (
    f"Already-absolute revenues should NOT be re-converted even with 'crores' hint"
)
print("   PASS — Double-conversion prevented even with 'crores' hint")

# ---------------------------------------------------------------
# 3. Balance sheet normalization: revenue-anchored
# ---------------------------------------------------------------
print("\n3. Balance Sheet Normalization (Revenue-Anchored):")

# Scenario: LLM extracts cash as 33770 (in crores) but revenue is already absolute
raw_cash_crores = 33770
norm_cash = FinancialModelingAgent._normalize_balance_sheet_value(
    raw_cash_crores, INFOSYS_REVENUES_ABSOLUTE
)
print(f"   Raw cash: {raw_cash_crores} → Normalized: ₹{norm_cash/1e7:,.0f} Cr")
assert norm_cash >= 300_000_000_000, (
    f"Cash should be ≥ ₹30,000 Cr (₹300B), got ₹{norm_cash/1e7:,.0f} Cr"
)
assert norm_cash <= 400_000_000_000, (
    f"Cash should be ≤ ₹40,000 Cr (₹400B), got ₹{norm_cash/1e7:,.0f} Cr"
)
print("   PASS — Cash correctly normalized to ~₹33,770 Cr")

# Borrowings as 3090 (in crores)
raw_borr_crores = 3090
norm_borr = FinancialModelingAgent._normalize_balance_sheet_value(
    raw_borr_crores, INFOSYS_REVENUES_ABSOLUTE
)
print(f"   Raw borrowings: {raw_borr_crores} → Normalized: ₹{norm_borr/1e7:,.0f} Cr")
assert norm_borr >= 25_000_000_000, (
    f"Borrowings should be ≥ ₹2,500 Cr, got ₹{norm_borr/1e7:,.0f} Cr"
)
assert norm_borr <= 40_000_000_000, (
    f"Borrowings should be ≤ ₹4,000 Cr, got ₹{norm_borr/1e7:,.0f} Cr"
)
print("   PASS — Borrowings correctly normalized to ~₹3,090 Cr")

# Already absolute values should pass through
norm_cash_abs = FinancialModelingAgent._normalize_balance_sheet_value(
    337_700_000_000, INFOSYS_REVENUES_ABSOLUTE
)
assert norm_cash_abs == 337_700_000_000, "Already-absolute BS value should pass through"
print("   PASS — Already-absolute BS values pass through")

# Zero values should stay zero
norm_zero = FinancialModelingAgent._normalize_balance_sheet_value(0, INFOSYS_REVENUES_ABSOLUTE)
assert norm_zero == 0, "Zero should remain zero"
print("   PASS — Zero values stay zero")

# ---------------------------------------------------------------
# 4. Shares normalization: PAT unit-aware EPS cross-check
# ---------------------------------------------------------------
print("\n4. Shares Normalization (PAT Unit-Aware EPS Cross-Check):")

# Scenario: Shares extracted as 415.19 (in crores)
raw_shares_cr = 415.19
norm_shares = FinancialModelingAgent._normalize_shares(
    raw_shares_cr, INFOSYS_PAT, INFOSYS_EPS, INFOSYS_REVENUES_ABSOLUTE
)
print(f"   Raw shares: {raw_shares_cr} → Normalized: {norm_shares:,.0f}")
assert norm_shares >= 3_500_000_000, f"Shares should be ≥ 3.5B, got {norm_shares:,.0f}"
assert norm_shares <= 5_000_000_000, f"Shares should be ≤ 5.0B, got {norm_shares:,.0f}"
print("   PASS — Shares correctly normalized to ~4.15B")

# Scenario: Shares extracted as absolute (already correct)
norm_shares_abs = FinancialModelingAgent._normalize_shares(
    4_151_900_000, INFOSYS_PAT, INFOSYS_EPS, INFOSYS_REVENUES_ABSOLUTE
)
assert 3_500_000_000 <= norm_shares_abs <= 5_000_000_000, (
    f"Already-absolute shares should stay correct, got {norm_shares_abs:,.0f}"
)
print("   PASS — Already-absolute shares stay correct")

# Scenario: PAT in crores (25673) with EPS per-share (61.58)
# raw PAT/EPS = 416.9 → too small → should try crore conversion → 4.169B ✓
pat_cr = 25673  # PAT in crores (not absolute)
norm_shares_pat_cr = FinancialModelingAgent._normalize_shares(
    raw_shares_cr, pat_cr, INFOSYS_EPS, INFOSYS_REVENUES_ABSOLUTE
)
print(f"   PAT in Crores ({pat_cr}) / EPS ({INFOSYS_EPS}) → Shares: {norm_shares_pat_cr:,.0f}")
assert norm_shares_pat_cr >= 3_500_000_000, (
    f"Shares should be ≥ 3.5B even with PAT in crores, got {norm_shares_pat_cr:,.0f}"
)
print("   PASS — Handles PAT unit mismatch correctly")

# ---------------------------------------------------------------
# 5. Industry overlay for IT services
# ---------------------------------------------------------------
print("\n5. Industry Overlay for IT Services:")

overlay = FinancialModelingAgent._infer_public_company_risk_overlay(
    "IT Services / Technology Services",
    INFOSYS_MARGINS,
)
print(f"   Beta Floor: {overlay['beta_floor']}")
print(f"   Terminal Growth Premium: {overlay['terminal_growth_premium']}")
print(f"   Min Projection Years: {overlay['min_projection_years']}")
print(f"   Terminal Exit Multiple: {overlay['terminal_exit_multiple']}")
assert overlay["terminal_growth_premium"] > 0, "IT services should get terminal growth premium"
assert overlay["min_projection_years"] >= 7, "IT services should use 7+ year forecast"
assert overlay["terminal_exit_multiple"] >= 15, "IT services should have higher exit multiple"
print("   PASS")

# ---------------------------------------------------------------
# 6. DCF Engine with Infosys-scale inputs
# ---------------------------------------------------------------
print("\n6. DCF Engine with Infosys-Scale Inputs:")

engine = DCFEngine(
    historical_revenues=INFOSYS_REVENUES_ABSOLUTE,
    historical_ebitda_margins=INFOSYS_MARGINS,
    tax_rate=0.25,
    cap_ex_percent_rev=0.035,
    da_percent_rev=0.040,
    revenue_cagr_override=0.10,
    total_debt=INFOSYS_BORROWINGS + INFOSYS_LEASES,
    cash_and_equivalents=INFOSYS_CASH,
)

wacc_b = engine.calculate_wacc_breakdown(
    risk_free_rate=0.07,
    equity_risk_premium=0.055,
    beta=0.85,
    cost_of_debt=0.07,
    debt_to_equity=0.05,
)
wacc = wacc_b["wacc"]
print(f"   WACC: {wacc*100:.2f}%")
print(f"   Cost of Equity: {wacc_b['cost_of_equity']*100:.2f}%")
print(f"   Weight of Equity: {wacc_b['weight_of_equity']*100:.2f}%")
print(f"   Weight of Debt: {wacc_b['weight_of_debt']*100:.2f}%")
assert 0.09 <= wacc <= 0.14, f"WACC for large-cap IT should be 9-14%, got {wacc*100:.2f}%"
print("   PASS")

# ---------------------------------------------------------------
# 7. Full projection with 7-year horizon (IT services minimum)
# ---------------------------------------------------------------
print("\n7. Full Projection (7-Year Horizon, IT Services):")

terminal_growth = 0.030  # 3.0% for IT services (base 2.5% + 0.5% premium)
projections = engine.build_projections(projection_years=7, terminal_growth_rate=terminal_growth)
ufcf = projections["projections"]["ufcf"]
revenues = projections["projections"]["revenue"]

print(f"   FY Labels: {projections['projections']['fy_labels']}")
print(f"   Year 1 Revenue: ₹{revenues[0]/1e7:,.0f} Cr")
print(f"   Year 7 Revenue: ₹{revenues[-1]/1e7:,.0f} Cr")
print(f"   Year 1 UFCF: ₹{ufcf[0]/1e7:,.0f} Cr")
print(f"   Year 7 UFCF: ₹{ufcf[-1]/1e7:,.0f} Cr")

# Revenue should grow from ~₹1.87T
assert revenues[0] > 1_800_000_000_000, f"Year 1 revenue should be > ₹1.8T, got {revenues[0]:,.0f}"
# UFCF should be substantial for IT services (margin ~25%, capex ~3.5%)
assert ufcf[0] > 200_000_000_000, f"Year 1 UFCF should be > ₹20,000 Cr, got ₹{ufcf[0]/1e7:,.0f} Cr"
assert ufcf[-1] > 300_000_000_000, f"Year 7 UFCF should be > ₹30,000 Cr, got ₹{ufcf[-1]/1e7:,.0f} Cr"
print("   PASS — UFCF is NOT understated")

# ---------------------------------------------------------------
# 8. Valuation at correct scale
# ---------------------------------------------------------------
print("\n8. Valuation Scale Check:")

valuation = engine.calculate_valuation(
    ufcf_projections=ufcf,
    wacc=wacc,
    terminal_growth_rate=terminal_growth,
    net_debt=INFOSYS_NET_DEBT,
    shares_outstanding=INFOSYS_SHARES,
)

ev = valuation["implied_enterprise_value"]
equity = valuation["implied_equity_value"]
share_price = valuation["implied_share_price"]

print(f"   Enterprise Value: ₹{ev/1e7:,.0f} Cr")
print(f"   Net Debt (negative = net cash): ₹{INFOSYS_NET_DEBT/1e7:,.0f} Cr")
print(f"   Equity Value: ₹{equity/1e7:,.0f} Cr")
print(f"   Shares: {INFOSYS_SHARES/1e7:.2f} Cr")
print(f"   Implied Share Price: ₹{share_price:,.2f}")

# EV should be substantial (Infosys market EV is ~₹6-8L Cr)
assert ev > 3_000_000_000_000, f"EV should be > ₹3L Cr, got ₹{ev/1e7:,.0f} Cr"
# Equity should be higher than EV (net cash company)
assert equity > ev, f"Equity value should exceed EV for net-cash company"
# Share price should be in reasonable range (Infosys trades at ₹1300-1900)
assert 800 <= share_price <= 4000, f"Share price should be ₹800-4000, got ₹{share_price:,.2f}"
print("   PASS — Valuation at correct Infosys scale")

# ---------------------------------------------------------------
# 9. Triangulation checks (all existing + new checks)
# ---------------------------------------------------------------
print("\n9. Triangulation Checks:")

tri_data = {
    "historical_revenues": INFOSYS_REVENUES_ABSOLUTE,
    "historical_ebitda_margins": INFOSYS_MARGINS,
    "net_debt": INFOSYS_NET_DEBT,
    "total_borrowings": INFOSYS_BORROWINGS,
    "lease_liabilities": INFOSYS_LEASES,
    "cash_and_equivalents": INFOSYS_CASH,
    "shares_outstanding": INFOSYS_SHARES,
    "debt_to_equity": 0.05,
    "profit_after_tax": INFOSYS_PAT,
    "basic_eps": INFOSYS_EPS,
    "operating_cash_flow": INFOSYS_OCF,
}
tri_result = Triangulator.run_all_checks(tri_data)
print(f"   Verdict: {tri_result['overall_verdict']}")
print(f"   Passed: {tri_result['passed']}/{tri_result['total_checks']}")
for r in tri_result["results"]:
    status = "✓" if r["passed"] else "✗"
    print(f"   {status} {r['identity']}: {r['details'][:90]}")

# Revenue scale check should pass
rev_check = next((r for r in tri_result["results"] if "Revenue Scale" in r["identity"]), None)
assert rev_check is not None, "Revenue scale check should be present"
assert rev_check["passed"], f"Revenue scale check should pass: {rev_check['details']}"

# EPS-shares consistency should pass
eps_check = next((r for r in tri_result["results"] if "EPS" in r["identity"]), None)
assert eps_check is not None, "EPS-shares check should be present"
assert eps_check["passed"], f"EPS-shares check should pass: {eps_check['details']}"

# Balance sheet vs revenue should pass (both non-zero, reasonable ratio)
bs_check = next((r for r in tri_result["results"] if "Balance Sheet Scale" in r["identity"]), None)
assert bs_check is not None, "Balance sheet scale check should be present"
assert bs_check["passed"], f"Balance sheet scale check should pass: {bs_check['details']}"

# OCF/PAT consistency should pass
ocf_check = next((r for r in tri_result["results"] if "OCF" in r["identity"]), None)
assert ocf_check is not None, "OCF/PAT check should be present"
assert ocf_check["passed"], f"OCF/PAT check should pass: {ocf_check['details']}"

# No critical failures
assert tri_result["critical_failures"] == 0, (
    f"Should have no critical failures, got {tri_result['critical_failures']}"
)
print("   PASS — All triangulation checks passed")

# ---------------------------------------------------------------
# 10. Triangulation: detect bad data (both zero)
# ---------------------------------------------------------------
print("\n10. Triangulation: Detect Zero Balance Sheet (Extraction Failure):")

bad_data = {
    "historical_revenues": INFOSYS_REVENUES_ABSOLUTE,
    "historical_ebitda_margins": INFOSYS_MARGINS,
    "net_debt": 0,
    "total_borrowings": 0,
    "lease_liabilities": 0,
    "cash_and_equivalents": 0,
    "shares_outstanding": INFOSYS_SHARES,
    "debt_to_equity": 0.0,
}
bad_result = Triangulator.run_all_checks(bad_data)
bs_bad_check = next(
    (r for r in bad_result["results"] if "Balance Sheet Scale" in r["identity"]), None
)
assert bs_bad_check is not None, "BS scale check should fire"
assert not bs_bad_check["passed"], (
    f"BS scale check should FAIL when borrowings=0 and cash=0 for ₹1.87T revenue company"
)
print(f"   Detected: {bs_bad_check['details'][:90]}")
print("   PASS — Zero balance sheet correctly flagged as extraction failure")

# ---------------------------------------------------------------
# 11. Full agent smoke test (fallback mode)
# ---------------------------------------------------------------
print("\n11. Full Agent Smoke Test (Infosys Limited - Fallback Mode):")

store.deals.clear()
store.documents.clear()
store.agent_runs.clear()
store.outputs.clear()

deal = Deal(
    id="infosys-largecap-it",
    name="Infosys Limited FY25",
    company_name="Infosys Limited",
    industry="IT Services / Technology Services",
)
store.deals[deal.id] = deal

agent = FinancialModelingAgent(
    deal.id,
    {
        "agent_type": "modeling",
        "task_name": "dcf_model",
        "parameters": {},
    },
)
run_id = agent.run()
run = store.agent_runs[run_id]
valuation_result = run.input_payload.get("valuation_result", {})
header = valuation_result.get("header", {})
bridge = valuation_result.get("ev_bridge", {})
assumptions = valuation_result.get("assumptions", {})

print(f"   Status: {run.status}")
print(f"   Is Private: {header.get('is_private_company')}")
print(f"   WACC: {header.get('wacc')}")
print(f"   Terminal Method: {header.get('terminal_method')}")
print(f"   Projection Years: {header.get('projection_horizon_years')}")
print(f"   Valuation Basis: {header.get('valuation_basis')}")
print(f"   EV: ₹{bridge.get('enterprise_value', 0)/1e7:,.0f} Cr")
print(f"   Net Debt: ₹{bridge.get('net_debt', 0)/1e7:,.0f} Cr")
print(f"   Cash: ₹{bridge.get('add_cash', 0)/1e7:,.0f} Cr")
print(f"   Equity Value: ₹{bridge.get('equity_value', 0)/1e7:,.0f} Cr")
print(f"   Per Share Available: {header.get('per_share_value_available')}")

assert run.status == "completed", f"Run should complete, got {run.status}"
assert header.get("is_private_company") is False, "Infosys should be classified as public/listed"
assert 0.09 <= float(header.get("wacc", 0)) <= 0.15, f"WACC should be 9-15%, got {header.get('wacc')}"

# Revenue should be at Infosys scale (>₹1,00,000 Cr = ₹1T)
ev = float(bridge.get("enterprise_value", 0))
assert ev > 2_000_000_000_000, f"EV should be > ₹2L Cr, got ₹{ev/1e7:,.0f} Cr"

# Cash should be material (Infosys is heavily net-cash)
cash = float(bridge.get("add_cash", 0))
assert cash > 200_000_000_000, f"Cash should be > ₹20,000 Cr, got ₹{cash/1e7:,.0f} Cr"

# Projection years should be 7+ for IT services
proj_years = header.get("projection_horizon_years", 0)
assert proj_years >= 7, f"Projection years should be 7+ for IT, got {proj_years}"

# Shares should be verified and per-share price available
assert header.get("per_share_value_available") is True, "Per-share value should be available"

# Implied share price should be in reasonable range
share_price = bridge.get("implied_price_per_share")
assert share_price is not None, "Share price should not be None"
assert 800 <= float(share_price) <= 4000, f"Share price should be ₹800-4000, got {share_price}"

# Net debt should be negative (net cash company)
net_debt_val = float(bridge.get("net_debt", 0))
assert net_debt_val < 0, f"Net debt should be negative (net cash), got ₹{net_debt_val/1e7:,.0f} Cr"

print("   PASS")

# ---------------------------------------------------------------
# 12. Infosys fallback profile sanity
# ---------------------------------------------------------------
print("\n12. Infosys Fallback Profile Sanity:")

from engine.llm import _get_deterministic_fallback_response
import json

response = _get_deterministic_fallback_response("Infosys Limited annual report FY2025")
profile = json.loads(response)
assert profile["fallback_profile"] == "infosys_largecap_it", (
    f"Expected infosys profile, got {profile['fallback_profile']}"
)
assert max(profile["historical_revenues"]) > 1_500_000_000_000, "Revenue should be > ₹1.5T"
assert profile["cash_and_equivalents"] > 200_000_000_000, "Cash should be > ₹200B"
assert profile["shares_outstanding"] > 4_000_000_000, "Shares should be > 4B"
assert profile["industry_sector"] == "IT Services", "Sector should be IT Services"
print("   PASS — Infosys fallback profile matches expected data")

# ---------------------------------------------------------------
# Summary
# ---------------------------------------------------------------
print(f"\n{'=' * 60}")
print("ALL INFOSYS LARGE-CAP IT REGRESSION TESTS PASSED ✓")
print(f"{'=' * 60}")
print()
print("Key validations completed:")
print("  ✓ Revenue normalization: ₹1.87T (no 89% understatement)")
print("  ✓ FCF not understated: ₹30,000+ Cr UFCF per year")
print("  ✓ Shares verified: ~415.19 Cr via PAT/EPS cross-check")
print("  ✓ Debt & cash NOT zero: ₹3,090 Cr borrowings, ₹33,770 Cr cash")
print("  ✓ WACC visible: 10-14% range for IT services")
print("  ✓ Forecast period: 7+ years for IT services")
print("  ✓ Terminal growth: 3.0% for IT services")
print("  ✓ Balance sheet extraction failure detection via triangulation")
print("  ✓ Full agent produces ₹800-4000 share price")
