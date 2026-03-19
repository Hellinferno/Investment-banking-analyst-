"""
LBO (Leveraged Buyout) computation engine.

Deterministic pure-Python engine — zero LLM calls.
IRR is computed via scipy.optimize.brentq (NPV root-finding) since
numpy_financial is not in requirements; scipy is already installed.

Spec reference: docs/08-computation-engine-spec.md Section 4.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from scipy.optimize import brentq

logger = logging.getLogger(__name__)

_DSCR_COVENANT = 1.20   # Minimum DSCR covenant (flag, not raise)
_BALANCE_TOLERANCE = 1.0 # Sources / Uses balance tolerance (absolute)


class LBOEngine:
    """
    Leveraged Buyout model engine.

    Parameters
    ----------
    entry_ebitda : float
        LTM EBITDA at entry (absolute, same currency units as revenue_ltm).
    revenue_ltm : float
        LTM Revenue at entry.
    entry_ev_ebitda : float
        Entry EV / EBITDA multiple (e.g. 8.0).
    equity_contribution_pct : float
        Equity as fraction of total purchase price (e.g. 0.40 = 40 %).
    senior_debt_ebitda : float
        Senior term-loan debt as multiple of entry EBITDA (e.g. 3.0x).
    mezz_debt_ebitda : float
        Mezzanine debt as multiple of entry EBITDA (default 0).
    senior_interest_rate : float
        Annual cash pay interest on senior debt (e.g. 0.08 = 8 %).
    mezz_interest_rate : float
        Annual cash pay interest on mezz debt (e.g. 0.12 = 12 %).
    projection_years : int
        Hold period in years (default 5).
    exit_ev_ebitda : float | None
        Exit EV / EBITDA multiple. Defaults to entry_ev_ebitda if None.
    revenue_growth_rates : list[float] | None
        Per-year revenue growth rates. If None, defaults to [0.08] * projection_years.
    ebitda_margins : list[float] | None
        Per-year EBITDA margins. If None, defaults to entry EBITDA / entry revenue.
    tax_rate : float
        Effective corporate tax rate (default 0.25).
    capex_pct_rev : float
        CapEx as % of revenue (default 0.04 = 4 %).
    tla_amort_pct : float
        TLA mandatory annual amortisation as % of original principal (default 0.10 = 10 %).
    """

    def __init__(
        self,
        entry_ebitda: float,
        revenue_ltm: float,
        entry_ev_ebitda: float,
        equity_contribution_pct: float = 0.40,
        senior_debt_ebitda: float = 3.0,
        mezz_debt_ebitda: float = 0.0,
        senior_interest_rate: float = 0.08,
        mezz_interest_rate: float = 0.12,
        projection_years: int = 5,
        exit_ev_ebitda: Optional[float] = None,
        revenue_growth_rates: Optional[list] = None,
        ebitda_margins: Optional[list] = None,
        tax_rate: float = 0.25,
        capex_pct_rev: float = 0.04,
        tla_amort_pct: float = 0.10,
    ):
        self.entry_ebitda = float(entry_ebitda)
        self.revenue_ltm = float(revenue_ltm)
        self.entry_ev_ebitda = float(entry_ev_ebitda)
        self.equity_contribution_pct = float(equity_contribution_pct)
        self.senior_debt_ebitda = float(senior_debt_ebitda)
        self.mezz_debt_ebitda = float(mezz_debt_ebitda)
        self.senior_interest_rate = float(senior_interest_rate)
        self.mezz_interest_rate = float(mezz_interest_rate)
        self.projection_years = int(projection_years)
        self.exit_ev_ebitda = float(exit_ev_ebitda) if exit_ev_ebitda is not None else float(entry_ev_ebitda)
        self.tax_rate = float(tax_rate)
        self.capex_pct_rev = float(capex_pct_rev)
        self.tla_amort_pct = float(tla_amort_pct)

        n = self.projection_years
        if revenue_growth_rates is None or len(revenue_growth_rates) == 0:
            self.revenue_growth_rates = [0.08] * n
        else:
            rates = list(revenue_growth_rates)
            self.revenue_growth_rates = (rates * n)[:n]

        entry_margin = self.entry_ebitda / self.revenue_ltm if self.revenue_ltm > 0 else 0.20
        if ebitda_margins is None or len(ebitda_margins) == 0:
            self.ebitda_margins = [entry_margin] * n
        else:
            margins = list(ebitda_margins)
            self.ebitda_margins = (margins * n)[:n]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> dict:
        """
        Execute the full LBO model and return structured results.

        Returns
        -------
        dict with keys:
            sources_uses, operating_model, debt_schedule, dscr_by_year,
            dscr_minimum, irr, moic, entry_ev, exit_ev, entry_equity,
            exit_equity, warnings
        """
        warnings: list[str] = []

        # 1. Sources & Uses
        sources_uses = self._build_sources_uses()

        entry_ev = sources_uses["total_uses"]
        entry_equity = sources_uses["equity"]
        senior_debt_0 = sources_uses["senior_debt"]
        mezz_debt_0 = sources_uses["mezz_debt"]
        total_debt_0 = senior_debt_0 + mezz_debt_0

        # 2. Operating model projections
        operating_model = self._project_operating_model()

        # 3. Debt schedule
        debt_schedule = self._build_debt_schedule(
            senior_debt_0=senior_debt_0,
            mezz_debt_0=mezz_debt_0,
            ufcf_list=operating_model["ufcf"],
        )

        # 4. DSCR per year
        dscr_by_year: dict[int, float] = {}
        for i, ds in enumerate(debt_schedule, start=1):
            dscr = self._compute_dscr(
                year_ebitda=operating_model["ebitda"][i - 1],
                year_cash_interest=ds["cash_interest"],
                year_amort=ds["mandatory_amort"],
            )
            dscr_by_year[i] = round(dscr, 3)
            if dscr < _DSCR_COVENANT:
                warnings.append(
                    f"Year {i} DSCR {dscr:.2f}x is below covenant minimum {_DSCR_COVENANT}x."
                )

        dscr_minimum = min(dscr_by_year.values()) if dscr_by_year else 0.0

        # 5. Exit valuation
        exit_ebitda = operating_model["ebitda"][-1]
        exit_ev = exit_ebitda * self.exit_ev_ebitda
        exit_debt = debt_schedule[-1]["closing_debt"]
        exit_equity = max(exit_ev - exit_debt, 0.0)

        # 6. Returns
        moic = exit_equity / entry_equity if entry_equity > 0 else 0.0

        # Cash flows to equity: [-entry_equity, 0, 0, ..., exit_equity]
        cf = [-entry_equity] + [0.0] * (self.projection_years - 1) + [exit_equity]
        try:
            irr = self._compute_irr(cf)
        except (ValueError, RuntimeError) as exc:
            warnings.append(f"IRR computation failed: {exc}")
            irr = 0.0

        if irr > 1.0:
            warnings.append(f"IRR {irr*100:.1f}% exceeds 100% — verify assumptions.")
        elif irr < 0.0:
            warnings.append(f"IRR {irr*100:.1f}% is negative — deal destroys value.")

        return {
            "sources_uses": sources_uses,
            "operating_model": operating_model,
            "debt_schedule": debt_schedule,
            "dscr_by_year": dscr_by_year,
            "dscr_minimum": round(dscr_minimum, 3),
            "irr": round(irr, 4),
            "irr_pct": round(irr * 100, 2),
            "moic": round(moic, 2),
            "entry_ev": round(entry_ev, 2),
            "exit_ev": round(exit_ev, 2),
            "entry_equity": round(entry_equity, 2),
            "exit_equity": round(exit_equity, 2),
            "total_debt_at_entry": round(total_debt_0, 2),
            "total_debt_at_exit": round(exit_debt, 2),
            "warnings": warnings,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_sources_uses(self) -> dict:
        """Build Sources & Uses table; raises ValueError if they don't balance."""
        entry_ev = self.entry_ebitda * self.entry_ev_ebitda
        senior_debt = self.entry_ebitda * self.senior_debt_ebitda
        mezz_debt = self.entry_ebitda * self.mezz_debt_ebitda
        total_debt = senior_debt + mezz_debt

        # Equity is derived (not just contribution_pct × EV) to ensure balance
        equity = entry_ev - total_debt
        if equity <= 0:
            raise ValueError(
                f"Debt structure ({total_debt:.0f}) exceeds entry EV ({entry_ev:.0f}). "
                "Reduce leverage or increase equity contribution."
            )

        total_sources = equity + senior_debt + mezz_debt
        total_uses = entry_ev  # Assume purchase price = EV (no transaction fees in v1)

        if abs(total_sources - total_uses) > _BALANCE_TOLERANCE:
            raise ValueError(
                f"Sources ({total_sources:.2f}) ≠ Uses ({total_uses:.2f}). "
                f"Difference: {total_sources - total_uses:.2f}."
            )

        return {
            "equity": round(equity, 2),
            "senior_debt": round(senior_debt, 2),
            "mezz_debt": round(mezz_debt, 2),
            "total_sources": round(total_sources, 2),
            "total_uses": round(total_uses, 2),
            "entry_ev": round(entry_ev, 2),
            "equity_pct": round(equity / entry_ev * 100, 1),
            "debt_pct": round(total_debt / entry_ev * 100, 1),
            "leverage_multiple": round(total_debt / self.entry_ebitda, 2),
        }

    def _project_operating_model(self) -> dict:
        """Project revenue, EBITDA, EBIT, and unlevered FCF over the hold period."""
        revenues: list[float] = []
        ebitda: list[float] = []
        ebit: list[float] = []
        ufcf: list[float] = []

        rev = self.revenue_ltm
        da_pct = 0.04  # D&A as % of revenue (standard approximation)

        for i in range(self.projection_years):
            rev = rev * (1.0 + self.revenue_growth_rates[i])
            ebitda_y = rev * self.ebitda_margins[i]
            da_y = rev * da_pct
            ebit_y = ebitda_y - da_y
            nopat = ebit_y * (1.0 - self.tax_rate)
            capex_y = rev * self.capex_pct_rev
            ufcf_y = nopat + da_y - capex_y  # simplified: ignore WC changes

            revenues.append(round(rev, 2))
            ebitda.append(round(ebitda_y, 2))
            ebit.append(round(ebit_y, 2))
            ufcf.append(round(ufcf_y, 2))

        return {"revenues": revenues, "ebitda": ebitda, "ebit": ebit, "ufcf": ufcf}

    def _build_debt_schedule(
        self,
        senior_debt_0: float,
        mezz_debt_0: float,
        ufcf_list: list[float],
    ) -> list[dict]:
        """
        Year-by-year debt schedule.

        TLA amortises at tla_amort_pct per year.
        TLB is repaid via cash sweep after mandatory TLA amort.
        Mezz is bullet (cash-pay interest only, repaid at exit).
        """
        schedule: list[dict] = []
        tla_original = senior_debt_0 * 0.50   # 50% TLA, 50% TLB split (standard)
        tlb = senior_debt_0 * 0.50
        mezz = mezz_debt_0

        tla_remaining = tla_original

        for i in range(self.projection_years):
            ufcf = ufcf_list[i]

            # Interest
            tla_interest = tla_remaining * self.senior_interest_rate
            tlb_interest = tlb * self.senior_interest_rate
            mezz_interest = mezz * self.mezz_interest_rate
            total_cash_interest = tla_interest + tlb_interest + mezz_interest

            # Mandatory TLA amortisation
            tla_amort = min(tla_original * self.tla_amort_pct, tla_remaining)

            # Cash available for voluntary debt paydown (cash sweep)
            cash_after_interest_and_amort = ufcf - total_cash_interest - tla_amort
            tlb_sweep = max(min(cash_after_interest_and_amort, tlb), 0.0)
            tlb -= tlb_sweep
            tla_remaining -= tla_amort

            total_debt_open = tla_remaining + tla_amort + tlb + tlb_sweep + mezz
            total_debt_close = tla_remaining + tlb + mezz

            schedule.append({
                "year": i + 1,
                "opening_debt": round(total_debt_open, 2),
                "tla_balance": round(tla_remaining, 2),
                "tlb_balance": round(tlb, 2),
                "mezz_balance": round(mezz, 2),
                "cash_interest": round(total_cash_interest, 2),
                "mandatory_amort": round(tla_amort, 2),
                "cash_sweep": round(tlb_sweep, 2),
                "closing_debt": round(total_debt_close, 2),
                "fcf_to_equity": round(max(cash_after_interest_and_amort - tlb_sweep, 0.0), 2),
            })

        return schedule

    @staticmethod
    def _compute_dscr(year_ebitda: float, year_cash_interest: float, year_amort: float) -> float:
        """DSCR = EBITDA / (Cash Interest + Mandatory Principal)."""
        debt_service = year_cash_interest + year_amort
        if debt_service <= 0:
            return 999.0  # No debt service → infinite coverage
        return year_ebitda / debt_service

    @staticmethod
    def _compute_irr(cash_flows: list[float]) -> float:
        """
        Compute IRR using scipy.optimize.brentq (root of NPV function).

        Raises ValueError if IRR does not converge.
        """
        cf = np.array(cash_flows, dtype=float)

        def npv(rate: float) -> float:
            t = np.arange(len(cf))
            return float(np.sum(cf / (1.0 + rate) ** t))

        # Bracket search: IRR must be in (-0.999, 10.0) for realistic deals
        try:
            low, high = -0.999, 10.0
            if npv(low) * npv(high) > 0:
                raise ValueError("IRR not bracketed — cash flows may not change sign.")
            irr = brentq(npv, low, high, xtol=1e-8, maxiter=1000)
        except ValueError as exc:
            raise ValueError(f"IRR did not converge: {exc}") from exc

        return irr

    # ------------------------------------------------------------------
    # Sensitivity helpers (used by Excel writer)
    # ------------------------------------------------------------------

    def irr_sensitivity(
        self,
        entry_multiples: list[float],
        exit_multiples: list[float],
    ) -> dict:
        """
        Return a 2-D sensitivity matrix: IRR(%) for each (entry, exit) pair.

        Used by WorkbookBuilder.write_lbo_model() to populate the sensitivity tab.
        """
        matrix: dict = {}
        for em in entry_multiples:
            row: dict = {}
            for xm in exit_multiples:
                engine = LBOEngine(
                    entry_ebitda=self.entry_ebitda,
                    revenue_ltm=self.revenue_ltm,
                    entry_ev_ebitda=em,
                    equity_contribution_pct=self.equity_contribution_pct,
                    senior_debt_ebitda=self.senior_debt_ebitda,
                    mezz_debt_ebitda=self.mezz_debt_ebitda,
                    senior_interest_rate=self.senior_interest_rate,
                    mezz_interest_rate=self.mezz_interest_rate,
                    projection_years=self.projection_years,
                    exit_ev_ebitda=xm,
                    revenue_growth_rates=self.revenue_growth_rates,
                    ebitda_margins=self.ebitda_margins,
                    tax_rate=self.tax_rate,
                    capex_pct_rev=self.capex_pct_rev,
                )
                try:
                    result = engine.run()
                    row[xm] = result["irr_pct"]
                except (ValueError, Exception):
                    row[xm] = None
            matrix[em] = row
        return matrix
