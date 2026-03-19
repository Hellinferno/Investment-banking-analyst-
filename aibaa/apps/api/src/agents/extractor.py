"""
Preparer agent for financial-data extraction.

This stage forces the model to produce:
1. Reconciliation notes
2. Per-field citations
3. Confidence scores
"""
from typing import Dict, Any
import json
import re

from engine.llm import ask_llm
from agents.prompt_builder import PromptBuilder


class PreparerAgent:
    @classmethod
    def extract(
        cls,
        system_prompt: str,
        document_context: str,
        params: dict,
        company_name: str = "",
    ) -> Dict[str, Any]:
        prompt = PromptBuilder.build_preparer_prompt(params, document_context, company_name)

        try:
            raw_response = ask_llm(system_prompt, prompt)
            parsed = cls._parse_preparer_response(raw_response)

            audit_trail = parsed.pop("audit_trail", [])
            reconciliation_log = parsed.pop("reconciliation_log", "")
            extraction_mode = parsed.pop("extraction_mode", "llm")

            extracted_data = {}
            for key, val in parsed.items():
                if isinstance(val, dict) and "value" in val:
                    extracted_data[key] = val["value"]
                    audit_trail.append(
                        {
                            "field": key,
                            "value": val["value"],
                            "confidence": val.get("confidence", 0.5),
                            "source_citation": val.get("source", "Not cited"),
                            "reasoning": val.get("reasoning", ""),
                        }
                    )
                else:
                    extracted_data[key] = val

            audit_fields = {entry["field"] for entry in audit_trail}
            for key, val in extracted_data.items():
                if key not in audit_fields and key not in {"currency", "extraction_mode", "fallback_profile"}:
                    audit_trail.append(
                        {
                            "field": key,
                            "value": val,
                            "confidence": 0.5 if val is not None else 0.0,
                            "source_citation": "Extracted without explicit citation",
                            "reasoning": "",
                        }
                    )

            return {
                "extracted_data": extracted_data,
                "audit_trail": audit_trail,
                "reconciliation_log": reconciliation_log,
                "extraction_mode": extraction_mode,
            }
        except Exception as exc:
            print(f"[Preparer] Extraction failed: {exc}")
            return {
                "extracted_data": {},
                "audit_trail": [],
                "reconciliation_log": f"Extraction failed: {exc}",
                "extraction_mode": "failed",
            }

    @staticmethod
    def _parse_preparer_response(raw: str) -> dict:
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

        raise ValueError(f"Preparer: could not parse JSON (len={len(raw)})")
