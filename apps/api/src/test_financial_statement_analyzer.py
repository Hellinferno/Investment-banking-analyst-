import sys
import unittest

sys.path.insert(0, ".")

from engine.financial_statement_analyzer import FinancialStatementAnalyzer


class TestFinancialStatementAnalyzer(unittest.TestCase):
    def setUp(self):
        self.analyzer = FinancialStatementAnalyzer()

    def test_ratio_calculation_structure(self):
        payload = {
            "revenue": 1000.0,
            "ebitda": 200.0,
            "ebit": 150.0,
            "net_income": 120.0,
            "current_assets": 500.0,
            "current_liabilities": 250.0,
            "inventory": 50.0,
            "cash_and_equivalents": 100.0,
            "total_debt": 200.0,
            "shareholders_equity": 400.0,
            "total_assets": 900.0,
            "interest_expense": 20.0,
            "accounts_receivable": 125.0,
        }
        ratios = self.analyzer.calculate_ratios(payload)
        self.assertIn("profitability", ratios)
        self.assertIn("liquidity", ratios)
        self.assertIn("leverage", ratios)
        self.assertIn("efficiency", ratios)
        self.assertGreater(ratios["liquidity"]["current_ratio"], 0)

    def test_overall_health_present(self):
        payload = {
            "revenue": 2000.0,
            "ebitda": 500.0,
            "ebit": 420.0,
            "net_income": 350.0,
            "current_assets": 1500.0,
            "current_liabilities": 600.0,
            "inventory": 80.0,
            "cash_and_equivalents": 700.0,
            "total_debt": 200.0,
            "shareholders_equity": 1800.0,
            "total_assets": 2600.0,
            "interest_expense": 12.0,
            "accounts_receivable": 300.0,
        }
        output = self.analyzer.analyze(payload, "technology")
        self.assertIn("ratios", output)
        self.assertIn("analysis", output)
        self.assertIn("overall_health", output["analysis"])
        self.assertIn(output["analysis"]["overall_health"]["status"], {"Excellent", "Good", "Fair", "Poor"})

    def test_trend_analysis_signal_present(self):
        payload = {
            "revenue": 2000.0,
            "ebitda": 500.0,
            "ebit": 420.0,
            "net_income": 350.0,
            "current_assets": 1500.0,
            "current_liabilities": 600.0,
            "inventory": 80.0,
            "cash_and_equivalents": 700.0,
            "total_debt": 200.0,
            "shareholders_equity": 1800.0,
            "total_assets": 2600.0,
            "interest_expense": 12.0,
            "accounts_receivable": 300.0,
            "historical_periods": [
                {
                    "revenue": 1200.0,
                    "ebitda": 180.0,
                    "ebit": 130.0,
                    "net_income": 100.0,
                    "current_assets": 700.0,
                    "current_liabilities": 500.0,
                    "inventory": 65.0,
                    "cash_and_equivalents": 220.0,
                    "total_debt": 360.0,
                    "shareholders_equity": 950.0,
                    "total_assets": 1800.0,
                    "interest_expense": 40.0,
                    "accounts_receivable": 250.0,
                },
                {
                    "revenue": 1500.0,
                    "ebitda": 300.0,
                    "ebit": 240.0,
                    "net_income": 180.0,
                    "current_assets": 1000.0,
                    "current_liabilities": 560.0,
                    "inventory": 70.0,
                    "cash_and_equivalents": 320.0,
                    "total_debt": 300.0,
                    "shareholders_equity": 1300.0,
                    "total_assets": 2100.0,
                    "interest_expense": 30.0,
                    "accounts_receivable": 280.0,
                },
                {
                    "revenue": 2000.0,
                    "ebitda": 500.0,
                    "ebit": 420.0,
                    "net_income": 350.0,
                    "current_assets": 1500.0,
                    "current_liabilities": 600.0,
                    "inventory": 80.0,
                    "cash_and_equivalents": 700.0,
                    "total_debt": 200.0,
                    "shareholders_equity": 1800.0,
                    "total_assets": 2600.0,
                    "interest_expense": 12.0,
                    "accounts_receivable": 300.0,
                },
            ],
        }
        output = self.analyzer.analyze(payload, "technology")
        self.assertIn("trend_analysis", output)
        self.assertIn(output["trend_analysis"]["signal"], {"Improving", "Stable", "Deteriorating", "Insufficient Data"})
        self.assertIn("metrics", output["trend_analysis"])


if __name__ == "__main__":
    unittest.main()
