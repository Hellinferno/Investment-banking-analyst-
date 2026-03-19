"""Regression checks for HCL Technologies (large-cap IT services) valuation behavior."""
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
print("HCL TECHNOLOGIES LARGE-CAP IT REGRESSION TESTS")
print("=" * 60)

# ---------------------------------------------------------------
# 1. Revenue normalization: crore-scale values must convert correctly
# ---------------------------------------------------------------
print("\n1. Revenue Normalization (Crore-Scale):")

# Values in crores (as LLM might extract from "₹ in Crores" statement)
raw_crore_revenues = [85405, 91846, 101456, 109650, 117055]
normalized = FinancialModelingAgent._normalize_revenues(raw_crore_revenues)
max_normalized = max(normalized)
print(f"   Raw: {raw_crore_revenues}")
print(f"   Normalized: {[f'{v:,.0f}' for v in normalized]}")
# HCL FY25 revenue should be ~₹1.17 Trillion = 1.17e12
assert max_normalized >= 500_000_000_000, (
    f"Revenue should be at least ₹50,000 Cr (₹500B) after normalization, got {max_normalized:,.0f}"
)
assert max_normalized <= 2_000_000_000_000, (
    f"Revenue should not exceed ₹2L Cr (₹2T), got {max_normalized:,.0f}"
)
print("   PASS")

# With explicit reporting_unit hint
print("\n2. Revenue Normalization with Reporting Unit Hint:")
normalized_with_hint = FinancialModelingAgent._normalize_revenues(raw_crore_revenues, "crores")
print(f"   Hint='crores', Normalized: {[f'{v:,.0f}' for v in normalized_with_hint]}")
assert all(abs(a - b * 1e7) < 1 for a, b in zip(normalized_with_hint, raw_crore_revenues))
print("   PASS")

# ---------------------------------------------------------------
# 3. Shares normalization with EPS cross-check
# ---------------------------------------------------------------
print("\n3. Shares Normalization with EPS Cross-Check:")

# HCL: PAT=₹18,104 Cr, EPS=₹64.16, Shares=~282 Cr
pat = 181_040_000_000  # ₹18,104 Cr in absolute
eps = 64.16
expected_shares = pat / eps  # ~282 Cr shares

# If shares extracted as 271.6 (in crores), normalization should convert
raw_shares_in_crores = 271.6
normalized_shares = FinancialModelingAgent._normalize_shares(raw_shares_in_crores, pat, eps)
print(f"   Raw shares: {raw_shares_in_crores}")
print(f"   Normalized: {normalized_shares:,.0f}")
assert normalized_shares >= 2_000_000_000, f"Shares should be ~2.7B+, got {normalized_shares:,.0f}"
assert normalized_shares <= 3_500_000_000, f"Shares should be ≤3.5B, got {normalized_shares:,.0f}"
print("   PASS")

# ---------------------------------------------------------------
# 4. Industry overlay for IT services
# ---------------------------------------------------------------
print("\n4. Industry Overlay for IT Services:")

