"""
WorldMonitor API Client — sidecar integration for macro/market/risk data.

Provides real-time FRED economic data, market quotes, country risk scores,
conflict events, and supply chain chokepoint status to AIBAA agents/engines.

All methods degrade gracefully: if WorldMonitor is unavailable, they return
None so callers fall back to hardcoded defaults.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

from tools.world_monitor_models import (
    AcledEvent,
    ChokepointInfo,
    ChokepointStatusResponse,
    CIIScore,
    CommodityQuotesResponse,
    ConflictEventsResponse,
    CreditSpreadData,
    FearGreedResponse,
    FredBatchResponse,
    FredSeries,
    FredSeriesResponse,
    MacroSignalsResponse,
    MarketImplicationCard,
    MarketImplicationsResponse,
    MarketQuote,
    MarketQuotesResponse,
    RiskScoresResponse,
    SectorSummaryResponse,
    SituationDeduction,
    YieldCurvePoint,
    YieldCurveSnapshot,
)

logger = logging.getLogger(__name__)

# FRED series IDs used for WACC / macro inputs
FRED_RISK_FREE = "DGS10"         # 10-Year Treasury Constant Maturity
FRED_FED_FUNDS = "FEDFUNDS"      # Effective Federal Funds Rate
FRED_HY_SPREAD = "BAMLH0A0HYM2"  # ICE BofA US High Yield OAS
FRED_IG_SPREAD = "BAMLC0A0CM"    # ICE BofA US Corporate IG OAS
FRED_SOFR = "SOFR"               # Secured Overnight Financing Rate
FRED_YIELD_CURVE = ["DGS1MO", "DGS3MO", "DGS6MO", "DGS1", "DGS2", "DGS5", "DGS10", "DGS30"]
FRED_T10Y2Y = "T10Y2Y"          # 10-Year minus 2-Year Treasury spread
FRED_VIX = "VIXCLS"             # CBOE Volatility Index
FRED_CPI = "CPIAUCSL"           # Consumer Price Index


def _get_base_url() -> str:
    """Read WorldMonitor base URL from environment."""
    return os.environ.get("WORLDMONITOR_API_URL", "").rstrip("/")


class _TTLCache:
    """Simple in-memory TTL cache to avoid hammering the sidecar."""

    def __init__(self, default_ttl: int = 300):
        self._store: dict[str, tuple[float, int, Any]] = {}
        self._default_ttl = default_ttl

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, ttl, data = entry
        if time.monotonic() - ts > ttl:
            del self._store[key]
            return None
        return data

    def set(self, key: str, data: Any, ttl: int | None = None) -> None:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        self._store[key] = (time.monotonic(), effective_ttl, data)

    def clear(self) -> None:
        self._store.clear()


# Endpoints whose data changes slowly — use a 30-minute TTL instead of 5 minutes.
_SLOW_ENDPOINTS: frozenset[str] = frozenset({
    "/api/economic/v1/getFredSeries",
    "/api/economic/v1/getFredSeriesBatch",
    "/api/economic/v1/getYieldCurve",
    "/api/economic/v1/getCreditSpreads",
    "/api/economic/v1/getMacroSignals",
    "/api/intelligence/v1/getRiskScores",
    "/api/intelligence/v1/getMarketImplications",
})
_SLOW_TTL = 1800  # 30 minutes


class WorldMonitorClient:
    """
    Async HTTP client for querying the WorldMonitor sidecar API.

    All public methods return typed Pydantic models or None on failure.
    The client is lazy-initialized: no connections until first use.
    """

    def __init__(self, timeout: float = 10.0, cache_ttl: int = 300):
        self._timeout = timeout
        self._cache = _TTLCache(default_ttl=cache_ttl)
        self._client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return bool(_get_base_url())

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=_get_base_url(),
                timeout=self._timeout,
                headers={"Accept": "application/json"},
            )
        return self._client

    async def _get(self, path: str, params: dict | None = None) -> dict | None:
        """Perform a GET request, returning parsed JSON or None on failure."""
        if not self.enabled:
            return None

        cache_key = f"{path}:{params}" if params else path
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            client = self._get_client()
            resp = await client.get(path, params=params)
            resp.raise_for_status()
            data = resp.json()
            ttl = _SLOW_TTL if path in _SLOW_ENDPOINTS else None
            self._cache.set(cache_key, data, ttl=ttl)
            return data
        except Exception as exc:
            logger.debug("WorldMonitor request failed: %s %s — %s", path, params, exc)
            return None

    async def _post(self, path: str, body: dict) -> dict | None:
        """Perform a POST request, returning parsed JSON or None on failure."""
        if not self.enabled:
            return None

        try:
            client = self._get_client()
            resp = await client.post(path, json=body)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("WorldMonitor POST failed: %s — %s", path, exc)
            return None

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Economic / FRED ──────────────────────────────────────────────────

    async def get_fred_series(self, series_id: str, limit: int = 120) -> FredSeries | None:
        """Fetch a single FRED time series."""
        data = await self._get(
            "/api/economic/v1/getFredSeries",
            {"seriesId": series_id, "limit": limit},
        )
        if not data:
            return None
        try:
            resp = FredSeriesResponse.model_validate(data)
            return resp.series
        except Exception:
            return None

    async def get_fred_batch(self, series_ids: list[str]) -> dict[str, FredSeries]:
        """Fetch multiple FRED series in one call."""
        data = await self._get(
            "/api/economic/v1/getFredSeriesBatch",
            {"seriesIds": ",".join(series_ids)},
        )
        if not data:
            return {}
        try:
            resp = FredBatchResponse.model_validate(data)
            return resp.results
        except Exception:
            return {}

    async def get_risk_free_rate(self) -> float | None:
        """Get the latest 10-Year Treasury yield (DGS10) as a decimal."""
        series = await self.get_fred_series(FRED_RISK_FREE, limit=5)
        if series and series.observations:
            # FRED returns percentage (e.g. 4.25), convert to decimal (0.0425)
            latest = series.observations[-1].value
            return latest / 100.0 if latest > 1.0 else latest
        return None

    async def get_credit_spreads(self) -> CreditSpreadData | None:
        """Get HY/IG credit spreads and SOFR from FRED."""
        batch = await self.get_fred_batch([FRED_HY_SPREAD, FRED_IG_SPREAD, FRED_SOFR])
        if not batch:
            return None

        def _latest_decimal(series_id: str) -> float | None:
            s = batch.get(series_id)
            if s and s.observations:
                v = s.observations[-1].value
                return v / 100.0 if v > 1.0 else v
            return None

        hy = _latest_decimal(FRED_HY_SPREAD)
        ig = _latest_decimal(FRED_IG_SPREAD)
        sofr = _latest_decimal(FRED_SOFR)

        if hy is None and ig is None and sofr is None:
            return None

        as_of = ""
        for sid in [FRED_HY_SPREAD, FRED_IG_SPREAD, FRED_SOFR]:
            s = batch.get(sid)
            if s and s.observations:
                as_of = s.observations[-1].date
                break

        return CreditSpreadData(hy_spread=hy, ig_spread=ig, sofr=sofr, as_of=as_of)

    async def get_yield_curve(self) -> YieldCurveSnapshot | None:
        """Get yield curve points across maturities."""
        batch = await self.get_fred_batch(FRED_YIELD_CURVE)
        if not batch:
            return None

        maturity_labels = {
            "DGS1MO": "1MO", "DGS3MO": "3MO", "DGS6MO": "6MO",
            "DGS1": "1Y", "DGS2": "2Y", "DGS5": "5Y",
            "DGS10": "10Y", "DGS30": "30Y",
        }
        points: list[YieldCurvePoint] = []
        as_of = ""
        for sid in FRED_YIELD_CURVE:
            s = batch.get(sid)
            if s and s.observations:
                v = s.observations[-1].value
                rate = v / 100.0 if v > 1.0 else v
                points.append(YieldCurvePoint(maturity=maturity_labels.get(sid, sid), rate=rate))
                if not as_of:
                    as_of = s.observations[-1].date

        if not points:
            return None

        # Inversion check: 2Y > 10Y
        rates_by_mat = {p.maturity: p.rate for p in points}
        inverted = rates_by_mat.get("2Y", 0) > rates_by_mat.get("10Y", 0)
        return YieldCurveSnapshot(points=points, as_of=as_of, inverted=inverted)

    async def get_macro_signals(self) -> MacroSignalsResponse | None:
        """Get macro regime signals (bullish/bearish verdict)."""
        data = await self._get("/api/economic/v1/getMacroSignals")
        if not data:
            return None
        try:
            return MacroSignalsResponse.model_validate(data)
        except Exception:
            return None

    # ── Market Data ──────────────────────────────────────────────────────

    async def get_market_quotes(self, symbols: list[str] | None = None) -> list[MarketQuote]:
        """Get stock/index market quotes, optionally filtered by symbols."""
        params = {}
        if symbols:
            params["symbols"] = ",".join(symbols)
        data = await self._get("/api/market/v1/listMarketQuotes", params or None)
        if not data:
            return []
        try:
            resp = MarketQuotesResponse.model_validate(data)
            return resp.quotes
        except Exception:
            return []

    async def get_sector_summary(self) -> SectorSummaryResponse | None:
        """Get sector performance summary."""
        data = await self._get("/api/market/v1/getSectorSummary")
        if not data:
            return None
        try:
            return SectorSummaryResponse.model_validate(data)
        except Exception:
            return None

    async def get_fear_greed_index(self) -> FearGreedResponse | None:
        """Get CNN Fear & Greed Index value."""
        data = await self._get("/api/market/v1/getFearGreedIndex")
        if not data:
            return None
        try:
            return FearGreedResponse.model_validate(data)
        except Exception:
            return None

    async def get_commodity_quotes(self) -> list[CommodityQuote]:
        """Get commodity quotes (oil, gold, etc.)."""
        data = await self._get("/api/market/v1/listCommodityQuotes")
        if not data:
            return []
        try:
            resp = CommodityQuotesResponse.model_validate(data)
            return resp.quotes
        except Exception:
            return []

    # ── Intelligence / Risk ──────────────────────────────────────────────

    async def get_risk_scores(self) -> RiskScoresResponse | None:
        """Get Country Intelligence Index scores for all tracked countries."""
        data = await self._get("/api/intelligence/v1/getRiskScores")
        if not data:
            return None
        try:
            return RiskScoresResponse.model_validate(data)
        except Exception:
            return None

    async def get_country_risk(self, country_code: str) -> CIIScore | None:
        """Get CII risk score for a single country (ISO-2 code)."""
        scores = await self.get_risk_scores()
        if not scores:
            return None
        code_upper = country_code.upper()
        for score in scores.cii_scores:
            if score.region == code_upper:
                return score
        return None

    async def deduct_situation(self, query: str, geo_context: str = "") -> SituationDeduction | None:
        """Use WorldMonitor's LLM deduction engine to analyze a situation."""
        data = await self._post(
            "/api/intelligence/v1/deductSituation",
            {"query": query, "geoContext": geo_context},
        )
        if not data:
            return None
        try:
            return SituationDeduction.model_validate(data)
        except Exception:
            return None

    async def get_market_implications(self) -> list[MarketImplicationCard]:
        """Get LLM-generated market implication cards."""
        data = await self._get("/api/intelligence/v1/listMarketImplications")
        if not data:
            return []
        try:
            resp = MarketImplicationsResponse.model_validate(data)
            return resp.cards
        except Exception:
            return []

    # ── Conflict ─────────────────────────────────────────────────────────

    async def get_conflict_events(
        self, country: str = "", start: int = 0, end: int = 0
    ) -> list[AcledEvent]:
        """Get ACLED conflict events (battles, explosions, civilian violence)."""
        params: dict[str, Any] = {}
        if country:
            params["country"] = country
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        data = await self._get("/api/conflict/v1/listAcledEvents", params or None)
        if not data:
            return []
        try:
            resp = ConflictEventsResponse.model_validate(data)
            return resp.events
        except Exception:
            return []

    # ── Supply Chain ─────────────────────────────────────────────────────

    async def get_chokepoint_status(self) -> list[ChokepointInfo]:
        """Get global maritime chokepoint disruption status."""
        data = await self._get("/api/supply-chain/v1/getChokepointStatus")
        if not data:
            return []
        try:
            resp = ChokepointStatusResponse.model_validate(data)
            return resp.chokepoints
        except Exception:
            return []

    # ── Health ───────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Check if WorldMonitor sidecar is reachable."""
        if not self.enabled:
            return False
        try:
            client = self._get_client()
            resp = await client.get("/api/health")
            return resp.status_code == 200
        except Exception:
            return False

    # ── Sync wrappers (for use inside sync agent .run() methods) ─────────

    def _run_async(self, coro):
        """Run an async coroutine from synchronous agent code."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # We're inside an existing event loop (e.g. FastAPI).
            # Use a new thread to avoid blocking the loop.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=self._timeout + 2)
        else:
            return asyncio.run(coro)

    @staticmethod
    async def _noop():
        """No-op coroutine used as a placeholder in _run_async_gather when a
        conditional fetch is not needed (e.g. no country code provided)."""
        return None

    def _run_async_gather(self, *coros) -> tuple:
        """Run multiple coroutines in parallel and return their results as a tuple.

        Significantly reduces latency when agents need several independent
        WorldMonitor endpoints — all HTTP requests are issued concurrently.
        """
        async def _gather():
            return await asyncio.gather(*coros, return_exceptions=True)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _gather())
                results = future.result(timeout=self._timeout * len(coros) + 5)
        else:
            results = asyncio.run(_gather())

        # Replace exceptions with None so callers can handle gracefully
        return tuple(None if isinstance(r, Exception) else r for r in results)

    def get_risk_free_rate_sync(self) -> float | None:
        return self._run_async(self.get_risk_free_rate())

    def get_credit_spreads_sync(self) -> CreditSpreadData | None:
        return self._run_async(self.get_credit_spreads())

    def get_macro_signals_sync(self) -> MacroSignalsResponse | None:
        return self._run_async(self.get_macro_signals())

    def get_risk_scores_sync(self) -> RiskScoresResponse | None:
        return self._run_async(self.get_risk_scores())

    def get_country_risk_sync(self, country_code: str) -> CIIScore | None:
        return self._run_async(self.get_country_risk(country_code))

    def get_conflict_events_sync(self, country: str = "") -> list[AcledEvent]:
        return self._run_async(self.get_conflict_events(country))

    def get_chokepoint_status_sync(self) -> list[ChokepointInfo]:
        return self._run_async(self.get_chokepoint_status())

    def get_market_quotes_sync(self, symbols: list[str] | None = None) -> list[MarketQuote]:
        return self._run_async(self.get_market_quotes(symbols))

    def get_fear_greed_index_sync(self) -> FearGreedResponse | None:
        return self._run_async(self.get_fear_greed_index())

    def get_fred_batch_sync(self, series_ids: list[str]) -> dict[str, FredSeries]:
        return self._run_async(self.get_fred_batch(series_ids))

    def get_yield_curve_sync(self) -> YieldCurveSnapshot | None:
        return self._run_async(self.get_yield_curve())

    def get_market_implications_sync(self) -> list[MarketImplicationCard]:
        return self._run_async(self.get_market_implications())

    def deduct_situation_sync(self, query: str, geo_context: str = "") -> SituationDeduction | None:
        return self._run_async(self.deduct_situation(query, geo_context))

    def get_sector_summary_sync(self) -> SectorSummaryResponse | None:
        return self._run_async(self.get_sector_summary())

    def get_commodity_quotes_sync(self) -> list:
        return self._run_async(self.get_commodity_quotes())

    def health_check_sync(self) -> bool:
        return self._run_async(self.health_check())


# ── Global singleton ─────────────────────────────────────────────────────

wm_client = WorldMonitorClient()
