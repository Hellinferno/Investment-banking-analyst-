"""
DocDrafterAgent — drafts a Confidential Information Memorandum (CIM) or Teaser as a DOCX.

Sections:
  1. Executive Summary
  2. Business Description
  3. Management Team
  4. Financial Overview
  5. Market Opportunity
"""
from __future__ import annotations

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

_CIM_SECTIONS = [
    ("executive_summary", "Executive Summary"),
    ("business_description", "Business Description"),
    ("management", "Management Team"),
    ("financials", "Financial Overview"),
    ("market", "Market Opportunity"),
]

_TEASER_SECTIONS = [
    ("teaser_overview", "Investment Overview"),
    ("teaser_financials", "Financial Highlights"),
]


class DocDrafterAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict, run_id: str | None = None):
        task_name = input_payload.get("task_name") or input_payload.get("task_mode", "cim_draft")
        super().__init__(
            agent_type="doc_drafter",
            task_name=task_name,
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("doc_drafter")

    def run(self) -> str:
        try:
            task_mode = self.input_payload.get("task_name") or self.input_payload.get("task_mode", "cim_draft")
            doc_type = "CIM" if task_mode == "cim_draft" else "Teaser"
            
            self.think(f"Drafting {doc_type} document.")
            doc_context = self._extract_document_context()
            deal_info = self._get_deal_info()
            dcf_result = self._get_latest_dcf_output()
            deal_name = deal_info.get("deal_name", "Deal")
            company = deal_info.get("company_name", "Company")

            if task_mode == "teaser_draft":
                pdf_path = self._draft_teaser_pdf(doc_context, deal_info, dcf_result, deal_name, company)
                self._register_output(pdf_path, output_type="pdf", output_category="teaser")
                self.complete(confidence=0.80)
                return self.run_id

            sections_to_draft = _CIM_SECTIONS if task_mode == "cim_draft" else _TEASER_SECTIONS
            sections: dict[str, str] = {}
            for section_key, section_label in sections_to_draft:
                self.act("ask_llm", f"drafting {doc_type} section: {section_label}")
                prompt = PromptBuilder.build_cim_section_prompt(
                    deal_info, doc_context, dcf_result, section_key
                )
                raw = ask_llm(self.system_prompt, prompt)
                sections[section_key] = raw.strip()
                self.observe(f"Section '{section_label}' drafted ({len(sections[section_key])} chars).")

            os.makedirs(_OUTPUT_DIR, exist_ok=True)
            date_str = datetime.now().strftime("%Y%m%d")
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)
            docx_filename = f"{safe_name}_{doc_type}_{date_str}.docx"
            docx_path = os.path.join(_OUTPUT_DIR, docx_filename)

            self.act("docx_writer", f"writing {doc_type} to DOCX")
            self._write_docx(docx_path, company, deal_info, sections, task_mode)
            self.observe(f"{doc_type} DOCX written: {docx_filename}")

            self._register_output(docx_path, output_type="docx", output_category=doc_type.lower())
            self.complete(confidence=0.80)

        except Exception as exc:
            logger.exception("DocDrafterAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    def _draft_teaser_pdf(
        self,
        doc_context: str,
        deal_info: dict,
        dcf_result: dict,
        deal_name: str,
        company: str,
    ) -> str:
        parameters = self.input_payload.get("parameters", {}) or {}
        codename = parameters.get("project_codename") or f"Project {deal_info.get('name') or 'Summit'}"
        self.act("ask_llm", "drafting blind one-page teaser")
        prompt = PromptBuilder.build_teaser_prompt(deal_info, doc_context, dcf_result, codename)
        raw = ask_llm(self.system_prompt, prompt)
        teaser_data = self._parse_teaser_data(raw)
        teaser_data = self._redact_teaser_data(teaser_data, company, codename)

        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        safe_name = re.sub(r"[^\w\-]", "_", deal_name)
        pdf_path = os.path.join(_OUTPUT_DIR, f"{safe_name}_Teaser_{date_str}.pdf")
        self._write_teaser_pdf(pdf_path, codename, deal_info, teaser_data)
        self.observe(f"Blind teaser PDF written: {os.path.basename(pdf_path)}")
        return pdf_path

    def _parse_teaser_data(self, raw: str) -> dict:
        import json

        match = re.search(r"\{[\s\S]*\}", raw.strip())
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {
            "investment_highlights": [raw[:500] or "Differentiated market position with actionable buyer interest."],
            "financial_snapshot": {},
            "transaction_overview": "Blind sale process for a scaled company in its sector.",
            "contact": "AIBAA Investment Banking Team",
        }

    def _redact_teaser_data(self, teaser_data: dict, company: str, codename: str) -> dict:
        company_tokens = [company] + [p for p in re.split(r"\s+", company or "") if len(p) > 2]

        def redact(value):
            if isinstance(value, str):
                text = value
                for token in company_tokens:
                    text = re.sub(re.escape(token), codename, text, flags=re.IGNORECASE)
                return text
            if isinstance(value, list):
                return [redact(v) for v in value]
            if isinstance(value, dict):
                return {k: redact(v) for k, v in value.items()}
            return value

        return redact(teaser_data)

    def _write_teaser_pdf(self, pdf_path: str, codename: str, deal_info: dict, teaser_data: dict) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=A4,
            rightMargin=1.4 * cm,
            leftMargin=1.4 * cm,
            topMargin=1.2 * cm,
            bottomMargin=1.2 * cm,
        )
        styles = getSampleStyleSheet()
        title = ParagraphStyle("Title", parent=styles["Heading1"], fontSize=16, leading=20, textColor=colors.HexColor("#1a1a2e"))
        h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=10, leading=12, textColor=colors.HexColor("#16213e"))
        body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8.5, leading=11)
        bullet = ParagraphStyle("Bullet", parent=body, leftIndent=10, firstLineIndent=-6)

        story = [
            Paragraph(f"{codename} - Blind Teaser", title),
            Paragraph(f"{deal_info.get('industry', 'Sector')} | {datetime.now().strftime('%B %Y')}", body),
            Spacer(1, 0.25 * cm),
        ]

        story.append(Paragraph("Investment Highlights", h2))
        for item in (teaser_data.get("investment_highlights") or [])[:6]:
            story.append(Paragraph(f"- {item}", bullet))
        story.append(Spacer(1, 0.2 * cm))

        financials = teaser_data.get("financial_snapshot") or {}
        if financials:
            rows = [["Metric", "Rounded Snapshot"]]
            for key, value in financials.items():
                rows.append([str(key).replace("_", " ").title(), str(value)])
            table = Table(rows, colWidths=[5 * cm, 11 * cm])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))
            story += [Paragraph("Financial Snapshot", h2), table, Spacer(1, 0.2 * cm)]

        story.append(Paragraph("Transaction Overview", h2))
        story.append(Paragraph(teaser_data.get("transaction_overview", "Blind process for qualified buyers."), body))
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("Banker Contact", h2))
        story.append(Paragraph(teaser_data.get("contact", "AIBAA Investment Banking Team"), body))

        doc.build(story)

    def _write_docx(
        self,
        docx_path: str,
        company: str,
        deal_info: dict,
        sections: dict[str, str],
        task_mode: str,
    ) -> None:
        from docx import Document
        from docx.shared import Pt, RGBColor, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        # ---- Document styles ----
        # Title
        display_title = company if task_mode == "cim_draft" else f"Project {deal_info.get('name', 'Alpha')}"
        title_para = doc.add_heading(display_title, level=0)
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_para.runs[0]
        run.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)

        # Subtitle
        sub_para = doc.add_paragraph()
        sub_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle_text = "CONFIDENTIAL INFORMATION MEMORANDUM" if task_mode == "cim_draft" else "PROJECT TEASER"
        sub_run = sub_para.add_run(subtitle_text)
        sub_run.bold = True
        sub_run.font.size = Pt(14)
        sub_run.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)

        meta_para = doc.add_paragraph()
        meta_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta_run = meta_para.add_run(
            f"{deal_info.get('deal_type', 'Transaction')} | {deal_info.get('industry', '')} | "
            f"{datetime.now().strftime('%B %Y')}"
        )
        meta_run.font.size = Pt(10)
        meta_run.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

        doc.add_paragraph()  # spacer

        # Disclaimer
        disc_para = doc.add_paragraph()
        disc_run = disc_para.add_run(
            "CONFIDENTIAL — This document is intended solely for the named recipient. "
            "It may not be reproduced or distributed without prior written consent. "
            "This document does not constitute an offer or solicitation."
        )
        disc_run.font.size = Pt(8)
        disc_run.font.color.rgb = RGBColor(0xff, 0x00, 0x00)
        disc_para.alignment = WD_ALIGN_PARAGRAPH.CENTER

        doc.add_page_break()

        # ---- Sections ----
        sections_to_draft = _CIM_SECTIONS if task_mode == "cim_draft" else _TEASER_SECTIONS
        for section_key, section_label in sections_to_draft:
            content = sections.get(section_key, "")
            if not content:
                continue

            # Section heading
            heading = doc.add_heading(section_label, level=1)
            heading_run = heading.runs[0]
            heading_run.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)

            # Section body — split by double newlines for paragraphs
            for para_text in content.split("\n\n"):
                para_text = para_text.strip()
                if not para_text:
                    continue
                p = doc.add_paragraph()
                p.add_run(para_text).font.size = Pt(10)

            doc.add_paragraph()  # spacer between sections

        # Page margins
        for section in doc.sections:
            section.top_margin = Inches(1)
            section.bottom_margin = Inches(1)
            section.left_margin = Inches(1.25)
            section.right_margin = Inches(1.25)

        doc.save(docx_path)
