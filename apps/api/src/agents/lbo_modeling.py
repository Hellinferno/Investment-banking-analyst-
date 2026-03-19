"""
LBOModelingAgent — orchestrates the full LBO pipeline:

  1. Extract LBO financials via LLM (using build_lbo_extraction_prompt)
  2. Compute LBO model via LBOEngine
  3. Generate IRR sensitivity matrix
  4. Write IB-quality Excel workbook via WorkbookBuilder.write_lbo_model()
  5. Register output and complete

Mirrors the pattern of agents/modeling.py (FinancialModelingAgent).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from agents.base import BaseAgent
from agents.prompt_builder import PromptBuilder
from engine.llm import ask_llm
from engine.lbo import LBOEngine

logger = logging.getLogger(__name__)


class LBOModelingAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict):
        super().__init__(
            agent_type="modeling",
            task_name="lbo_model",
            deal_id=deal_id,
            input_payload=input_payload,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("modeling")
        self.params = input_payload.get("parameters", {})

    def run(self) -> str:
        try:
            self.think("Starting LBO model pipeline: Extract → Compute → Excel.")
            deal_info = self._get_deal_info()
            company = deal_info.get("company_name", "Company")
            deal_name = deal_info.get("deal_name", "Deal")
            doc_context = self._extract_document_context()

            # ---- Step 1: Extract LBO financials ----
            # Skip LLM if the two required inputs are already in params
            _has_required = (
                self.params.get("entry_ebitda") and self.params.get("revenue_ltm")
            )
            if _has_required:
                extracted = {}
                self.observe("Required LBO params provided directly — skipping LLM extraction.")
            else:
                self.act("llm_extract", "extracting LBO financial inputs from documents")
                prompt = PromptBuilder.build_lbo_extraction_prompt(doc_context, self.params)
                raw = ask_llm(self.system_prompt, prompt)
                extracted = self._parse_extraction(raw)
                self.observe(
                    f"Extracted: EBITDA={extracted.get('entry_ebitda')}, "
                    f"Revenue={extracted.get('revenue_ltm')}, "
                    f"Net Debt={extracted.get('net_debt')}"
                )

            # ---- Step 2: Build LBO Engine inputs ----
            entry_ebitda = self._resolve(extracted, "entry_ebitda", self.params, 0.0)
            revenue_ltm = self._resolve(extracted, "revenue_ltm", self.params, 0.0)

            if not entry_ebitda or entry_ebitda <= 0:
                raise ValueError(
                    f"Could not extract a valid EBITDA for {company}. "
                    "Upload financial statements with EBITDA data."
                )
            if not revenue_ltm or revenue_ltm <= 0:
                # Approximate revenue from EBITDA and a default 20% margin
                revenue_ltm = entry_ebitda / 0.20
                self.observe(f"Revenue not found — approximating from EBITDA: {revenue_ltm:.0f}")

            entry_ev_ebitda = float(self.params.get("entry_ev_ebitda", 8.0))
            equity_contribution_pct = float(self.params.get("equity_contribution_pct", 0.40))
            senior_debt_ebitda = float(self.params.get("senior_debt_ebitda", 3.0))
            mezz_debt_ebitda = float(self.params.get("mezz_debt_ebitda", 0.0))
            exit_ev_ebitda = float(self.params.get("exit_ev_ebitda", entry_ev_ebitda))
            projection_years = int(self.params.get("projection_years", 5))

            # Growth rates from params or defaults
            revenue_growth_rates = self.params.get("revenue_growth_rates") or None
            ebitda_margins = self.params.get("ebitda_margins") or None

            self.think(
                f"LBO inputs: entry EV/EBITDA={entry_ev_ebitda}x, "
                f"equity={equity_contribution_pct*100:.0f}%, "
                f"senior debt={senior_debt_ebitda}x EBITDA, "
                f"exit={exit_ev_ebitda}x, hold={projection_years}y"
            )

            # ---- Step 3: Run LBO Engine ----
            self.act("lbo_engine", "running deterministic LBO computation")
            engine = LBOEngine(
                entry_ebitda=entry_ebitda,
                revenue_ltm=revenue_ltm,
                entry_ev_ebitda=entry_ev_ebitda,
                equity_contribution_pct=equity_contribution_pct,
                senior_debt_ebitda=senior_debt_ebitda,
                mezz_debt_ebitda=mezz_debt_ebitda,
                projection_years=projection_years,
                exit_ev_ebitda=exit_ev_ebitda,
                revenue_growth_rates=revenue_growth_rates,
                ebitda_margins=ebitda_margins,
            )
            lbo_result = engine.run()

            # Compute IRR sensitivity
            self.act("lbo_sensitivity", "computing IRR sensitivity matrix")
            entry_range = [
                round(entry_ev_ebitda - 2, 1),
                round(entry_ev_ebitda - 1, 1),
                entry_ev_ebitda,
                round(entry_ev_ebitda + 1, 1),
                round(entry_ev_ebitda + 2, 1),
            ]
            exit_range = [
                round(exit_ev_ebitda - 2, 1),
                round(exit_ev_ebitda - 1, 1),
                exit_ev_ebitda,
                round(exit_ev_ebitda + 1, 1),
                round(exit_ev_ebitda + 2, 1),
            ]
            # Only use positive multiples
            entry_range = [m for m in entry_range if m > 1]
            exit_range = [m for m in exit_range if m > 1]

            lbo_result["irr_sensitivity"] = engine.irr_sensitivity(entry_range, exit_range)

            self.observe(
                f"LBO complete. IRR={lbo_result['irr_pct']}%, "
                f"MOIC={lbo_result['moic']}x, "
                f"DSCR min={lbo_result['dscr_minimum']}x. "
                f"Warnings: {len(lbo_result.get('warnings', []))}"
            )

            if lbo_result.get("warnings"):
                for w in lbo_result["warnings"]:
                    self.think(f"LBO warning: {w}")

            # ---- Step 4: Write Excel ----
            self.act("excel_writer", "writing LBO model workbook")
            from tools.excel_writer import WorkbookBuilder
            wb = WorkbookBuilder()
            excel_path = wb.write_lbo_model(deal_name, lbo_result)
            self._register_output(excel_path, output_type="xlsx", output_category="lbo_model")
            self.observe(f"LBO Excel written: {excel_path}")

            # ---- Step 5: Store result in payload ----
            self.update_payload("lbo_result", lbo_result)
            self.update_payload("extraction_confidence", extracted.get("extraction_confidence", 0.5))

            self.complete(confidence=0.88)

        except Exception as exc:
            logger.exception("LBOModelingAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_extraction(self, raw: str) -> dict:
        """Parse LBO extraction JSON from LLM response."""
        text = raw.strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        text = text.replace("```json", "").replace("```", "").strip()

        for attempt in [text, text[text.find("{"):text.rfind("}") + 1]]:
            try:
                return json.loads(attempt)
            except (json.JSONDecodeError, ValueError):
                pass

        logger.warning("LBOModelingAgent: could not parse extraction JSON.")
        return {}

    @staticmethod
    def _resolve(extracted: dict, key: str, params: dict, default: Any) -> Any:
        """Priority: params override → extracted → default."""
        if key in params and params[key] is not None:
            return params[key]
        val = extracted.get(key)
        if val is not None:
            return val
        return default
