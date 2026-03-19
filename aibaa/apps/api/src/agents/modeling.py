from typing import Dict, Any, Optional, Tuple
import json
import re
import os

from agents.base import BaseAgent
from agents.prompt_builder import PromptBuilder
from agents.extractor import PreparerAgent
from agents.auditor import AuditorAgent
from engine.dcf import DCFEngine
from engine.llm import ask_llm
from engine.triangulator import Triangulator
from tools.excel_writer import WorkbookBuilder
from store import store, Output, ExtractionAudit


class FinancialModelingAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: Dict[str, Any]):
        super().__init__(
            agent_type="modeling",
            task_name=input_payload.get("task_name", "dcf_model"),
            deal_id=deal_id,
            input_payload=input_payload,
        )
        self.system_prompt = PromptBuilder.get_system_prompt(self.agent_type)
        self.excel_tool = WorkbookBuilder()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_document_context(self) -> str:
        docs = store.get_documents_for_deal(self.deal_id)
        if not docs:
            return "No documents available."
        context = ""
        for doc in docs:
            context += f"\n--- Document: {doc.filename} ---\n"
            context += doc.parsed_text if doc.parsed_text else "(Parsing incomplete or text unavailable)"
        return context

    def _resolve(
        self,
        param_key: str,
        params: dict,
        llm_data: dict,
        defaults: dict,
        *,
        cast=float,
        label: str = "",
    ) -> Tuple[Any, str]:
        name = label or param_key

        override = params.get(param_key)
        if override is not None and override != "":
            return cast(override), f"{name}: user override"

        llm_val = llm_data.get(param_key)
        if llm_val is not None and llm_val != "":
            try:
                return cast(llm_val), f"{name}: extracted"
            except (ValueError, TypeError):
                pass

        default = defaults.get(param_key)
        if default is not None:
            return cast(default), f"{name}: generic default"

        return None, f"{name}: missing"

    @staticmethod
    def _parse_llm_response(raw: str) -> dict:
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

        raise ValueError(f"Could not parse JSON from LLM response (length={len(raw)})")

    @staticmethod
    def _normalize_revenues(revenues: list) -> list:
        if not revenues or not all(isinstance(value, (int, float)) for value in revenues):
            return revenues

        max_val = max(abs(value) for value in revenues)
        if max_val < 1:
            return revenues
        if max_val < 100_000:
            return [value * 1e7 for value in revenues]
        if max_val < 10_000_000:
            return [value * 1e5 for value in revenues]
        return revenues

    @staticmethod
    def _normalize_margins(margins: list) -> list:
        if not margins or not all(isinstance(value, (int, float)) for value in margins):
            return margins
        if any(abs(value) > 1.0 for value in margins):
            return [value / 100.0 for value in margins]
        return margins

    @staticmethod
    def _normalize_shares(shares) -> float:
        if not isinstance(shares, (int, float)) or shares <= 0:
            return shares

        min_shares = 4_200_000
        max_shares = 6_400_000_000

        if min_shares <= shares <= max_shares:
            return shares

        if shares < 100:
            candidate = shares * 1e7
            return candidate if min_shares <= candidate <= max_shares else shares

        if shares < 10_000:
            candidate_crore = shares * 1e7
            if min_shares <= candidate_crore <= max_shares:
                return candidate_crore
            candidate_lakh = shares * 1e5
            if min_shares <= candidate_lakh <= max_shares:
                return candidate_lakh
            return shares

        if shares < 100_000:
            candidate = shares * 1e5
            return candidate if min_shares <= candidate <= max_shares else shares

        if shares < min_shares:
            candidate = shares * 1_000
            return candidate if min_shares <= candidate <= max_shares else shares

        return shares

    @staticmethod
    def _normalize_pct_field(value, field_name: str = "") -> float:
        if not isinstance(value, (int, float)):
            return value
        if value > 1.0:
            return value / 100.0
        return value

    @staticmethod
    def _normalize_net_debt(value) -> float:
        if not isinstance(value, (int, float)):
            return value
        if abs(value) < 100_000 and value != 0:
            return value * 1e7
        return value

    @staticmethod
    def _to_number(value) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip().replace(",", "")
            if not cleaned or cleaned.lower() in {"na", "n/a", "null", "none", "-"}:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @classmethod
    def _enforce_capital_structure_consistency(cls, llm_data: dict) -> dict:
        if not llm_data:
            return llm_data

        data = dict(llm_data)
        borrowings = cls._to_number(data.get("total_borrowings"))
        cash = cls._to_number(data.get("cash_and_equivalents"))
        net_debt = cls._to_number(data.get("net_debt"))
        debt_to_equity = cls._to_number(data.get("debt_to_equity"))
        lease_liabilities = cls._to_number(data.get("lease_liabilities"))

        total_debt = (borrowings or 0) + (lease_liabilities or 0)

        if borrowings is not None and cash is not None:
            data["net_debt"] = total_debt - cash
            if total_debt <= 0:
                data["debt_to_equity"] = 0.0
        elif total_debt <= 0:
            data["debt_to_equity"] = 0.0
            if net_debt is not None and net_debt > 0:
                data["net_debt"] = 0.0

        if debt_to_equity is not None and debt_to_equity > 0 and total_debt <= 0:
            data["debt_to_equity"] = 0.0

        return data

    @staticmethod
    def _find_triangulation_match(field_name: str, results: list) -> dict:
        normalized_field = field_name.replace("_", " ").lower()
        field_aliases = {
            "historical_revenues": ["revenue"],
            "historical_ebitda_margins": ["ebitda"],
            "net_debt": ["net debt"],
            "total_borrowings": ["net debt", "debt"],
            "lease_liabilities": ["lease"],
            "cash_and_equivalents": ["net debt", "cash"],
            "shares_outstanding": ["shares"],
            "diluted_shares_outstanding": ["shares"],
            "debt_to_equity": ["d/e", "debt"],
            "cap_ex_percent_rev": ["cash flow", "capex"],
            "da_percent_rev": ["ebitda", "d&a"],
        }
        candidates = field_aliases.get(field_name, [normalized_field])

        for result in results:
            identity = str(result.get("identity", "")).lower()
            if any(candidate in identity for candidate in candidates):
                return result
        return {}

    @staticmethod
    def _extract_cin(text: str) -> Optional[str]:
        if not text:
            return None
        match = re.search(r"\b[LU]\d{5}[A-Z]{2}\d{4}(PTC|PLC)\d{6}\b", text.upper())
        return match.group(0) if match else None

    @classmethod
    def _classify_company_context(cls, company_name: str, context: str, llm_data: dict) -> dict:
        legal_form = str(llm_data.get("company_legal_form") or "").strip()
        listing_status = str(llm_data.get("listing_status") or "").strip().lower()
        cin = str(llm_data.get("cin") or cls._extract_cin(context) or "").strip().upper() or None

        evidence = []
        search_blob = " ".join(filter(None, [company_name, legal_form, listing_status, cin or ""])).lower()

        is_private = False
        entity_type = "unknown"

        if "private limited" in search_blob or "pvt ltd" in search_blob or "private ltd" in search_blob:
            is_private = True
            entity_type = "private_limited"
            evidence.append("Legal name indicates Private Limited status")

        if cin and "PTC" in cin:
            is_private = True
            entity_type = "private_limited"
            evidence.append(f"CIN {cin} contains PTC")
        elif cin and "PLC" in cin and not is_private:
            entity_type = "public_limited"
            evidence.append(f"CIN {cin} contains PLC")

        if listing_status in {"private", "unlisted"} and not is_private:
            is_private = True
            entity_type = "private_limited" if entity_type == "unknown" else entity_type
            evidence.append(f"Listing status extracted as {listing_status}")
        elif listing_status in {"public", "listed"} and entity_type == "unknown":
            entity_type = "listed_public" if listing_status == "listed" else "public_limited"
            evidence.append(f"Listing status extracted as {listing_status}")

        if not is_private and entity_type == "unknown" and company_name.lower().endswith("limited"):
            entity_type = "public_or_unclassified_limited"
            evidence.append("Legal name ends with Limited but no private markers found")

        return {
            "is_private_company": is_private,
            "entity_type": entity_type,
            "listing_status": "private" if is_private else listing_status or "unknown",
            "cin": cin,
            "evidence": evidence,
        }

    # ------------------------------------------------------------------
    # Main Agent Logic
    # ------------------------------------------------------------------

    def run(self) -> str:
        self.think("Initializing Financial Modeling Agent. Verifying task type.")

        if self.task_name != "dcf_model":
            self.fail(f"Unsupported modeling task: {self.task_name}")
            return self.run_id

        self.think("Extracting context from the virtual data room.")
        context = self._extract_document_context()
        self.observe(f"Extracted {len(context)} characters of document context.")

        params = self.input_payload.get("parameters", {})
        deal = store.get_deal(self.deal_id)
        deal_name = deal.name if deal else "Unknown Deal"
        company_name = deal.company_name if deal else "the target company"

        context_header = f"CRITICALLY IMPORTANT: The target company is {company_name} (Deal: {deal_name}).\n"
        context_header += "1. Do not extract data for any other entity.\n"
        context_header += "2. Extract exactly 5 years of historical revenue and EBITDA margins when available.\n"
        context_header += "3. Search thoroughly for total debt, borrowings, lease liabilities, and cash.\n"
        context_header += "4. Extract CapEx from the cash flow statement and D&A from the profit and loss statement separately.\n"
        context_header += "5. Calculate debt-to-equity from the balance sheet. If the company is debt-free, return 0.0.\n\n"
        full_context = context_header + context
        legacy_prompt = PromptBuilder.build_modeling_dcf_prompt(params, full_context)

        generic_defaults = {
            "historical_revenues": [150_000_000_000, 180_000_000_000, 200_000_000_000, 220_000_000_000, 250_000_000_000],
            "historical_ebitda_margins": [0.12, 0.12, 0.12, 0.12, 0.12],
            "net_debt": 0,
            "shares_outstanding": 100_000_000,
            "total_borrowings": 0,
            "lease_liabilities": 0,
            "cash_and_equivalents": 0,
            "cap_ex_percent_rev": 0.03,
            "da_percent_rev": 0.056,
            "debt_to_equity": 0.0,
            "beta": 1.0,
            "size_premium": 0.03,
            "specific_risk_premium": 0.04,
            "liquidity_discount": 0.25,
            "control_premium": 0.0,
            "base_fy": 2025,
            "currency": "INR",
        }

        llm_data = {}
        fallback_mode = False
        fallback_profile = ""
        extraction_mode = "none"
        extraction_audit_trail = []
        auditor_verdicts = []
        triangulation_result = {}
        preparer_output = {}
        auditor_status = "skipped"

        self.think("[Stage 1/3] Running preparer extraction with reconciliation prompting.")
        self.act("preparer_agent", "Extracting financial data with citations and confidence scores")
        try:
            preparer_output = PreparerAgent.extract(
                system_prompt=self.system_prompt,
                document_context=full_context,
                params=params,
                company_name=company_name,
            )
            llm_data = preparer_output.get("extracted_data", {})
            extraction_audit_trail = preparer_output.get("audit_trail", [])
            extraction_mode = preparer_output.get("extraction_mode", "llm")
            fallback_mode = str(extraction_mode).lower() == "deterministic_fallback"
            fallback_profile = str(llm_data.get("fallback_profile", ""))
            self.observe(
                f"Preparer extracted {len(llm_data)} fields with {len(extraction_audit_trail)} audit entries."
            )
        except Exception as exc:
            self.observe(f"Preparer extraction failed ({exc}).")
            llm_data = {}

        if not llm_data:
            self.observe("Preparer returned no usable data. Retrying with legacy extraction prompt.")
            self.act("llm_inference", "Running legacy financial extraction fallback")
            try:
                raw_response = ask_llm(self.system_prompt, legacy_prompt)
                llm_data = self._parse_llm_response(raw_response)
                extraction_mode = str(llm_data.get("extraction_mode", "legacy_llm"))
                fallback_mode = extraction_mode.lower() == "deterministic_fallback"
                fallback_profile = str(llm_data.get("fallback_profile", ""))
                extraction_audit_trail = [
                    {
                        "field": key,
                        "value": value,
                        "confidence": 0.4 if value is not None else 0.0,
                        "source_citation": "Legacy extraction mode without per-field citations",
                        "reasoning": "",
                    }
                    for key, value in llm_data.items()
                    if key not in {"currency", "extraction_mode", "fallback_profile"}
                ]
                self.observe(f"Legacy extraction parsed {len(llm_data)} fields.")
            except Exception as exc:
                self.observe(f"Legacy extraction also failed ({exc}). Will use generic defaults.")
                llm_data = {}
                extraction_audit_trail = []

        if llm_data and extraction_audit_trail:
            self.think("[Stage 2/3] Running auditor verification on extracted fields.")
            self.act("auditor_agent", "Verifying citations and accounting logic")
            try:
                auditor_result = AuditorAgent.audit(
                    system_prompt=PromptBuilder.get_system_prompt("auditor"),
                    preparer_output=preparer_output
                    if preparer_output
                    else {
                        "extracted_data": llm_data,
                        "audit_trail": extraction_audit_trail,
                        "reconciliation_log": "",
                        "extraction_mode": extraction_mode,
                    },
                    company_name=company_name,
                )
                auditor_verdicts = auditor_result.get("field_verdicts", [])
                auditor_status = auditor_result.get("overall_status", "flagged")
                corrections = auditor_result.get("corrections", {})
                if corrections:
                    llm_data = AuditorAgent.merge_corrections(llm_data, auditor_result)
                    self.observe(f"Auditor applied corrections to: {list(corrections.keys())}")
                self.observe(
                    f"Auditor verdict: {auditor_status} with {len(auditor_verdicts)} field checks."
                )
            except Exception as exc:
                auditor_status = "flagged"
                self.observe(f"Auditor stage failed ({exc}). Proceeding with extracted data.")
        else:
            self.observe("Skipping auditor stage because there is no extracted data or audit trail.")

        if llm_data:
            if llm_data.get("historical_revenues"):
                raw_revenues = llm_data["historical_revenues"]
                llm_data["historical_revenues"] = self._normalize_revenues(raw_revenues)
                if raw_revenues != llm_data["historical_revenues"]:
                    self.observe(f"Auto-normalized revenues: {raw_revenues} -> {llm_data['historical_revenues']}")

            if llm_data.get("historical_ebitda_margins"):
                raw_margins = llm_data["historical_ebitda_margins"]
                llm_data["historical_ebitda_margins"] = self._normalize_margins(raw_margins)
                if raw_margins != llm_data["historical_ebitda_margins"]:
                    self.observe(f"Auto-normalized margins: {raw_margins} -> {llm_data['historical_ebitda_margins']}")

            for share_field in ("shares_outstanding", "diluted_shares_outstanding"):
                if llm_data.get(share_field):
                    raw_shares = llm_data[share_field]
                    llm_data[share_field] = self._normalize_shares(raw_shares)
                    if raw_shares != llm_data[share_field]:
                        self.observe(f"Auto-normalized {share_field}: {raw_shares} -> {llm_data[share_field]}")

            if llm_data.get("net_debt") is not None:
                llm_data["net_debt"] = self._normalize_net_debt(llm_data["net_debt"])

            for pct_field in ("cap_ex_percent_rev", "da_percent_rev"):
                if llm_data.get(pct_field) is not None:
                    raw_value = llm_data[pct_field]
                    llm_data[pct_field] = self._normalize_pct_field(raw_value, pct_field)
                    if raw_value != llm_data[pct_field]:
                        self.observe(f"Auto-normalized {pct_field}: {raw_value} -> {llm_data[pct_field]}")

            for debt_field in ("total_borrowings", "cash_and_equivalents", "lease_liabilities"):
                if llm_data.get(debt_field) is not None:
                    llm_data[debt_field] = self._normalize_net_debt(llm_data[debt_field])

            llm_data = self._enforce_capital_structure_consistency(llm_data)
            if fallback_mode:
                self.observe(f"Using deterministic fallback profile: {fallback_profile or 'default'}")
            self.observe(f"Normalized extraction payload: {json.dumps(llm_data)}")

        company_context = self._classify_company_context(company_name, context, llm_data)
        if company_context["evidence"]:
            self.observe(
                f"Company classification: {company_context['entity_type']} "
                f"({'private' if company_context['is_private_company'] else 'public/unknown'}) "
                f"via {', '.join(company_context['evidence'])}"
            )

        if llm_data:
            self.think("[Stage 3/3] Running deterministic accounting triangulation checks.")
            self.act("triangulator", "Checking net debt, shares, EBITDA, and D/E consistency")
            triangulation_result = Triangulator.run_all_checks(llm_data)
            self.observe(
                f"Triangulation verdict: {triangulation_result.get('overall_verdict', 'unknown')} "
                f"({triangulation_result.get('passed', 0)}/{triangulation_result.get('total_checks', 0)} passed)."
            )
        else:
            self.observe("Skipping triangulation because there is no extracted data.")

        audit_records = []
        for entry in extraction_audit_trail:
            field_name = entry.get("field", "unknown")
            auditor_match = next(
                (verdict for verdict in auditor_verdicts if verdict.get("field") == field_name),
                {},
            )
            triangulation_match = self._find_triangulation_match(
                field_name,
                triangulation_result.get("results", []),
            )
            audit_records.append(
                ExtractionAudit(
                    deal_id=self.deal_id,
                    agent_run_id=self.run_id,
                    field_name=field_name,
                    extracted_value=entry.get("value"),
                    confidence_score=entry.get("confidence", 0.5),
                    source_citation=entry.get("source_citation", ""),
                    reasoning=entry.get("reasoning", ""),
                    auditor_status=auditor_match.get("status", "pending"),
                    auditor_confidence=auditor_match.get("auditor_confidence", 0.0),
                    auditor_reason=auditor_match.get("reason", ""),
                    triangulation_status="pass" if triangulation_match.get("passed", True) else "fail",
                    triangulation_details=triangulation_match.get("details", ""),
                )
            )
        store.extraction_audits[self.run_id] = audit_records
        if audit_records:
            self.observe(f"Stored {len(audit_records)} extraction audit records.")

        data_sources = []
        historical_revenues = generic_defaults["historical_revenues"]
        historical_ebitda_margins = generic_defaults["historical_ebitda_margins"]

        if llm_data.get("historical_revenues"):
            candidate_revenues = llm_data["historical_revenues"]
            if (
                isinstance(candidate_revenues, list)
                and len(candidate_revenues) >= 2
                and all(isinstance(value, (int, float)) and value > 100_000_000 for value in candidate_revenues)
            ):
                if len({round(value, -7) for value in candidate_revenues}) == 1:
                    self.observe(f"Extracted revenues look flat ({candidate_revenues}); using generic defaults.")
                    data_sources.append("historical_revenues: generic default (flat extraction)")
                else:
                    historical_revenues = candidate_revenues
                    data_sources.append("historical_revenues: extracted")
            else:
                self.observe(f"Extracted revenues failed sanity ({candidate_revenues}); using generic defaults.")
                data_sources.append("historical_revenues: generic default (sanity failed)")
        else:
            data_sources.append("historical_revenues: generic default (missing)")

        if llm_data.get("historical_ebitda_margins"):
            candidate_margins = llm_data["historical_ebitda_margins"]
            if (
                isinstance(candidate_margins, list)
                and len(candidate_margins) >= 2
                and all(isinstance(value, (int, float)) and -2.0 < value < 0.99 for value in candidate_margins)
            ):
                historical_ebitda_margins = candidate_margins
                data_sources.append("historical_ebitda_margins: extracted")
            else:
                self.observe(f"Extracted margins failed sanity ({candidate_margins}); using generic defaults.")
                data_sources.append("historical_ebitda_margins: generic default (sanity failed)")
        else:
            data_sources.append("historical_ebitda_margins: generic default (missing)")

        if len(historical_revenues) >= 2:
            latest_revenue = historical_revenues[-1]
            previous_revenue = historical_revenues[-2]
            if previous_revenue > 0:
                latest_yoy = (latest_revenue - previous_revenue) / previous_revenue
                first_revenue = historical_revenues[0]
                year_count = len(historical_revenues) - 1
                historical_cagr = (
                    (latest_revenue / first_revenue) ** (1.0 / year_count) - 1.0
                    if first_revenue > 0 and year_count > 0
                    else latest_yoy
                )
                if latest_yoy < 0.02 and not params.get("revenue_cagr_override"):
                    conservative_cagr = max(min(historical_cagr, 0.06), 0.02)
                    params["revenue_cagr_override_auto"] = conservative_cagr
                    data_sources.append(
                        f"growth_sanity: auto-capped CAGR to {conservative_cagr * 100:.1f}% "
                        f"(latest YoY={latest_yoy * 100:.1f}%)"
                    )
                    self.observe(
                        f"Growth sanity check triggered: latest YoY={latest_yoy * 100:.1f}%, "
                        f"historical CAGR={historical_cagr * 100:.1f}%, auto-capped to {conservative_cagr * 100:.1f}%."
                    )

        self.think("Engaging deterministic DCF computation engine.")
        self.act("python_exec", "Instantiating DCFEngine and calculating WACC and UFCF")
        try:
            is_private_company = company_context["is_private_company"]
            terminal_growth_rate = params.get("terminal_growth_rate", 0.025)

            risk_free_rate, _ = self._resolve("risk_free_rate", params, llm_data, generic_defaults, label="risk_free_rate")
            risk_free_rate = risk_free_rate if risk_free_rate else 0.07

            equity_risk_premium, _ = self._resolve(
                "equity_risk_premium",
                params,
                llm_data,
                generic_defaults,
                label="equity_risk_premium",
            )
            equity_risk_premium = equity_risk_premium if equity_risk_premium else (0.065 if is_private_company else 0.06)

            cost_of_debt, _ = self._resolve("cost_of_debt", params, llm_data, generic_defaults, label="cost_of_debt")
            cost_of_debt = cost_of_debt if cost_of_debt else 0.09

            tax_rate = float(params.get("tax_rate") or 0.25)

            debt_to_equity, source = self._resolve(
                "debt_to_equity",
                params,
                llm_data,
                generic_defaults,
                label="debt_to_equity",
            )
            data_sources.append(source)
            debt_to_equity = debt_to_equity if debt_to_equity is not None else 0.0

            wacc_override = params.get("wacc_override")
            if wacc_override:
                wacc = float(wacc_override)
                wacc_breakdown = {"wacc": wacc, "note": "Manually overridden by user"}
            else:
                temp_engine = DCFEngine(historical_revenues, historical_ebitda_margins, tax_rate=tax_rate)
                if is_private_company:
                    size_premium, source = self._resolve(
                        "size_premium",
                        params,
                        llm_data,
                        generic_defaults,
                        label="size_premium",
                    )
                    data_sources.append(source)
                    size_premium = size_premium if size_premium is not None else 0.03

                    specific_risk_premium, source = self._resolve(
                        "specific_risk_premium",
                        params,
                        llm_data,
                        generic_defaults,
                        label="specific_risk_premium",
                    )
                    data_sources.append(source)
                    specific_risk_premium = specific_risk_premium if specific_risk_premium is not None else 0.04

                    wacc_breakdown = temp_engine.calculate_private_company_wacc_breakdown(
                        risk_free_rate=risk_free_rate,
                        equity_risk_premium=equity_risk_premium,
                        size_premium=size_premium,
                        specific_risk_premium=specific_risk_premium,
                        cost_of_debt=cost_of_debt,
                        debt_to_equity=debt_to_equity,
                    )
                else:
                    beta, source = self._resolve("beta", params, llm_data, generic_defaults, label="beta")
                    data_sources.append(source)
                    beta = beta if beta else 1.0
                    wacc_breakdown = temp_engine.calculate_wacc_breakdown(
                        risk_free_rate=risk_free_rate,
                        equity_risk_premium=equity_risk_premium,
                        beta=beta,
                        cost_of_debt=cost_of_debt,
                        debt_to_equity=debt_to_equity,
                    )
                wacc = wacc_breakdown["wacc"]

            currency = params.get("currency", llm_data.get("currency", generic_defaults["currency"]))

            net_debt, source = self._resolve("net_debt", params, llm_data, generic_defaults, label="net_debt")
            data_sources.append(source)
            net_debt = net_debt if net_debt is not None else 0

            shares_outstanding = None
            shares_for_valuation = None
            if not is_private_company:
                shares_outstanding, source = self._resolve(
                    "shares_outstanding",
                    params,
                    llm_data,
                    generic_defaults,
                    label="shares_outstanding",
                )
                data_sources.append(source)
                shares_outstanding = shares_outstanding if shares_outstanding else 100_000_000

                diluted_shares = llm_data.get("diluted_shares_outstanding")
                if diluted_shares is not None:
                    diluted_shares = self._normalize_shares(diluted_shares)
                    if diluted_shares and diluted_shares > shares_outstanding:
                        shares_outstanding = diluted_shares
                        data_sources.append("shares_outstanding: diluted shares used")
                        self.observe(f"Using diluted shares ({diluted_shares:,.0f}) instead of basic shares.")

                shares_for_valuation = float(shares_outstanding)
            else:
                extracted_shares = llm_data.get("shares_outstanding")
                if extracted_shares is not None:
                    self.observe(
                        "Private company detected; suppressing per-share valuation even though share count was extracted."
                    )

            da_percent_rev, source = self._resolve("da_percent_rev", params, llm_data, generic_defaults, label="da_percent_rev")
            data_sources.append(source)
            da_percent_rev = da_percent_rev if da_percent_rev is not None else 0.056

            cap_ex_percent_rev, source = self._resolve(
                "cap_ex_percent_rev",
                params,
                llm_data,
                generic_defaults,
                label="cap_ex_percent_rev",
            )
            data_sources.append(source)
            cap_ex_percent_rev = cap_ex_percent_rev if cap_ex_percent_rev is not None else 0.03

            revenue_cagr_override, source = self._resolve(
                "revenue_cagr_override",
                params,
                llm_data,
                generic_defaults,
                label="revenue_cagr_override",
            )
            data_sources.append(source)
            if revenue_cagr_override is not None:
                revenue_cagr_override = self._normalize_pct_field(revenue_cagr_override, "revenue_cagr_override")
            if revenue_cagr_override is None and params.get("revenue_cagr_override_auto") is not None:
                revenue_cagr_override = params["revenue_cagr_override_auto"]
                data_sources.append(f"revenue_cagr_override: auto-capped to {revenue_cagr_override * 100:.1f}%")

            nwc_percent_rev = float(params.get("nwc_percent_rev") or 0.10)

            base_fy, source = self._resolve("base_fy", params, llm_data, generic_defaults, cast=int, label="base_fy")
            data_sources.append(source)
            base_fy = base_fy if base_fy else 2025

            dso = float(params.get("dso") or 45.0)
            dpo = float(params.get("dpo") or 30.0)
            dio = float(params.get("dio") or 30.0)

            ebitda_margin_override = params.get("ebitda_margin_override")
            if ebitda_margin_override:
                margin_value = float(ebitda_margin_override)
                if margin_value > 1.0:
                    margin_value = margin_value / 100.0
                historical_ebitda_margins = [margin_value] * len(historical_ebitda_margins)

            avg_margin = sum(historical_ebitda_margins) / len(historical_ebitda_margins)
            is_loss_making = avg_margin < 0
            if is_loss_making:
                self.observe(f"Warning: negative average EBITDA margin ({avg_margin * 100:.1f}%).")

            self.observe(f"Data source audit: {'; '.join(data_sources)}")

            total_borrowings = llm_data.get("total_borrowings", generic_defaults["total_borrowings"])
            lease_liabilities = llm_data.get("lease_liabilities", generic_defaults["lease_liabilities"])
            cash_and_equivalents = llm_data.get("cash_and_equivalents", generic_defaults["cash_and_equivalents"])

            if isinstance(total_borrowings, str):
                total_borrowings = float(total_borrowings)
            if isinstance(lease_liabilities, str):
                lease_liabilities = float(lease_liabilities)
            if isinstance(cash_and_equivalents, str):
                cash_and_equivalents = float(cash_and_equivalents)

            total_debt_for_bridge = (total_borrowings or 0) + (lease_liabilities or 0)

            engine = DCFEngine(
                historical_revenues=historical_revenues,
                historical_ebitda_margins=historical_ebitda_margins,
                tax_rate=tax_rate,
                da_percent_rev=da_percent_rev,
                cap_ex_percent_rev=cap_ex_percent_rev,
                revenue_cagr_override=revenue_cagr_override,
                nwc_percent_rev=nwc_percent_rev,
                base_fy=base_fy,
                dso=dso,
                dpo=dpo,
                dio=dio,
                total_debt=total_debt_for_bridge,
                cash_and_equivalents=cash_and_equivalents,
            )

            projections_data = engine.build_projections(projection_years=7, terminal_growth_rate=terminal_growth_rate)
            valuation_data = engine.calculate_valuation(
                ufcf_projections=projections_data["projections"]["ufcf"],
                wacc=wacc,
                terminal_growth_rate=terminal_growth_rate,
                net_debt=net_debt,
                shares_outstanding=shares_for_valuation,
            )
            self.observe("DCF computed successfully.")

            private_adjustment_factor = 1.0
            liquidity_discount = 0.0
            control_premium = 0.0
            valuation_basis = "share_price"
            if is_private_company:
                liquidity_discount, source = self._resolve(
                    "liquidity_discount",
                    params,
                    llm_data,
                    generic_defaults,
                    label="liquidity_discount",
                )
                data_sources.append(source)
                liquidity_discount = liquidity_discount if liquidity_discount is not None else 0.25

                control_premium, source = self._resolve(
                    "control_premium",
                    params,
                    llm_data,
                    generic_defaults,
                    label="control_premium",
                )
                data_sources.append(source)
                control_premium = control_premium if control_premium is not None else 0.0

                private_adjustment_factor = (1 - liquidity_discount) * (1 + control_premium)
                raw_equity_value = valuation_data["implied_equity_value"]
                valuation_data["pre_private_adjustment_equity_value"] = raw_equity_value
                valuation_data["liquidity_discount"] = liquidity_discount
                valuation_data["control_premium"] = control_premium
                valuation_data["implied_equity_value"] = round(raw_equity_value * private_adjustment_factor, 2)
                valuation_data["implied_share_price"] = None
                valuation_basis = "equity_value"

            ufcf = projections_data["projections"]["ufcf"]
            scenario_data = engine.build_full_scenario_analysis(wacc, terminal_growth_rate, float(net_debt), shares_for_valuation)
            tv_crosscheck = engine.terminal_value_crosscheck(ufcf, wacc, terminal_growth_rate, exit_multiple=12.0)

            if is_private_company:
                for scenario in scenario_data.values():
                    raw_equity_value = scenario["valuation"]["equity_value"]
                    scenario["valuation"]["pre_private_adjustment_equity_value"] = raw_equity_value
                    scenario["valuation"]["equity_value"] = round(raw_equity_value * private_adjustment_factor, 2)
                    scenario["valuation"]["share_price"] = None

            total_projected_revenue = sum(projections_data["projections"]["revenue"])
            sbc_data = engine.calculate_sbc_adjusted(
                valuation_data["implied_equity_value"],
                shares_for_valuation or 1,
                sbc_pct_rev=0.01,
                total_projected_revenue=total_projected_revenue,
            )

            margin_sensitivity = engine.calculate_margin_sensitivity(
                projections_data["projections"]["revenue"],
                wacc,
                terminal_growth_rate,
                float(net_debt),
                shares_for_valuation,
                base_margin=projections_data["assumptions"]["avg_ebitda_margin"],
            )

            capex_sensitivity = engine.calculate_capex_sensitivity(
                ufcf,
                projections_data["projections"]["revenue"],
                wacc,
                terminal_growth_rate,
                float(net_debt),
                shares_for_valuation,
                float(cap_ex_percent_rev),
            )

            sensitivity = engine.build_sensitivity_matrix(
                ufcf,
                wacc,
                terminal_growth_rate,
                float(net_debt),
                shares_for_valuation,
                metric="equity_value" if is_private_company else "share_price",
                adjustment_factor=private_adjustment_factor,
            )

            def safe_round(value):
                return round(float(value), 2) if value is not None else 0.0

            if is_private_company:
                ev_bridge = {
                    "enterprise_value": safe_round(valuation_data.get("implied_enterprise_value")),
                    "less_total_debt": safe_round(total_debt_for_bridge),
                    "lease_liabilities": safe_round(lease_liabilities),
                    "add_cash": safe_round(cash_and_equivalents),
                    "net_debt": safe_round(net_debt),
                    "pre_private_adjustment_equity_value": safe_round(valuation_data.get("pre_private_adjustment_equity_value")),
                    "liquidity_discount_percent": liquidity_discount,
                    "control_premium_percent": control_premium,
                    "equity_value": safe_round(valuation_data.get("implied_equity_value")),
                }
            else:
                ev_bridge = {
                    "enterprise_value": safe_round(valuation_data.get("implied_enterprise_value")),
                    "less_total_debt": safe_round(total_debt_for_bridge),
                    "lease_liabilities": safe_round(lease_liabilities),
                    "add_cash": safe_round(cash_and_equivalents),
                    "net_debt": safe_round(net_debt),
                    "is_net_cash": float(net_debt) < 0 if net_debt is not None else False,
                    "equity_value": safe_round(valuation_data.get("implied_equity_value")),
                    "shares_outstanding": shares_outstanding,
                    "implied_price_per_share": safe_round(valuation_data.get("implied_share_price")),
                }

            docs = store.get_documents_for_deal(self.deal_id)
            if llm_data and fallback_mode:
                data_source_mode = "Deterministic Fallback"
            elif llm_data and extraction_mode == "legacy_llm":
                data_source_mode = "Legacy LLM Extraction"
            elif llm_data:
                data_source_mode = "Maker-Checker Pipeline"
            else:
                data_source_mode = "Generic Defaults"

            audit_trail_summary = [
                {
                    "field": record.field_name,
                    "confidence": record.confidence_score,
                    "source": record.source_citation,
                    "auditor_status": record.auditor_status,
                    "triangulation": record.triangulation_status,
                }
                for record in audit_records
            ]

            extraction_quality = {
                "mode": data_source_mode,
                "source_type": docs[0].file_type.upper() if docs else "N/A",
                "pages_parsed": "N/A",
                "missing_fields": "none" if llm_data else "all (using generic fallbacks)",
                "is_loss_making": is_loss_making,
                "data_sources": data_sources,
                "pipeline_stages": ["Preparer", "Auditor", "Triangulator"],
                "audit_trail": audit_trail_summary,
                "triangulation": triangulation_result,
                "company_classification": company_context,
            }

            warnings = list(valuation_data.get("warnings", []))
            if is_loss_making:
                warnings.append(f"NEGATIVE EBITDA MARGIN ({avg_margin * 100:.1f}%): company is loss-making.")
            if fallback_mode:
                warnings.append(
                    "DETERMINISTIC FALLBACK USED: the model relied on a predefined extraction profile "
                    f"({fallback_profile or 'default'})."
                )
            if auditor_status in {"flagged", "rejected"}:
                warnings.append(f"AUDITOR STATUS: {auditor_status.upper()}. Review extracted facts before relying on the valuation.")
            if triangulation_result.get("overall_verdict") == "halt":
                warnings.append("TRIANGULATION FAILED: fundamental accounting identities did not reconcile.")
            elif triangulation_result.get("overall_verdict") == "warning":
                warnings.append("TRIANGULATION WARNING: some extracted facts did not fully reconcile.")
            if is_private_company:
                warnings.append(
                    "PRIVATE COMPANY DETECTED: per-share valuation suppressed; using build-up cost of equity "
                    "and applying illiquidity adjustments."
                )
            if not llm_data:
                warnings.append("EXTRACTION FAILED: using generic fallback values. Results do not reflect the uploaded company's actual financials.")

            valuation_result = {
                "header": {
                    "enterprise_value": valuation_data["implied_enterprise_value"],
                    "equity_value": valuation_data["implied_equity_value"],
                    "implied_share_price": valuation_data["implied_share_price"],
                    "wacc": wacc,
                    "wacc_breakdown": wacc_breakdown,
                    "terminal_method": "Gordon",
                    "currency": currency,
                    "valuation_basis": valuation_basis,
                    "is_private_company": is_private_company,
                    "company_type": company_context["entity_type"],
                    "liquidity_discount": liquidity_discount if is_private_company else None,
                    "control_premium": control_premium if is_private_company else None,
                },
                "currency": currency,
                "historical": projections_data.get("historical", {}),
                "fy_labels": projections_data["projections"].get("fy_labels", []),
                "scenarios": scenario_data,
                "ev_bridge": ev_bridge,
                "tv_crosscheck": tv_crosscheck,
                "sbc_adjusted": sbc_data,
                "margin_sensitivity": margin_sensitivity,
                "capex_sensitivity": capex_sensitivity,
                "sensitivity_wacc_tgr": sensitivity.get("matrix", []),
                "sensitivity_labels": {
                    "wacc": sensitivity.get("wacc_headers", []),
                    "tgr": sensitivity.get("tgr_headers", []),
                    "metric": sensitivity.get("metric", valuation_basis),
                },
                "extraction_quality": extraction_quality,
                "company_classification": company_context,
                "assumptions": projections_data["assumptions"],
                "uploaded_company": deal_name,
                "warnings": warnings,
            }

            self.think("Generating professional Excel output artifact.")
            self.act("excel_writer", "Writing projections and valuation into DCF template")

            try:
                filepath = self.excel_tool.write_dcf_model(
                    deal_name=deal_name,
                    assumptions=projections_data["assumptions"],
                    projections=projections_data["projections"],
                    valuation={
                        **valuation_data,
                        "total_borrowings": total_debt_for_bridge,
                        "lease_liabilities": lease_liabilities,
                        "wacc_breakdown": wacc_breakdown,
                        "valuation_basis": valuation_basis,
                        "is_private_company": is_private_company,
                        "liquidity_discount": liquidity_discount if is_private_company else 0.0,
                        "control_premium": control_premium if is_private_company else 0.0,
                    },
                    currency=currency,
                    historical=projections_data.get("historical"),
                )
                self.observe(f"Workbook correctly saved to {filepath}")
            except Exception as exc:
                self.fail(f"Excel generation failed: {exc}")
                return self.run_id

            new_output = Output(
                deal_id=self.deal_id,
                agent_run_id=self.run_id,
                filename=os.path.basename(filepath),
                output_type="xlsx",
                output_category="financial_model",
                storage_path=filepath,
            )
            store.outputs[new_output.id] = new_output

            run_record = store.agent_runs.get(self.run_id)
            if run_record:
                run_record.input_payload["valuation_result"] = valuation_result

            self.complete(confidence=0.95 if llm_data else 0.6)
        except Exception as exc:
            self.fail(f"Computation or formatting failed: {exc}")

        return self.run_id
