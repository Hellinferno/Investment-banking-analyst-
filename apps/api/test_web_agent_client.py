"""
Unit tests for the TinyFish Web Agent client (apps/api/src/tools/web_agent.py).

All tests mock HTTP calls — no real TinyFish API requests are made.
Run with:  cd apps/api && python -m pytest test_web_agent_client.py -v
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from tools.web_agent import WebAgentClient, _cache_key
from tools.web_agent_models import SSEEvent, WebAgentRequest, WebAgentResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse_lines(*events: dict) -> list[str]:
    """Build a list of SSE data lines from dicts."""
    lines = []
    for ev in events:
        lines.append(f"data: {json.dumps(ev)}")
    return lines


class FakeStreamResponse:
    """Mimics the httpx async streaming response with aiter_lines()."""

    def __init__(self, lines: list[str]):
        self._lines = lines
        self.status_code = 200

    def raise_for_status(self):
        pass

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line


class _AsyncCtx:
    """Generic async context manager that yields a fixed value."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


def _mock_async_client(fake_resp: FakeStreamResponse):
    """
    Build a patched httpx.AsyncClient constructor that, when used as
    ``async with httpx.AsyncClient(...) as client``, yields an object
    whose ``.stream(...)`` returns another async context manager yielding
    ``fake_resp``.
    """
    inner_client = MagicMock()
    inner_client.stream = MagicMock(return_value=_AsyncCtx(fake_resp))

    def constructor(*args, **kwargs):
        return _AsyncCtx(inner_client)

    return constructor, inner_client


def _mock_async_client_error(exc: Exception):
    """Build a patched httpx.AsyncClient whose .stream() raises ``exc``."""
    inner_client = MagicMock()
    inner_client.stream = MagicMock(side_effect=exc)

    def constructor(*args, **kwargs):
        return _AsyncCtx(inner_client)

    return constructor, inner_client


# ── TTL Cache Tests ───────────────────────────────────────────────────────────

class TestCacheKey:
    def test_deterministic(self):
        k1 = _cache_key("https://example.com", "extract data")
        k2 = _cache_key("https://example.com", "extract data")
        assert k1 == k2

    def test_different_goals_differ(self):
        k1 = _cache_key("https://example.com", "goal A")
        k2 = _cache_key("https://example.com", "goal B")
        assert k1 != k2

    def test_different_urls_differ(self):
        k1 = _cache_key("https://a.com", "goal")
        k2 = _cache_key("https://b.com", "goal")
        assert k1 != k2


# ── Disabled Client (no API key) ─────────────────────────────────────────────

class TestDisabledClient:
    """When TINYFISH_API_KEY is unset, all methods return graceful failures."""

    @pytest.fixture(autouse=True)
    def _no_key(self, monkeypatch):
        monkeypatch.delenv("TINYFISH_API_KEY", raising=False)

    def test_enabled_is_false(self):
        client = WebAgentClient()
        assert client.enabled is False

    def test_fetch_sync_returns_failure(self):
        client = WebAgentClient()
        result = client.fetch_sync("https://example.com", "extract data")
        assert result.success is False
        assert "not configured" in (result.error or "")

    def test_fetch_company_financials_sync_returns_failure(self):
        client = WebAgentClient()
        result = client.fetch_company_financials_sync("AAPL")
        assert result.success is False

    def test_fetch_recent_ma_activity_sync_returns_failure(self):
        client = WebAgentClient()
        result = client.fetch_recent_ma_activity_sync("technology")
        assert result.success is False

    def test_fetch_sector_multiples_sync_returns_failure(self):
        client = WebAgentClient()
        result = client.fetch_sector_multiples_sync("healthcare")
        assert result.success is False


# ── Enabled Client (with API key + mocked HTTP) ──────────────────────────────

