"""
ResearchAgent — produces an industry brief (PDF) and buyer universe (JSON).
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from agents.base import BaseAgent
from agents.prompt_builder import PromptBuilder
from engine.llm import ask_llm

logger = logging.getLogger(__name__)

_OUTPUT_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs")


class ResearchAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict, run_id: str | None = None):
        # task_name can be "industry_brief" or "buyer_universe"
        task = input_payload.get("task_name", "industry_brief")
        super().__init__(
            agent_type="research",
            task_name=task,
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("research")

    def run(self) -> str:
        try:
            self.think("Analyzing documents for market and industry context.")
            doc_context = self._extract_document_context()
            deal_info = self._get_deal_info()
            deal_name = deal_info.get("deal_name", "Deal")
            os.makedirs(_OUTPUT_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)

            # Determine tasks to run
            task = self.task_name
            run_brief = task == "industry_brief"
            run_buyers = task in ("buyer_universe", "industry_brief")  # always run buyers with brief

            # Enrich with WorldMonitor macro/market context
            macro_context = self._fetch_macro_context()
            if macro_context:
                self.observe(f"WorldMonitor macro context appended ({len(macro_context)} chars).")
                doc_context += (
                    "\n\n--- Macro & Market Context (WorldMonitor Live Data) ---\n"
                    + macro_context
                )

            # Enrich with SerpAPI search intelligence (on whenever key is set —
            # free tier; the client caches and guards the monthly quota)
            serp_context = self._fetch_serp_context(deal_info)
            if serp_context:
                self.observe(f"SerpAPI search context appended ({len(serp_context)} chars).")
                doc_context += (
                    "\n\n--- Live Search Intelligence (SerpAPI / Google) ---\n"
                    + serp_context
                )

            # Enrich with TinyFish web intelligence (opt-in)
            if self.input_payload.get("parameters", {}).get("web_enrichment"):
                web_context = self._fetch_web_buyer_context(deal_info)
                if web_context:
                    self.observe(f"TinyFish web context appended ({len(web_context)} chars).")
                    doc_context += (
                        "\n\n--- Live Web Intelligence (TinyFish) ---\n"
                        + web_context
                    )

            if run_brief:
                self.act("ask_llm", "generating industry brief")
                prompt = PromptBuilder.build_research_prompt(deal_info, doc_context, "industry_brief")
                raw = ask_llm(self.system_prompt, prompt)
                self.observe(f"Industry brief LLM response ({len(raw)} chars).")

                brief_data = self._parse_json(raw)
                pdf_path = self._write_industry_brief_pdf(
                    os.path.join(_OUTPUT_DIR, f"{safe_name}_IndustryBrief_{date_str}.pdf"),
                    deal_info, brief_data
                )
                self._register_output(pdf_path, output_type="pdf", output_category="research")
                self.observe(f"Industry brief PDF written: {os.path.basename(pdf_path)}")

            if run_buyers:
                self.act("ask_llm", "generating buyer universe")
                prompt2 = PromptBuilder.build_research_prompt(deal_info, doc_context, "buyer_universe")
                raw2 = ask_llm(self.system_prompt, prompt2)
                self.observe(f"Buyer universe LLM response ({len(raw2)} chars).")

                buyer_data = self._parse_json(raw2)
                self._persist_buyer_outreach(buyer_data)
                json_path = os.path.join(_OUTPUT_DIR, f"{safe_name}_BuyerUniverse_{date_str}.json")
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(buyer_data, f, indent=2, ensure_ascii=False)
                self._register_output(json_path, output_type="json", output_category="research")
                self.observe(f"Buyer universe JSON written: {os.path.basename(json_path)}")

            self.complete(confidence=0.75)

        except Exception as exc:
            logger.exception("ResearchAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    def _persist_buyer_outreach(self, buyer_data: dict) -> None:
        from database import SessionLocal, ensure_database_ready
        from db_models import BuyerOutreachModel
        import uuid as uuid_mod

        ensure_database_ready()
        buyers: list[tuple[str, str, dict]] = []
        for buyer_type, key in (("strategic", "strategic_buyers"), ("financial", "financial_buyers")):
            for item in buyer_data.get(key, []) or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if name:
                    payload = dict(item)
                    payload.setdefault("outreach_status", "not_contacted")
                    buyers.append((buyer_type, name, payload))

        if not buyers:
            return

        with SessionLocal() as db:
            existing = {
                b.buyer_name.strip().lower(): b
                for b in db.query(BuyerOutreachModel).filter(BuyerOutreachModel.deal_id == self.deal_id).all()
            }
            next_idx = len(existing)
            for buyer_type, name, payload in buyers:
                key = name.strip().lower()
                row = existing.get(key)
                if row:
                    row.buyer_payload = payload
                    row.buyer_type = buyer_type
                    continue
                row = BuyerOutreachModel(
                    id=str(uuid_mod.uuid4()),
                    deal_id=self.deal_id,
                    buyer_idx=next_idx,
                    buyer_name=name,
                    buyer_type=buyer_type,
                    outreach_status=payload.get("outreach_status", "not_contacted"),
                    source_run_id=self.run_id,
                    buyer_payload=payload,
                )
                db.add(row)
                next_idx += 1
            db.commit()

    def _fetch_macro_context(self) -> str:
        """Fetch macro/market data from WorldMonitor for research enrichment."""
        try:
            from tools.world_monitor import wm_client
            if not wm_client.enabled:
                return ""

            # Fetch all four endpoints in parallel to cut latency
            signals, fg, fred, implications = wm_client._run_async_gather(
                wm_client.get_macro_signals(),
                wm_client.get_fear_greed_index(),
                wm_client.get_fred_batch(["DGS10", "FEDFUNDS", "CPIAUCSL", "VIXCLS"]),
                wm_client.get_market_implications(),
            )

            sections: list[str] = []

            if signals and not signals.unavailable:
                sections.append(
                    f"Market Regime: {signals.verdict} "
                    f"({signals.bullish_count}/{signals.total_count} signals bullish)"
                )

            if fg and fg.value:
                sections.append(
                    f"Fear & Greed Index: {fg.value} ({fg.classification})"
                )

            if fred:
                labels = {
                    "DGS10": "10Y Treasury Yield",
                    "FEDFUNDS": "Fed Funds Rate",
                    "CPIAUCSL": "CPI (All Urban)",
                    "VIXCLS": "VIX Volatility",
                }
                for sid, data in fred.items():
                    if data.observations:
                        obs = data.observations[-1]
                        sections.append(
                            f"{labels.get(sid, sid)}: {obs.value} (as of {obs.date})"
                        )

            if implications:
                imp_lines = []
                for card in implications[:3]:
                    imp_lines.append(
                        f"  - {card.ticker} {card.name}: {card.direction} "
                        f"({card.confidence} confidence, {card.timeframe}) — "
                        f"{card.title}"
                    )
                if imp_lines:
                    sections.append(
                        "Market Implications:\n" + "\n".join(imp_lines)
                    )

            return "\n".join(sections)
        except Exception as exc:
            logger.debug("WorldMonitor macro context fetch failed: %s", exc)
            return ""

    def _fetch_serp_context(self, deal_info: dict) -> str:
        """Fetch M&A news, company coverage, and competitor landscape via SerpAPI."""
        try:
            from tools.serp import serp_client
            if not serp_client.enabled:
                return ""

            industry = deal_info.get("industry", "")
            company = deal_info.get("company_name", "")
            sections: list[str] = []

            import concurrent.futures
            futures: dict[str, concurrent.futures.Future] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                if industry:
                    futures["ma"] = pool.submit(serp_client.get_ma_news_sync, industry, 6)
                if company:
                    futures["news"] = pool.submit(serp_client.get_company_news_sync, company, 6)
                if company and industry:
                    futures["comp"] = pool.submit(
                        serp_client.find_competitors_sync, company, industry
                    )

            if "ma" in futures:
                block = serp_client.format_news_block(
                    f"Recent M&A Activity ({industry})", futures["ma"].result()
                )
                if block:
                    sections.append(block)

            if "news" in futures:
                block = serp_client.format_news_block(
                    f"Recent News Coverage ({company})", futures["news"].result()
                )
                if block:
                    sections.append(block)

            if "comp" in futures:
                comp = futures["comp"].result()
                if comp and comp.organic:
                    lines = [
                        f"  - {r.title}: {r.snippet}"
                        for r in comp.organic[:5]
                        if r.snippet
                    ]
                    if lines:
                        sections.append(
                            "Competitor Landscape (search results):\n" + "\n".join(lines)
                        )

            return "\n\n".join(sections)
        except Exception as exc:
            logger.debug("SerpAPI research context fetch failed: %s", exc)
            return ""

    def _fetch_web_buyer_context(self, deal_info: dict) -> str:
        """Fetch live web data via TinyFish for buyer universe enrichment."""
        try:
            from tools.web_agent import web_agent
            if not web_agent.enabled:
                return ""

            industry = deal_info.get("industry", "")
            company = deal_info.get("company_name", "")
            sections: list[str] = []

            # Submit M&A and competitor fetches in parallel using threads
            import concurrent.futures
            futures: dict[str, concurrent.futures.Future] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                if industry:
                    futures["ma"] = pool.submit(
                        web_agent.fetch_recent_ma_activity_sync, industry
                    )
                if company and industry:
                    futures["comp"] = pool.submit(
                        web_agent.fetch_competitor_landscape_sync, company, industry
                    )

            if "ma" in futures:
                ma_result = futures["ma"].result()
                if ma_result.success and ma_result.data:
                    deals = ma_result.data if isinstance(ma_result.data, list) else [ma_result.data]
                    lines = []
                    for d in deals[:5]:
                        if isinstance(d, dict):
                            acq = d.get("acquirer", "Unknown")
                            tgt = d.get("target", "Unknown")
                            val = d.get("deal_value_usd", "N/A")
                            lines.append(f"  - {acq} -> {tgt} ({val})")
                    if lines:
                        sections.append("Recent M&A Activity:\n" + "\n".join(lines))

            if "comp" in futures:
                comp_result = futures["comp"].result()
                if comp_result.success and comp_result.data:
                    comps = comp_result.data if isinstance(comp_result.data, list) else [comp_result.data]
                    lines = []
                    for c in comps[:8]:
                        if isinstance(c, dict):
                            name = c.get("name", "Unknown")
                            mcap = c.get("market_cap", "N/A")
                            lines.append(f"  - {name} (Market Cap: {mcap})")
                    if lines:
                        sections.append("Competitor Landscape:\n" + "\n".join(lines))

            return "\n".join(sections)
        except Exception as exc:
            logger.debug("TinyFish web buyer context fetch failed: %s", exc)
            return ""

    def _parse_json(self, raw: str) -> dict:
        match = re.search(r"\{[\s\S]*\}", raw.strip())
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        logger.warning("ResearchAgent: could not parse LLM JSON.")
        return {"raw_response": raw[:1000]}

    def _write_industry_brief_pdf(self, pdf_path: str, deal_info: dict, brief_data: dict) -> str:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )

        doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, textColor=colors.HexColor("#1a1a2e"))
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, textColor=colors.HexColor("#16213e"))
        body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, leading=14)
        bullet = ParagraphStyle("Bullet", parent=styles["Normal"], fontSize=9, leftIndent=12, leading=12)
        sub = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=8, textColor=colors.grey)

        story = []
        company = deal_info.get("company_name", "Company")
        industry = deal_info.get("industry", brief_data.get("sector", "Industry"))

        story.append(Paragraph(f"INDUSTRY BRIEF — {industry.upper()}", h1))
        story.append(Paragraph(f"Context: {company}", sub))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
        story.append(Spacer(1, 0.3*cm))

        # Market overview table
        mkt_rows = [
            ["Market Size", brief_data.get("market_size", "N/A")],
            ["Growth CAGR", brief_data.get("market_growth_cagr", "N/A")],
        ]
        t = Table(mkt_rows, colWidths=[5*cm, 12*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.3*cm))

        for section_title, data_key in [
            ("Growth Drivers", "growth_drivers"),
            ("Key Industry Players", None),
            ("Risks", "risks"),
        ]:
            story.append(Paragraph(section_title, h2))
            if data_key == "growth_drivers":
                for item in brief_data.get("growth_drivers", []):
                    story.append(Paragraph(f"• {item}", bullet))
            elif data_key == "risks":
                for item in brief_data.get("risks", []):
                    story.append(Paragraph(f"• {item}", bullet))
            else:
                for player in brief_data.get("key_players", []):
                    name = player.get("name", "") if isinstance(player, dict) else str(player)
                    pos = player.get("market_position", "") if isinstance(player, dict) else ""
                    story.append(Paragraph(f"• {name} — {pos}", bullet))
            story.append(Spacer(1, 0.2*cm))

        cl = brief_data.get("competitive_landscape", "")
        if cl:
            story.append(Paragraph("Competitive Landscape", h2))
            story.append(Paragraph(cl, body))

        thesis = brief_data.get("investment_thesis", "")
        if thesis:
            story.append(Spacer(1, 0.3*cm))
            story.append(Paragraph("Investment Thesis", h2))
            story.append(Paragraph(thesis, body))

        doc.build(story)
        return pdf_path
