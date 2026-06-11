"""
Pydantic models for the SerpAPI client (tools/serp.py).

All models are tolerant of partial payloads — SerpAPI omits fields freely
depending on the query, so every field is optional with a sensible default.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SerpNewsItem(BaseModel):
    """One result from the google_news engine."""

    title: str = ""
    link: str = ""
    source: str = ""
    date: str = ""          # ISO-8601 when available, else SerpAPI's display date
    snippet: str = ""

    @classmethod
    def from_raw(cls, raw: dict) -> "SerpNewsItem":
        source = raw.get("source") or {}
        return cls(
            title=raw.get("title") or "",
            link=raw.get("link") or "",
            source=source.get("name", "") if isinstance(source, dict) else str(source),
            date=raw.get("iso_date") or raw.get("date") or "",
            snippet=raw.get("snippet") or "",
        )


class SerpOrganicResult(BaseModel):
    """One organic result from the google engine."""

    title: str = ""
    link: str = ""
    snippet: str = ""
    position: int = 0

    @classmethod
    def from_raw(cls, raw: dict) -> "SerpOrganicResult":
        return cls(
            title=raw.get("title") or "",
            link=raw.get("link") or "",
            snippet=raw.get("snippet") or "",
            position=raw.get("position") or 0,
        )


class SerpWebSearch(BaseModel):
    """Organic results plus the knowledge-graph card (when Google shows one)."""

    query: str = ""
    organic: list[SerpOrganicResult] = Field(default_factory=list)
    knowledge_graph: dict = Field(default_factory=dict)
    answer_box: dict = Field(default_factory=dict)
    related_questions: list[dict] = Field(default_factory=list)


class SerpFinanceQuote(BaseModel):
    """Summary + key stats from the google_finance engine."""

    ticker: str = ""
    name: str = ""
    exchange: str = ""
    price: float | None = None
    currency: str = ""
    change_pct: float | None = None
    # Label -> value pairs from the knowledge graph (Mkt. cap, P/E ratio, EPS,
    # Beta, 52-wk high/low, Dividend, Shares outstanding, ...). Values stay as
    # Google's display strings ("4.28T", "$317.40") — parsing them numerically
    # is lossy and the consumers only need them for context blocks.
    key_stats: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, raw: dict) -> "SerpFinanceQuote":
        summary = raw.get("summary") or {}
        movement = summary.get("price_movement") or {}
        pct = movement.get("percentage")
        if pct is not None and movement.get("movement") == "Down":
            pct = -abs(float(pct))

        stats: dict[str, str] = {}
        kg = raw.get("knowledge_graph") or {}
        for stat in (kg.get("key_stats") or {}).get("stats", []) or []:
            label = stat.get("label")
            value = stat.get("value")
            if label and value:
                stats[str(label)] = str(value)

        return cls(
            ticker=summary.get("stock") or "",
            name=summary.get("title") or "",
            exchange=summary.get("exchange") or "",
            price=summary.get("extracted_price"),
            currency=summary.get("currency") or "",
            change_pct=round(float(pct), 2) if pct is not None else None,
            key_stats=stats,
        )


class SerpQuota(BaseModel):
    """Account usage snapshot from /account.json (a free endpoint)."""

    plan_name: str = ""
    searches_per_month: int = 0
    total_searches_left: int = 0
    this_month_usage: int = 0

    @classmethod
    def from_raw(cls, raw: dict) -> "SerpQuota":
        return cls(
            plan_name=raw.get("plan_name") or "",
            searches_per_month=raw.get("searches_per_month") or 0,
            total_searches_left=raw.get("total_searches_left") or 0,
            this_month_usage=raw.get("this_month_usage") or 0,
        )
