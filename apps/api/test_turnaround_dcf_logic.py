"""Regression checks for turnaround-company DCF behavior."""
import os
import sys

os.environ["GEMINI_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""

sys.path.insert(0, "src")

from engine.dcf import DCFEngine
from agents.modeling import FinancialModelingAgent
from store import store, Deal


print("=" * 60)
print("TURNAROUND DCF REGRESSION TESTS")
print("=" * 60)

# 1. Loss-making companies should not be forced into an immediate positive EBITDA margin.
engine = DCFEngine(
    historical_revenues=[
        58_000_000_000,
        63_000_000_000,
        62_000_000_000,
        69_000_000_000,
    ],
    historical_ebitda_margins=[-0.11, -0.16, -0.19, -0.22],
    tax_rate=0.25,
    cap_ex_percent_rev=0.02,
    da_percent_rev=0.03,
    tax_loss_carryforward=4_000_000_000,
)
projections = engine.build_projections(projection_years=7, terminal_growth_rate=0.025)
margin_path = projections["projections"]["ebitda_margin_pct"]
taxes = projections["projections"]["taxes"]

print("\n1. Margin Ramp Test:")
print(f"   Margin Path (%): {margin_path}")
assert margin_path[0] < 0, "Year 1 margin should remain negative for a loss-making company"
assert margin_path[-1] > margin_path[0], "Margin path should improve over the forecast period"
assert taxes[0] == 0, "Cash taxes should be zero while the company is still loss-making"
print("   PASS")

# 2. Terminal value cross-check should use EBITDA, not FCF.
terminal_ebitda = projections["projections"]["ebitda"][-1]
tv_check = engine.terminal_value_crosscheck(
    projections["projections"]["ufcf"],
    terminal_ebitda,
    wacc=0.18,
    tgr=0.025,
    exit_multiple=15.0,
)

print("\n2. TV Cross-Check Test:")
print(f"   Exit Multiple TV: {tv_check['exit_multiple_tv']}")
expected_exit_tv = round(terminal_ebitda * 15.0, 2)
assert tv_check["exit_multiple_tv"] == expected_exit_tv, "Exit multiple cross-check must use terminal EBITDA"
print("   PASS")

# 3. Public-company runs without verified shares should suppress per-share valuation.
store.deals.clear()
store.documents.clear()
store.agent_runs.clear()
store.outputs.clear()

deal = Deal(
    id="paytm-like-public-smoke",
    name="Paytm-like Public Smoke",
    company_name="One 97 Communications Limited",
    industry="Fintech / Digital Payments",
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

print("\n3. Public Share Suppression Test:")
print(f"   Status: {run.status}")
print(f"   Valuation Basis: {valuation_result.get('header', {}).get('valuation_basis')}")
print(f"   Share Price: {valuation_result.get('header', {}).get('implied_share_price')}")
print(f"   Warnings: {valuation_result.get('warnings', [])}")
assert run.status == "completed"
assert valuation_result.get("header", {}).get("is_private_company") is False
assert valuation_result.get("header", {}).get("valuation_basis") == "equity_value"
assert valuation_result.get("header", {}).get("implied_share_price") is None
assert any("PER-SHARE VALUATION SUPPRESSED" in warning for warning in valuation_result.get("warnings", []))
print("   PASS")

print("\nAll turnaround DCF regression tests passed.")
