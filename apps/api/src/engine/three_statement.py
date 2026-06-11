from __future__ import annotations

from typing import Any, Dict, List


class ThreeStatementEngine:
    """Deterministic linked income statement, balance sheet, cash flow, and debt schedule."""

    def __init__(
        self,
        historical_revenues: List[float],
        historical_ebitda_margins: List[float],
        tax_rate: float = 0.25,
        cap_ex_percent_rev: float = 0.04,
        da_percent_rev: float = 0.05,
        base_fy: int = 2025,
        dso: float = 45.0,
        dpo: float = 30.0,
        dio: float = 30.0,
        opening_cash: float = 10.0,
        revolver_balance: float = 0.0,
        term_loan_balance: float = 50.0,
        revolver_interest_rate: float = 0.06,
        term_loan_interest_rate: float = 0.08,
        term_loan_amortization_pct: float = 0.01,
        min_cash_balance: float = 5.0,
        opening_retained_earnings: float = 20.0,
        opening_common_stock: float = 100.0,
    ):
        self.historical_revenues = historical_revenues
        self.historical_ebitda_margins = historical_ebitda_margins
        self.tax_rate = tax_rate
        self.cap_ex_percent_rev = cap_ex_percent_rev
        self.da_percent_rev = da_percent_rev
        self.base_fy = base_fy
        self.dso = dso
        self.dpo = dpo
        self.dio = dio
        self.opening_cash = opening_cash
        self.revolver_balance = revolver_balance
        self.term_loan_balance = term_loan_balance
        self.revolver_interest_rate = revolver_interest_rate
        self.term_loan_interest_rate = term_loan_interest_rate
        self.term_loan_amortization_pct = term_loan_amortization_pct
        self.min_cash_balance = min_cash_balance
        self.opening_retained_earnings = opening_retained_earnings
        self.opening_common_stock = opening_common_stock

    def calculate_cagr(self, values: List[float]) -> float:
        if len(values) < 2 or values[0] == 0:
            return 0.08
        cagr = (values[-1] / values[0]) ** (1 / (len(values) - 1)) - 1
        return max(-0.30, min(0.30, cagr))

    def _estimate_nwc(self, revenue: float, margin: float) -> tuple[float, float, float]:
        daily_revenue = revenue / 365
        receivables = daily_revenue * self.dso
        cogs_percent_rev = max(0.0, 1.0 - margin - self.da_percent_rev)
        daily_cogs = (revenue * cogs_percent_rev) / 365
        inventory = daily_cogs * self.dio
        payables = daily_cogs * self.dpo
        return receivables, inventory, payables

    @staticmethod
    def _round_series(data: dict[str, list[float]]) -> dict[str, list[float]]:
        return {key: [round(v, 2) for v in values] for key, values in data.items()}

    def build_projections(self, projection_years: int = 5) -> Dict[str, Any]:
        if not self.historical_revenues or not self.historical_ebitda_margins:
            raise ValueError("Historical revenue and EBITDA margin series are required")

        revenue_cagr = self.calculate_cagr(self.historical_revenues)
        avg_ebitda_margin = sum(self.historical_ebitda_margins) / len(self.historical_ebitda_margins)

        fy_labels: list[str] = []
        is_data = {k: [] for k in ("revenue", "cogs", "gross_profit", "sgga", "ebitda", "da", "ebit", "interest_expense", "ebt", "taxes", "net_income")}
        bs_data = {k: [] for k in ("cash", "receivables", "inventory", "ppne", "total_assets", "payables", "revolver", "term_loan", "total_liabilities", "common_stock", "retained_earnings", "total_equity", "total_liab_and_equity", "balance_check")}
        cf_data = {k: [] for k in ("net_income", "da", "change_in_nwc", "cfo", "capex", "cfi", "term_loan_amort", "revolver_draw_repay", "cff", "net_change_in_cash", "ending_cash", "ufcf")}
        debt_schedule = {k: [] for k in ("term_loan_opening", "term_loan_amortization", "term_loan_ending", "revolver_opening", "revolver_draw", "revolver_repay", "revolver_ending", "interest_expense")}

        last_revenue = float(self.historical_revenues[-1])
        last_ar, last_inv, last_ap = self._estimate_nwc(last_revenue, self.historical_ebitda_margins[-1])

        current_cash = float(self.opening_cash)
        current_term_loan = float(self.term_loan_balance)
        current_revolver = float(self.revolver_balance)
        current_retained_earnings = float(self.opening_retained_earnings)
        current_ppne = last_revenue * self.cap_ex_percent_rev * 3

        opening_assets = current_cash + last_ar + last_inv + current_ppne
        opening_liabilities = last_ap + current_revolver + current_term_loan
        current_common_stock = opening_assets - opening_liabilities - current_retained_earnings

        for year in range(1, projection_years + 1):
            fy_labels.append(f"FY{self.base_fy + year}E")
            revenue = last_revenue * (1 + revenue_cagr)
            cogs_pct = max(0.0, 1.0 - avg_ebitda_margin - self.da_percent_rev)
            cogs = revenue * cogs_pct
            gross_profit = revenue - cogs
            ebitda = revenue * avg_ebitda_margin
            sgga = gross_profit - ebitda
            da = revenue * self.da_percent_rev
            ebit = ebitda - da

            ar, inv, ap = self._estimate_nwc(revenue, avg_ebitda_margin)
            change_nwc = (ar - last_ar) + (inv - last_inv) - (ap - last_ap)
            capex = revenue * self.cap_ex_percent_rev

            interest_expense = (
                current_term_loan * self.term_loan_interest_rate
                + current_revolver * self.revolver_interest_rate
            )
            ebt = ebit - interest_expense
            taxes = max(0.0, ebt * self.tax_rate)
            net_income = ebt - taxes
            cfo = net_income + da - change_nwc
            cfi = -capex
            ufcf = ebit * (1 - self.tax_rate) + da - change_nwc - capex

            term_loan_amort = min(current_term_loan, self.term_loan_balance * self.term_loan_amortization_pct)
            cash_after_amort = current_cash + cfo + cfi - term_loan_amort
            revolver_draw = max(0.0, self.min_cash_balance - cash_after_amort)
            cash_after_draw = cash_after_amort + revolver_draw
            revolver_repay = min(current_revolver, max(0.0, cash_after_draw - self.min_cash_balance))
            ending_cash = cash_after_draw - revolver_repay
            cff = -term_loan_amort + revolver_draw - revolver_repay
            net_change_cash = cfo + cfi + cff

            next_term_loan = current_term_loan - term_loan_amort
            next_revolver = current_revolver + revolver_draw - revolver_repay
            next_retained_earnings = current_retained_earnings + net_income
            next_ppne = current_ppne + capex - da

            total_assets = ending_cash + ar + inv + next_ppne
            total_liabilities = ap + next_revolver + next_term_loan
            total_equity = current_common_stock + next_retained_earnings
            total_liab_and_equity = total_liabilities + total_equity
            balance_check = total_assets - total_liab_and_equity

            for key, value in {
                "revenue": revenue,
                "cogs": cogs,
                "gross_profit": gross_profit,
                "sgga": sgga,
                "ebitda": ebitda,
                "da": da,
                "ebit": ebit,
                "interest_expense": interest_expense,
                "ebt": ebt,
                "taxes": taxes,
                "net_income": net_income,
            }.items():
                is_data[key].append(value)

            for key, value in {
                "cash": ending_cash,
                "receivables": ar,
                "inventory": inv,
                "ppne": next_ppne,
                "total_assets": total_assets,
                "payables": ap,
                "revolver": next_revolver,
                "term_loan": next_term_loan,
                "total_liabilities": total_liabilities,
                "common_stock": current_common_stock,
                "retained_earnings": next_retained_earnings,
                "total_equity": total_equity,
                "total_liab_and_equity": total_liab_and_equity,
                "balance_check": balance_check,
            }.items():
                bs_data[key].append(value)

            for key, value in {
                "net_income": net_income,
                "da": da,
                "change_in_nwc": -change_nwc,
                "cfo": cfo,
                "capex": -capex,
                "cfi": cfi,
                "term_loan_amort": -term_loan_amort,
                "revolver_draw_repay": revolver_draw - revolver_repay,
                "cff": cff,
                "net_change_in_cash": net_change_cash,
                "ending_cash": ending_cash,
                "ufcf": ufcf,
            }.items():
                cf_data[key].append(value)

            for key, value in {
                "term_loan_opening": current_term_loan,
                "term_loan_amortization": -term_loan_amort,
                "term_loan_ending": next_term_loan,
                "revolver_opening": current_revolver,
                "revolver_draw": revolver_draw,
                "revolver_repay": -revolver_repay,
                "revolver_ending": next_revolver,
                "interest_expense": interest_expense,
            }.items():
                debt_schedule[key].append(value)

            last_revenue = revenue
            last_ar, last_inv, last_ap = ar, inv, ap
            current_cash = ending_cash
            current_term_loan = next_term_loan
            current_revolver = next_revolver
            current_retained_earnings = next_retained_earnings
            current_ppne = next_ppne

        rounded_bs = self._round_series(bs_data)
        return {
            "fy_labels": fy_labels,
            "income_statement": self._round_series(is_data),
            "balance_sheet": rounded_bs,
            "cash_flow_statement": self._round_series(cf_data),
            "debt_schedule": self._round_series(debt_schedule),
            "balance_checks": [
                {
                    "year": fy,
                    "balance_check": rounded_bs["balance_check"][idx],
                    "balanced": abs(rounded_bs["balance_check"][idx]) < 1.0,
                }
                for idx, fy in enumerate(fy_labels)
            ],
            "assumptions": {
                "revenue_cagr": round(revenue_cagr, 4),
                "avg_ebitda_margin": round(avg_ebitda_margin, 4),
                "tax_rate": self.tax_rate,
                "cap_ex_percent_rev": self.cap_ex_percent_rev,
                "da_percent_rev": self.da_percent_rev,
                "dso": self.dso,
                "dpo": self.dpo,
                "dio": self.dio,
                "revolver_rate": self.revolver_interest_rate,
                "term_loan_rate": self.term_loan_interest_rate,
                "min_cash_balance": self.min_cash_balance,
            },
        }
