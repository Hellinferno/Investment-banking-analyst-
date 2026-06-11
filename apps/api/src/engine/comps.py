from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


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

    def _resolve_multiple_band(
        self, industry: str, live_market_data: dict | None = None,
    ) -> tuple[float, float, float]:
        blob = (industry or "").lower()

        # Try live sector multiples from WorldMonitor if available
        if live_market_data:
            live_band = self._resolve_multiple_band_live(blob, live_market_data)
            if live_band:
                return live_band

        for key, band in self.DEFAULT_EV_EBITDA_BY_SECTOR.items():
            if key != "default" and key in blob:
                return band
        return self.DEFAULT_EV_EBITDA_BY_SECTOR["default"]

    @staticmethod
    def _resolve_multiple_band_live(
        industry_lower: str, live_data: dict,
    ) -> tuple[float, float, float] | None:
        """Derive EV/EBITDA band from live WorldMonitor market data.

        ``live_data`` may contain a ``sector_multiples`` dict mapping sector
        names to ``(bear, base, bull)`` tuples — pre-computed from real-time
        market caps and EBITDA estimates.  Returns *None* when no live data
        matches, letting the caller fall back to the hardcoded defaults.
        """
        sector_multiples = live_data.get("sector_multiples")
        if not sector_multiples or not isinstance(sector_multiples, dict):
            return None

        for key, band in sector_multiples.items():
            if key.lower() in industry_lower or industry_lower in key.lower():
                if isinstance(band, (list, tuple)) and len(band) == 3:
                    bear, base, bull = float(band[0]), float(band[1]), float(band[2])
                    if 1.0 < bear < bull < 100.0:
                        logger.debug(
                            "Using live sector multiples for '%s': %.1fx / %.1fx / %.1fx",
                            key, bear, base, bull,
                        )
                        return (bear, base, bull)
        return None

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
        live_market_data: dict | None = None,
    ) -> Dict[str, Any]:
        bear_mult, base_mult, bull_mult = self._resolve_multiple_band(
            industry, live_market_data,
        )
        margin = self._safe_margin(avg_ebitda_margin)
        latest_ebitda = max(0.0, latest_revenue * margin)

        scenarios = {
            "bear": self._compute_point(latest_ebitda, bear_mult, net_debt, shares_outstanding, private_company),
            "base": self._compute_point(latest_ebitda, base_mult, net_debt, shares_outstanding, private_company),
            "bull": self._compute_point(latest_ebitda, bull_mult, net_debt, shares_outstanding, private_company),
        }

        # Determine if live multiples were used
        hardcoded_band = None
        blob = (industry or "").lower()
        for key, band in self.DEFAULT_EV_EBITDA_BY_SECTOR.items():
            if key != "default" and key in blob:
                hardcoded_band = band
                break
        if hardcoded_band is None:
            hardcoded_band = self.DEFAULT_EV_EBITDA_BY_SECTOR["default"]
        multiples_source = (
            "worldmonitor_live"
            if (bear_mult, base_mult, bull_mult) != hardcoded_band
            else "hardcoded_sector_defaults"
        )

        return {
            "method": "ev_ebitda_comps",
            "industry": industry or "Unknown",
            "multiple_band": {"bear": bear_mult, "base": base_mult, "bull": bull_mult},
            "multiples_source": multiples_source,
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
