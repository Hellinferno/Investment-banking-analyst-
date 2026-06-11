"""
SerpAPI Client — structured Google search results for AIBAA agents.

Provides news sweeps (google_news), live quotes and key stats
(google_finance), and organic web search with knowledge-graph cards (google)
without the fragility of page scraping.  Unlike TinyFish (paid per step),
SerpAPI's free tier allows 250 searches/month, so the client is enabled by
default whenever ``SERPAPI_API_KEY`` is set — but it protects the quota:

  * Every search is cached aggressively (configurable TTL, default 6 h for
    news/web, 15 min for finance quotes).
  * Before each uncached search the client checks the account's remaining
    quota (a free endpoint, cached 10 min) and refuses to spend below the
    ``SERPAPI_QUOTA_RESERVE`` floor.
  * All methods degrade gracefully — failures return ``[]``/``None`` and the
    agents fall back to document-only analysis.

Follows the same singleton + async/sync-bridge pattern as WorldMonitorClient.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

import httpx

from tools.serp_models import (
    SerpFinanceQuote,
    SerpNewsItem,
    SerpOrganicResult,
    SerpQuota,
    SerpWebSearch,
)
from tools.world_monitor import _TTLCache

logger = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
SERPAPI_ACCOUNT_ENDPOINT = "https://serpapi.com/account.json"

_QUOTA_CACHE_TTL = 600          # account snapshot freshness (free endpoint)
_FINANCE_TTL = 900              # quotes move intraday
_DEFAULT_TTL = int(os.environ.get("SERPAPI_CACHE_TTL_SECONDS", "21600"))  # 6 h


def _get_api_key() -> str:
    return os.environ.get("SERPAPI_API_KEY", "")


def _quota_reserve() -> int:
    """Searches to keep unspent as a safety floor (free plan = 250/month)."""
    try:
        return int(os.environ.get("SERPAPI_QUOTA_RESERVE", "20"))
    except ValueError:
        return 20


class SerpClient:
    """Async HTTP client for SerpAPI with caching and quota protection."""

    def __init__(self, timeout: float = 20.0):
        self._timeout = timeout
        self._cache = _TTLCache(default_ttl=_DEFAULT_TTL)
        # Local spend counter — belt-and-braces alongside the account check,
        # which can lag a few seconds behind actual usage.
        self._session_spend = 0

    @property
    def enabled(self) -> bool:
        return bool(_get_api_key())

    # ── Quota guard ───────────────────────────────────────────────────────

    async def get_quota(self) -> SerpQuota | None:
        """Fetch account usage. Free endpoint — does not consume a search."""
        if not self.enabled:
            return None
        cached = self._cache.get("__quota__")
        if cached is not None:
            return cached
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    SERPAPI_ACCOUNT_ENDPOINT, params={"api_key": _get_api_key()},
                )
                resp.raise_for_status()
                quota = SerpQuota.from_raw(resp.json())
                self._cache.set("__quota__", quota, ttl=_QUOTA_CACHE_TTL)
                return quota
        except Exception as exc:
            logger.debug("SerpAPI quota check failed: %s", exc)
            return None

    async def _quota_allows_search(self) -> bool:
        quota = await self.get_quota()
        if quota is None:
            # Account endpoint unreachable — allow the search; the search call
            # itself will fail loudly if the key is dead or quota exhausted.
            return True
        remaining = quota.total_searches_left - self._session_spend
        if remaining <= _quota_reserve():
            logger.warning(
                "SerpAPI quota guard: %s searches left (reserve=%s) — skipping search.",
                remaining, _quota_reserve(),
            )
            return False
        return True

    # ── Core search ───────────────────────────────────────────────────────

    async def _search(
        self, params: dict[str, Any], ttl: int | None = None,
    ) -> dict | None:
        """Run one SerpAPI search. Returns the raw JSON dict or None."""
        if not self.enabled:
            return None

        cache_key = "|".join(f"{k}={params[k]}" for k in sorted(params))
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        if not await self._quota_allows_search():
            return None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    SERPAPI_ENDPOINT,
                    params={**params, "api_key": _get_api_key()},
                )
                resp.raise_for_status()
                data = resp.json()
            if data.get("error"):
                logger.debug("SerpAPI returned error: %s", data["error"])
                return None
            self._session_spend += 1
            self._cache.set(cache_key, data, ttl=ttl)
            return data
        except Exception as exc:
            logger.debug("SerpAPI request failed (%s): %s", params.get("engine"), exc)
            return None

    # ── News (google_news) ────────────────────────────────────────────────

    async def get_news(self, query: str, limit: int = 8) -> list[SerpNewsItem]:
        """Top news results for an arbitrary query."""
        data = await self._search({"engine": "google_news", "q": query})
        if not data:
            return []
        items = [
            SerpNewsItem.from_raw(r)
            for r in data.get("news_results", [])
            if isinstance(r, dict)
        ]
        return items[:limit]

    async def get_company_news(self, company: str, limit: int = 8) -> list[SerpNewsItem]:
        """Recent headline coverage of a company."""
        return await self.get_news(f'"{company}"', limit)

    async def get_ma_news(self, company_or_sector: str, limit: int = 8) -> list[SerpNewsItem]:
        """Recent M&A activity in a sector or involving a company."""
        return await self.get_news(
            f"{company_or_sector} acquisition OR merger OR takeover deal", limit,
        )

    async def get_adverse_media(self, company: str, limit: int = 8) -> list[SerpNewsItem]:
        """Adverse-media sweep for due diligence: litigation, probes, fraud."""
        return await self.get_news(
            f'"{company}" lawsuit OR investigation OR fraud OR regulatory OR penalty OR recall',
            limit,
        )

    # ── Web search (google) ───────────────────────────────────────────────

    async def search_web(self, query: str, num: int = 10) -> SerpWebSearch | None:
        """Organic Google results plus knowledge graph / answer box."""
        data = await self._search({"engine": "google", "q": query, "num": num})
        if not data:
            return None
        return SerpWebSearch(
            query=query,
            organic=[
                SerpOrganicResult.from_raw(r)
                for r in data.get("organic_results", [])
                if isinstance(r, dict)
            ],
            knowledge_graph=data.get("knowledge_graph") or {},
            answer_box=data.get("answer_box") or {},
            related_questions=data.get("related_questions") or [],
        )

    async def find_competitors(self, company: str, industry: str) -> SerpWebSearch | None:
        """Competitor discovery via organic search."""
        return await self.search_web(
            f"top competitors of {company} in {industry} industry market share",
        )

    # ── Finance (google_finance) ──────────────────────────────────────────

    async def get_finance_quote(self, ticker: str) -> SerpFinanceQuote | None:
        """Live quote + key stats (Mkt cap, P/E, EPS, 52-wk range, Beta).

        ``ticker`` accepts Google Finance format ("AAPL:NASDAQ", "RELIANCE:NSE")
        or a bare symbol, which Google resolves to the primary listing.
        """
        data = await self._search(
            {"engine": "google_finance", "q": ticker}, ttl=_FINANCE_TTL,
        )
        if not data or not data.get("summary"):
            return None
        return SerpFinanceQuote.from_raw(data)

    # ── Context-block formatters (for LLM prompt enrichment) ─────────────

    @staticmethod
    def format_news_block(title: str, items: list[SerpNewsItem]) -> str:
        """Render news items as a compact text block for prompt context."""
        if not items:
            return ""
        lines = [
            f"  - [{i.source}] {i.date[:10]}: {i.title}"
            for i in items
        ]
        return f"{title}:\n" + "\n".join(lines)

    # ── Sync wrappers ─────────────────────────────────────────────────────

    def get_news_sync(self, query: str, limit: int = 8) -> list[SerpNewsItem]:
        return self._run_async(self.get_news(query, limit))

    def get_company_news_sync(self, company: str, limit: int = 8) -> list[SerpNewsItem]:
        return self._run_async(self.get_company_news(company, limit))

    def get_ma_news_sync(self, company_or_sector: str, limit: int = 8) -> list[SerpNewsItem]:
        return self._run_async(self.get_ma_news(company_or_sector, limit))

    def get_adverse_media_sync(self, company: str, limit: int = 8) -> list[SerpNewsItem]:
        return self._run_async(self.get_adverse_media(company, limit))

    def search_web_sync(self, query: str, num: int = 10) -> SerpWebSearch | None:
        return self._run_async(self.search_web(query, num))

    def find_competitors_sync(self, company: str, industry: str) -> SerpWebSearch | None:
        return self._run_async(self.find_competitors(company, industry))

    def get_finance_quote_sync(self, ticker: str) -> SerpFinanceQuote | None:
        return self._run_async(self.get_finance_quote(ticker))

    def get_quota_sync(self) -> SerpQuota | None:
        return self._run_async(self.get_quota())

    # ── Async/sync bridge ─────────────────────────────────────────────────

    def _run_async(self, coro: Any) -> Any:
        """Run an async coroutine from synchronous agent code."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result(timeout=self._timeout + 5)
        else:
            return asyncio.run(coro)


# ── Global singleton ─────────────────────────────────────────────────────

serp_client = SerpClient()
