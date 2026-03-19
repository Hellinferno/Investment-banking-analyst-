"""
PitchbookAgent — generates a professional PDF pitchbook for a deal.

Produces a 4-section PDF using ReportLab:
1. Company Overview
2. Industry Analysis
3. Financial Highlights
4. Valuation Summary
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


class PitchbookAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict):
        super().__init__(
            agent_type="pitchbook",
            task_name="generate_pitchbook",
            deal_id=deal_id,
            input_payload=input_payload,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("pitchbook")

    def run(self) -> str:
        try:
            self.think("Gathering deal context and prior DCF output for pitchbook generation.")
            doc_context = self._extract_document_context()
            deal_info = self._get_deal_info()
            dcf_result = self._get_latest_dcf_output()

            company = deal_info.get("company_name", "Company")
            deal_name = deal_info.get("deal_name", "Deal")

            self.think(f"Building pitchbook prompt for {company}.")
            prompt = PromptBuilder.build_pitchbook_prompt(deal_info, dcf_result, doc_context)

            self.act("ask_llm", "generating pitchbook sections via LLM")
            raw = ask_llm(self.system_prompt, prompt)

            self.observe(f"LLM response received ({len(raw)} chars). Parsing JSON sections.")
            sections = self._parse_sections(raw)

            self.act("pdf_writer", "writing PDF pitchbook to disk")
            os.makedirs(_OUTPUT_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)
            filename = f"{safe_name}_Pitchbook_{date_str}.pdf"
            pdf_path = os.path.join(_OUTPUT_DIR, filename)

            self._write_pdf(pdf_path, company, deal_info, sections, dcf_result)
            self.observe(f"Pitchbook PDF written to {filename}.")

            self._register_output(pdf_path, output_type="pdf", output_category="pitchbook")
            self.complete(confidence=0.85)

        except Exception as exc:
            logger.exception("PitchbookAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_sections(self, raw: str) -> dict:
        """Extract JSON from LLM response, with fallback."""
        text = raw.strip()
        # Try to extract JSON block
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        # Fallback: return empty sections so PDF still renders
        logger.warning("PitchbookAgent: could not parse LLM JSON response, using fallback.")
        return {
            "company_overview": {"headline": "Investment Opportunity", "description": raw[:500], "key_highlights": [], "business_model": "", "competitive_position": ""},
            "industry_analysis": {"market_size": "N/A", "growth_rate": "N/A", "key_trends": [], "competitive_landscape": "", "tailwinds": [], "headwinds": []},
            "financial_highlights": {"revenue_trend": "See financials", "ebitda_trend": "See financials", "balance_sheet": "N/A", "key_metrics": []},
            "valuation_summary": {"methodology": "DCF", "bear_case": "N/A", "base_case": "N/A", "bull_case": "N/A", "key_value_drivers": [], "transaction_rationale": ""},
        }

    def _write_pdf(self, pdf_path: str, company: str, deal_info: dict, sections: dict, dcf_result: dict) -> None:
        """Write the 4-section pitchbook PDF using ReportLab."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
        )

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle("Title", parent=styles["Title"], fontSize=22, spaceAfter=6, textColor=colors.HexColor("#1a1a2e"))
        h1_style = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, spaceAfter=6, textColor=colors.HexColor("#1a1a2e"), borderPad=4)
        h2_style = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, spaceAfter=4, textColor=colors.HexColor("#16213e"))
        body_style = ParagraphStyle("Body", parent=styles["Normal"], fontSize=9, spaceAfter=4, leading=14)
        bullet_style = ParagraphStyle("Bullet", parent=styles["Normal"], fontSize=9, leftIndent=12, spaceAfter=2, leading=12)
        sub_style = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=8, textColor=colors.grey, spaceAfter=2)
        conf_style = ParagraphStyle("Conf", parent=styles["Normal"], fontSize=7, textColor=colors.red, alignment=1)

        story = []

        # ---- COVER PAGE ----
        story.append(Spacer(1, 3 * cm))
        story.append(Paragraph("CONFIDENTIAL", conf_style))
        story.append(Spacer(1, 0.5 * cm))
        story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1a1a2e")))
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(company, title_style))
        story.append(Paragraph(f"{deal_info.get('deal_type', 'M&A')} Transaction", h2_style))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(f"Industry: {deal_info.get('industry', 'N/A')}", sub_style))
        story.append(Spacer(1, 0.3 * cm))
        overview = sections.get("company_overview", {})
        headline = overview.get("headline", "")
        if headline:
            story.append(Paragraph(headline, h2_style))
        story.append(Spacer(1, 1 * cm))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(f"Prepared: {datetime.now().strftime('%B %Y')}", sub_style))
        story.append(Paragraph("For Discussion Purposes Only", sub_style))
        story.append(PageBreak())

        # ---- SECTION 1: COMPANY OVERVIEW ----
        story.append(Paragraph("1. Company Overview", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
        story.append(Spacer(1, 0.3 * cm))

        desc = overview.get("description", "")
        if desc:
            story.append(Paragraph(desc, body_style))
        story.append(Spacer(1, 0.3 * cm))

        highlights = overview.get("key_highlights", [])
        if highlights:
            story.append(Paragraph("Key Highlights", h2_style))
            for h in highlights:
                story.append(Paragraph(f"• {h}", bullet_style))

        biz_model = overview.get("business_model", "")
        if biz_model:
            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph("Business Model", h2_style))
            story.append(Paragraph(biz_model, body_style))

        comp_pos = overview.get("competitive_position", "")
        if comp_pos:
            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph("Competitive Position", h2_style))
            story.append(Paragraph(comp_pos, body_style))
        story.append(PageBreak())

        # ---- SECTION 2: INDUSTRY ANALYSIS ----
        industry_data = sections.get("industry_analysis", {})
        story.append(Paragraph("2. Industry Analysis", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
        story.append(Spacer(1, 0.3 * cm))

        # Market size / growth table
        mkt_data = [
            ["Market Size", industry_data.get("market_size", "N/A")],
            ["Growth Rate (CAGR)", industry_data.get("growth_rate", "N/A")],
        ]
        mkt_table = Table(mkt_data, colWidths=[5 * cm, 12 * cm])
        mkt_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(mkt_table)
        story.append(Spacer(1, 0.3 * cm))

        cl = industry_data.get("competitive_landscape", "")
        if cl:
            story.append(Paragraph("Competitive Landscape", h2_style))
            story.append(Paragraph(cl, body_style))

        for label, key in [("Key Trends", "key_trends"), ("Tailwinds", "tailwinds"), ("Headwinds", "headwinds")]:
            items = industry_data.get(key, [])
            if items:
                story.append(Paragraph(label, h2_style))
                for item in items:
                    story.append(Paragraph(f"• {item}", bullet_style))
        story.append(PageBreak())

        # ---- SECTION 3: FINANCIAL HIGHLIGHTS ----
        fin = sections.get("financial_highlights", {})
        story.append(Paragraph("3. Financial Highlights", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
        story.append(Spacer(1, 0.3 * cm))

        for label, key in [("Revenue Trajectory", "revenue_trend"), ("EBITDA / Margins", "ebitda_trend"), ("Balance Sheet", "balance_sheet")]:
            val = fin.get(key, "")
            if val:
                story.append(Paragraph(label, h2_style))
                story.append(Paragraph(val, body_style))

        metrics = fin.get("key_metrics", [])
        if metrics:
            story.append(Paragraph("Key Financial Metrics", h2_style))
            for m in metrics:
                story.append(Paragraph(f"• {m}", bullet_style))
        story.append(PageBreak())

        # ---- SECTION 4: VALUATION SUMMARY ----
        val_data = sections.get("valuation_summary", {})
        story.append(Paragraph("4. Valuation Summary", h1_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a1a2e")))
        story.append(Spacer(1, 0.3 * cm))

        story.append(Paragraph(f"Methodology: {val_data.get('methodology', 'DCF + CCA')}", body_style))
        story.append(Spacer(1, 0.3 * cm))

        val_table_data = [
            ["Scenario", "Equity Value"],
            ["Bear Case", str(val_data.get("bear_case", "N/A"))],
            ["Base Case", str(val_data.get("base_case", "N/A"))],
            ["Bull Case", str(val_data.get("bull_case", "N/A"))],
        ]
        vt = Table(val_table_data, colWidths=[6 * cm, 11 * cm])
        vt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("PADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#f0f4ff")),  # Base case highlight
        ]))
        story.append(vt)
        story.append(Spacer(1, 0.3 * cm))

        drivers = val_data.get("key_value_drivers", [])
        if drivers:
            story.append(Paragraph("Key Value Drivers", h2_style))
            for d in drivers:
                story.append(Paragraph(f"• {d}", bullet_style))

        rationale = val_data.get("transaction_rationale", "")
        if rationale:
            story.append(Spacer(1, 0.3 * cm))
            story.append(Paragraph("Transaction Rationale", h2_style))
            story.append(Paragraph(rationale, body_style))

        # ---- DISCLAIMER ----
        story.append(PageBreak())
        story.append(Spacer(1, 5 * cm))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            "DISCLAIMER: This document is confidential and has been prepared solely for informational "
            "purposes. It does not constitute an offer, solicitation, or advice. The projections and "
            "valuations contained herein are based on information available at the time of preparation "
            "and are subject to change. Recipients should conduct their own due diligence.",
            ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=7, textColor=colors.grey, leading=10)
        ))

        doc.build(story)
