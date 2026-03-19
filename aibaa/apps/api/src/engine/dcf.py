from typing import Dict, List, Any, Optional

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
                 base_fy: int = 2025,
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
        self.base_fy = base_fy
        
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
                                 debt_to_equity: float = 0.0) -> Dict[str, Any]:
        """Calculates WACC components explicitly."""
        cost_of_equity = risk_free_rate + (beta * equity_risk_premium)
        after_tax_cost_of_debt = cost_of_debt * (1 - self.tax_rate)

        weight_of_debt = debt_to_equity / (1 + debt_to_equity)
        weight_of_equity = 1 - weight_of_debt

        wacc = (weight_of_equity * cost_of_equity) + (weight_of_debt * after_tax_cost_of_debt)

        return {
            "wacc": round(wacc, 4),
            "risk_free_rate": risk_free_rate,
            "equity_risk_premium": equity_risk_premium,
            "beta": beta,
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
        avg_ebitda_margin = sum(self.historical_ebitda_margins) / len(self.historical_ebitda_margins)
        
        # Scenario adjustments
        scenario_adjustments = {
            'bear': {'growth_multiplier': 0.7, 'margin_adjustment': -0.02, 'label': 'Bear Case'},
            'base': {'growth_multiplier': 1.0, 'margin_adjustment': 0.0, 'label': 'Base Case'},
            'bull': {'growth_multiplier': 1.3, 'margin_adjustment': 0.02, 'label': 'Bull Case'},
        }
        adj = scenario_adjustments.get(scenario, scenario_adjustments['base'])
        
        # Apply scenario adjustments
        adjusted_cagr = revenue_cagr * adj['growth_multiplier']
        adjusted_margin = avg_ebitda_margin + adj['margin_adjustment']
        
        # Floor margin at 5% (minimum viable business)
        adjusted_margin = max(0.05, adjusted_margin)

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
        
        # Cost assumptions for working capital
        cogs_percent_rev = 1.0 - adjusted_margin - self.da_percent_rev  # COGS = Revenue - EBITDA - D&A
        
        last_revenue = self.historical_revenues[-1]
        last_nwc_balance = last_revenue * self.nwc_percent_rev

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

            # EBITDA with scenario-adjusted margin
            current_ebitda = current_rev * adjusted_margin
            projected_ebitda.append(round(current_ebitda, 2))
            ebitda_margin_pct.append(round(adjusted_margin * 100, 2))

            # D&A
            current_da = current_rev * self.da_percent_rev
            projected_da.append(round(current_da, 2))

            # EBIT
            current_ebit = current_ebitda - current_da
            projected_ebit.append(round(current_ebit, 2))

            # Taxes
            current_taxes = max(0, current_ebit * self.tax_rate)
            projected_taxes.append(round(current_taxes, 2))

            # EBIAT
            current_ebiat = current_ebit - current_taxes
            projected_ebiat.append(round(current_ebiat, 2))

            # CapEx
            capex = current_rev * self.cap_ex_percent_rev
            projected_capex.append(round(capex, 2))

            # Working Capital using days methodology
            daily_revenue = current_rev / 365
            receivables = daily_revenue * self.dso
            
            daily_cogs = (current_rev * cogs_percent_rev) / 365
            payables = daily_cogs * self.dpo
            inventory = daily_cogs * self.dio
            
            nwc_balance = receivables + inventory - payables
            change_in_nwc = nwc_balance - last_nwc_balance
            
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
                "tax_rate": round(self.tax_rate, 4),
                "da_percent_rev": round(self.da_percent_rev, 4),
                "cap_ex_percent_rev": round(self.cap_ex_percent_rev, 4),
                "nwc_percent_rev": round(self.nwc_percent_rev, 4),
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

        projection_years = len(ufcf_projections)
        final_year_ufcf = ufcf_projections[-1]

        # Terminal Value (Gordon Growth Method)
        tv = (final_year_ufcf * (1 + terminal_growth_rate)) / (wacc - terminal_growth_rate)

        # Discount Free Cash Flows
        pv_of_fcf = 0
        discount_factors = []
        pv_fcf_array = []
        for i, cash_flow in enumerate(ufcf_projections):
            discount_factor = 1 / ((1 + wacc) ** (i + 1))
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

    def terminal_value_crosscheck(self, ufcf: List[float], wacc: float, tgr: float,
                                   exit_multiple: float = 12.0) -> Dict[str, Any]:
        """Compare Gordon Growth TV with Exit Multiple TV."""
        final_fcf = ufcf[-1]
        n = len(ufcf)

        gordon_tv = (final_fcf * (1 + tgr)) / (wacc - tgr)
        exit_tv = final_fcf * exit_multiple
        blended_tv = (gordon_tv + exit_tv) / 2

        gap_pct = ((gordon_tv - exit_tv) / exit_tv * 100) if exit_tv != 0 else 0

        return {
            "selected_method": "Gordon",
            "gordon_tv": round(gordon_tv, 2),
            "exit_multiple_tv": round(exit_tv, 2),
            "exit_multiple_used": exit_multiple,
            "blended_tv": round(blended_tv, 2),
            "gordon_vs_multiple_gap_pct": round(gap_pct, 2),
        }

    def calculate_sbc_adjusted(self, equity_value: float, shares: float,
                                sbc_pct_rev: float, total_projected_revenue: float) -> Dict[str, Any]:
        """SBC dilution impact on share price."""
        base_price = equity_value / shares if shares > 0 else 0
        total_sbc = total_projected_revenue * sbc_pct_rev
        adj_equity = equity_value - total_sbc
        adj_price = adj_equity / shares if shares > 0 else 0

        return {
            "sbc_source": "Assumed stress case",
            "sbc_pct_revenue": sbc_pct_rev,
            "equity_value": round(adj_equity, 2),
            "implied_price": round(adj_price, 2),
            "price_impact_vs_no_sbc": round(adj_price - base_price, 2),
        }

    def calculate_margin_sensitivity(self, revs: List[float],
                                     wacc: float, tgr: float,
                                     net_debt: float, shares: Optional[float],
                                     base_margin: float) -> Dict[str, Any]:
        """Run scenarios using absolute EBITDA margin impacts."""
        results = []

        # We test margins at -2%, Base, and +2%
        margin_scenarios = [
            (max(0.01, base_margin - 0.02), "Bear Case (-2% Margin)"),
            (base_margin, "Base Case"),
            (base_margin + 0.02, "Bull Case (+2% Margin)")
        ]

        for margin_rate, label in margin_scenarios:
            new_ufcf = []
            last_nwc = revs[0] * self.nwc_percent_rev
            for i, r in enumerate(revs):
                ebitda = r * margin_rate
                da = r * self.da_percent_rev
                ebit = ebitda - da
                taxes = max(0, ebit * self.tax_rate)
                ebiat = ebit - taxes
                capex = r * self.cap_ex_percent_rev
                nwc_bal = r * self.nwc_percent_rev
                change_nwc = nwc_bal - last_nwc

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

        capex_scenarios = [0.08, 0.10, 0.12, 0.15]
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
