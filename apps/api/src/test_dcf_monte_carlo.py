import sys
import unittest

sys.path.insert(0, ".")

from engine.dcf import DCFEngine


class TestDCFMonteCarlo(unittest.TestCase):
    def setUp(self):
        self.engine = DCFEngine(
            historical_revenues=[1000.0, 1100.0, 1200.0],
            historical_ebitda_margins=[0.20, 0.21, 0.22],
            tax_rate=0.25,
            cap_ex_percent_rev=0.04,
            da_percent_rev=0.03,
            nwc_percent_rev=0.10,
            revenue_cagr_override=0.08,
        )

    def test_monte_carlo_summary_fields(self):
        projections = self.engine.build_projections(projection_years=5, terminal_growth_rate=0.03)
        ufcf = projections["projections"]["ufcf"]
        out = self.engine.run_monte_carlo(
            ufcf_base=ufcf,
            wacc=0.11,
            tgr=0.03,
            net_debt=100.0,
            shares=50.0,
            iterations=400,
            seed=7,
        )
        self.assertIn("summary", out)
        self.assertIn("iterations", out)
        self.assertGreaterEqual(out["iterations"], 100)
        self.assertIn("mean", out["summary"])
        self.assertIn("p5", out["summary"])
        self.assertIn("p95", out["summary"])
        self.assertIn("var_value", out["summary"])
        self.assertIn("cvar_value", out["summary"])

    def test_monte_carlo_with_correlated_shocks(self):
        projections = self.engine.build_projections(projection_years=5, terminal_growth_rate=0.03)
        ufcf = projections["projections"]["ufcf"]
        corr = {
            "growth": {"margin": 0.6, "wacc": -0.4, "tgr": 0.3},
            "margin": {"wacc": -0.2, "tgr": 0.2},
            "wacc": {"tgr": 0.5},
        }
        out = self.engine.run_monte_carlo(
            ufcf_base=ufcf,
            wacc=0.11,
            tgr=0.03,
            net_debt=100.0,
            shares=50.0,
            iterations=500,
            seed=11,
            correlation_matrix=corr,
            var_confidence_level=0.95,
        )
        summary = out["summary"]
        self.assertIn("var_confidence_level", summary)
        self.assertAlmostEqual(summary["var_confidence_level"], 0.95, places=4)
        self.assertLessEqual(summary["cvar_value"], summary["var_value"])
        self.assertIn("correlation_matrix", out["assumptions"])

    def test_probability_weighted_scenario_value(self):
        scenarios = {
            "bear": {"valuation": {"share_price": 80.0, "equity_value": 800.0}},
            "base": {"valuation": {"share_price": 100.0, "equity_value": 1000.0}},
            "bull": {"valuation": {"share_price": 130.0, "equity_value": 1300.0}},
        }
        res = self.engine.probability_weighted_scenario_value(
            scenarios,
            {"bear": 0.2, "base": 0.5, "bull": 0.3},
        )
        self.assertEqual(res["metric"], "share_price")
        self.assertAlmostEqual(res["expected_value"], 105.0, places=4)


if __name__ == "__main__":
    unittest.main()
