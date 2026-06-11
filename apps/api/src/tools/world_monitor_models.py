"""
Pydantic response models for WorldMonitor API integration.

These models mirror the WorldMonitor TypeScript/Protobuf response shapes,
translated into Python Pydantic models for type-safe deserialization.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Economic / FRED ──────────────────────────────────────────────────────

class FredObservation(BaseModel):
    date: str
    value: float


class FredSeries(BaseModel):
    series_id: str = Field(default="", alias="seriesId")
    title: str = ""
    frequency: str = ""
    units: str = ""
    observations: list[FredObservation] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class FredSeriesResponse(BaseModel):
    series: FredSeries | None = None


class FredBatchResponse(BaseModel):
    results: dict[str, FredSeries] = Field(default_factory=dict)
    fetched: int = 0
    requested: int = 0


class CreditSpreadData(BaseModel):
    """Credit spread proxies from FRED HY/IG OAS indices."""
    hy_spread: float | None = None   # BAMLH0A0HYM2 — ICE BofA US HY OAS
    ig_spread: float | None = None   # BAMLC0A0CM — ICE BofA US IG OAS
    sofr: float | None = None        # SOFR — Secured Overnight Financing Rate
    as_of: str = ""


class YieldCurvePoint(BaseModel):
    maturity: str          # e.g. "1MO", "3MO", "1", "2", "5", "10", "30"
    rate: float


class YieldCurveSnapshot(BaseModel):
    points: list[YieldCurvePoint] = Field(default_factory=list)
    as_of: str = ""
    inverted: bool = False  # True if short rates > long rates


# ── Market Data ──────────────────────────────────────────────────────────

class MarketQuote(BaseModel):
    symbol: str = ""
    name: str = ""
    price: float = 0.0
    change: float = 0.0
    change_percent: float = Field(default=0.0, alias="changePercent")
    market_cap: float | None = Field(default=None, alias="marketCap")
    volume: float | None = None
    currency: str = ""

    model_config = {"populate_by_name": True}


class MarketQuotesResponse(BaseModel):
    quotes: list[MarketQuote] = Field(default_factory=list)
    finnhub_skipped: bool = Field(default=False, alias="finnhubSkipped")
    rate_limited: bool = Field(default=False, alias="rateLimited")

    model_config = {"populate_by_name": True}


class SectorPerformance(BaseModel):
    sector: str = ""
    change_percent: float = 0.0
    market_cap: float = 0.0


class SectorSummaryResponse(BaseModel):
    sectors: list[SectorPerformance] = Field(default_factory=list)


class CommodityQuote(BaseModel):
    symbol: str = ""
    name: str = ""
    price: float = 0.0
    change: float = 0.0
    change_percent: float = 0.0
    unit: str = ""


class CommodityQuotesResponse(BaseModel):
    quotes: list[CommodityQuote] = Field(default_factory=list)


class FearGreedResponse(BaseModel):
    value: int = 0
    classification: str = ""  # Extreme Fear / Fear / Neutral / Greed / Extreme Greed
    previous_close: int = 0
    one_week_ago: int = 0
    one_month_ago: int = 0


# ── Macro Signals ────────────────────────────────────────────────────────

class MacroSignalDetail(BaseModel):
    status: str = "UNKNOWN"
    sparkline: list[float] = Field(default_factory=list)
    history: list[Any] = Field(default_factory=list)


class MacroSignals(BaseModel):
    liquidity: MacroSignalDetail = Field(default_factory=MacroSignalDetail)
    flow_structure: MacroSignalDetail = Field(default_factory=MacroSignalDetail, alias="flowStructure")
    macro_regime: MacroSignalDetail = Field(default_factory=MacroSignalDetail, alias="macroRegime")
    technical_trend: MacroSignalDetail = Field(default_factory=MacroSignalDetail, alias="technicalTrend")
    fear_greed: MacroSignalDetail = Field(default_factory=MacroSignalDetail, alias="fearGreed")

    model_config = {"populate_by_name": True}


class MacroSignalsResponse(BaseModel):
    timestamp: str = ""
    verdict: str = "UNKNOWN"         # BULLISH / BEARISH / UNKNOWN
    bullish_count: int = Field(default=0, alias="bullishCount")
    total_count: int = Field(default=0, alias="totalCount")
    signals: MacroSignals = Field(default_factory=MacroSignals)
    unavailable: bool = False

    model_config = {"populate_by_name": True}


# ── Intelligence / Risk ──────────────────────────────────────────────────

class CIIComponents(BaseModel):
    news_activity: float = Field(default=0.0, alias="newsActivity")
    cii_contribution: float = Field(default=0.0, alias="ciiContribution")
    geo_convergence: float = Field(default=0.0, alias="geoConvergence")
    military_activity: float = Field(default=0.0, alias="militaryActivity")

    model_config = {"populate_by_name": True}


class CIIScore(BaseModel):
    """Country Intelligence Index — composite risk score (0–100)."""
    region: str = ""                     # ISO-2 country code
    static_baseline: float = Field(default=0.0, alias="staticBaseline")
    dynamic_score: float = Field(default=0.0, alias="dynamicScore")
    combined_score: float = Field(default=0.0, alias="combinedScore")
    trend: str = ""                      # TREND_DIRECTION_STABLE, etc.
    components: CIIComponents = Field(default_factory=CIIComponents)
    computed_at: int = Field(default=0, alias="computedAt")

    model_config = {"populate_by_name": True}


class StrategicRisk(BaseModel):
    region: str = ""
    level: str = ""          # SEVERITY_LEVEL_HIGH / MEDIUM / LOW
    score: float = 0.0
    factors: list[str] = Field(default_factory=list)
    trend: str = ""


class RiskScoresResponse(BaseModel):
    cii_scores: list[CIIScore] = Field(default_factory=list, alias="ciiScores")
    strategic_risks: list[StrategicRisk] = Field(default_factory=list, alias="strategicRisks")

    model_config = {"populate_by_name": True}


class SituationDeduction(BaseModel):
    analysis: str = ""
    model: str = ""
    provider: str = ""


class MarketImplicationCard(BaseModel):
    ticker: str = ""
    name: str = ""
    direction: str = ""          # bullish / bearish / neutral
    timeframe: str = ""          # e.g. "1-3 months"
    confidence: str = ""         # high / medium / low
    title: str = ""
    narrative: str = ""
    risk_caveat: str = Field(default="", alias="riskCaveat")
    driver: str = ""

    model_config = {"populate_by_name": True}


class MarketImplicationsResponse(BaseModel):
    cards: list[MarketImplicationCard] = Field(default_factory=list)
    degraded: bool = False
    generated_at: str = Field(default="", alias="generatedAt")

    model_config = {"populate_by_name": True}


# ── Conflict ─────────────────────────────────────────────────────────────

class GeoLocation(BaseModel):
    latitude: float = 0.0
    longitude: float = 0.0


class AcledEvent(BaseModel):
    id: str = ""
    event_type: str = Field(default="", alias="eventType")
    country: str = ""
    location: GeoLocation = Field(default_factory=GeoLocation)
    occurred_at: int = Field(default=0, alias="occurredAt")
    fatalities: int = 0
    actors: list[str] = Field(default_factory=list)
    source: str = ""
    admin1: str = ""

    model_config = {"populate_by_name": True}


class ConflictEventsResponse(BaseModel):
    events: list[AcledEvent] = Field(default_factory=list)


# ── Supply Chain ─────────────────────────────────────────────────────────

class TransitSummary(BaseModel):
    today_total: int = Field(default=0, alias="todayTotal")
    today_tanker: int = Field(default=0, alias="todayTanker")
    today_cargo: int = Field(default=0, alias="todayCargo")
    today_other: int = Field(default=0, alias="todayOther")
    wow_change_pct: float = Field(default=0.0, alias="wowChangePct")
    risk_level: str = Field(default="", alias="riskLevel")
    incident_count_7d: int = Field(default=0, alias="incidentCount7d")
    disruption_pct: float = Field(default=0.0, alias="disruptionPct")
    risk_summary: str = Field(default="", alias="riskSummary")

    model_config = {"populate_by_name": True}


class ChokepointInfo(BaseModel):
    id: str = ""
    name: str = ""
    lat: float = 0.0
    lon: float = 0.0
    disruption_score: float = Field(default=0.0, alias="disruptionScore")
    status: str = ""                   # operational / degraded / disrupted
    active_warnings: int = Field(default=0, alias="activeWarnings")
    ais_disruptions: int = Field(default=0, alias="aisDisruptions")
    congestion_level: str = Field(default="normal", alias="congestionLevel")
    affected_routes: list[str] = Field(default_factory=list, alias="affectedRoutes")
    description: str = ""
    transit_summary: TransitSummary | None = Field(default=None, alias="transitSummary")

    model_config = {"populate_by_name": True}


class ChokepointStatusResponse(BaseModel):
    chokepoints: list[ChokepointInfo] = Field(default_factory=list)
    fetched_at: str = Field(default="", alias="fetchedAt")
    upstream_unavailable: bool = Field(default=False, alias="upstreamUnavailable")

    model_config = {"populate_by_name": True}
