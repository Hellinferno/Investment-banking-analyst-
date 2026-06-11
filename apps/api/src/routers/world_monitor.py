"""
WorldMonitor API router — exposes macro/market/risk data to the frontend.

All endpoints degrade gracefully: if WorldMonitor is unreachable,
they return a structured error with ``available: false``.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/world-monitor", tags=["WorldMonitor"])


def _wm():
    """Lazy import to avoid import-time network calls."""
    from tools.world_monitor import wm_client
    return wm_client


# ── Health ───────────────────────────────────────────────────────────────

@router.get("/health")
async def wm_health():
    """Check if WorldMonitor sidecar is reachable."""
    client = _wm()
    connected = await client.health_check()
    return {"connected": connected, "enabled": client.enabled}


# ── Economic / FRED ──────────────────────────────────────────────────────

@router.get("/fred/{series_id}")
async def get_fred_series(
    series_id: str,
    limit: int = Query(default=120, ge=1, le=1000),
):
    """Fetch a single FRED time series."""
    series = await _wm().get_fred_series(series_id, limit)
    if series is None:
        return {"available": False, "series": None}
    return {"available": True, "series": series.model_dump()}


@router.get("/fred-batch")
async def get_fred_batch(
    series_ids: str = Query(
        default="DGS10,FEDFUNDS,VIXCLS",
        description="Comma-separated FRED series IDs",
    ),
):
    """Fetch multiple FRED series."""
    ids = [s.strip().upper() for s in series_ids.split(",") if s.strip()]
    results = await _wm().get_fred_batch(ids)
    return {
        "available": bool(results),
        "results": {k: v.model_dump() for k, v in results.items()},
    }


@router.get("/macro-signals")
async def get_macro_signals():
    """Get macro regime signals (bullish/bearish verdict)."""
    signals = await _wm().get_macro_signals()
    if signals is None:
        return {"available": False, "signals": None}
    return {"available": True, "signals": signals.model_dump()}


@router.get("/yield-curve")
async def get_yield_curve():
    """Get current yield curve snapshot."""
    curve = await _wm().get_yield_curve()
    if curve is None:
        return {"available": False, "curve": None}
    return {"available": True, "curve": curve.model_dump()}


@router.get("/credit-spreads")
async def get_credit_spreads():
    """Get HY/IG credit spreads and SOFR."""
    spreads = await _wm().get_credit_spreads()
    if spreads is None:
        return {"available": False, "spreads": None}
    return {"available": True, "spreads": spreads.model_dump()}


# ── Market Data ──────────────────────────────────────────────────────────

@router.get("/market-quotes")
async def get_market_quotes(
    symbols: str = Query(default="", description="Comma-separated symbols (empty = all)"),
):
    """Get stock/index market quotes."""
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else None
    quotes = await _wm().get_market_quotes(sym_list)
    return {
        "available": bool(quotes),
        "quotes": [q.model_dump() for q in quotes],
    }


@router.get("/sector-summary")
async def get_sector_summary():
    """Get sector performance summary."""
    summary = await _wm().get_sector_summary()
    if summary is None:
        return {"available": False, "sectors": []}
    return {"available": True, "sectors": summary.model_dump()}


@router.get("/fear-greed")
async def get_fear_greed():
    """Get CNN Fear & Greed Index."""
    fg = await _wm().get_fear_greed_index()
    if fg is None:
        return {"available": False, "data": None}
    return {"available": True, "data": fg.model_dump()}


@router.get("/commodities")
async def get_commodities():
    """Get commodity quotes."""
    quotes = await _wm().get_commodity_quotes()
    return {
        "available": bool(quotes),
        "quotes": [q.model_dump() for q in quotes],
    }


# ── Intelligence / Risk ──────────────────────────────────────────────────

@router.get("/risk-scores")
async def get_risk_scores():
    """Get Country Intelligence Index scores for all tracked countries."""
    scores = await _wm().get_risk_scores()
    if scores is None:
        return {"available": False, "cii_scores": [], "strategic_risks": []}
    return {"available": True, **scores.model_dump()}


@router.get("/risk-scores/{country_code}")
async def get_country_risk(country_code: str):
    """Get CII risk score for a single country."""
    score = await _wm().get_country_risk(country_code)
    if score is None:
        return {"available": False, "score": None}
    return {"available": True, "score": score.model_dump()}


@router.get("/market-implications")
async def get_market_implications():
    """Get LLM-generated market implication cards."""
    cards = await _wm().get_market_implications()
    return {
        "available": bool(cards),
        "cards": [c.model_dump() for c in cards],
    }


# ── Conflict ─────────────────────────────────────────────────────────────

@router.get("/conflict-events")
async def get_conflict_events(
    country: str = Query(default="", description="Country name filter"),
):
    """Get ACLED conflict events."""
    events = await _wm().get_conflict_events(country)
    return {
        "available": bool(events),
        "events": [e.model_dump() for e in events],
        "count": len(events),
    }


# ── Supply Chain ─────────────────────────────────────────────────────────

@router.get("/chokepoints")
async def get_chokepoints():
    """Get global maritime chokepoint disruption status."""
    chokepoints = await _wm().get_chokepoint_status()
    return {
        "available": bool(chokepoints),
        "chokepoints": [c.model_dump() for c in chokepoints],
    }
