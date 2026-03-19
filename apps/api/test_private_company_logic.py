"""Regression checks for private-company valuation handling."""
import os
import sys

os.environ["GEMINI_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""

sys.path.insert(0, "src")

from engine.dcf import DCFEngine
from agents.modeling import FinancialModelingAgent
from store import store, Deal


print("=" * 60)
print("PRIVATE COMPANY VALUATION TESTS")
print("=" * 60)

engine = DCFEngine(
    historical_revenues=[100_000_000_000, 110_000_000_000],
    historical_ebitda_margins=[0.08, 0.09],
    tax_rate=0.25,
)
wacc_breakdown = engine.calculate_private_company_wacc_breakdown(
    risk_free_rate=0.07,
    equity_risk_premium=0.065,
    size_premium=0.03,
    specific_risk_premium=0.04,
    cost_of_debt=0.09,
    debt_to_equity=0.0,
)
print("\n1. Private WACC Build-Up:")
print(f"   Cost of Equity: {wacc_breakdown['cost_of_equity']*100:.2f}%")
print(f"   WACC: {wacc_breakdown['wacc']*100:.2f}%")
assert abs(wacc_breakdown["cost_of_equity"] - 0.205) < 0.0001
assert abs(wacc_breakdown["wacc"] - 0.205) < 0.0001
print("   PASS")

company_context = FinancialModelingAgent._classify_company_context(
    "Flipkart Internet Private Limited",
    "Corporate Identity Number: U74999DL2012PTC066107",
    {"cin": "U74999DL2012PTC066107"},
)
print("\n2. Company Classification:")
print(f"   Entity Type: {company_context['entity_type']}")
print(f"   Listing Status: {company_context['listing_status']}")
assert company_context["is_private_company"] is True
assert company_context["entity_type"] == "private_limited"
print("   PASS")

store.deals.clear()
store.documents.clear()
store.agent_runs.clear()
store.outputs.clear()

deal = Deal(
    id="flipkart-smoke",
    name="Flipkart DCF Smoke",
    company_name="Flipkart Internet Private Limited",
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

print("\n3. Agent Output:")
print(f"   Status: {run.status}")
print(f"   Valuation Basis: {valuation_result.get('header', {}).get('valuation_basis')}")
print(f"   Share Price: {valuation_result.get('header', {}).get('implied_share_price')}")
print(f"   Liquidity Discount: {valuation_result.get('header', {}).get('liquidity_discount')}")
assert run.status == "completed"
assert valuation_result.get("header", {}).get("valuation_basis") == "equity_value"
assert valuation_result.get("header", {}).get("implied_share_price") is None
assert valuation_result.get("company_classification", {}).get("is_private_company") is True
print("   PASS")

print("\nAll private-company tests passed.")
