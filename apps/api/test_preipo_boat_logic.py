"""Regression checks for boAt/Imagine pre-IPO valuation behavior."""
# pyright: reportMissingImports=false
import os
import sys
os.environ["GEMINI_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""

sys.path.insert(0, "src")

from agents.modeling import FinancialModelingAgent
from store import store, Deal


print("=" * 60)
print("PRE-IPO boAt REGRESSION TESTS")
print("=" * 60)

store.deals.clear()
store.documents.clear()
store.agent_runs.clear()
store.outputs.clear()

# Name/context should trigger pre-IPO deterministic fallback profile when no API keys are present.
deal = Deal(
    id="boat-preipo-smoke",
    name="Imagine Marketing Limited P-DRHP Scenario",
    company_name="Imagine Marketing Limited",
    industry="Consumer Electronics / D2C",
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

print("\n1. Run and Classification:")
print(f"   Status: {run.status}")
print(f"   Company Type: {header.get('company_type')}")
print(f"   Is Private: {header.get('is_private_company')}")
assert run.status == "completed"
assert header.get("is_private_company") is True
assert header.get("valuation_basis") == "equity_value"
print("   PASS")

print("\n2. Discount Rate and Growth Anchors:")
print(f"   WACC: {header.get('wacc')}")
print(f"   Projection Horizon: {header.get('projection_horizon_years')}")
assert float(header.get("wacc") or 0) >= 0.18
assert header.get("projection_horizon_years") >= 5
print("   PASS")

print("\n3. Capital Structure Integrity:")
print(f"   CCPS Liability: {bridge.get('ccps_liability')}")
print(f"   Net Debt: {bridge.get('net_debt')}")
assert float(bridge.get("ccps_liability") or 0) > 0
assert float(bridge.get("net_debt") or 0) > 0
print("   PASS")

print("\nAll boAt pre-IPO tests passed.")