class TestEnabledClient:
    """Tests with TINYFISH_API_KEY set and HTTP mocked."""

    @pytest.fixture(autouse=True)
    def _set_key(self, monkeypatch):
        monkeypatch.setenv("TINYFISH_API_KEY", "test-key-12345")

    def test_enabled_is_true(self):
        client = WebAgentClient()
        assert client.enabled is True

    # ── SSE Parsing ───────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_successful_sse_stream(self):
        """Full SSE lifecycle: STARTED -> PROGRESS -> COMPLETE."""
        lines = _sse_lines(
            {"type": "STARTED", "runId": "run_abc"},
            {"type": "PROGRESS", "runId": "run_abc", "purpose": "Navigating to page"},
            {"type": "PROGRESS", "runId": "run_abc", "purpose": "Extracting data"},
            {
                "type": "COMPLETE",
                "runId": "run_abc",
                "status": "COMPLETED",
                "resultJson": {"revenue": 394328, "currency": "USD"},
            },
        )
        fake_resp = FakeStreamResponse(lines)
        constructor, _ = _mock_async_client(fake_resp)
        client = WebAgentClient()

        with patch("tools.web_agent.httpx.AsyncClient", side_effect=constructor):
            result = await client.fetch("https://finance.yahoo.com", "Extract revenue")

        assert result.success is True
        assert result.data == {"revenue": 394328, "currency": "USD"}
        assert result.run_id == "run_abc"
        assert result.elapsed_seconds >= 0

    @pytest.mark.asyncio
    async def test_failed_sse_stream(self):
        """COMPLETE event with FAILED status."""
        lines = _sse_lines(
            {"type": "STARTED", "runId": "run_fail"},
            {
                "type": "COMPLETE",
                "runId": "run_fail",
                "status": "FAILED",
                "error": "Page not found",
            },
        )
        fake_resp = FakeStreamResponse(lines)
        constructor, _ = _mock_async_client(fake_resp)
        client = WebAgentClient()

        with patch("tools.web_agent.httpx.AsyncClient", side_effect=constructor):
            result = await client.fetch("https://broken.com", "Extract data")

        assert result.success is False
        assert "Page not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_empty_sse_stream(self):
        """Stream ends without a COMPLETE event."""
        fake_resp = FakeStreamResponse([
            "data: " + json.dumps({"type": "STARTED", "runId": "run_empty"}),
            ": heartbeat",
        ])
        constructor, _ = _mock_async_client(fake_resp)
        client = WebAgentClient()

        with patch("tools.web_agent.httpx.AsyncClient", side_effect=constructor):
            result = await client.fetch("https://example.com", "goal")

        assert result.success is False
        assert "without a COMPLETE" in (result.error or "")

    @pytest.mark.asyncio
    async def test_malformed_json_lines_skipped(self):
        """Lines with invalid JSON are skipped, valid COMPLETE still works."""
        lines = [
            "data: {invalid json",
            "data: " + json.dumps({
                "type": "COMPLETE", "runId": "run_ok",
                "status": "COMPLETED", "resultJson": {"ok": True},
            }),
        ]
        fake_resp = FakeStreamResponse(lines)
        constructor, _ = _mock_async_client(fake_resp)
        client = WebAgentClient()

        with patch("tools.web_agent.httpx.AsyncClient", side_effect=constructor):
            result = await client.fetch("https://example.com", "goal")

        assert result.success is True
        assert result.data == {"ok": True}

    # ── Caching ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cache_deduplication(self):
        """Second call with same URL+goal returns cached result without HTTP."""
        lines = _sse_lines(
            {"type": "COMPLETE", "runId": "run_c", "status": "COMPLETED",
             "resultJson": {"cached": True}},
        )
        fake_resp = FakeStreamResponse(lines)
        constructor, inner = _mock_async_client(fake_resp)
        client = WebAgentClient()

        with patch("tools.web_agent.httpx.AsyncClient", side_effect=constructor):
            r1 = await client.fetch("https://x.com", "cache me")
            r2 = await client.fetch("https://x.com", "cache me")

        assert r1.success is True
        assert r2.success is True
        assert r2.data == {"cached": True}
        # stream() should only be called once (second call hits cache)
        assert inner.stream.call_count == 1

    # ── Timeout Handling ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_timeout_returns_failure(self):
        """httpx.TimeoutException is caught and returns graceful failure."""
        import httpx as httpx_mod

        constructor, _ = _mock_async_client_error(httpx_mod.TimeoutException("timed out"))
        client = WebAgentClient(timeout=5.0)

        with patch("tools.web_agent.httpx.AsyncClient", side_effect=constructor):
            result = await client.fetch("https://slow.com", "goal")

        assert result.success is False
        assert "timed out" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_connection_error_returns_failure(self):
        """Generic connection error is caught gracefully."""
        constructor, _ = _mock_async_client_error(ConnectionError("refused"))
        client = WebAgentClient()

        with patch("tools.web_agent.httpx.AsyncClient", side_effect=constructor):
            result = await client.fetch("https://down.com", "goal")

        assert result.success is False
        assert "refused" in (result.error or "")

    # ── Goal Templates ────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_fetch_company_financials_builds_correct_url(self):
        """Verify the Yahoo Finance URL construction."""
        client = WebAgentClient()
        captured_url = None

        original_fetch = client.fetch

        async def mock_fetch(url, goal, browser_profile="lite"):
            nonlocal captured_url
            captured_url = url
            return WebAgentResult(success=False, error="mock")

        client.fetch = mock_fetch
        await client.fetch_company_financials("AAPL")
        assert captured_url is not None
        assert "AAPL" in captured_url
        assert "financials" in captured_url

    @pytest.mark.asyncio
    async def test_fetch_sector_multiples_goal_text(self):
        """Verify the sector multiples goal includes the industry name."""
        client = WebAgentClient()
        captured_goal = None

        async def mock_fetch(url, goal, browser_profile="lite"):
            nonlocal captured_goal
            captured_goal = goal
            return WebAgentResult(success=False, error="mock")

        client.fetch = mock_fetch
        await client.fetch_sector_multiples("Healthcare")
        assert captured_goal is not None
        assert "Healthcare" in captured_goal
        assert "EV/EBITDA" in captured_goal

    @pytest.mark.asyncio
    async def test_fetch_regulatory_filings_goal_text(self):
        """Verify the regulatory filings goal includes the company name."""
        client = WebAgentClient()
        captured_goal = None

        async def mock_fetch(url, goal, browser_profile="lite"):
            nonlocal captured_goal
            captured_goal = goal
            return WebAgentResult(success=False, error="mock")

        client.fetch = mock_fetch
        await client.fetch_regulatory_filings("Tesla")
        assert captured_goal is not None
        assert "Tesla" in captured_goal
        assert "SEC" in captured_goal


# ── Pydantic Model Tests ─────────────────────────────────────────────────────

class TestModels:
    def test_web_agent_request_defaults(self):
        req = WebAgentRequest(url="https://x.com", goal="test")
        assert req.browser_profile == "lite"

    def test_sse_event_alias(self):
        """runId alias should populate run_id field."""
        event = SSEEvent.model_validate({
            "type": "STARTED",
            "runId": "run_xyz",
        })
        assert event.run_id == "run_xyz"

    def test_sse_event_complete_with_result(self):
        event = SSEEvent.model_validate({
            "type": "COMPLETE",
            "runId": "run_1",
            "status": "COMPLETED",
            "resultJson": {"key": "value"},
        })
        assert event.status == "COMPLETED"
        assert event.result_json == {"key": "value"}

    def test_web_agent_result_success(self):
        r = WebAgentResult(success=True, data={"a": 1}, run_id="r1", elapsed_seconds=2.5)
        assert r.success is True
        assert r.data == {"a": 1}

    def test_web_agent_result_failure(self):
        r = WebAgentResult(success=False, error="timeout")
        assert r.success is False
        assert r.error == "timeout"
        assert r.data is None
