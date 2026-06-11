"""
MarketDataClient — live peer multiples for comps analysis.

Fetches market cap, debt, cash, EBITDA, and revenue per ticker (Yahoo Finance
via yfinance — supports NSE tickers like RELIANCE.NS) and computes real
EV/EBITDA, EV/Revenue, and P/E multiples.

Security / reliability posture:
  - No API key required; nothing secret is ever sent upstream (tickers only).
  - Every fetch is fault-isolated: a failing ticker is skipped, a failing
    library import disables the client, and callers always receive a dict
    (possibly empty) — agents degrade to LLM-estimated multiples.
  - Responses are cached in-process with a TTL so repeated agent runs do not
    hammer the upstream source.
"""
from __future__ import annotations

import logging
import os
import time
from statistics import median
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = int(os.environ.get("MARKET_DATA_CACHE_TTL_SECONDS", "900"))
_FETCH_TIMEOUT_SECONDS = int(os.environ.get("MARKET_DATA_FETCH_TIMEOUT_SECONDS", "10"))
_MULTIPLE_SANITY_RANGE = (1.0, 100.0)  # discard EV/EBITDA outside this band

# Dedicated small pool to enforce a hard timeout on each yfinance call.
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout

_FETCH_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mktdata")


def _fetch_info_with_timeout(ticker: str, timeout: int) -> dict[str, Any] | None:
    """Fetch yfinance .info under a hard wall-clock timeout. Returns None on
    timeout or any error so the caller keeps its analyst estimate."""
    def _do() -> dict[str, Any]:
        import yfinance as yf
        return yf.Ticker(ticker).info or {}

    future = _FETCH_POOL.submit(_do)
    try:
        return future.result(timeout=timeout)
    except _FutureTimeout:
        logger.debug("Market data fetch timed out for %s after %ss", ticker, timeout)
        future.cancel()
        return None
    except Exception as exc:
        logger.debug("Market data fetch failed for %s: %s", ticker, exc)
        return None


class MarketDataClient:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        # This client is a module singleton shared across agent threads;
        # guard the cache against concurrent check-then-delete races.
        self._cache_lock = Lock()
        try:
            import yfinance  # noqa: F401
            self.enabled = True
        except ImportError:
            logger.warning("yfinance not installed — live market data disabled.")
            self.enabled = False

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------

    def _cache_get(self, ticker: str) -> dict[str, Any] | None:
        with self._cache_lock:
            entry = self._cache.get(ticker)
            if entry is None:
                return None
            ts, data = entry
            if time.monotonic() - ts > _CACHE_TTL_SECONDS:
                self._cache.pop(ticker, None)
                return None
            return data

    def _fetch_one(self, ticker: str) -> dict[str, Any] | None:
        """Fetch fundamentals for one ticker. Returns None on any failure."""
        cached = self._cache_get(ticker)
        if cached is not None:
            return cached

        # Bound the HTTP call so one unresponsive ticker can't hang the comps
        # worker thread indefinitely (yfinance/requests default is no timeout).
        # The fetch runs in a short-lived worker with a hard wall-clock cap.
        info = _fetch_info_with_timeout(ticker, _FETCH_TIMEOUT_SECONDS)
        if not info:
            return None

        market_cap = info.get("marketCap")
        if not market_cap:
            return None

        total_debt = info.get("totalDebt") or 0
        total_cash = info.get("totalCash") or 0
        ebitda = info.get("ebitda")
        revenue = info.get("totalRevenue")
        pe = info.get("trailingPE")

        enterprise_value = float(market_cap) + float(total_debt) - float(total_cash)

        ev_ebitda = None
        if ebitda and ebitda > 0:
            candidate = enterprise_value / float(ebitda)
            if _MULTIPLE_SANITY_RANGE[0] < candidate < _MULTIPLE_SANITY_RANGE[1]:
                ev_ebitda = round(candidate, 1)

        ev_revenue = None
        if revenue and revenue > 0:
            candidate = enterprise_value / float(revenue)
            if 0.05 < candidate < 50.0:
                ev_revenue = round(candidate, 2)

        data = {
            "ticker": ticker,
            "market_cap": float(market_cap),
            "enterprise_value": round(enterprise_value, 0),
            "ev_ebitda": ev_ebitda,
            "ev_revenue": ev_revenue,
            "pe": round(float(pe), 1) if pe and 0 < pe < 500 else None,
            "currency": info.get("currency"),
            "name": info.get("shortName") or info.get("longName"),
        }
        with self._cache_lock:
            self._cache[ticker] = (time.monotonic(), data)
        return data

    def get_peer_multiples(self, tickers: list[str]) -> dict[str, dict[str, Any]]:
        """Return {ticker: multiples} for every ticker that resolves live.

        Unresolvable tickers are silently omitted; callers treat missing
        entries as "keep the analyst estimate".
        """
        if not self.enabled:
            return {}

        results: dict[str, dict[str, Any]] = {}
        for raw in tickers:
            ticker = (raw or "").strip().upper()
            if not ticker or ticker in ("PRIVATE", "N/A", "NA", "-"):
                continue
            data = self._fetch_one(ticker)
            if data:
                results[ticker] = data
        return results

    # ------------------------------------------------------------------
    # Band derivation
    # ------------------------------------------------------------------

    @staticmethod
    def band_from_peers(
        peer_multiples: dict[str, dict[str, Any]],
        metric: str = "ev_ebitda",
        min_peers: int = 4,
    ) -> dict[str, float] | None:
        """Derive a bear/base/bull band from the live peer distribution.

        bear = 25th percentile, base = median, bull = 75th percentile.
        Returns None when fewer than ``min_peers`` peers have the metric —
        a tiny sample would produce a misleadingly tight band.
        """
        values = sorted(
            v[metric] for v in peer_multiples.values()
            if isinstance(v.get(metric), (int, float))
        )
        if len(values) < min_peers:
            return None

        def percentile(sorted_vals: list[float], pct: float) -> float:
            k = (len(sorted_vals) - 1) * pct
            lower = int(k)
            upper = min(lower + 1, len(sorted_vals) - 1)
            frac = k - lower
            return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac

        return {
            "bear": round(percentile(values, 0.25), 1),
            "base": round(median(values), 1),
            "bull": round(percentile(values, 0.75), 1),
            "sample_size": len(values),
        }


market_data_client = MarketDataClient()
