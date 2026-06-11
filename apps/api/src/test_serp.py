"""Unit tests for the SerpAPI client (tools/serp.py) — no live HTTP."""
from __future__ import annotations

import pytest

import tools.serp as serp_mod
from tools.serp import SerpClient
from tools.serp_models import SerpFinanceQuote, SerpNewsItem, SerpQuota


# ── Fixtures ─────────────────────────────────────────────────────────────

NEWS_RAW = {
    "position": 1,
    "title": "Acquirer buys Target Co",
    "source": {"name": "Reuters", "icon": "https://..."},
    "link": "https://example.com/article",
    "date": "02/11/2026, 08:00 AM, +0000 UTC",
    "iso_date": "2026-02-11T08:00:00Z",
}

FINANCE_RAW = {
    "summary": {
        "title": "Apple Inc",
        "stock": "AAPL",
        "exchange": "NASDAQ",
        "price": "USD291.58",
        "extracted_price": 291.58,
        "currency": "USD",
        "price_movement": {"percentage": 0.354, "value": 1.03, "movement": "Down"},
    },
    "knowledge_graph": {
        "key_stats": {
            "stats": [
                {"label": "Mkt. cap", "value": "4.28T"},
                {"label": "P/E ratio", "value": "35.27"},
            ]
        }
    },
}


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient; serves canned payloads per endpoint."""

    calls: list[dict] = []
    payload: dict = {}
    account_payload: dict = {"plan_name": "Free Plan", "total_searches_left": 250}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url: str, params: dict | None = None):
        _FakeAsyncClient.calls.append({"url": url, "params": params or {}})
        if "account" in url:
            return _FakeResponse(_FakeAsyncClient.account_payload)
        return _FakeResponse(_FakeAsyncClient.payload)


@pytest.fixture
def fake_http(monkeypatch):
    monkeypatch.setattr(serp_mod.httpx, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setenv("SERPAPI_API_KEY", "test-key")
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.payload = {}
    _FakeAsyncClient.account_payload = {
        "plan_name": "Free Plan",
        "searches_per_month": 250,
        "total_searches_left": 250,
        "this_month_usage": 0,
    }
    yield _FakeAsyncClient


# ── Model parsing ────────────────────────────────────────────────────────

def test_news_item_parses_source_and_iso_date():
    item = SerpNewsItem.from_raw(NEWS_RAW)
    assert item.title == "Acquirer buys Target Co"
    assert item.source == "Reuters"
    assert item.date == "2026-02-11T08:00:00Z"


def test_finance_quote_parses_summary_and_stats():
    quote = SerpFinanceQuote.from_raw(FINANCE_RAW)
    assert quote.ticker == "AAPL"
    assert quote.price == 291.58
    assert quote.key_stats["Mkt. cap"] == "4.28T"
    # "Down" movement is normalized to a negative percentage
    assert quote.change_pct == -0.35


def test_quota_parses_account_payload():
    quota = SerpQuota.from_raw({"plan_name": "Free Plan", "total_searches_left": 42})
    assert quota.total_searches_left == 42


# ── Client gating & degradation ──────────────────────────────────────────

def test_disabled_without_key(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    client = SerpClient()
    assert not client.enabled
    assert client.get_news_sync("anything") == []
    assert client.search_web_sync("anything") is None
    assert client.get_finance_quote_sync("AAPL") is None
    assert client.get_quota_sync() is None


def test_news_search_returns_items(fake_http):
    fake_http.payload = {"news_results": [NEWS_RAW, NEWS_RAW]}
    client = SerpClient()
    items = client.get_news_sync("acme acquisition", limit=1)
    assert len(items) == 1
    assert items[0].source == "Reuters"


def test_search_results_are_cached(fake_http):
    fake_http.payload = {"news_results": [NEWS_RAW]}
    client = SerpClient()
    client.get_news_sync("acme")
    search_calls = [c for c in fake_http.calls if "account" not in c["url"]]
    assert len(search_calls) == 1

    client.get_news_sync("acme")  # identical query — served from cache
    search_calls = [c for c in fake_http.calls if "account" not in c["url"]]
    assert len(search_calls) == 1


def test_quota_reserve_blocks_search(fake_http, monkeypatch):
    monkeypatch.setenv("SERPAPI_QUOTA_RESERVE", "20")
    fake_http.account_payload["total_searches_left"] = 15  # below reserve
    fake_http.payload = {"news_results": [NEWS_RAW]}
    client = SerpClient()
    assert client.get_news_sync("acme") == []
    search_calls = [c for c in fake_http.calls if "account" not in c["url"]]
    assert search_calls == []


def test_api_error_payload_returns_none(fake_http):
    fake_http.payload = {"error": "Google hasn't returned any results"}
    client = SerpClient()
    assert client.get_news_sync("acme") == []
    assert client.search_web_sync("acme") is None


def test_finance_quote_requires_summary(fake_http):
    fake_http.payload = {"knowledge_graph": {}}
    client = SerpClient()
    assert client.get_finance_quote_sync("ZZZZ") is None

    fake_http.payload = FINANCE_RAW
    client2 = SerpClient()
    quote = client2.get_finance_quote_sync("AAPL:NASDAQ")
    assert quote is not None and quote.name == "Apple Inc"


# ── Prompt formatting ────────────────────────────────────────────────────

def test_format_news_block():
    items = [SerpNewsItem.from_raw(NEWS_RAW)]
    block = SerpClient.format_news_block("Recent News (Acme)", items)
    assert block.startswith("Recent News (Acme):")
    assert "[Reuters] 2026-02-11" in block
    assert SerpClient.format_news_block("Empty", []) == ""
