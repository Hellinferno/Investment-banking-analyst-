"""
DueDiligenceAgent — produces a risk assessment report + Excel checklist.

Outputs:
  1. JSON risk assessment file (.json)
  2. Excel DD checklist workbook (.xlsx)
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from agents.base import BaseAgent, parse_llm_json
from agents.prompt_builder import PromptBuilder
from engine.llm import ask_llm

logger = logging.getLogger(__name__)

_OUTPUT_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs")


class DueDiligenceAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict, run_id: str | None = None):
        super().__init__(
            agent_type="due_diligence",
            task_name="dd_report",
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("due_diligence")

    def run(self) -> str:
        try:
            self.think("Loading all deal documents for due diligence risk analysis.")
            doc_context = self._extract_document_context()
            deal_info = self._get_deal_info()
            deal_name = deal_info.get("deal_name", "Deal")

            if not doc_context.strip():
                self.think("No parsed documents found — generating risk assessment from deal metadata only.")

            # Enrich with WorldMonitor geopolitical risk data
            geo_risk_context = self._fetch_geo_risk_context(deal_info)
            if geo_risk_context:
                self.observe(f"WorldMonitor geo-risk overlay appended ({len(geo_risk_context)} chars).")

            # Enrich with SerpAPI adverse-media sweep (on whenever key is set)
            adverse_media_context = self._fetch_adverse_media_context(deal_info)
            if adverse_media_context:
                self.observe(
                    f"SerpAPI adverse-media context appended ({len(adverse_media_context)} chars)."
                )

            # Enrich with TinyFish web due diligence (opt-in)
            web_dd_context = ""
            if self.input_payload.get("parameters", {}).get("web_enrichment"):
                web_dd_context = self._fetch_web_dd_context(deal_info)
                if web_dd_context:
                    self.observe(f"TinyFish DD web context appended ({len(web_dd_context)} chars).")

            self.act("ask_llm", "performing due diligence risk analysis via LLM")
            enriched_context = doc_context
            if geo_risk_context:
                enriched_context += (
                    "\n\n--- External Risk Intelligence (WorldMonitor) ---\n"
                    + geo_risk_context
                )
            if adverse_media_context:
                enriched_context += (
                    "\n\n--- Adverse Media Sweep (SerpAPI / Google News) ---\n"
                    + adverse_media_context
                )
            if web_dd_context:
                enriched_context += (
                    "\n\n--- Live Web Due Diligence (TinyFish) ---\n"
                    + web_dd_context
                )
            prompt = PromptBuilder.build_dd_prompt(enriched_context)
            raw = ask_llm(self.system_prompt, prompt)

            self.observe(f"LLM response received ({len(raw)} chars). Parsing risk data.")
            risk_data = self._parse_risk_data(raw)

            os.makedirs(_OUTPUT_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)

            # Output 1: JSON risk assessment
            self.act("file_writer", "writing JSON risk assessment")
            json_filename = f"{safe_name}_DD_RiskAssessment_{date_str}.json"
            json_path = os.path.join(_OUTPUT_DIR, json_filename)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(risk_data, f, indent=2, ensure_ascii=False)
            self._register_output(json_path, output_type="json", output_category="due_diligence")
            self.observe(f"JSON risk assessment written: {json_filename}")

            # Output 2: Excel checklist
            self.act("excel_writer", "generating DD checklist Excel workbook")
            from tools.excel_writer import WorkbookBuilder
            wb = WorkbookBuilder()
            excel_path = wb.write_dd_checklist(deal_name, risk_data)
            self._register_output(excel_path, output_type="xlsx", output_category="due_diligence")
            self.observe(f"Excel checklist written: {os.path.basename(excel_path)}")

            overall_score = risk_data.get("overall_risk_score", 0)
            red_flag_count = len(risk_data.get("red_flags", []))
            self.think(
                f"DD complete. Risk score: {overall_score}/10. "
                f"Red flags: {red_flag_count}. Rating: {risk_data.get('risk_rating', 'MEDIUM')}."
            )

            confidence = 0.85 if doc_context.strip() else 0.50
            self.complete(confidence=confidence)

        except Exception as exc:
            logger.exception("DueDiligenceAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    def _fetch_geo_risk_context(self, deal_info: dict) -> str:
        """Fetch WorldMonitor geopolitical risk data for DD enrichment.

        Returns a text block summarizing country risk, supply-chain chokepoint
        status, and recent conflict events.  Returns ``""`` on any failure so
        the DD proceeds with document-only analysis.
        """
        try:
            from tools.world_monitor import wm_client
            if not wm_client.enabled:
                return ""

            country = deal_info.get("country", "")
            sections: list[str] = []

            # Fetch all four endpoints in parallel to cut latency
            risk, chokepoints, events, signals = wm_client._run_async_gather(
                wm_client.get_country_risk(country) if country else wm_client._noop(),
                wm_client.get_chokepoint_status(),
                wm_client.get_conflict_events(country) if country else wm_client._noop(),
                wm_client.get_macro_signals(),
            )

            # 1. Country risk score (CII)
            if risk:
                trend = risk.trend.replace("TREND_DIRECTION_", "").title()
                sections.append(
                    f"Country Risk Index ({risk.region}): "
                    f"{risk.combined_score:.0f}/100 "
                    f"(baseline {risk.static_baseline:.0f}, "
                    f"dynamic +{risk.dynamic_score:.0f}, trend: {trend})"
                )

            # 2. Supply chain chokepoint disruptions
            if chokepoints:
                disrupted = [c for c in chokepoints if c.disruption_score > 50]
                if disrupted:
                    cp_lines = []
                    for c in sorted(disrupted, key=lambda x: -x.disruption_score)[:5]:
                        routes = ", ".join(c.affected_routes[:3]) if c.affected_routes else "N/A"
                        cp_lines.append(
                            f"  - {c.name}: {c.status} "
                            f"(disruption={c.disruption_score:.0f}/100, "
                            f"warnings={c.active_warnings}, "
                            f"routes: {routes})"
                        )
                    sections.append(
                        "Disrupted Global Trade Chokepoints:\n" + "\n".join(cp_lines)
                    )

            # 3. Regional conflict events (last 30 days)
            if events:
                total_fatalities = sum(e.fatalities for e in events)
                type_counts: dict[str, int] = {}
                for e in events:
                    t = e.event_type or "Unknown"
                    type_counts[t] = type_counts.get(t, 0) + 1
                breakdown = ", ".join(f"{v} {k}" for k, v in type_counts.items())
                sections.append(
                    f"ACLED Conflict Events ({country}, 30d): "
                    f"{len(events)} events, "
                    f"{total_fatalities} fatalities "
                    f"({breakdown})"
                )

            # 4. Macro regime context
            if signals and not signals.unavailable:
                sections.append(
                    f"Macro Market Regime: {signals.verdict} "
                    f"({signals.bullish_count}/{signals.total_count} signals bullish)"
                )

            return "\n".join(sections)
        except Exception as exc:
            logger.debug("WorldMonitor geo-risk fetch failed: %s", exc)
            return ""

    def _fetch_adverse_media_context(self, deal_info: dict) -> str:
        """Sweep Google News for litigation, probes, and penalties via SerpAPI.

        Returns ``""`` on any failure so DD proceeds without the overlay.
        """
        try:
            from tools.serp import serp_client
            if not serp_client.enabled:
                return ""

            company = deal_info.get("company_name", "")
            if not company:
                return ""

            items = serp_client.get_adverse_media_sync(company, limit=8)
            block = serp_client.format_news_block(
                f"Adverse Media & Regulatory Coverage ({company})", items
            )
            if not block:
                return ""
            return (
                block
                + "\n(Headlines above match litigation/investigation/penalty queries; "
                "verify relevance — name collisions are possible.)"
            )
        except Exception as exc:
            logger.debug("SerpAPI adverse-media fetch failed: %s", exc)
            return ""

    def _fetch_web_dd_context(self, deal_info: dict) -> str:
        """Fetch live regulatory filings via TinyFish for DD enrichment."""
        try:
            from tools.web_agent import web_agent
            if not web_agent.enabled:
                return ""

            company = deal_info.get("company_name", "")
            if not company:
                return ""

            sections: list[str] = []

            result = web_agent.fetch_regulatory_filings_sync(company)
            if result.success and result.data:
                filings = result.data if isinstance(result.data, list) else [result.data]
                lines = []
                for f in filings[:5]:
                    if isinstance(f, dict):
                        ftype = f.get("filing_type", "Filing")
                        date = f.get("date", "")
                        summary = f.get("summary", f.get("title", ""))
                        lines.append(f"  - [{ftype}] {date}: {summary}")
                if lines:
                    sections.append(
                        f"Recent Regulatory Filings ({company}):\n" + "\n".join(lines)
                    )

            return "\n".join(sections)
        except Exception as exc:
            logger.debug("TinyFish DD web context fetch failed: %s", exc)
            return ""

    def _parse_risk_data(self, raw: str) -> dict:
        """Extract JSON from LLM response with fallback."""
        data = parse_llm_json(raw, required_keys=("overall_risk_score", "risk_rating", "financial_risks"))
        if data is not None:
            try:
                # Clamp score to 0-10
                score = data.get("overall_risk_score", 5)
                data["overall_risk_score"] = max(0.0, min(10.0, float(score)))
                return data
            except (ValueError, TypeError):
                pass

        logger.warning("DueDiligenceAgent: could not parse valid LLM JSON, using fallback structure.")
        return {
            "overall_risk_score": 5.0,
            "risk_rating": "MEDIUM",
            "financial_risks": [{"risk": "Unable to parse structured risks", "severity": "medium", "evidence": raw[:300], "mitigation": "Manual review required"}],
            "operational_risks": [],
            "legal_risks": [],
            "market_risks": [],
            "red_flags": [],
            "positive_factors": [],
            "summary": "Automated parsing failed. Please review raw LLM output manually.",
        }
