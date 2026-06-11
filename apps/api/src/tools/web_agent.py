"""
TinyFish Web Agent Client — live web scraping for AIBAA agents.

Given a URL and a natural-language goal, TinyFish navigates the page and
returns structured JSON.  Unlike WorldMonitor (instant, free, structured API),
TinyFish uses SSE streaming with 3-60 s latency and costs $0.014/step, so:

  * All calls are opt-in (gated on ``web_enrichment`` agent parameter).
  * Results are cached aggressively (30-min TTL keyed on URL+goal hash).
  * All methods degrade gracefully when ``TINYFISH_API_KEY`` is absent.

Follows the same singleton + async/sync-bridge pattern as WorldMonitorClient.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from typing import Any

import httpx

from tools.web_agent_models import SSEEvent, WebAgentResult
from tools.world_monitor import _TTLCache

logger = logging.getLogger(__name__)

TINYFISH_ENDPOINT = "https://agent.tinyfish.ai/v1/run"


def _get_api_key() -> str:
    return os.environ.get("TINYFISH_API_KEY", "")


def _cache_key(url: str, goal: str) -> str:
    raw = f"{url}|{goal}"
    return hashlib.sha256(raw.encode()).hexdigest()


class WebAgentClient:
    """
    Async HTTP client for querying the TinyFish Web Agent API.

    The client consumes an SSE event stream (POST), parses individual events,
    and returns a ``WebAgentResult`` with the structured ``resultJson``.
    """

    def __init__(self, timeout: float = 90.0, cache_ttl: int = 1800):
        self._timeout = timeout
        self._cache = _TTLCache(default_ttl=cache_ttl)

    @property
    def enabled(self) -> bool:
        return bool(_get_api_key())

    # ── Core fetch ────────────────────────────────────────────────────────

    async def fetch(
        self,
        url: str,
        goal: str,
        browser_profile: str = "lite",
    ) -> WebAgentResult:
        """
        Send a URL + goal to TinyFish and stream SSE until COMPLETE.

        Returns a ``WebAgentResult`` with parsed ``resultJson`` on success,
        or ``success=False`` with an error message on failure.
        """
        if not self.enabled:
            return WebAgentResult(success=False, error="TinyFish API key not configured")

        ck = _cache_key(url, goal)
        cached = self._cache.get(ck)
        if cached is not None:
            return cached

        payload = {"url": url, "goal": goal, "browserProfile": browser_profile}
        headers = {
            "Authorization": f"Bearer {_get_api_key()}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST", TINYFISH_ENDPOINT, json=payload, headers=headers,
                ) as resp:
                    resp.raise_for_status()
                    result = await self._consume_sse(resp, start)
                    if result.success:
                        self._cache.set(ck, result)
                    return result
        except httpx.TimeoutException:
            elapsed = time.monotonic() - start
            return WebAgentResult(
                success=False, error="TinyFish request timed out", elapsed_seconds=elapsed,
            )
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.debug("TinyFish request failed: %s", exc)
            return WebAgentResult(
                success=False, error=str(exc), elapsed_seconds=elapsed,
            )

    async def _consume_sse(
        self, resp: httpx.Response, start: float,
    ) -> WebAgentResult:
        """Parse the SSE stream line-by-line until a COMPLETE event."""
        run_id = ""
        async for line in resp.aiter_lines():
            if not line.startswith("data: "):
                continue
            try:
                raw = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            event = SSEEvent.model_validate(raw)
            if event.run_id:
                run_id = event.run_id

            if event.type == "COMPLETE":
                elapsed = time.monotonic() - start
                if event.status == "COMPLETED":
                    return WebAgentResult(
                        success=True,
                        data=event.result_json,
                        run_id=run_id,
                        elapsed_seconds=elapsed,
                    )
                else:
                    return WebAgentResult(
                        success=False,
                        error=event.error or "TinyFish run failed",
                        run_id=run_id,
                        elapsed_seconds=elapsed,
                    )

        elapsed = time.monotonic() - start
        return WebAgentResult(
            success=False,
            error="SSE stream ended without a COMPLETE event",
            run_id=run_id,
            elapsed_seconds=elapsed,
        )

    def fetch_sync(
        self, url: str, goal: str, browser_profile: str = "lite",
    ) -> WebAgentResult:
        """Synchronous wrapper for ``fetch()``."""
        return self._run_async(self.fetch(url, goal, browser_profile))

    # ── IB-specific goal templates ────────────────────────────────────────

    async def fetch_company_financials(
        self, company: str, site: str = "https://finance.yahoo.com",
    ) -> WebAgentResult:
        """Extract key financial metrics for a public company."""
        url = f"{site}/quote/{company}/financials" if "yahoo" in site else site
        goal = (
            f"Extract the latest annual revenue, EBITDA, net income, total debt, "
            f"and EV/EBITDA multiple for {company}. Return as JSON with keys: "
            f"revenue, ebitda, net_income, total_debt, ev_ebitda, currency, fiscal_year."
        )
        return await self.fetch(url, goal)

    async def fetch_recent_ma_activity(self, company_or_sector: str) -> WebAgentResult:
        """Find recent M&A transactions in a sector or involving a company."""
        url = "https://www.reuters.com/business/deals/"
        goal = (
            f"Find the 5 most recent M&A deals related to '{company_or_sector}'. "
            f"For each deal extract: acquirer, target, deal_value_usd, date_announced, "
            f"deal_type (merger/acquisition/divestiture), and status. "
            f"Return as a JSON array of objects."
        )
        return await self.fetch(url, goal)

    async def fetch_competitor_landscape(
        self, company: str, industry: str,
    ) -> WebAgentResult:
        """Extract top competitors and their market positioning."""
        url = f"https://finance.yahoo.com/quote/{company}/competitors"
        goal = (
            f"Extract the top competitors of {company} in the {industry} industry. "
            f"For each competitor provide: name, market_cap, revenue, pe_ratio, "
            f"ev_ebitda. Return as a JSON array of objects."
        )
        return await self.fetch(url, goal)

    async def fetch_regulatory_filings(self, company: str) -> WebAgentResult:
        """Find recent regulatory filings, lawsuits, or enforcement actions."""
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?company={company}&CIK=&type=&dateb=&owner=include&count=10&search_text=&action=getcompany"
        goal = (
            f"Find the 5 most recent SEC filings or regulatory actions for {company}. "
            f"For each extract: filing_type, date, title, and a one-sentence summary. "
            f"Return as a JSON array of objects."
        )
        return await self.fetch(url, goal)

    async def fetch_sector_multiples(self, industry: str) -> WebAgentResult:
        """Extract current valuation multiples for an industry sector."""
        url = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/vebitda.html"
        goal = (
            f"Extract the current EV/EBITDA, EV/Revenue, and P/E valuation multiples "
            f"for the '{industry}' sector or the closest matching sector. "
            f"Return as JSON with keys: industry_name, ev_ebitda, ev_revenue, pe_ratio, "
            f"number_of_firms, and source_date."
        )
        return await self.fetch(url, goal)

    # ── Sync wrappers for IB templates ────────────────────────────────────

    def fetch_company_financials_sync(
        self, company: str, site: str = "https://finance.yahoo.com",
    ) -> WebAgentResult:
        return self._run_async(self.fetch_company_financials(company, site))

    def fetch_recent_ma_activity_sync(self, company_or_sector: str) -> WebAgentResult:
        return self._run_async(self.fetch_recent_ma_activity(company_or_sector))

    def fetch_competitor_landscape_sync(
        self, company: str, industry: str,
    ) -> WebAgentResult:
        return self._run_async(self.fetch_competitor_landscape(company, industry))

    def fetch_regulatory_filings_sync(self, company: str) -> WebAgentResult:
        return self._run_async(self.fetch_regulatory_filings(company))

    def fetch_sector_multiples_sync(self, industry: str) -> WebAgentResult:
        return self._run_async(self.fetch_sector_multiples(industry))

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

web_agent = WebAgentClient()