overlay = FinancialModelingAgent._infer_public_company_risk_overlay(
    "IT Services / Technology Services",
    [0.235, 0.225, 0.215, 0.218, 0.222],
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
# 5. DCF Engine with HCL-scale inputs
# ---------------------------------------------------------------
print("\n5. DCF Engine with HCL-Scale Inputs:")

hcl_revenues = [
    854_050_000_000,
    918_460_000_000,
    1_014_560_000_000,
    1_096_500_000_000,
    1_170_550_000_000,
]
hcl_margins = [0.235, 0.225, 0.215, 0.218, 0.222]

engine = DCFEngine(
    historical_revenues=hcl_revenues,
    historical_ebitda_margins=hcl_margins,
    tax_rate=0.25,
    cap_ex_percent_rev=0.04,
    da_percent_rev=0.045,
    revenue_cagr_override=0.09,
    total_debt=92_000_000_000,
    cash_and_equivalents=180_000_000_000,
)

wacc_breakdown = engine.calculate_wacc_breakdown(
    risk_free_rate=0.07,
    equity_risk_premium=0.055,
    beta=0.90,
    cost_of_debt=0.075,
    debt_to_equity=0.12,
)
wacc = wacc_breakdown["wacc"]
print(f"   WACC: {wacc*100:.2f}%")
print(f"   Cost of Equity: {wacc_breakdown['cost_of_equity']*100:.2f}%")
assert 0.10 <= wacc <= 0.14, f"WACC for large-cap IT should be 10-14%, got {wacc*100:.2f}%"
print("   PASS")

# ---------------------------------------------------------------
# 6. Full projection with 7-year horizon
# ---------------------------------------------------------------
print("\n6. Full Projection (7-Year Horizon):")

terminal_growth = 0.030  # 3.0% for IT services
projections = engine.build_projections(projection_years=7, terminal_growth_rate=terminal_growth)
ufcf = projections["projections"]["ufcf"]
revenues = projections["projections"]["revenue"]

print(f"   FY Labels: {projections['projections']['fy_labels']}")
print(f"   Year 1 Revenue: ₹{revenues[0]/1e7:,.0f} Cr")
print(f"   Year 7 Revenue: ₹{revenues[-1]/1e7:,.0f} Cr")
print(f"   Year 1 UFCF: ₹{ufcf[0]/1e7:,.0f} Cr")
print(f"   Year 7 UFCF: ₹{ufcf[-1]/1e7:,.0f} Cr")

# Revenue should grow from ~₹1.17T
assert revenues[0] > 1_000_000_000_000, f"Year 1 revenue should be > ₹1T, got {revenues[0]:,.0f}"
# UFCF should be substantial for IT services
assert ufcf[-1] > 100_000_000_000, f"Final year UFCF should be > ₹100B, got {ufcf[-1]:,.0f}"
print("   PASS")

# ---------------------------------------------------------------
# 7. Valuation at correct scale
# ---------------------------------------------------------------
print("\n7. Valuation Scale Check:")

net_debt = 92_000_000_000 - 180_000_000_000  # net cash positive
shares = 2_716_000_000

valuation = engine.calculate_valuation(
    ufcf_projections=ufcf,
    wacc=wacc,
    terminal_growth_rate=terminal_growth,
    net_debt=net_debt,
    shares_outstanding=shares,
)

ev = valuation["implied_enterprise_value"]
equity = valuation["implied_equity_value"]
share_price = valuation["implied_share_price"]

print(f"   Enterprise Value: ₹{ev/1e7:,.0f} Cr")
print(f"   Equity Value: ₹{equity/1e7:,.0f} Cr")
print(f"   Implied Share Price: ₹{share_price:,.2f}")

# EV should be in the 3-10L Cr range for HCL
assert ev > 2_000_000_000_000, f"EV should be > ₹2L Cr, got ₹{ev/1e7:,.0f} Cr"
# Share price should be in a reasonable range (₹500-5000 for HCL)
assert share_price is not None
assert 500 <= share_price <= 5000, f"Share price should be ₹500-5000, got ₹{share_price:,.2f}"
print("   PASS")

# ---------------------------------------------------------------
# 8. Triangulation checks
# ---------------------------------------------------------------
print("\n8. Triangulation Checks:")

tri_data = {
    "historical_revenues": hcl_revenues,
    "historical_ebitda_margins": hcl_margins,
    "net_debt": net_debt,
    "total_borrowings": 50_000_000_000,
    "lease_liabilities": 42_000_000_000,
    "cash_and_equivalents": 180_000_000_000,
    "shares_outstanding": 2_716_000_000,
    "debt_to_equity": 0.12,
    "profit_after_tax": 181_040_000_000,
    "basic_eps": 64.16,
}
tri_result = Triangulator.run_all_checks(tri_data)
print(f"   Verdict: {tri_result['overall_verdict']}")
print(f"   Passed: {tri_result['passed']}/{tri_result['total_checks']}")
for r in tri_result["results"]:
    status = "✓" if r["passed"] else "✗"
    print(f"   {status} {r['identity']}: {r['details'][:80]}")

# Revenue scale check should pass
rev_check = next((r for r in tri_result["results"] if "Revenue Scale" in r["identity"]), None)
assert rev_check is not None, "Revenue scale check should be present"
assert rev_check["passed"], f"Revenue scale check should pass, got: {rev_check['details']}"

# EPS-shares check should pass
eps_check = next((r for r in tri_result["results"] if "EPS" in r["identity"]), None)
assert eps_check is not None, "EPS-shares consistency check should be present"
# 10% tolerance: PAT/EPS = 2822M vs 2716M is ~4% off, should pass
assert eps_check["passed"], f"EPS-shares check should pass, got: {eps_check['details']}"
print("   PASS")

# ---------------------------------------------------------------
# 9. Full agent smoke test
# ---------------------------------------------------------------
print("\n9. Full Agent Smoke Test (HCL Technologies):")

store.deals.clear()
store.documents.clear()
store.agent_runs.clear()
store.outputs.clear()

deal = Deal(
    id="hcl-tech-largecap",
    name="HCL Technologies Limited FY25",
    company_name="HCL Technologies Limited",
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

assert run.status == "completed"
assert header.get("is_private_company") is False, "HCL should be classified as public/listed"
assert 0.09 <= float(header.get("wacc", 0)) <= 0.15, f"WACC should be 9-15%, got {header.get('wacc')}"

# Revenue should be at HCL scale (>₹80,000 Cr = ₹800B)
ev = float(bridge.get("enterprise_value", 0))
assert ev > 1_000_000_000_000, f"EV should be > ₹1L Cr, got ₹{ev/1e7:,.0f} Cr"

# Cash should be material (HCL is net-cash)
cash = float(bridge.get("add_cash", 0))
assert cash > 100_000_000_000, f"Cash should be > ₹10,000 Cr, got ₹{cash/1e7:,.0f} Cr"

# Projection years should be 7+ for IT services
proj_years = header.get("projection_horizon_years", 0)
assert proj_years >= 7, f"Projection years should be 7+ for IT, got {proj_years}"

# Shares should be verified and per-share price available
assert header.get("per_share_value_available") is True, "Per-share value should be available"

# Implied share price should be in reasonable range
share_price = bridge.get("implied_price_per_share")
assert share_price is not None, "Share price should not be None"
assert 500 <= float(share_price) <= 5000, f"Share price should be ₹500-5000, got {share_price}"

print("   PASS")

print("\n" + "=" * 60)
print("ALL HCL TECHNOLOGIES REGRESSION TESTS PASSED")
print("=" * 60)
