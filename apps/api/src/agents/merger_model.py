"""
MergerModelAgent — merger consequence (accretion/dilution) analysis.

The LLM only extracts inputs (target/acquirer financials, deal assumptions).
All accretion/dilution math is computed deterministically in Python so the
numbers are auditable and never hallucinated.

Outputs:
  1. JSON merger model result (.json)
  2. Excel merger model workbook (.xlsx)
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

_PROJECTION_YEARS = 3


class MergerModelAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict, run_id: str | None = None):
        super().__init__(
            agent_type="merger_model",
            task_name="accretion_dilution",
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("merger_model")

    def run(self) -> str:
        try:
            self.think("Loading deal documents for merger consequence analysis.")
            doc_context = self._extract_document_context()
            deal_info = self._get_deal_info()
            deal_name = deal_info.get("deal_name", "Deal")
            parameters = self.input_payload.get("parameters", {}) or {}

            self.act("ask_llm", "extracting merger model inputs via LLM")
            prompt = PromptBuilder.build_merger_model_prompt(deal_info, doc_context, parameters)
            raw = ask_llm(self.system_prompt, prompt)
            self.observe(f"LLM response received ({len(raw)} chars). Parsing model inputs.")
            inputs = self._parse_inputs(raw)

            # User parameters always override extracted assumptions
            assumptions = inputs.get("assumptions", {}) or {}
            for src_key, dst_key in (
                ("offer_premium_pct", "offer_premium_pct"),
                ("cash_pct", "cash_pct"),
                ("cost_of_debt", "cost_of_debt_pretax"),
                ("annual_synergies", "annual_pretax_synergies"),
            ):
                if parameters.get(src_key) not in (None, ""):
                    try:
                        assumptions[dst_key] = float(parameters[src_key])
                    except (TypeError, ValueError):
                        pass
            if "cash_pct" in assumptions:
                assumptions["stock_pct"] = round(1.0 - float(assumptions.get("cash_pct") or 0.5), 4)
            inputs["assumptions"] = assumptions

            # Fill target equity value from prior DCF run when documents lack it
            dcf_result = self._get_latest_dcf_output()
            dcf_equity = ((dcf_result.get("base") or {}).get("valuation") or {}).get("equity_value")
            if dcf_equity:
                inputs.setdefault("target", {})["dcf_equity_value"] = dcf_equity
                self.observe("Target equity value anchored to prior DCF base case.")

            self.act("merger_engine", "computing pro-forma accretion/dilution deterministically")
            result = self._compute_accretion_dilution(inputs)
            inputs["accretion_dilution"] = result
            self.observe(f"Accretion/dilution computed: {result.get('verdict', 'n/a')}")

            os.makedirs(_OUTPUT_DIR, exist_ok=True)
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)
            date_str = datetime.now().strftime("%Y%m%d")
            json_path = os.path.join(_OUTPUT_DIR, f"{safe_name}_MergerModel_{date_str}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(inputs, f, indent=2, ensure_ascii=False)
            self._register_output(json_path, output_type="json", output_category="valuation")

            self.act("excel_writer", "generating merger model Excel workbook")
            from tools.excel_writer import WorkbookBuilder
            wb = WorkbookBuilder()
            excel_path = wb.write_merger_model(deal_name, inputs)
            self._register_output(excel_path, output_type="xlsx", output_category="valuation")

            self.update_payload("merger_result", inputs)

            confidence = float(inputs.get("extraction_confidence") or 0.6)
            if result.get("status") == "insufficient_acquirer_data":
                confidence = min(confidence, 0.45)
            self.complete(confidence=confidence)

        except Exception as exc:
            logger.exception("MergerModelAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    @staticmethod
    def _compute_accretion_dilution(inputs: dict) -> dict:
        target = inputs.get("target", {}) or {}
        acquirer = inputs.get("acquirer", {}) or {}
        a = inputs.get("assumptions", {}) or {}

        def num(d: dict, key: str, default: float | None = None) -> float | None:
            v = d.get(key)
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default

        premium = num(a, "offer_premium_pct", 0.25)
        cash_pct = num(a, "cash_pct", 0.50)
        stock_pct = num(a, "stock_pct", 1.0 - cash_pct)
        cost_of_debt = num(a, "cost_of_debt_pretax", 0.09)
        tax_rate = num(a, "tax_rate", 0.25)
        synergies = num(a, "annual_pretax_synergies", 0.0) or 0.0
        phase_in = a.get("synergies_phase_in") or [0.5, 0.75, 1.0]

        target_ni = num(target, "net_income")
        target_equity = num(target, "dcf_equity_value")
        if target_equity is None:
            t_eps = num(target, "eps")
            t_shares = num(target, "shares_outstanding")
            # Without a DCF anchor or market cap, value the target at a deal P/E
            # of 20x earnings as a placeholder (flagged in caveats below).
            if target_ni is not None:
                target_equity = target_ni * 20.0
            elif t_eps is not None and t_shares is not None:
                target_equity = t_eps * t_shares * 20.0

        acq_ni = num(acquirer, "net_income")
        acq_shares = num(acquirer, "shares_outstanding")
        acq_price = num(acquirer, "share_price")
        if acq_price is None and acq_shares and num(acquirer, "pe") and num(acquirer, "eps"):
            acq_price = num(acquirer, "pe") * num(acquirer, "eps")

        missing = [
            name
            for name, val in (
                ("target_net_income", target_ni),
                ("target_equity_value", target_equity),
                ("acquirer_net_income", acq_ni),
                ("acquirer_shares_outstanding", acq_shares),
                ("acquirer_share_price", acq_price),
            )
            if val is None
        ]
        if missing:
            return {
                "status": "insufficient_acquirer_data",
                "missing_inputs": missing,
                "note": (
                    "Accretion/dilution requires both target and acquirer financials. "
                    "Provide acquirer_name plus acquirer financial documents, or pass "
                    "the missing values as run parameters."
                ),
            }

        offer_value = target_equity * (1.0 + premium)
        cash_consideration = offer_value * cash_pct
        stock_consideration = offer_value * stock_pct
        new_shares_issued = stock_consideration / acq_price if acq_price else 0.0
        after_tax_interest = cash_consideration * cost_of_debt * (1.0 - tax_rate)

        standalone_eps: list[float] = []
        proforma_eps: list[float] = []
        accretion_pct: list[float] = []
        proforma_shares = acq_shares + new_shares_issued

        for yr in range(_PROJECTION_YEARS):
            phase = phase_in[yr] if yr < len(phase_in) else 1.0
            synergy_after_tax = synergies * float(phase) * (1.0 - tax_rate)
            pf_ni = acq_ni + target_ni + synergy_after_tax - after_tax_interest
            sa_eps = acq_ni / acq_shares
            pf_eps = pf_ni / proforma_shares
            standalone_eps.append(round(sa_eps, 4))
            proforma_eps.append(round(pf_eps, 4))
            accretion_pct.append(round((pf_eps / sa_eps) - 1.0, 6))

        yr1 = accretion_pct[0]
        verdict = (
            f"{'ACCRETIVE' if yr1 >= 0 else 'DILUTIVE'} in Year 1 "
            f"({yr1 * 100:+.1f}% EPS impact)"
        )

        return {
            "status": "computed",
            "offer_value": round(offer_value, 2),
            "offer_premium_pct": premium,
            "cash_consideration": round(cash_consideration, 2),
            "stock_consideration": round(stock_consideration, 2),
            "new_shares_issued": round(new_shares_issued, 0),
            "after_tax_interest_cost": round(after_tax_interest, 2),
            "proforma_shares_outstanding": round(proforma_shares, 0),
            "standalone_eps": standalone_eps,
            "proforma_eps": proforma_eps,
            "accretion_dilution_pct": accretion_pct,
            "verdict": verdict,
            "caveats": (
                ["Target equity value proxied at 20x earnings — no DCF anchor or market cap available."]
                if num(inputs.get("target", {}) or {}, "dcf_equity_value") is None
                else []
            ),
        }

    def _parse_inputs(self, raw: str) -> dict:
        data = parse_llm_json(raw, required_keys=("target", "acquirer", "assumptions"))
        if data is not None:
            return data
        logger.warning("MergerModelAgent: could not parse valid LLM JSON, using empty input structure.")
        return {
            "target": {},
            "acquirer": {},
            "assumptions": {},
            "extraction_confidence": 0.2,
            "notes": f"LLM output could not be parsed: {raw[:300]}",
        }
