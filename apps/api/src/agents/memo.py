"""
InvestmentMemoAgent — Investment Committee (IC) memorandum.

Synthesizes prior agent work (DCF valuation, due diligence, comps) plus deal
documents into a decision-ready IC memo.

Outputs:
  1. JSON memo content (.json)
  2. Professionally formatted PDF memo (.pdf)
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


class InvestmentMemoAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict, run_id: str | None = None):
        super().__init__(
            agent_type="memo_writer",
            task_name="investment_memo",
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("memo_writer")

    def run(self) -> str:
        try:
            self.think("Gathering deal documents and prior agent outputs for IC memo.")
            doc_context = self._extract_document_context()
            deal_info = self._get_deal_info()
            deal_name = deal_info.get("deal_name", "Deal")

            valuation_summary = self._get_latest_dcf_output()
            dd_summary = self._get_latest_run_payload("due_diligence", "risk_data") or \
                self._load_latest_json_output("due_diligence")
            comps_summary = self._get_latest_run_payload("comps", "comps_result")

            sources = [
                name
                for name, present in (
                    ("DCF", bool(valuation_summary)),
                    ("DD", bool(dd_summary)),
                    ("Comps", bool(comps_summary)),
                )
                if present
            ]
            self.observe(f"Prior workstreams available: {', '.join(sources) or 'none'}.")

            self.act("ask_llm", "drafting IC memorandum via LLM")
            prompt = PromptBuilder.build_investment_memo_prompt(
                deal_info, doc_context, valuation_summary, dd_summary, comps_summary
            )
            raw = ask_llm(self.system_prompt, prompt)
            self.observe(f"LLM response received ({len(raw)} chars). Parsing memo content.")
            memo = self._parse_memo(raw)

            os.makedirs(_OUTPUT_DIR, exist_ok=True)
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)
            date_str = datetime.now().strftime("%Y%m%d")

            self.act("file_writer", "writing IC memo JSON")
            json_path = os.path.join(_OUTPUT_DIR, f"{safe_name}_IC_Memo_{date_str}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(memo, f, indent=2, ensure_ascii=False)
            self._register_output(json_path, output_type="json", output_category="memo")

            self.act("pdf_writer", "rendering IC memo PDF")
            pdf_path = os.path.join(_OUTPUT_DIR, f"{safe_name}_IC_Memo_{date_str}.pdf")
            self._write_pdf(pdf_path, deal_info, memo)
            self._register_output(pdf_path, output_type="pdf", output_category="memo")

            self.update_payload("memo_result", memo)

            rec = (memo.get("deal_snapshot") or {}).get("recommendation", "N/A")
            self.think(f"IC memo complete. Recommendation: {rec}.")
            confidence = 0.85 if len(sources) >= 2 else (0.7 if sources else 0.5)
            self.complete(confidence=confidence)

        except Exception as exc:
            logger.exception("InvestmentMemoAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    def _get_latest_run_payload(self, agent_type: str, payload_key: str) -> dict:
        """Return a payload value from the most recent completed run of an agent type."""
        from store import store
        runs = [
            r for r in store.agent_runs.values()
            if r.deal_id == self.deal_id and r.agent_type == agent_type and r.status == "completed"
        ]
        if not runs:
            return {}
        latest = max(runs, key=lambda r: getattr(r, "created_at", "") or "")
        return (latest.input_payload or {}).get(payload_key) or {}

    def _load_latest_json_output(self, category: str) -> dict:
        """Fallback: read the most recent JSON output file in a category."""
        from store import store
        outputs = [
            o for o in store.outputs.values()
            if o.deal_id == self.deal_id
            and o.output_category == category
            and o.output_type == "json"
        ]
        if not outputs:
            return {}
        latest = max(outputs, key=lambda o: o.storage_path)
        try:
            with open(latest.storage_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _parse_memo(self, raw: str) -> dict:
        data = parse_llm_json(raw, required_keys=("executive_summary", "deal_snapshot"))
        if data is not None:
            return data
        logger.warning("InvestmentMemoAgent: could not parse valid LLM JSON, using fallback structure.")
        return {
            "deal_snapshot": {"recommendation": "PROCEED_WITH_CONDITIONS", "conviction": "LOW"},
            "executive_summary": raw[:2000],
            "investment_thesis": [],
            "valuation_view": "",
            "key_risks": [],
            "diligence_summary": "",
            "deal_structure_considerations": "",
            "conditions_to_proceed": ["Automated memo parsing failed — manual review required."],
            "next_steps": [],
        }

    @staticmethod
    def _write_pdf(pdf_path: str, deal_info: dict, memo: dict) -> None:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        company = deal_info.get("company_name") or deal_info.get("deal_name", "Target")
        snapshot = memo.get("deal_snapshot") or {}

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "MemoTitle", parent=styles["Title"], fontName="Helvetica-Bold",
            fontSize=18, textColor=colors.black, spaceAfter=4,
        )
        h2 = ParagraphStyle(
            "MemoH2", parent=styles["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, textColor=colors.black, spaceBefore=14, spaceAfter=6,
        )
        body = ParagraphStyle(
            "MemoBody", parent=styles["BodyText"], fontName="Helvetica",
            fontSize=9.5, leading=14, alignment=4,
        )
        meta_style = ParagraphStyle(
            "MemoMeta", parent=styles["Normal"], fontName="Helvetica",
            fontSize=9, textColor=colors.HexColor("#555555"),
        )

        doc = SimpleDocTemplate(
            pdf_path, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
            title=f"Investment Committee Memorandum — {company}",
        )

        story = [
            Paragraph("INVESTMENT COMMITTEE MEMORANDUM", title_style),
            Paragraph(
                f"{company} — {deal_info.get('deal_type', 'M&A')} | "
                f"{deal_info.get('industry', '')} | "
                f"STRICTLY CONFIDENTIAL | {datetime.now().strftime('%d %B %Y')}",
                meta_style,
            ),
            Spacer(1, 6),
            HRFlowable(width="100%", thickness=1.2, color=colors.black),
            Spacer(1, 10),
        ]

        rec = snapshot.get("recommendation", "N/A")
        rec_color = {
            "PROCEED": colors.HexColor("#0B6E1F"),
            "PROCEED_WITH_CONDITIONS": colors.HexColor("#B36B00"),
            "DECLINE": colors.HexColor("#9B1313"),
        }.get(rec, colors.black)
        rec_table = Table(
            [
                ["RECOMMENDATION", rec.replace("_", " ")],
                ["CONVICTION", snapshot.get("conviction", "N/A")],
                ["TRANSACTION", snapshot.get("transaction", "")],
            ],
            colWidths=[4.5 * cm, 12 * cm],
        )
        rec_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("TEXTCOLOR", (1, 0), (1, 0), rec_color),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F2F2F2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.extend([rec_table, Spacer(1, 8)])

        def add_section(title: str, content) -> None:
            if not content:
                return
            story.append(Paragraph(title, h2))
            if isinstance(content, str):
                for para in content.split("\n\n"):
                    if para.strip():
                        story.append(Paragraph(para.strip(), body))
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        risk = item.get("risk", "")
                        sev = (item.get("severity") or "").upper()
                        mit = item.get("mitigant", "")
                        story.append(Paragraph(
                            f"• <b>[{sev}]</b> {risk} — <i>Mitigant:</i> {mit}", body
                        ))
                    else:
                        story.append(Paragraph(f"• {item}", body))

        add_section("Executive Summary", memo.get("executive_summary"))
        add_section("Investment Thesis", memo.get("investment_thesis"))
        add_section("Valuation View", memo.get("valuation_view"))

        # Embed football field chart if one exists for this deal
        try:
            from tools.football_field import collect_valuation_ranges, render_football_field
            import tempfile
            ranges = collect_valuation_ranges(deal_info.get("deal_id", ""))
            if ranges:
                ff_path = os.path.join(_OUTPUT_DIR, "_tmp_football_field.png")
                market_cap = deal_info.get("current_market_cap")
                rendered = render_football_field(ranges, ff_path, current_market_cap=market_cap)
                if rendered and os.path.exists(rendered):
                    from reportlab.platypus import Image as RLImage
                    story.append(Spacer(1, 8))
                    story.append(Paragraph("Valuation Football Field", h2))
                    img = RLImage(rendered, width=15 * cm, height=6 * cm)
                    story.append(img)
                    story.append(Spacer(1, 4))
                    story.append(Paragraph(
                        f"Sources: {', '.join(r['method'] for r in ranges)}",
                        meta_style,
                    ))
        except Exception as exc:
            logger.debug("Football field embed in IC memo skipped: %s", exc)

        add_section("Key Risks & Mitigants", memo.get("key_risks"))
        add_section("Due Diligence Summary", memo.get("diligence_summary"))
        add_section("Deal Structure Considerations", memo.get("deal_structure_considerations"))
        add_section("Conditions to Proceed", memo.get("conditions_to_proceed"))
        add_section("Next Steps", memo.get("next_steps"))

        story.extend([
            Spacer(1, 16),
            HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#999999")),
            Paragraph(
                "Prepared by AIBAA — AI Investment Banking Analyst. For internal committee use only. "
                "All valuations are estimates and require human review before any investment decision.",
                meta_style,
            ),
        ])

        doc.build(story)
