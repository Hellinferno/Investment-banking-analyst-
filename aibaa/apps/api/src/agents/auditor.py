"""
Auditor agent for verifying extracted financial data.

This checker challenges the preparer output using accounting logic and citations.
"""
from typing import Dict, Any
import json
import re

from engine.llm import ask_llm
from agents.prompt_builder import PromptBuilder


class AuditorAgent:
    @classmethod
    def audit(cls, system_prompt: str, preparer_output: Dict[str, Any], company_name: str = "") -> Dict[str, Any]:
        extracted = preparer_output.get("extracted_data", {})
        audit_trail = preparer_output.get("audit_trail", [])
        reconciliation = preparer_output.get("reconciliation_log", "")

        if not extracted:
            return {
                "overall_status": "rejected",
                "field_verdicts": [],
                "auditor_notes": "No data to audit; extraction returned empty.",
                "corrections": {},
            }

        if preparer_output.get("extraction_mode") == "deterministic_fallback":
            verdicts = []
            for entry in audit_trail:
                verdicts.append(
                    {
                        "field": entry["field"],
                        "status": "approved",
                        "auditor_confidence": 0.6,
                        "reason": "Deterministic fallback used; no citation verification available.",
                    }
                )
            return {
                "overall_status": "approved",
                "field_verdicts": verdicts,
                "auditor_notes": "Deterministic fallback used. Auto-approved with reduced confidence.",
                "corrections": {},
            }

        prompt = PromptBuilder.build_auditor_prompt(
            extracted_data=extracted,
            audit_trail=audit_trail,
            reconciliation_log=reconciliation,
            company_name=company_name,
        )

        try:
            auditor_system = PromptBuilder.get_system_prompt("auditor")
            raw_response = ask_llm(auditor_system, prompt)
            return cls._parse_auditor_response(raw_response)
        except Exception as exc:
            print(f"[Auditor] Audit failed: {exc}")
            verdicts = []
            for entry in audit_trail:
                verdicts.append(
                    {
                        "field": entry["field"],
                        "status": "flagged",
                        "auditor_confidence": 0.4,
                        "reason": f"Auditor unavailable ({exc}). Flagged for review.",
                    }
                )
            return {
                "overall_status": "flagged",
                "field_verdicts": verdicts,
                "auditor_notes": f"Auditor agent failed: {exc}. All fields flagged.",
                "corrections": {},
            }

    @staticmethod
    def _parse_auditor_response(raw: str) -> dict:
        text = raw.strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = text.replace("```json", "").replace("```", "").strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            try:
                return json.loads(text[first_brace:last_brace + 1])
            except json.JSONDecodeError:
                pass

        return {
            "overall_status": "flagged",
            "field_verdicts": [],
            "auditor_notes": f"Could not parse auditor response (len={len(raw)}).",
            "corrections": {},
        }

    @classmethod
    def merge_corrections(cls, extracted_data: dict, auditor_result: dict) -> dict:
        merged = dict(extracted_data)
        corrections = auditor_result.get("corrections", {})

        for field_name, corrected_value in corrections.items():
            if corrected_value is not None:
                merged[field_name] = corrected_value

        return merged
