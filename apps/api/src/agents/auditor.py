"""Auditor agent for verifying extracted financial data."""
import logging
import json
import re
import math
from typing import Dict, Any

logger = logging.getLogger(__name__)

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

        extraction_mode = preparer_output.get("extraction_mode")

        if extraction_mode == "deterministic_fallback":
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

        if extraction_mode == "structured_spreadsheet":
            verdicts = []
            for entry in audit_trail:
                verdicts.append(
                    {
                        "field": entry["field"],
                        "status": "approved",
                        "auditor_confidence": 0.85,
                        "reason": "Structured spreadsheet extraction provided deterministic sheet/row citations.",
                    }
                )
            return {
                "overall_status": "approved",
                "field_verdicts": verdicts,
                "auditor_notes": "Structured spreadsheet extraction used. Auto-approved pending any downstream triangulation failures.",
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
            raw_response = ask_llm(auditor_system, prompt, task="financial")
            return cls._apply_arithmetic_checks(cls._parse_auditor_response(raw_response), extracted)
        except Exception as exc:
            logger.exception("[Auditor] Audit failed")
            verdicts = [
                {
                    "field": entry["field"],
                    "status": "flagged",
                    "auditor_confidence": 0.4,
                    "reason": "Auditor unavailable. Flagged for review.",
                }
                for entry in audit_trail
            ]
            return {
                "overall_status": "flagged",
                "field_verdicts": verdicts,
                "auditor_notes": "Auditor agent failed. All fields flagged. Check server logs.",
                "corrections": {},
            }

    @staticmethod
    def _apply_arithmetic_checks(result: dict, extracted: dict) -> dict:
        """LLM approval cannot override contradictions in supplied numeric fields."""
        result = dict(result)
        verdicts = list(result.get("field_verdicts") or [])
        corrections = dict(result.get("corrections") or {})
        failures = []

        def numeric(*keys):
            return all(isinstance(extracted.get(key), (int, float)) and not isinstance(extracted[key], bool)
                       and math.isfinite(extracted[key]) for key in keys)

        def reconcile(field, expected):
            proposed = corrections.get(field, extracted[field])
            correction_valid = isinstance(proposed, (int, float)) and not isinstance(proposed, bool) and math.isfinite(proposed)
            if not math.isclose(extracted[field], expected, rel_tol=1e-6, abs_tol=1) or not correction_valid or not math.isclose(proposed, expected, rel_tol=1e-6, abs_tol=1):
                failures.append(field)
                verdicts[:] = [v for v in verdicts if v.get("field") != field]
                verdicts.append({"field": field, "status": "flagged", "auditor_confidence": 1.0,
                                 "reason": "Supplied numeric fields fail deterministic arithmetic reconciliation; analyst review required."})
                corrections[field] = expected

        if numeric("lease_liabilities", "lease_liabilities_current", "lease_liabilities_noncurrent"):
            reconcile("lease_liabilities", extracted["lease_liabilities_current"] + extracted["lease_liabilities_noncurrent"])
        if numeric("net_debt", "total_borrowings", "lease_liabilities", "cash_and_equivalents"):
            ccps = extracted.get("ccps_liability")
            if ccps is None or numeric("ccps_liability"):
                lease_total = corrections.get("lease_liabilities", extracted["lease_liabilities"])
                if isinstance(lease_total, (int, float)) and math.isfinite(lease_total):
                    reconcile("net_debt", extracted["total_borrowings"] + lease_total + (ccps or 0) - extracted["cash_and_equivalents"])
        if failures:
            result.update(overall_status="flagged", field_verdicts=verdicts, corrections=corrections,
                          auditor_notes=str(result.get("auditor_notes", "")) + " Deterministic reconciliation flagged: " + ", ".join(failures) + ". This checks arithmetic, not source authenticity.")
        return result

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
