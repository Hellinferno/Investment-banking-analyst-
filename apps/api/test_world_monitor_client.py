"""
Unit tests for WorldMonitor client — async methods with mocked httpx responses.

Tests cover:
  1. Graceful degradation when WorldMonitor is disabled / unreachable
  2. FRED series parsing and risk-free rate conversion
  3. Credit spread assembly from batch FRED data
  4. Yield curve construction and inversion detection
  5. TTL cache hit/miss behavior
  6. Market quote, risk score, chokepoint parsing
  7. Health check success/failure
"""
import sys
import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "src")

import pytest
import httpx

from tools.world_monitor import WorldMonitorClient, _TTLCache, FRED_RISK_FREE


# ─── Fixtures ─────────────────────────────────────────────────────────


def make_fred_response(series_id: str, value: float, date: str = "2026-03-25"):
    """Build a mock FRED series JSON response."""
    return {
        "series": {
            "seriesId": series_id,
            "title": f"Test {series_id}",
            "observations": [{"date": date, "value": value}],
        }
    }


def make_fred_batch_response(items: dict[str, float]):
    """Build a mock FRED batch response."""
    return {
        "results": {
            sid: {
                "seriesId": sid,
                "title": f"Test {sid}",
                "observations": [{"date": "2026-03-25", "value": val}],
            }
            for sid, val in items.items()
        }
    }


def make_macro_signals_response():
    return {
        "timestamp": "2026-03-25T12:00:00Z",
        "verdict": "BULLISH",
        "bullishCount": 8,
        "totalCount": 12,
        "unavailable": False,
        "signals": {},
    }


def make_risk_scores_response():
    return {
        "ciiScores": [
            {
                "region": "US",
                "staticBaseline": 20.0,
                "dynamicScore": 15.0,
                "combinedScore": 18.0,
                "trend": "stable",
                "components": {
                    "newsActivity": 5.0,
                    "ciiContribution": 3.0,
                    "geoConvergence": 2.0,
                    "militaryActivity": 1.0,
                },
            },
            {
                "region": "RU",
                "staticBaseline": 70.0,
                "dynamicScore": 75.0,
                "combinedScore": 72.0,
                "trend": "worsening",
                "components": {
                    "newsActivity": 30.0,
                    "ciiContribution": 20.0,
                    "geoConvergence": 15.0,
                    "militaryActivity": 10.0,
                },
            },
        ],
        "strategicRisks": [
            {
                "region": "Eastern Europe",
                "level": "critical",
                "score": 85.0,
                "factors": ["armed conflict", "sanctions"],
            }
        ],
    }


def make_chokepoints_response():
    return {
        "chokepoints": [
            {
                "id": "suez",
                "name": "Suez Canal",
                "lat": 30.58,
                "lon": 32.27,
                "disruptionScore": 65.0,
                "status": "degraded",
                "activeWarnings": 3,
                "congestionLevel": "high",
                "affectedRoutes": ["Asia-Europe", "Asia-Mediterranean"],
                "description": "Houthi attacks reducing transits",
            }
        ]
    }


def make_market_quotes_response():
    return {
        "quotes": [
            {
                "symbol": "SPY",
                "name": "SPDR S&P 500",
                "price": 520.50,
                "change": 3.25,
                "changePercent": 0.63,
                "marketCap": None,
            }
        ]
    }


def make_fear_greed_response():
    return {
        "value": 42,
        "classification": "fear",
        "previous_close": 45,
        "one_week_ago": 38,
        "one_month_ago": 55,
    }


# ─── TTL Cache Tests ─────────────────────────────────────────────────


class TestTTLCache:
    def test_set_and_get(self):
        cache = _TTLCache(default_ttl=300)
        cache.set("key1", {"data": 42})
        assert cache.get("key1") == {"data": 42}

    def test_miss_returns_none(self):
        cache = _TTLCache(default_ttl=300)
        assert cache.get("missing") is None

    def test_expired_entry_returns_none(self):
        cache = _TTLCache(default_ttl=0)  # Immediately expires
        cache.set("key1", "value")
        # TTL=0 means any monotonic delta > 0 triggers expiry
        import time
        time.sleep(0.01)
        assert cache.get("key1") is None

    def test_clear(self):
        cache = _TTLCache(default_ttl=300)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None


# ─── Client Tests (disabled WorldMonitor) ──────────────────────────────


