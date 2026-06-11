"""
Search API router — exposes SerpAPI-backed search to the frontend.

All endpoints degrade gracefully: if SerpAPI is not configured or the
monthly quota reserve is hit, they return ``available: false`` instead
of erroring.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["Search"])


def _serp():
    """Lazy import to avoid import-time side effects."""
    from tools.serp import serp_client
    return serp_client


@router.get("/health")
async def search_health():
    """Check whether SerpAPI is configured and report remaining quota."""
    client = _serp()
    quota = await client.get_quota()
    return {
        "enabled": client.enabled,
        "quota": quota.model_dump() if quota else None,
    }


@router.get("/news")
async def search_news(
    q: str = Query(..., min_length=2, max_length=200, description="News query"),
    limit: int = Query(default=8, ge=1, le=20),
):
    """Google News results for an arbitrary query."""
    items = await _serp().get_news(q, limit)
    return {"available": bool(items), "results": [i.model_dump() for i in items]}


@router.get("/adverse-media")
async def search_adverse_media(
    company: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
):
    """Due-diligence adverse-media sweep (litigation, probes, penalties)."""
    items = await _serp().get_adverse_media(company, limit)
    return {"available": bool(items), "results": [i.model_dump() for i in items]}


@router.get("/web")
async def search_web(
    q: str = Query(..., min_length=2, max_length=200, description="Search query"),
    num: int = Query(default=10, ge=1, le=20),
):
    """Organic Google results plus knowledge graph / answer box."""
    result = await _serp().search_web(q, num)
    if result is None:
        return {"available": False, "result": None}
    return {"available": True, "result": result.model_dump()}


@router.get("/finance/{ticker}")
async def search_finance(ticker: str):
    """Live quote + key stats via Google Finance (e.g. AAPL:NASDAQ, RELIANCE:NSE)."""
    quote = await _serp().get_finance_quote(ticker)
    if quote is None:
        return {"available": False, "quote": None}
    return {"available": True, "quote": quote.model_dump()}
