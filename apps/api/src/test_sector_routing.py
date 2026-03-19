import pytest

from agents.modeling import FinancialModelingAgent
from engine.dcf import DCFEngine


def test_it_services_sector_profile_routes_asset_light_assumptions():
    profile = FinancialModelingAgent._build_sector_routing_profile(
        "Information Technology and Consultancy Services",
        [0.22, 0.24, 0.26],
    )

    assert profile["sector"] == "it_services"
    assert profile["margin_baseline_override"] == pytest.approx(0.24, rel=1e-6)
    assert profile["da_cap_percent_rev"] == pytest.approx(0.02, rel=1e-6)
    assert profile["capex_cap_percent_rev"] == pytest.approx(0.03, rel=1e-6)
    assert profile["nwc_method"] == "percent_revenue_balance"
    assert profile["nwc_percent_rev"] == pytest.approx(-0.01, rel=1e-6)
    assert profile["min_projection_years"] == 7


def test_percent_revenue_balance_nwc_creates_negative_drag_for_it_services():
    engine = DCFEngine(
        historical_revenues=[1_000.0, 1_100.0, 1_200.0],
        historical_ebitda_margins=[0.22, 0.23, 0.24],
        tax_rate=0.25,
        cap_ex_percent_rev=0.03,
        da_percent_rev=0.02,
        nwc_percent_rev=-0.01,
        nwc_method="percent_revenue_balance",
        revenue_cagr_override=0.10,
    )

    projections = engine.build_projections(projection_years=1, terminal_growth_rate=0.03)

    assert projections["assumptions"]["nwc_method"] == "percent_revenue_balance"
    assert projections["projections"]["receivables"] == [0.0]
    assert projections["projections"]["payables"] == [0.0]
    assert projections["projections"]["inventory"] == [0.0]
    assert projections["projections"]["nwc_change"][0] == pytest.approx(-1.2, rel=1e-6)


def test_mid_year_discounting_is_used_for_dcf_valuation():
    engine = DCFEngine(
        historical_revenues=[1_000.0, 1_100.0],
        historical_ebitda_margins=[0.20, 0.21],
    )

    valuation = engine.calculate_valuation(
        ufcf_projections=[100.0, 110.0],
        wacc=0.10,
        terminal_growth_rate=0.03,
        net_debt=50.0,
        shares_outstanding=10.0,
    )

    assert valuation["discount_convention"] == "mid_year"
    assert valuation["discount_periods"] == [0.5, 1.5]
    assert valuation["discount_factors"][0] == pytest.approx(1 / (1.10 ** 0.5), rel=1e-3)
    assert valuation["discount_factors"][1] == pytest.approx(1 / (1.10 ** 1.5), rel=1e-3)
