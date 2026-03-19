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
    def __init__(self, deal_id: str, input_payload: dict):
        # task_name can be "industry_brief" or "buyer_universe"
        task = input_payload.get("task_name", "industry_brief")
        super().__init__(
            agent_type="research",
            task_name=task,
            deal_id=deal_id,
            input_payload=input_payload,
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
            run_brief = task in ("industry_brief", "industry_brief")
            run_buyers = task in ("buyer_universe", "industry_brief")  # always do both if brief

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
