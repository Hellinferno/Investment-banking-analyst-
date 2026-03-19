from typing import Dict, Any


class ComparableAnalysisEngine:
    """Deterministic, sector-aware public comps approximation."""

    DEFAULT_EV_EBITDA_BY_SECTOR = {
        "it services": (14.0, 18.0, 22.0),
        "software": (12.0, 16.0, 20.0),
        "technology": (11.0, 15.0, 19.0),
        "consumer": (9.0, 12.0, 15.0),
        "industrial": (8.0, 10.5, 13.0),
        "manufacturing": (8.0, 10.0, 12.0),
        "default": (8.0, 11.0, 14.0),
    }

    def _resolve_multiple_band(self, industry: str) -> tuple[float, float, float]:
        blob = (industry or "").lower()
        for key, band in self.DEFAULT_EV_EBITDA_BY_SECTOR.items():
            if key != "default" and key in blob:
                return band
        return self.DEFAULT_EV_EBITDA_BY_SECTOR["default"]

    @staticmethod
    def _safe_margin(avg_margin: float) -> float:
        # Constrain normalized EBITDA margin to a practical range.
        return max(0.03, min(0.35, float(avg_margin)))

    def build_comps_snapshot(
        self,
        latest_revenue: float,
        avg_ebitda_margin: float,
        net_debt: float,
        shares_outstanding: float | None,
        industry: str,
        private_company: bool,
    ) -> Dict[str, Any]:
        bear_mult, base_mult, bull_mult = self._resolve_multiple_band(industry)
        margin = self._safe_margin(avg_ebitda_margin)
        latest_ebitda = max(0.0, latest_revenue * margin)

        scenarios = {
            "bear": self._compute_point(latest_ebitda, bear_mult, net_debt, shares_outstanding, private_company),
            "base": self._compute_point(latest_ebitda, base_mult, net_debt, shares_outstanding, private_company),
            "bull": self._compute_point(latest_ebitda, bull_mult, net_debt, shares_outstanding, private_company),
        }

        return {
            "method": "ev_ebitda_comps",
            "industry": industry or "Unknown",
            "multiple_band": {"bear": bear_mult, "base": base_mult, "bull": bull_mult},
            "latest_ebitda": latest_ebitda,
            "valuation_basis": "equity_value" if private_company or not shares_outstanding else "share_price",
            "scenarios": scenarios,
        }

    @staticmethod
    def _compute_point(
        latest_ebitda: float,
        multiple: float,
        net_debt: float,
        shares_outstanding: float | None,
        private_company: bool,
    ) -> Dict[str, Any]:
        enterprise_value = latest_ebitda * multiple
        equity_value = enterprise_value - float(net_debt or 0.0)
        share_price = None
        if not private_company and shares_outstanding and shares_outstanding > 0:
            share_price = equity_value / shares_outstanding

        return {
            "ev_ebitda": multiple,
            "enterprise_value": round(enterprise_value, 2),
            "equity_value": round(equity_value, 2),
            "implied_share_price": round(share_price, 2) if share_price is not None else None,
        }
