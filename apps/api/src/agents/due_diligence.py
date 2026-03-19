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

from agents.base import BaseAgent
from agents.prompt_builder import PromptBuilder
from engine.llm import ask_llm

logger = logging.getLogger(__name__)

_OUTPUT_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs")


class DueDiligenceAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict):
        super().__init__(
            agent_type="due_diligence",
            task_name="dd_report",
            deal_id=deal_id,
            input_payload=input_payload,
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

            self.act("ask_llm", "performing due diligence risk analysis via LLM")
            prompt = PromptBuilder.build_dd_prompt(doc_context)
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

    def _parse_risk_data(self, raw: str) -> dict:
        """Extract JSON from LLM response with fallback."""
        text = raw.strip()
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                data = json.loads(match.group(0))
                # Clamp score to 0-10
                score = data.get("overall_risk_score", 5)
                data["overall_risk_score"] = max(0.0, min(10.0, float(score)))
                return data
            except (json.JSONDecodeError, ValueError):
                pass

        logger.warning("DueDiligenceAgent: could not parse LLM JSON, using fallback structure.")
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
