from typing import Dict, List, Any, Optional, Tuple
import random
import statistics
import math

class DCFEngine:
    """
    Deterministic Financial Computation Engine for building a Discounted Cash Flow model.
    This prevents LLMs from hallucinating math operations.
    
    Industry-Grade Features:
    - Scenario analysis (Bear/Base/Bull)
    - Working capital days (DSO, DPO, DIO)
    - Margin progression with operating leverage
    - CapEx sensitivity analysis
    - Realistic capital structure modeling
    """

    def __init__(self, historical_revenues: List[float], historical_ebitda_margins: List[float],
                 tax_rate: float = 0.25, cap_ex_percent_rev: float = 0.04,
                 nwc_percent_rev: float = 0.10, da_percent_rev: float = 0.05,
                 revenue_cagr_override: float = None,
                 margin_baseline_override: Optional[float] = None,
                 base_fy: int = 2025,
                 tax_loss_carryforward: float = 0.0,
                 nwc_method: str = "days",
                 # Working capital assumptions
                 dso: float = 45.0,  # Days Sales Outstanding
                 dpo: float = 30.0,  # Days Payable Outstanding
                 dio: float = 30.0,  # Days Inventory Outstanding
                 # Capital structure
                 total_debt: float = 0.0,
                 cash_and_equivalents: float = 0.0):
        # Base Data
        self.historical_revenues = historical_revenues
        self.historical_ebitda_margins = historical_ebitda_margins

        # Assumptions
        self.tax_rate = tax_rate
        self.cap_ex_percent_rev = cap_ex_percent_rev
        self.nwc_percent_rev = nwc_percent_rev
        self.da_percent_rev = da_percent_rev
        self.revenue_cagr_override = revenue_cagr_override
        self.margin_baseline_override = margin_baseline_override
        self.base_fy = base_fy
        self.tax_loss_carryforward = max(0.0, float(tax_loss_carryforward or 0.0))
        self.nwc_method = (nwc_method or "days").strip().lower()
        
        # Working capital days
        self.dso = dso
        self.dpo = dpo
        self.dio = dio
        
        # Capital structure
        self.total_debt = total_debt
        self.cash_and_equivalents = cash_and_equivalents
        
    def calculate_cagr(self, values: List[float]) -> float:
        """Calculate CAGR from historical values. Allows negative growth for declining companies."""
        if len(values) < 2 or values[0] == 0:
            return 0.08  # Default 8% for missing data
        cagr = (values[-1] / values[0]) ** (1 / (len(values) - 1)) - 1
        # Clamp to ±30% to prevent extreme extrapolation, but allow negative growth
        return max(-0.30, min(0.30, cagr))

    def calculate_wacc_breakdown(self, risk_free_rate: float = 0.07, equity_risk_premium: float = 0.06,
                                 beta: float = 1.1, cost_of_debt: float = 0.09,
                                 debt_to_equity: float = 0.0, size_premium: float = 0.0,
                                 specific_risk_premium: float = 0.0) -> Dict[str, Any]:
        """Calculates WACC components explicitly."""
        cost_of_equity = risk_free_rate + (beta * equity_risk_premium) + size_premium + specific_risk_premium
        after_tax_cost_of_debt = cost_of_debt * (1 - self.tax_rate)

        weight_of_debt = debt_to_equity / (1 + debt_to_equity)
        weight_of_equity = 1 - weight_of_debt

        wacc = (weight_of_equity * cost_of_equity) + (weight_of_debt * after_tax_cost_of_debt)

        return {
            "wacc": round(wacc, 4),
            "method": "capm",
            "risk_free_rate": risk_free_rate,
            "equity_risk_premium": equity_risk_premium,
            "beta": beta,
            "size_premium": round(size_premium, 4),
            "specific_risk_premium": round(specific_risk_premium, 4),
            "cost_of_equity": round(cost_of_equity, 4),
            "cost_of_debt": cost_of_debt,
            "after_tax_cost_of_debt": round(after_tax_cost_of_debt, 4),
            "debt_to_equity": debt_to_equity,
            "weight_of_equity": round(weight_of_equity, 4),
            "weight_of_debt": round(weight_of_debt, 4)
        }

    def calculate_private_company_wacc_breakdown(
        self,
        risk_free_rate: float = 0.07,
        equity_risk_premium: float = 0.065,
        size_premium: float = 0.03,
        specific_risk_premium: float = 0.04,
        cost_of_debt: float = 0.09,
        debt_to_equity: float = 0.0,
    ) -> Dict[str, Any]:
        """Build-up method for private-company cost of equity."""
        cost_of_equity = risk_free_rate + equity_risk_premium + size_premium + specific_risk_premium
        after_tax_cost_of_debt = cost_of_debt * (1 - self.tax_rate)

        weight_of_debt = debt_to_equity / (1 + debt_to_equity)
        weight_of_equity = 1 - weight_of_debt
        wacc = (weight_of_equity * cost_of_equity) + (weight_of_debt * after_tax_cost_of_debt)

        return {
            "wacc": round(wacc, 4),
            "method": "build_up",
            "risk_free_rate": risk_free_rate,
            "equity_risk_premium": equity_risk_premium,
            "size_premium": size_premium,
            "specific_risk_premium": specific_risk_premium,
            "cost_of_equity": round(cost_of_equity, 4),
            "cost_of_debt": cost_of_debt,
            "after_tax_cost_of_debt": round(after_tax_cost_of_debt, 4),
            "debt_to_equity": debt_to_equity,
            "weight_of_equity": round(weight_of_equity, 4),
            "weight_of_debt": round(weight_of_debt, 4),
        }

    def _build_margin_path(self, projection_years: int, scenario_adjustment: float) -> Tuple[List[float], float, float]:
        """
        Build a year-by-year EBITDA margin path.
        Loss-making companies ramp gradually toward profitability instead of being
        floored to an arbitrary positive margin in Year 1.
        """
        latest_margin = self.historical_ebitda_margins[-1]
        avg_margin = (
            float(self.margin_baseline_override)
            if self.margin_baseline_override is not None
            else sum(self.historical_ebitda_margins) / len(self.historical_ebitda_margins)
        )
        positive_history = [margin for margin in self.historical_ebitda_margins if margin > 0]

        if latest_margin < 0 or avg_margin < 0:
            positive_anchor = (
                sum(positive_history) / len(positive_history)
                if positive_history
                else 0.10
            )
            target_margin = min(0.18, max(0.08, positive_anchor))
            target_margin = max(-0.25, min(0.30, target_margin + scenario_adjustment))
            start_margin = max(-0.50, min(0.30, latest_margin + (scenario_adjustment * 0.5)))
        else:
            start_margin = max(-0.10, min(0.30, latest_margin + (scenario_adjustment * 0.5)))
            target_margin = max(-0.10, min(0.30, avg_margin + scenario_adjustment))

        path = []
        for idx in range(projection_years):
            progress = (idx + 1) / projection_years
            margin = start_margin + ((target_margin - start_margin) * progress)
            path.append(round(max(-0.50, min(0.30, margin)), 6))

        return path, latest_margin, target_margin

    def _calculate_nwc_components(
        self,
        current_rev: float,
        previous_rev: float,
        current_margin: float,
        last_nwc_balance: float,
    ) -> Tuple[float, float, float, float, float]:
        """
        Return receivables, payables, inventory, current NWC balance, and change in NWC.

        `days` mode uses DSO/DPO/DIO.
        `percent_revenue_balance` mode derives change in NWC from revenue growth/decline:
            change_in_nwc = (current_rev - previous_rev) * nwc_percent_rev
        This lets sector routing model negative/near-zero working-capital drag for asset-light firms.
        """
        if self.nwc_method == "percent_revenue_balance":
            nwc_balance = current_rev * self.nwc_percent_rev
            change_in_nwc = nwc_balance - last_nwc_balance
            return 0.0, 0.0, 0.0, nwc_balance, change_in_nwc

        daily_revenue = current_rev / 365
        receivables = daily_revenue * self.dso

        cogs_percent_rev = max(0.0, 1.0 - current_margin - self.da_percent_rev)
        daily_cogs = (current_rev * cogs_percent_rev) / 365
        payables = daily_cogs * self.dpo
        inventory = daily_cogs * self.dio

        nwc_balance = receivables + inventory - payables
        change_in_nwc = nwc_balance - last_nwc_balance
        return receivables, payables, inventory, nwc_balance, change_in_nwc

    def _estimate_opening_nwc_balance(self, revenue: float, margin: float) -> float:
        """Estimate the opening NWC balance using the active sector routing method."""
        if self.nwc_method == "percent_revenue_balance":
            return revenue * self.nwc_percent_rev

        daily_revenue = revenue / 365
        receivables = daily_revenue * self.dso

        cogs_percent_rev = max(0.0, 1.0 - margin - self.da_percent_rev)
        daily_cogs = (revenue * cogs_percent_rev) / 365
        payables = daily_cogs * self.dpo
        inventory = daily_cogs * self.dio
        return receivables + inventory - payables

    def build_projections(self, projection_years: int = 7, terminal_growth_rate: float = 0.025,
                          scenario: str = 'base') -> Dict[str, Any]:
        """
        Runs the deterministic projection model with scenario support.
        
        Scenarios:
        - base: Standard CAGR fade to terminal growth
        - bull: +30% growth, +2% margin expansion
        - bear: -30% growth, -2% margin contraction
        """
        # 1. Base Assumptions
        if self.revenue_cagr_override is not None:
            revenue_cagr = max(-0.30, min(0.30, float(self.revenue_cagr_override)))
        else:
            revenue_cagr = self.calculate_cagr(self.historical_revenues)
        avg_ebitda_margin = (
            float(self.margin_baseline_override)
            if self.margin_baseline_override is not None
            else sum(self.historical_ebitda_margins) / len(self.historical_ebitda_margins)
        )
        
        # Scenario adjustments
        scenario_adjustments = {
            'bear': {'growth_multiplier': 0.7, 'margin_adjustment': -0.02, 'label': 'Bear Case'},
            'base': {'growth_multiplier': 1.0, 'margin_adjustment': 0.0, 'label': 'Base Case'},
            'bull': {'growth_multiplier': 1.3, 'margin_adjustment': 0.02, 'label': 'Bull Case'},
        }
        adj = scenario_adjustments.get(scenario, scenario_adjustments['base'])

        # Apply scenario adjustments
        adjusted_cagr = revenue_cagr * adj['growth_multiplier']
        margin_path, latest_margin, terminal_margin = self._build_margin_path(
            projection_years,
            adj['margin_adjustment'],
        )
        adjusted_margin = sum(margin_path) / len(margin_path)

        # 2. Year arrays
        fy_labels = []
        projected_revenues = []
        projected_ebitda = []
        projected_da = []
        projected_ebit = []
        projected_taxes = []
        projected_ebiat = []
        projected_capex = []
        projected_nwc_change = []
        projected_ufcf = []
        revenue_growth_pct = []
        ebitda_margin_pct = []
        
        # Working capital components
        projected_receivables = []
        projected_payables = []
        projected_inventory = []
        projected_tax_loss_carryforward = []

        last_revenue = self.historical_revenues[-1]
        opening_margin = self.historical_ebitda_margins[-1] if self.historical_ebitda_margins else avg_ebitda_margin
        last_nwc_balance = self._estimate_opening_nwc_balance(last_revenue, opening_margin)
        nol_balance = self.tax_loss_carryforward

        for year in range(1, projection_years + 1):
            fy_labels.append(f"FY{self.base_fy + year}E")

            # Revenue with scenario-adjusted growth fade
            if projection_years > 1:
                fade_step = (adjusted_cagr - terminal_growth_rate) / projection_years
                current_growth = adjusted_cagr - (fade_step * (year - 1))
            else:
                current_growth = adjusted_cagr

            current_rev = last_revenue * (1 + current_growth)
            projected_revenues.append(round(current_rev, 2))
            revenue_growth_pct.append(round(current_growth * 100, 2))

            current_margin = margin_path[year - 1]
            current_ebitda = current_rev * current_margin
            projected_ebitda.append(round(current_ebitda, 2))
            ebitda_margin_pct.append(round(current_margin * 100, 2))

            # D&A
            current_da = current_rev * self.da_percent_rev
            projected_da.append(round(current_da, 2))

            # EBIT
            current_ebit = current_ebitda - current_da
            projected_ebit.append(round(current_ebit, 2))

            # Taxes with NOL carryforward support
            if current_ebit <= 0:
                current_taxes = 0.0
                nol_balance += abs(current_ebit)
            else:
                nol_utilized = min(nol_balance, current_ebit)
                taxable_ebit = current_ebit - nol_utilized
                nol_balance -= nol_utilized
                current_taxes = max(0, taxable_ebit * self.tax_rate)
            projected_taxes.append(round(current_taxes, 2))
            projected_tax_loss_carryforward.append(round(nol_balance, 2))

            # EBIAT
            current_ebiat = current_ebit - current_taxes
            projected_ebiat.append(round(current_ebiat, 2))

            # CapEx
            capex = current_rev * self.cap_ex_percent_rev
            projected_capex.append(round(capex, 2))

            receivables, payables, inventory, nwc_balance, change_in_nwc = self._calculate_nwc_components(
                current_rev=current_rev,
                previous_rev=last_revenue,
                current_margin=current_margin,
                last_nwc_balance=last_nwc_balance,
            )
            
            projected_nwc_change.append(round(change_in_nwc, 2))
            projected_receivables.append(round(receivables, 2))
            projected_payables.append(round(payables, 2))
            projected_inventory.append(round(inventory, 2))

            # UFCF
            ufcf = current_ebiat + current_da - capex - change_in_nwc
            projected_ufcf.append(round(ufcf, 2))

            # Rollover
            last_revenue = current_rev
            last_nwc_balance = nwc_balance

        # Historical actuals
        hist_labels = []
        for i in range(len(self.historical_revenues)):
            hist_labels.append(f"FY{self.base_fy - len(self.historical_revenues) + 1 + i}A")

        return {
            "assumptions": {
                "revenue_cagr": round(adjusted_cagr, 4),
                "revenue_cagr_override": round(self.revenue_cagr_override, 4) if self.revenue_cagr_override is not None else None,
                "avg_ebitda_margin": round(adjusted_margin, 4),
                "latest_ebitda_margin": round(latest_margin, 4),
                "terminal_ebitda_margin": round(terminal_margin, 4),
                "tax_rate": round(self.tax_rate, 4),
                "opening_tax_loss_carryforward": round(self.tax_loss_carryforward, 2),
                "da_percent_rev": round(self.da_percent_rev, 4),
                "cap_ex_percent_rev": round(self.cap_ex_percent_rev, 4),
                "nwc_percent_rev": round(self.nwc_percent_rev, 4),
                "nwc_method": self.nwc_method,
                "margin_baseline_override": round(self.margin_baseline_override, 4) if self.margin_baseline_override is not None else None,
                "base_fy": self.base_fy,
                "scenario": adj['label'],
                "working_capital_days": {
                    "dso": self.dso,
                    "dpo": self.dpo,
                    "dio": self.dio
                }
            },
            "historical": {
                "fy_labels": hist_labels,
                "revenue": self.historical_revenues,
                "ebitda_margins": self.historical_ebitda_margins,
                "ebitda": [round(r * m, 2) for r, m in zip(self.historical_revenues, self.historical_ebitda_margins)]
            },
            "projections": {
                "fy_labels": fy_labels,
                "revenue": projected_revenues,
                "revenue_growth_pct": revenue_growth_pct,
                "ebitda": projected_ebitda,
                "ebitda_margin_pct": ebitda_margin_pct,
                "da": projected_da,
                "ebit": projected_ebit,
                "taxes": projected_taxes,
                "ebiat": projected_ebiat,
                "capex": projected_capex,
                "nwc_change": projected_nwc_change,
                "ufcf": projected_ufcf,
                "tax_loss_carryforward_balance": projected_tax_loss_carryforward,
                "receivables": projected_receivables,
                "payables": projected_payables,
                "inventory": projected_inventory
            }
        }

    def calculate_valuation(self, ufcf_projections: List[float], wacc: float, terminal_growth_rate: float,
                           net_debt: float = 0, shares_outstanding: Optional[float] = 1) -> Dict[str, Any]:
        """Calculates Terminal Value and Enterprise Value (EV)."""
        if not ufcf_projections:
            raise ValueError("UFCF projections are empty.")
        if wacc <= terminal_growth_rate:
            raise ValueError("WACC must exceed terminal growth rate")

        projection_years = len(ufcf_projections)
        final_year_ufcf = ufcf_projections[-1]

        # Terminal Value (Gordon Growth Method)
        tv = (final_year_ufcf * (1 + terminal_growth_rate)) / (wacc - terminal_growth_rate)

        # Discount Free Cash Flows using the mid-year convention.
        pv_of_fcf = 0
        discount_periods = []
        discount_factors = []
        pv_fcf_array = []
        for i, cash_flow in enumerate(ufcf_projections):
            discount_period = (i + 1) - 0.5
            discount_factor = 1 / ((1 + wacc) ** discount_period)
            discount_periods.append(round(discount_period, 2))
            discount_factors.append(round(discount_factor, 4))

            pv = cash_flow * discount_factor
            pv_fcf_array.append(round(pv, 2))
            pv_of_fcf += pv

        # Discount Terminal Value
        pv_of_tv = tv * discount_factors[-1]

        # Implied Enterprise Value
        implied_ev = pv_of_fcf + pv_of_tv

        # Implied Equity Value & Share Price
        equity_value = implied_ev - net_debt
        share_price = None
        if shares_outstanding is not None and shares_outstanding > 0:
            share_price = equity_value / shares_outstanding

        # Sanity checks
        warnings = []
        if equity_value < 0:
            warnings.append("NEGATIVE EQUITY VALUE: Check net_debt and EBITDA margin inputs.")
        if share_price is not None and share_price < 0:
            warnings.append("NEGATIVE SHARE PRICE: Model output is mathematically impossible for a going concern.")
        if pv_of_fcf < 0:
            warnings.append("NEGATIVE PV OF FCF: EBITDA margins may be too low relative to D&A and CapEx.")

        return {
            "wacc": wacc,
            "terminal_growth_rate": terminal_growth_rate,
            "terminal_value": round(tv, 2),
            "discount_convention": "mid_year",
            "discount_periods": discount_periods,
            "discount_factors": discount_factors,
            "pv_of_fcf_array": pv_fcf_array,
            "pv_of_fcf_sum": round(pv_of_fcf, 2),
            "pv_of_tv": round(pv_of_tv, 2),
            "implied_enterprise_value": round(implied_ev, 2),
            "net_debt": net_debt,
            "implied_equity_value": round(equity_value, 2),
            "shares_outstanding": shares_outstanding,
            "implied_share_price": round(share_price, 2) if share_price is not None else None,
            "warnings": warnings
        }

    # ------------------------------------------------------------------
    # Advanced Analysis Methods
    # ------------------------------------------------------------------

    def run_scenario_analysis(self, ufcf: List[float], wacc: float, tgr: float,
                              net_debt: float, shares: Optional[float]) -> Dict[str, Any]:
        """Bear / Base / Bull scenarios with WACC shifts."""
        scenarios = {}
        configs = [
            ("Bear", wacc + 0.02, tgr - 0.005),
            ("Base", wacc, tgr),
            ("Bull", wacc - 0.02, tgr + 0.005),
        ]
        for label, w, t in configs:
            val = self.calculate_valuation(ufcf, w, t, net_debt, shares)
            scenarios[label.lower()] = {
                "label": label,
                "enterprise_value": val["implied_enterprise_value"],
                "equity_value": val["implied_equity_value"],
                "implied_price": val["implied_share_price"],
            }
        return scenarios

    def terminal_value_crosscheck(self, ufcf: List[float], terminal_ebitda: Optional[float], wacc: float, tgr: float,
                                   exit_multiple: float = 12.0) -> Dict[str, Any]:
        """Compare Gordon Growth TV with an EV/EBITDA terminal multiple."""
        final_fcf = ufcf[-1]
        gordon_tv = (final_fcf * (1 + tgr)) / (wacc - tgr)
        if terminal_ebitda is None or terminal_ebitda <= 0:
            return {
                "selected_method": "Gordon",
                "terminal_metric": "EBITDA",
                "terminal_metric_value": round(float(terminal_ebitda or 0), 2),
                "gordon_tv": round(gordon_tv, 2),
                "exit_multiple_tv": None,
                "exit_multiple_used": exit_multiple,
                "blended_tv": None,
                "gordon_vs_multiple_gap_pct": None,
                "note": "Exit multiple cross-check unavailable because terminal EBITDA is non-positive.",
            }

        exit_tv = terminal_ebitda * exit_multiple
        blended_tv = (gordon_tv + exit_tv) / 2

        gap_pct = ((gordon_tv - exit_tv) / exit_tv * 100) if exit_tv != 0 else 0

        return {
            "selected_method": "Gordon",
            "terminal_metric": "EBITDA",
            "terminal_metric_value": round(terminal_ebitda, 2),
            "gordon_tv": round(gordon_tv, 2),
            "exit_multiple_tv": round(exit_tv, 2),
            "exit_multiple_used": exit_multiple,
            "blended_tv": round(blended_tv, 2),
            "gordon_vs_multiple_gap_pct": round(gap_pct, 2),
        }

    def calculate_sbc_adjusted(self, equity_value: float, shares: Optional[float],
                                sbc_pct_rev: float, total_projected_revenue: float) -> Dict[str, Any]:
        """SBC dilution impact on share price."""
        base_price = equity_value / shares if shares and shares > 0 else None
        total_sbc = total_projected_revenue * sbc_pct_rev
        adj_equity = equity_value - total_sbc
        adj_price = adj_equity / shares if shares and shares > 0 else None

        return {
            "sbc_source": "Assumed stress case",
            "sbc_pct_revenue": sbc_pct_rev,
            "equity_value": round(adj_equity, 2),
            "implied_price": round(adj_price, 2) if adj_price is not None else None,
            "price_impact_vs_no_sbc": round(adj_price - base_price, 2)
            if adj_price is not None and base_price is not None
            else None,
        }

    def calculate_margin_sensitivity(self, revs: List[float],
                                     wacc: float, tgr: float,
                                     net_debt: float, shares: Optional[float],
                                     base_margin: float) -> Dict[str, Any]:
        """Run scenarios using absolute EBITDA margin impacts."""
        results = []

        # We test margins at -2%, Base, and +2%
        margin_scenarios = [
            (max(-0.50, base_margin - 0.02), "Bear Case (-2% Margin)"),
            (base_margin, "Base Case"),
            (base_margin + 0.02, "Bull Case (+2% Margin)")
        ]

        for margin_rate, label in margin_scenarios:
            new_ufcf = []
            opening_margin = self.historical_ebitda_margins[-1] if self.historical_ebitda_margins else base_margin
            last_nwc = self._estimate_opening_nwc_balance(revs[0], opening_margin)
            for i, r in enumerate(revs):
                ebitda = r * margin_rate
                da = r * self.da_percent_rev
                ebit = ebitda - da
                taxes = max(0, ebit * self.tax_rate)
                ebiat = ebit - taxes
                capex = r * self.cap_ex_percent_rev
                previous_revenue = revs[i - 1] if i > 0 else revs[0]
                _, _, _, nwc_bal, change_nwc = self._calculate_nwc_components(
                    current_rev=r,
                    previous_rev=previous_revenue,
                    current_margin=margin_rate,
                    last_nwc_balance=last_nwc,
                )

                ufcf = ebiat + da - capex - change_nwc
                new_ufcf.append(ufcf)
                last_nwc = nwc_bal

            val = self.calculate_valuation(new_ufcf, wacc, tgr, net_debt, shares)

            results.append({
                "margin_pct": round(margin_rate, 4),
                "label": label,
                "equity_value": val["implied_equity_value"],
                "implied_price": val["implied_share_price"]
            })

        return {"cases": results}

    def build_sensitivity_matrix(self, ufcf: List[float], wacc: float, tgr: float,
                                  net_debt: float, shares: Optional[float],
                                  metric: str = "share_price",
                                  adjustment_factor: float = 1.0) -> Dict[str, Any]:
        """WACC x Terminal Growth Rate two-way sensitivity table."""
        wacc_steps = [wacc - 0.02, wacc - 0.01, wacc, wacc + 0.01, wacc + 0.02]
        tgr_steps = [tgr - 0.01, tgr - 0.005, tgr, tgr + 0.005, tgr + 0.01]

        matrix = []
        for w in wacc_steps:
            row = []
            for t in tgr_steps:
                if w <= t:
                    row.append(None)
                    continue
                val = self.calculate_valuation(ufcf, w, t, net_debt, shares)
                value = val["implied_share_price"] if metric == "share_price" else val["implied_equity_value"]
                row.append(round(value * adjustment_factor, 2) if value is not None else None)
            matrix.append(row)

        return {
            "wacc_headers": [round(w, 4) for w in wacc_steps],
            "tgr_headers": [round(t, 4) for t in tgr_steps],
            "matrix": matrix,
            "metric": metric,
        }

    def calculate_capex_sensitivity(self, ufcf_base: List[float], revs: List[float],
                                     wacc: float, tgr: float, net_debt: float, shares: Optional[float],
                                     base_capex_pct: float) -> Dict[str, Any]:
        """Test sensitivity of valuation to CapEx intensity."""
        base_val = self.calculate_valuation(ufcf_base, wacc, tgr, net_debt, shares)
        base_price = base_val["implied_share_price"]

        capex_scenarios = sorted({
            max(0.0, round(base_capex_pct - 0.01, 4)),
            round(base_capex_pct, 4),
            round(base_capex_pct + 0.01, 4),
            round(base_capex_pct + 0.02, 4),
        })
        results = []

        for new_pct in capex_scenarios:
            if new_pct == base_capex_pct:
                label = f"{new_pct*100:.1f}% (Base Case)"
            else:
                label = f"{new_pct*100:.1f}%"

            delta_pct = new_pct - base_capex_pct

            # Reconstruct UFCF with new CapEx
            new_ufcf = []
            for i, u_base in enumerate(ufcf_base):
                penalty = revs[i] * delta_pct
                new_ufcf.append(u_base - penalty)

            val = self.calculate_valuation(new_ufcf, wacc, tgr, net_debt, shares)
            results.append({
                "capex_pct": new_pct,
                "label": label,
                "equity_value": val["implied_equity_value"],
                "implied_price": val["implied_share_price"],
                "price_delta_vs_base": round(val["implied_share_price"] - base_price, 2)
                if base_price is not None and val["implied_share_price"] is not None
                else None
            })

        return {"cases": results}

    def build_full_scenario_analysis(self, wacc: float, tgr: float, net_debt: float,
                                     shares: Optional[float], projection_years: int = 7) -> Dict[str, Any]:
        """
        Build comprehensive 3-scenario analysis (Bear/Base/Bull) with full projections.
        Returns all scenario data for display.
        """
        scenarios = {}
        
        for scenario_name in ['bear', 'base', 'bull']:
            projections = self.build_projections(projection_years, tgr, scenario_name)
            ufcf = projections['projections']['ufcf']
            
            # Apply scenario-specific WACC adjustment
            wacc_adj = {'bear': 0.02, 'base': 0.0, 'bull': -0.02}[scenario_name]
            scenario_wacc = wacc + wacc_adj
            
            valuation = self.calculate_valuation(ufcf, scenario_wacc, tgr, net_debt, shares)
            
            scenarios[scenario_name] = {
                'label': projections['assumptions']['scenario'],
                'revenue_cagr': projections['assumptions']['revenue_cagr'],
                'ebitda_margin': projections['assumptions']['avg_ebitda_margin'],
                'projections': projections['projections'],
                'valuation': {
                    'enterprise_value': valuation['implied_enterprise_value'],
                    'equity_value': valuation['implied_equity_value'],
                    'share_price': valuation['implied_share_price'],
                }
            }
        
        return scenarios

    def probability_weighted_scenario_value(self, scenario_data: Dict[str, Any],
                                            probability_weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        """Compute expected value from Bear/Base/Bull scenario outputs."""
        if not scenario_data:
            return {
                "expected_value": None,
                "weights": {},
                "metric": None,
                "note": "No scenario data available",
            }

        weights = probability_weights or {
            "bear": 0.25,
            "base": 0.50,
            "bull": 0.25,
        }

        # Normalize weights to sum to 1.
        total = sum(max(0.0, float(v)) for v in weights.values())
        if total <= 0:
            weights = {"bear": 0.25, "base": 0.50, "bull": 0.25}
            total = 1.0
        normalized = {k: max(0.0, float(v)) / total for k, v in weights.items()}

        # Prefer per-share if available, else fallback to equity value.
        metric = "share_price"
        has_share_price = all(
            scenario_data.get(name, {}).get("valuation", {}).get("share_price") is not None
            for name in ["bear", "base", "bull"]
            if name in scenario_data
        )
        if not has_share_price:
            metric = "equity_value"

        expected_value = 0.0
        weighted_rows = []
        for name, scenario in scenario_data.items():
            val_block = scenario.get("valuation", {})
            value = val_block.get("share_price") if metric == "share_price" else val_block.get("equity_value")
            if not isinstance(value, (int, float)):
                continue
            w = normalized.get(name, 0.0)
            weighted_rows.append({
                "scenario": name,
                "weight": round(w, 4),
                "value": round(float(value), 4),
                "weighted_value": round(float(value) * w, 4),
            })
            expected_value += float(value) * w

        return {
            "expected_value": round(expected_value, 4),
            "weights": {k: round(v, 4) for k, v in normalized.items()},
            "metric": metric,
            "details": weighted_rows,
        }

    def run_monte_carlo(self,
                        ufcf_base: List[float],
                        wacc: float,
                        tgr: float,
                        net_debt: float,
                        shares: Optional[float],
                        iterations: int = 1000,
                        seed: int = 42,
                        growth_volatility: float = 0.015,
                        margin_volatility: float = 0.04,
                        wacc_volatility: float = 0.01,
                        tgr_volatility: float = 0.003,
                        correlation_matrix: Optional[Dict[str, Dict[str, float]]] = None,
                        var_confidence_level: float = 0.95) -> Dict[str, Any]:
        """
        Monte Carlo simulation around base DCF inputs.
        Returns distribution stats and confidence intervals.
        """
        if not ufcf_base:
            return {
                "iterations": 0,
                "metric": None,
                "distribution": [],
                "summary": {"error": "Empty UFCF base series"},
            }

        iterations = max(100, int(iterations or 1000))
        random.seed(seed)

        use_share_price = shares is not None and shares > 0
        metric = "share_price" if use_share_price else "equity_value"
        outputs: List[float] = []

        factor_names = ["growth", "margin", "wacc", "tgr"]

        def _build_corr_lookup() -> Dict[str, Dict[str, float]]:
            defaults = {
                "growth": {"margin": 0.45, "wacc": -0.35, "tgr": 0.20},
                "margin": {"growth": 0.45, "wacc": -0.25, "tgr": 0.15},
                "wacc": {"growth": -0.35, "margin": -0.25, "tgr": 0.40},
                "tgr": {"growth": 0.20, "margin": 0.15, "wacc": 0.40},
            }
            if not isinstance(correlation_matrix, dict):
                return defaults
            merged = {
                key: dict(value)
                for key, value in defaults.items()
            }
            for k, nested in correlation_matrix.items():
                if k in merged and isinstance(nested, dict):
                    for k2, corr in nested.items():
                        if k2 in factor_names and k2 != k:
                            merged[k][k2] = max(-0.95, min(0.95, float(corr)))
            return merged

        def _build_corr_matrix(lookup: Dict[str, Dict[str, float]]) -> List[List[float]]:
            matrix: List[List[float]] = []
            for i_name in factor_names:
                row: List[float] = []
                for j_name in factor_names:
                    if i_name == j_name:
                        row.append(1.0)
                    else:
                        corr = lookup.get(i_name, {}).get(j_name)
                        if corr is None:
                            corr = lookup.get(j_name, {}).get(i_name, 0.0)
                        row.append(max(-0.95, min(0.95, float(corr))))
                matrix.append(row)
            return matrix

        def _cholesky_decompose(matrix: List[List[float]]) -> Optional[List[List[float]]]:
            n = len(matrix)
            l = [[0.0] * n for _ in range(n)]
            try:
                for i in range(n):
                    for j in range(i + 1):
                        s = sum(l[i][k] * l[j][k] for k in range(j))
                        if i == j:
                            diag = matrix[i][i] - s
                            if diag <= 0:
                                return None
                            l[i][j] = math.sqrt(diag)
                        else:
                            if l[j][j] == 0:
                                return None
                            l[i][j] = (matrix[i][j] - s) / l[j][j]
            except Exception:
                return None
            return l

        corr_lookup = _build_corr_lookup()
        corr_matrix = _build_corr_matrix(corr_lookup)
        cholesky = _cholesky_decompose(corr_matrix)
        if not cholesky:
            corr_matrix = [
                [1.0 if i == j else 0.0 for j in range(len(factor_names))]
                for i in range(len(factor_names))
            ]
            cholesky = _cholesky_decompose(corr_matrix)

        for _ in range(iterations):
            z = [random.gauss(0.0, 1.0) for _ in factor_names]
            correlated = [
                sum(cholesky[i][k] * z[k] for k in range(len(factor_names)))
                for i in range(len(factor_names))
            ]
            growth_shock = correlated[0] * growth_volatility
            margin_shock = correlated[1] * margin_volatility
            wacc_shock = correlated[2] * wacc_volatility
            tgr_shock = correlated[3] * tgr_volatility

            # Keep sampled parameters in sane bounds.
            sampled_wacc = max(0.06, min(0.30, wacc + wacc_shock))
            sampled_tgr = max(0.005, min(0.06, tgr + tgr_shock))
            if sampled_tgr >= sampled_wacc - 0.01:
                sampled_tgr = max(0.005, sampled_wacc - 0.01)

            sampled_ufcf = []
            for i, cf in enumerate(ufcf_base):
                period_growth = (1.0 + growth_shock) ** (i + 1)
                shocked_cf = cf * period_growth * (1.0 + margin_shock)
                sampled_ufcf.append(shocked_cf)

            try:
                val = self.calculate_valuation(sampled_ufcf, sampled_wacc, sampled_tgr, net_debt, shares)
                metric_val = val["implied_share_price"] if use_share_price else val["implied_equity_value"]
                if isinstance(metric_val, (int, float)):
                    outputs.append(float(metric_val))
            except Exception:
                continue

        if not outputs:
            return {
                "iterations": iterations,
                "metric": metric,
                "distribution": [],
                "summary": {"error": "No valid Monte Carlo samples produced"},
            }

        sorted_vals = sorted(outputs)
        n = len(sorted_vals)

        def pct(p: float) -> float:
            idx = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
            return sorted_vals[idx]

        mean_val = statistics.fmean(sorted_vals)
        median_val = statistics.median(sorted_vals)
        std_val = statistics.pstdev(sorted_vals) if n > 1 else 0.0
        p5 = pct(5)
        p95 = pct(95)
        p10 = pct(10)
        p90 = pct(90)

        var_confidence_level = max(0.80, min(0.995, float(var_confidence_level or 0.95)))
        tail_percentile = (1.0 - var_confidence_level) * 100.0
        var_value = pct(tail_percentile)
        tail_values = [v for v in sorted_vals if v <= var_value]
        cvar_value = statistics.fmean(tail_values) if tail_values else var_value

        prob_negative = sum(1 for x in sorted_vals if x < 0) / n
        prob_above_base = sum(1 for x in sorted_vals if x > median_val) / n

        return {
            "iterations": n,
            "metric": metric,
            "summary": {
                "mean": round(mean_val, 4),
                "median": round(median_val, 4),
                "std_dev": round(std_val, 4),
                "p5": round(p5, 4),
                "p10": round(p10, 4),
                "p90": round(p90, 4),
                "p95": round(p95, 4),
                "confidence_interval_90": [round(p5, 4), round(p95, 4)],
                "probability_of_loss": round(prob_negative, 4),
                "probability_above_median": round(prob_above_base, 4),
                "var_confidence_level": round(var_confidence_level, 4),
                "var_value": round(var_value, 4),
                "cvar_value": round(cvar_value, 4),
                "var_downside_from_mean": round(max(0.0, mean_val - var_value), 4),
                "cvar_downside_from_mean": round(max(0.0, mean_val - cvar_value), 4),
            },
            # Keep payload bounded for API consumers.
            "distribution_preview": {
                "min": round(sorted_vals[0], 4),
                "max": round(sorted_vals[-1], 4),
                "sample": [round(v, 4) for v in sorted_vals[::max(1, n // 25)]][:25],
            },
            "assumptions": {
                "growth_volatility": growth_volatility,
                "margin_volatility": margin_volatility,
                "wacc_volatility": wacc_volatility,
                "tgr_volatility": tgr_volatility,
                "seed": seed,
                "correlation_matrix": corr_matrix,
            },
        }