class TestWorldMonitorDisabled:
    """When WORLDMONITOR_API_URL is empty, all methods return None/empty."""

    def setup_method(self):
        os.environ.pop("WORLDMONITOR_API_URL", None)
        self.client = WorldMonitorClient()

    def test_enabled_is_false(self):
        assert self.client.enabled is False

    def test_health_check_returns_false(self):
        result = asyncio.run(self.client.health_check())
        assert result is False

    def test_get_fred_series_returns_none(self):
        result = asyncio.run(self.client.get_fred_series("DGS10"))
        assert result is None

    def test_get_risk_free_rate_returns_none(self):
        result = asyncio.run(self.client.get_risk_free_rate())
        assert result is None

    def test_get_market_quotes_returns_empty(self):
        result = asyncio.run(self.client.get_market_quotes())
        assert result == []

    def test_get_chokepoint_status_returns_empty(self):
        result = asyncio.run(self.client.get_chokepoint_status())
        assert result == []

    def test_get_conflict_events_returns_empty(self):
        result = asyncio.run(self.client.get_conflict_events())
        assert result == []


# ─── Client Tests (enabled, mocked responses) ────────────────────────


class TestWorldMonitorEnabled:
    """With WorldMonitor enabled, test parsing of mocked HTTP responses."""

    def setup_method(self):
        os.environ["WORLDMONITOR_API_URL"] = "http://localhost:5173"
        self.client = WorldMonitorClient(timeout=5.0, cache_ttl=0)

    def teardown_method(self):
        os.environ.pop("WORLDMONITOR_API_URL", None)
        asyncio.run(self.client.close())

    def _mock_get(self, response_json: dict, status_code: int = 200):
        """Create a mock httpx response."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = status_code
        mock_response.json.return_value = response_json
        mock_response.raise_for_status = MagicMock()
        if status_code >= 400:
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "error", request=MagicMock(), response=mock_response
            )
        return mock_response

    # ── FRED ──

    def test_get_fred_series(self):
        resp = make_fred_response("DGS10", 4.25)
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            result = asyncio.run(self.client.get_fred_series("DGS10", limit=5))

        assert result is not None
        assert result.series_id == "DGS10"
        assert len(result.observations) == 1
        assert result.observations[0].value == 4.25

    def test_get_risk_free_rate_converts_percentage(self):
        """DGS10 returns 4.25% → should become 0.0425."""
        resp = make_fred_response("DGS10", 4.25)
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            rate = asyncio.run(self.client.get_risk_free_rate())

        assert rate is not None
        assert abs(rate - 0.0425) < 1e-6

    def test_get_risk_free_rate_decimal_passthrough(self):
        """If FRED returns already-decimal (0.0425), pass through."""
        resp = make_fred_response("DGS10", 0.0425)
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            rate = asyncio.run(self.client.get_risk_free_rate())

        assert rate is not None
        assert abs(rate - 0.0425) < 1e-6

    # ── Credit Spreads ──

    def test_get_credit_spreads(self):
        batch_resp = make_fred_batch_response({
            "BAMLH0A0HYM2": 3.50,  # HY spread: 3.50% → 0.035
            "BAMLC0A0CM": 1.20,     # IG spread: 1.20% → 0.012
            "SOFR": 5.33,           # SOFR: 5.33% → 0.0533
        })
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(batch_resp)
            mock_client_fn.return_value = mock_client

            spreads = asyncio.run(self.client.get_credit_spreads())

        assert spreads is not None
        assert abs(spreads.hy_spread - 0.035) < 1e-6
        assert abs(spreads.ig_spread - 0.012) < 1e-6
        assert abs(spreads.sofr - 0.0533) < 1e-6

    # ── Yield Curve ──

    def test_get_yield_curve_detects_inversion(self):
        """When 2Y > 10Y, inverted should be True."""
        batch_resp = make_fred_batch_response({
            "DGS1MO": 5.50, "DGS3MO": 5.40, "DGS6MO": 5.30,
            "DGS1": 5.10, "DGS2": 4.80, "DGS5": 4.50,
            "DGS10": 4.25, "DGS30": 4.40,
        })
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(batch_resp)
            mock_client_fn.return_value = mock_client

            curve = asyncio.run(self.client.get_yield_curve())

        assert curve is not None
        assert curve.inverted is True  # 2Y (4.80) > 10Y (4.25)
        assert len(curve.points) == 8

    def test_get_yield_curve_normal(self):
        """Normal curve: 2Y < 10Y."""
        batch_resp = make_fred_batch_response({
            "DGS1MO": 3.00, "DGS3MO": 3.20, "DGS6MO": 3.40,
            "DGS1": 3.60, "DGS2": 3.80, "DGS5": 4.00,
            "DGS10": 4.25, "DGS30": 4.50,
        })
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(batch_resp)
            mock_client_fn.return_value = mock_client

            curve = asyncio.run(self.client.get_yield_curve())

        assert curve is not None
        assert curve.inverted is False

    # ── Macro Signals ──

    def test_get_macro_signals(self):
        resp = make_macro_signals_response()
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            signals = asyncio.run(self.client.get_macro_signals())

        assert signals is not None
        assert signals.verdict == "BULLISH"
        assert signals.bullish_count == 8
        assert signals.total_count == 12

    # ── Risk Scores ──

    def test_get_risk_scores(self):
        resp = make_risk_scores_response()
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            scores = asyncio.run(self.client.get_risk_scores())

        assert scores is not None
        assert len(scores.cii_scores) == 2
        us = scores.cii_scores[0]
        assert us.region == "US"
        assert us.combined_score == 18.0
        assert len(scores.strategic_risks) == 1
        assert scores.strategic_risks[0].level == "critical"

    def test_get_country_risk(self):
        resp = make_risk_scores_response()
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            score = asyncio.run(self.client.get_country_risk("RU"))

        assert score is not None
        assert score.region == "RU"
        assert score.combined_score == 72.0

    def test_get_country_risk_not_found(self):
        resp = make_risk_scores_response()
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            score = asyncio.run(self.client.get_country_risk("XX"))

        assert score is None

    # ── Chokepoints ──

    def test_get_chokepoint_status(self):
        resp = make_chokepoints_response()
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            chokepoints = asyncio.run(self.client.get_chokepoint_status())

        assert len(chokepoints) == 1
        suez = chokepoints[0]
        assert suez.name == "Suez Canal"
        assert suez.disruption_score == 65.0
        assert suez.status == "degraded"

    # ── Market Quotes ──

    def test_get_market_quotes(self):
        resp = make_market_quotes_response()
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            quotes = asyncio.run(self.client.get_market_quotes(["SPY"]))

        assert len(quotes) == 1
        assert quotes[0].symbol == "SPY"
        assert quotes[0].price == 520.50

    # ── Fear & Greed ──

    def test_get_fear_greed_index(self):
        resp = make_fear_greed_response()
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            fg = asyncio.run(self.client.get_fear_greed_index())

        assert fg is not None
        assert fg.value == 42
        assert fg.classification == "fear"

    # ── Health Check ──

    def test_health_check_success(self):
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.status_code = 200
            mock_client.get.return_value = mock_resp
            mock_client_fn.return_value = mock_client

            result = asyncio.run(self.client.health_check())

        assert result is True

    def test_health_check_failure(self):
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client_fn.return_value = mock_client

            result = asyncio.run(self.client.health_check())

        assert result is False

    # ── Graceful degradation on HTTP errors ──

    def test_fred_returns_none_on_500(self):
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get({}, status_code=500)
            mock_client_fn.return_value = mock_client

            result = asyncio.run(self.client.get_fred_series("DGS10"))

        assert result is None

    def test_risk_scores_returns_none_on_timeout(self):
        with patch.object(self.client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.ReadTimeout("timeout")
            mock_client_fn.return_value = mock_client

            result = asyncio.run(self.client.get_risk_scores())

        assert result is None

    # ── Cache behavior ──

    def test_cache_prevents_duplicate_requests(self):
        """Second call to same endpoint should use cache, not HTTP."""
        client = WorldMonitorClient(timeout=5.0, cache_ttl=300)
        resp = make_fred_response("DGS10", 4.25)

        with patch.object(client, "_get_client") as mock_client_fn:
            mock_client = AsyncMock()
            mock_client.get.return_value = self._mock_get(resp)
            mock_client_fn.return_value = mock_client

            # First call — hits HTTP
            r1 = asyncio.run(client.get_fred_series("DGS10", limit=5))
            # Second call — should use cache
            r2 = asyncio.run(client.get_fred_series("DGS10", limit=5))

        assert r1 is not None
        assert r2 is not None
        # httpx.get should have been called only once
        assert mock_client.get.call_count == 1


# ─── Run ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
