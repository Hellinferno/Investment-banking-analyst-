"""
Unit tests for the deterministic merger accretion/dilution math.

These target MergerModelAgent._compute_accretion_dilution — a *pure* static
method (no LLM, no DB, no file I/O). That is exactly what makes it ideal to
unit test: same input always yields the same output, so we can assert exact
numbers and lock the financial logic against regressions.
"""
import sys

sys.path.insert(0, ".")

from agents.merger_model import MergerModelAgent


def _base_inputs():
    """A clean, fully-specified deal: target + acquirer + assumptions."""
    return {
        "target": {"net_income": 10_000_000_000, "dcf_equity_value": 200_000_000_000},
        "acquirer": {
            "net_income": 50_000_000_000,
            "shares_outstanding": 1_000_000_000,
            "share_price": 500.0,
        },
        "assumptions": {
            "offer_premium_pct": 0.25,
            "cash_pct": 0.5,
            "stock_pct": 0.5,
            "cost_of_debt_pretax": 0.09,
            "tax_rate": 0.25,
            "annual_pretax_synergies": 2_000_000_000,
            "synergies_phase_in": [0.5, 0.75, 1.0],
        },
    }


def test_offer_value_applies_premium():
    r = MergerModelAgent._compute_accretion_dilution(_base_inputs())
    # offer = equity value × (1 + premium) = 200bn × 1.25
    assert r["status"] == "computed"
    assert r["offer_value"] == 250_000_000_000


def test_cash_stock_split_matches_mix():
    r = MergerModelAgent._compute_accretion_dilution(_base_inputs())
    assert r["cash_consideration"] == 125_000_000_000   # 50% of 250bn
    assert r["stock_consideration"] == 125_000_000_000


def test_new_shares_issued_from_stock_leg():
    r = MergerModelAgent._compute_accretion_dilution(_base_inputs())
    # stock consideration / acquirer share price = 125bn / 500
    assert r["new_shares_issued"] == 250_000_000


def test_year1_is_dilutive_for_this_deal():
    r = MergerModelAgent._compute_accretion_dilution(_base_inputs())
    assert "DILUTIVE" in r["verdict"]
    assert r["accretion_dilution_pct"][0] < 0


def test_accretion_improves_as_synergies_phase_in():
    r = MergerModelAgent._compute_accretion_dilution(_base_inputs())
    pct = r["accretion_dilution_pct"]
    # As synergies ramp 0.5 → 0.75 → 1.0, dilution should shrink each year.
    assert pct[0] < pct[1] < pct[2]


def test_all_cash_deal_issues_no_shares():
    inputs = _base_inputs()
    inputs["assumptions"]["cash_pct"] = 1.0
    inputs["assumptions"]["stock_pct"] = 0.0
    r = MergerModelAgent._compute_accretion_dilution(inputs)
    assert r["new_shares_issued"] == 0
    assert r["proforma_shares_outstanding"] == 1_000_000_000  # unchanged


def test_missing_acquirer_data_is_flagged_not_crashed():
    r = MergerModelAgent._compute_accretion_dilution(
        {"target": {"net_income": 1_000}, "acquirer": {}, "assumptions": {}}
    )
    assert r["status"] == "insufficient_acquirer_data"
    assert "acquirer_net_income" in r["missing_inputs"]


def test_zero_division_guard_on_missing_shares():
    # Acquirer has income but no share count — must not raise ZeroDivisionError.
    inputs = _base_inputs()
    inputs["acquirer"]["shares_outstanding"] = None
    r = MergerModelAgent._compute_accretion_dilution(inputs)
    assert r["status"] == "insufficient_acquirer_data"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
