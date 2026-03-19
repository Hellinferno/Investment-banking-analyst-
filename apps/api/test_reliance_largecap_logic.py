"""Regression checks for Reliance Industries Limited (mega-cap diversified) valuation behavior."""
# pyright: reportMissingImports=false
import json
import os
import sys

os.environ["GEMINI_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""

sys.path.insert(0, "src")

from engine.dcf import DCFEngine
from engine.llm import _get_deterministic_fallback_response


def test_reliance_largecap_regression_behavior():
    prompt_variants = [
        "Target company is Reliance Industries Limited",
        "Please build a DCF for RIL",
    ]
    for prompt in prompt_variants:
        payload = json.loads(_get_deterministic_fallback_response(prompt))
        assert payload.get("fallback_profile") == "reliance_industries_megacap_diversified", (
            f"Expected Reliance fallback profile for prompt '{prompt}', got {payload.get('fallback_profile')}"
        )

    ril = json.loads(_get_deterministic_fallback_response("Reliance Industries Limited"))

    fy25_revenue = ril["historical_revenues"][-1]
    net_debt = ril["net_debt"]
    shares = ril["shares_outstanding"]

    assert fy25_revenue >= 10_000_000_000_000, "Revenue must be at mega-cap scale (>= ₹10L Cr)"
    assert 1_000_000_000_000 <= net_debt <= 1_300_000_000_000, "Net debt should be around ₹1.17L Cr"
    assert 6_000_000_000 <= shares <= 7_500_000_000, "Shares should be around 676.6 Cr"

    engine = DCFEngine(
        historical_revenues=ril["historical_revenues"],
        historical_ebitda_margins=ril["historical_ebitda_margins"],
        tax_rate=0.25,
        cap_ex_percent_rev=ril["cap_ex_percent_rev"],
        da_percent_rev=ril["da_percent_rev"],
        revenue_cagr_override=ril["revenue_cagr_override"],
        base_fy=ril["base_fy"],
    )

    wacc_breakdown = engine.calculate_wacc_breakdown(
        risk_free_rate=ril["risk_free_rate"],
        equity_risk_premium=ril["equity_risk_premium"],
        beta=ril["beta"],
        cost_of_debt=ril["cost_of_debt"],
        debt_to_equity=ril["debt_to_equity"],
        size_premium=ril.get("size_premium", 0.0),
        specific_risk_premium=ril.get("specific_risk_premium", 0.0),
    )

    wacc = wacc_breakdown["wacc"]
    weight_debt = wacc_breakdown["weight_of_debt"]
    cost_of_equity = wacc_breakdown["cost_of_equity"]

    assert 0.125 <= cost_of_equity <= 0.132, "Cost of equity should be around 13%"
    assert 0.14 <= weight_debt <= 0.16, "Debt weight should be ~15%"
    assert 0.115 <= wacc <= 0.125, "WACC should be in the 11.5%-12.5% band"
