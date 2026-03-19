from typing import Dict, Any, Optional, Tuple
import json
import re
import os
from concurrent.futures import ThreadPoolExecutor

from agents.base import BaseAgent
from agents.prompt_builder import PromptBuilder
from agents.extractor import PreparerAgent
from agents.auditor import AuditorAgent
from engine.dcf import DCFEngine
from engine.llm import ask_llm
from engine.triangulator import Triangulator
from engine.comps import ComparableAnalysisEngine
from engine.financial_statement_analyzer import FinancialStatementAnalyzer
from tools.document_parser import extract_structured_financials
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

    # Maximum characters per document fed into the LLM context.
    # Annual reports have financials in the back half, so we keep the tail.
    # ~400 K chars ≈ 100 K tokens — well within Gemini 2.5 Flash's 1 M limit
    # while also fitting the NVIDIA DeepSeek 128 K-token fallback (per doc).
    _MAX_DOC_CHARS = 400_000

    def _extract_document_context(self) -> str:
        docs = store.get_documents_for_deal(self.deal_id)
        if not docs:
            return "No documents available."
        context = ""
        for doc in docs:
            context += f"\n--- Document: {doc.filename} ---\n"
            if doc.parsed_text:
                text = doc.parsed_text
                if len(text) > self._MAX_DOC_CHARS:
                    # Keep the last _MAX_DOC_CHARS: financial statements live at
                    # the back of Indian annual reports (Ind AS format).
                    text = f"[...{len(text) - self._MAX_DOC_CHARS:,} chars omitted for length...]\n" + text[-self._MAX_DOC_CHARS:]
                context += text
            else:
                context += "(Parsing incomplete or text unavailable)"
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
    def _normalize_revenues(revenues: list, reporting_unit: str = "") -> list:
        """
        Convert extracted revenues to absolute INR.

        Handles Indian number systems:
        - Crores: multiply by 1e7
        - Lakhs: multiply by 1e5
        - Millions: multiply by 1e6
        - Absolute: no conversion

        Uses reporting_unit hint when available, falls back to heuristic.
        Guards against double-conversion by checking if values are already
        in the plausible absolute INR range before applying any multiplier.
        """
        if not revenues or not all(isinstance(value, (int, float)) for value in revenues):
            return revenues

        max_val = max(abs(value) for value in revenues)
        if max_val < 1:
            return revenues

        plausible_min = 500_000_000        # ₹50 Cr (smallest company we'd model)
        plausible_max = 20_000_000_000_000  # ₹20L Cr (larger than any Indian company)

        # GUARD: If values are already in the plausible absolute INR range,
        # do NOT apply any unit conversion regardless of reporting_unit.
        # This prevents double-conversion when the LLM already converted to absolute.
        if plausible_min <= max_val <= plausible_max:
            return revenues

        unit = (reporting_unit or "").lower().strip()

        # If reporting unit explicitly specified, use it (with double-conversion guard)
        if unit in ("crores", "crore", "cr"):
            candidate = max_val * 1e7
            if plausible_min <= candidate <= plausible_max:
                return [value * 1e7 for value in revenues]
        if unit in ("lakhs", "lakh", "lacs", "lac"):
            candidate = max_val * 1e5
            if plausible_min <= candidate <= plausible_max:
                return [value * 1e5 for value in revenues]
        if unit in ("millions", "million", "mn"):
            candidate = max_val * 1e6
            if plausible_min <= candidate <= plausible_max:
                return [value * 1e6 for value in revenues]
        if unit in ("absolute", "inr", "rupees"):
            return revenues

        # Heuristic: determine the most likely unit from the value scale.
        # Indian company annual revenues (in absolute INR):
        #   Small-cap: ₹1B-50B (10^9 to 5×10^10)
        #   Mid-cap:   ₹50B-500B (5×10^10 to 5×10^11)
        #   Large-cap: ₹500B-5T (5×10^11 to 5×10^12)
        #   Mega-cap:  ₹5T-20T (5×10^12 to 2×10^13)
        #
        # In crores: small=100-5000, mid=5000-50000, large=50000-500000, mega=500000+
        # In lakhs:  small=10000-500000, mid=500000-5000000, large=5000000+
        #
        # Strategy: try crores first (most common in Indian filings), then lakhs,
        # then assume absolute. Validate that result falls in plausible range.

        if max_val < 1_000_000:
            # Values < 1M → most likely in crores
            candidate_cr = max_val * 1e7
            if plausible_min <= candidate_cr <= plausible_max:
                return [value * 1e7 for value in revenues]
            # Maybe lakhs for very small companies
            candidate_lk = max_val * 1e5
            if plausible_min <= candidate_lk <= plausible_max:
                return [value * 1e5 for value in revenues]
        elif max_val < 100_000_000:
            # Values 1M-100M → could be lakhs (for large-cap) or crores (for mega-cap)
            candidate_lk = max_val * 1e5
            candidate_cr = max_val * 1e7
            if plausible_min <= candidate_lk <= plausible_max and candidate_cr > plausible_max:
                return [value * 1e5 for value in revenues]
            if plausible_min <= candidate_cr <= plausible_max:
                return [value * 1e7 for value in revenues]
            if plausible_min <= candidate_lk <= plausible_max:
                return [value * 1e5 for value in revenues]
        elif max_val < 1_000_000_000:
            # Values 100M-1B → likely lakhs, check
            candidate_lk = max_val * 1e5
            if plausible_min <= candidate_lk <= plausible_max:
                return [value * 1e5 for value in revenues]

        # If already in plausible absolute range, no conversion needed
        return revenues

    @staticmethod
    def _normalize_margins(margins: list) -> list:
        if not margins or not all(isinstance(value, (int, float)) for value in margins):
            return margins
        if any(abs(value) > 1.0 for value in margins):
            return [value / 100.0 for value in margins]
        return margins

    @staticmethod
    def _normalize_shares(shares, profit_after_tax: float = None, basic_eps: float = None,
                          revenues: list = None) -> float:
        """
        Normalize shares outstanding to absolute count.

        Cross-checks with PAT/EPS if available:
            implied_shares = profit_after_tax / basic_eps

        Uses revenue scale to ensure PAT is in the same unit as revenues
        before computing implied shares from EPS.
        """
        min_shares = 4_200_000
        max_shares = 10_000_000_000  # 10B (expanded for mega-cap Indian companies)

        def _eps_implied_shares(pat: float, eps: float) -> float:
            """Compute implied shares from PAT/EPS, handling PAT unit mismatch."""
            if pat is None or eps is None or not isinstance(pat, (int, float)) or not isinstance(eps, (int, float)) or eps <= 0:
                return 0.0
            raw_implied = pat / eps
            # If raw_implied is already in valid range, use it
            if min_shares <= raw_implied <= max_shares:
                return raw_implied
            # PAT might be in Crores while EPS is per-share INR
            # Try Crore conversion: raw_implied * 1e7
            cr_implied = raw_implied * 1e7
            if min_shares <= cr_implied <= max_shares:
                return cr_implied
            # Try Lakh conversion
            lk_implied = raw_implied * 1e5
            if min_shares <= lk_implied <= max_shares:
                return lk_implied
            return raw_implied

        if not isinstance(shares, (int, float)) or shares <= 0:
            eps_shares = _eps_implied_shares(profit_after_tax, basic_eps)
            if min_shares <= eps_shares <= max_shares:
                return eps_shares
            return shares

        if min_shares <= shares <= max_shares:
            # Cross-check with EPS if available
            eps_implied = _eps_implied_shares(profit_after_tax, basic_eps)
            if min_shares <= eps_implied <= max_shares:
                ratio = eps_implied / shares
                if 0.8 <= ratio <= 1.2:
                    return shares  # consistent
                else:
                    return eps_implied  # EPS-derived is more reliable
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

    @classmethod
    def _normalize_balance_sheet_value(cls, value, revenues: list = None) -> float:
        """
        Normalize a balance-sheet monetary value to absolute INR.

        Uses revenue scale as an anchor: if we know revenues are in the
        trillions, a balance-sheet value of 25,000 is almost certainly in
        Crores (₹25,000 Cr = ₹250B), not absolute INR.

        Prevents double-conversion by checking if the value is already
        in a plausible absolute range relative to the revenue scale.
        """
        if not isinstance(value, (int, float)):
            return value
        if value == 0:
            return value

        abs_val = abs(value)

        # If value is already very large (> ₹50 Cr absolute), assume it's absolute
        if abs_val >= 500_000_000:
            return value

        # Use revenue scale to determine the right multiplier
        if revenues and isinstance(revenues, list):
            max_rev = max(abs(r) for r in revenues if isinstance(r, (int, float)))
            if max_rev > 0:
                # If revenue is in absolute range (>₹50Cr=500M), this BS value needs conversion
                if max_rev >= 500_000_000:
                    # Revenue is absolute; BS value < 500M likely needs crore conversion
                    candidate_cr = abs_val * 1e7
                    # BS value should be within reasonable proportion of revenue
                    # (e.g. cash up to 50% of revenue, debt up to 200% of revenue)
                    if candidate_cr <= max_rev * 3:
                        return value * 1e7
                    # Try lakh conversion for smaller values
                    candidate_lk = abs_val * 1e5
                    if candidate_lk <= max_rev * 3:
                        return value * 1e5

        # Legacy fallback: small values likely in Crores
        if abs_val < 100_000:
            return value * 1e7
        return value

    @staticmethod
    def _normalize_net_debt(value) -> float:
        """Legacy wrapper - use _normalize_balance_sheet_value for better accuracy."""
        if not isinstance(value, (int, float)):
            return value
        if value == 0:
            return value
        if abs(value) >= 500_000_000:
            return value
        if abs(value) < 100_000:
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
        ccps_liability = cls._to_number(data.get("ccps_liability"))
        cash = cls._to_number(data.get("cash_and_equivalents"))
        net_debt = cls._to_number(data.get("net_debt"))
        debt_to_equity = cls._to_number(data.get("debt_to_equity"))
        lease_liabilities = cls._to_number(data.get("lease_liabilities"))

        total_debt = (borrowings or 0) + (lease_liabilities or 0) + (ccps_liability or 0)

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
    def _get_audit_entry(field_name: str, audit_trail: list) -> dict:
        for entry in audit_trail or []:
            if entry.get("field") == field_name:
                return entry
        return {}

    @classmethod
    def _field_has_strong_support(cls, field_name: str, audit_trail: list, min_confidence: float = 0.75) -> bool:
        entry = cls._get_audit_entry(field_name, audit_trail)
        if not entry:
            return False

        confidence = float(entry.get("confidence") or 0.0)
        source = str(entry.get("source_citation") or "").lower()
        weak_markers = (
            "without explicit citation",
            "legacy extraction mode",
            "deterministic fallback",
            "not cited",
        )

        return confidence >= min_confidence and not any(marker in source for marker in weak_markers)

    @staticmethod
    def _estimate_tax_loss_carryforward(revenues: list, margins: list, da_percent_rev: float) -> float:
        if not revenues or not margins:
            return 0.0

        estimated_nol = 0.0
        for revenue, margin in zip(revenues, margins):
            if not isinstance(revenue, (int, float)) or not isinstance(margin, (int, float)):
                continue
            ebit = revenue * (margin - da_percent_rev)
            if ebit < 0:
                estimated_nol += abs(ebit)

        return estimated_nol

    @classmethod
    def _build_market_sanity_snapshot(
        cls,
        valuation_data: dict,
        shares_outstanding: Optional[float],
        params: dict,
    ) -> dict:
        market_cap = cls._to_number(params.get("current_market_cap"))
        current_share_price = cls._to_number(params.get("current_share_price"))

        if market_cap is None and current_share_price is not None and shares_outstanding:
            market_cap = current_share_price * shares_outstanding
        if current_share_price is None and market_cap is not None and shares_outstanding:
            current_share_price = market_cap / shares_outstanding

        if market_cap is None and current_share_price is None:
            return {}

        implied_equity_value = cls._to_number(valuation_data.get("implied_equity_value"))
        implied_share_price = cls._to_number(valuation_data.get("implied_share_price"))

        equity_gap_pct = None
        share_price_gap_pct = None
        gap_candidates = []
        reasons = []

        if market_cap is not None and implied_equity_value is not None and market_cap > 0:
            equity_gap_pct = (implied_equity_value - market_cap) / market_cap
            gap_candidates.append(abs(equity_gap_pct))
            reasons.append(
                f"implied equity value vs market cap gap = {equity_gap_pct * 100:.1f}%"
            )

        if current_share_price is not None and implied_share_price is not None and current_share_price > 0:
            share_price_gap_pct = (implied_share_price - current_share_price) / current_share_price
            gap_candidates.append(abs(share_price_gap_pct))
            reasons.append(
                f"implied share price vs market price gap = {share_price_gap_pct * 100:.1f}%"
            )

        max_gap = max(gap_candidates) if gap_candidates else 0.0
        if max_gap >= 0.75:
            status = "flagged"
        elif max_gap >= 0.35:
            status = "warning"
        else:
            status = "ok"

        return {
            "status": status,
            "market_cap": round(market_cap, 2) if market_cap is not None else None,
            "current_share_price": round(current_share_price, 2) if current_share_price is not None else None,
            "implied_equity_value": round(implied_equity_value, 2) if implied_equity_value is not None else None,
            "implied_share_price": round(implied_share_price, 2) if implied_share_price is not None else None,
            "equity_value_gap_pct": round(equity_gap_pct, 4) if equity_gap_pct is not None else None,
            "share_price_gap_pct": round(share_price_gap_pct, 4) if share_price_gap_pct is not None else None,
            "reasons": reasons,
        }

    @staticmethod
    def _infer_public_company_risk_overlay(industry: str, margins: list) -> dict:
        industry_blob = (industry or "").lower()

        # --- Sector marker groups (classification priority: highest → lowest) ---
        it_services_markers = (
            "it services", "it consulting", "information technology",
            "technology services", "software services", "systems integration",
        )
        energy_markers = (
            "oil", "gas", "petroleum", "refinery", "refining", "o2c",
            "hydrocarbon", "petrochemical", "upstream", "downstream",
            "lng", "lpg", "energy",
        )
        telecom_markers = (
            "telecom", "telecommunications", "mobile network",
            "wireless", "broadband", "cellular", "spectrum",
        )
        conglomerate_markers = (
            "conglomerate", "diversified", "holding company",
            "group of companies", "multi-sector", "multi segment",
        )
        manufacturing_markers = (
            "manufacturing", "industrial", "steel", "cement", "auto",
            "automobile", "chemicals", "specialty chemicals", "mining",
            "infrastructure", "power generation", "power transmission",
            "renewable energy", "engineering",
        )
        consumer_stable_markers = (
            "fmcg", "consumer staples", "staples", "food", "beverages",
            "tobacco", "household products", "pharma", "pharmaceutical",
            "healthcare", "hospital", "diagnostics", "retail",
        )
        # High-beta digital: only when NO stable/large-cap sector is present
        high_beta_markers = (
            "fintech", "payments", "digital", "internet", "technology",
            "software", "platform", "e-commerce", "ecommerce", "marketplace",
            "consumer internet", "saas",
        )

        latest_margin = margins[-1] if margins else 0.0
        avg_margin = sum(margins) / len(margins) if margins else 0.0

        beta_floor = 1.0
        size_premium = 0.0
        specific_risk_premium = 0.0
        terminal_exit_multiple = 12.0
        terminal_growth_premium = 0.0
        min_projection_years = 5
        reasons = []

        is_it_services   = any(m in industry_blob for m in it_services_markers)
        is_energy        = any(m in industry_blob for m in energy_markers)
        is_telecom       = any(m in industry_blob for m in telecom_markers)
        is_conglomerate  = any(m in industry_blob for m in conglomerate_markers)
        is_manufacturing = any(m in industry_blob for m in manufacturing_markers)
        is_consumer      = any(m in industry_blob for m in consumer_stable_markers)
        # High-beta only fires when no stable large-cap sector is identified
        is_stable_sector = is_it_services or is_energy or is_telecom or is_conglomerate or is_manufacturing or is_consumer
        is_high_beta     = (not is_stable_sector) and any(m in industry_blob for m in high_beta_markers)

        if is_it_services:
            beta_floor = max(beta_floor, 0.85)
            terminal_exit_multiple = max(terminal_exit_multiple, 18.0)
            terminal_growth_premium = 0.005          # +0.5% for IT recurring revenue
            min_projection_years = max(min_projection_years, 7)
            reasons.append("IT services sector: 18x exit multiple, +0.5% TGR premium, 7-yr forecast")
        elif is_energy:
            beta_floor = max(beta_floor, 1.00)
            terminal_exit_multiple = max(terminal_exit_multiple, 10.0)
            reasons.append("energy/O2C sector: beta ~1.0, 10x terminal multiple, no size/specific premium")
        elif is_telecom:
            beta_floor = max(beta_floor, 0.90)
            terminal_exit_multiple = max(terminal_exit_multiple, 10.0)
            terminal_growth_premium = 0.003          # +0.3% for telecom subscriber growth
            reasons.append("telecom sector: defensive beta, 10x terminal multiple, no size/specific premium")
        elif is_conglomerate:
            beta_floor = max(beta_floor, 1.00)
            terminal_exit_multiple = max(terminal_exit_multiple, 11.0)
            reasons.append("diversified conglomerate: market beta ~1.0, 11x terminal multiple")
        elif is_manufacturing:
            beta_floor = max(beta_floor, 1.00)
            terminal_exit_multiple = max(terminal_exit_multiple, 10.0)
            reasons.append("manufacturing/industrial sector: beta ~1.0, 10x terminal multiple")
        elif is_consumer:
            beta_floor = max(beta_floor, 0.90)
            terminal_exit_multiple = max(terminal_exit_multiple, 13.0)
            reasons.append("consumer staples/pharma/retail sector: defensive beta, 13x multiple")
        elif is_high_beta:
            beta_floor = max(beta_floor, 1.30)
            size_premium = max(size_premium, 0.02)
            specific_risk_premium = max(specific_risk_premium, 0.03)
            terminal_exit_multiple = max(terminal_exit_multiple, 15.0)
            reasons.append("high-beta digital/fintech sector: elevated risk premiums, 15x exit multiple")

        # Loss-making overlay — size/specific premiums suppressed for known stable sectors
        if latest_margin < 0 or avg_margin < 0:
            beta_floor = max(beta_floor, 1.25)
            if not is_stable_sector:
                size_premium = max(size_premium, 0.02)
                specific_risk_premium = max(specific_risk_premium, 0.03)
            min_projection_years = max(min_projection_years, 7)
            reasons.append("turnaround overlay for loss-making operating profile")

        return {
            "beta_floor": beta_floor,
            "size_premium": size_premium,
            "specific_risk_premium": specific_risk_premium,
            "terminal_exit_multiple": terminal_exit_multiple,
            "terminal_growth_premium": terminal_growth_premium,
            "min_projection_years": min_projection_years,
            "reasons": reasons,
        }

    @staticmethod
    def _build_sector_routing_profile(industry: str, margins: list) -> dict:
        industry_blob = (industry or "").lower()
        recent_margins = [
            float(margin)
            for margin in (margins or [])[-3:]
            if isinstance(margin, (int, float))
        ]
        recent_margin_average = (
            sum(recent_margins) / len(recent_margins)
            if recent_margins
            else None
        )

        it_services_markers = (
            "it services",
            "technology services",
            "information technology",
            "software services",
            "consultancy services",
            "it consulting",
        )

        if any(marker in industry_blob for marker in it_services_markers):
            return {
                "sector": "it_services",
                "margin_floor": 0.20,
                "margin_baseline_override": max(recent_margin_average or 0.0, 0.20),
                "da_cap_percent_rev": 0.02,
                "capex_cap_percent_rev": 0.03,
                "nwc_method": "percent_revenue_balance",
                "nwc_percent_rev": -0.01,
                "min_projection_years": 7,
                "reasons": [
                    "sector routing: IT services baseline enabled",
                    "margin anchored to recent operating history with 20% floor",
                    "working capital modeled as -1% of revenue balance (<=0% change on growth)",
                ],
            }

        return {
            "sector": "generic",
            "margin_floor": None,
            "margin_baseline_override": None,
            "da_cap_percent_rev": None,
            "capex_cap_percent_rev": None,
            "nwc_method": "days",
            "nwc_percent_rev": None,
            "min_projection_years": 5,
            "reasons": [],
        }

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
        context_blob = (context or "").lower()
        search_blob = " ".join(filter(None, [company_name, legal_form, listing_status, cin or "", context_blob])).lower()

        is_private = False
        entity_type = "unknown"

        if "private limited" in search_blob or "pvt ltd" in search_blob or "private ltd" in search_blob:
            is_private = True
            entity_type = "private_limited"
            evidence.append("Legal name indicates Private Limited status")

        pre_ipo_markers = (
            "pre-ipo",
            "pre ipo",
            "drhp",
            "p-drhp",
            "proposed listing",
            "proposed bse",
            "proposed nse",
            "offer for sale",
            "initial public offering",
        )
        if any(marker in search_blob for marker in pre_ipo_markers):
            is_private = True
            entity_type = "pre_ipo_unlisted"
            evidence.append("Pre-IPO markers detected (DRHP/proposed listing disclosures)")

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

    @staticmethod
    def _summarize_preparer_quality(audit_trail: list, extracted_data: dict) -> dict:
        confidences = [
            float(entry.get("confidence") or 0.0)
            for entry in (audit_trail or [])
            if isinstance(entry, dict)
        ]
        avg_conf = (sum(confidences) / len(confidences)) if confidences else 0.0

        required_fields = [
            "historical_revenues",
            "historical_ebitda_margins",
            "net_debt",
            "cash_and_equivalents",
            "total_borrowings",
        ]
        present_required = sum(
            1
            for field in required_fields
            if extracted_data.get(field) is not None
        )
        coverage = present_required / len(required_fields)

        low_fields = [
            entry.get("field")
            for entry in (audit_trail or [])
            if float(entry.get("confidence") or 0.0) < 0.65
        ]

        # Weighted quality score for evaluator stage.
        quality_score = round((avg_conf * 0.7) + (coverage * 0.3), 4)
        return {
            "quality_score": quality_score,
            "avg_confidence": round(avg_conf, 4),
            "required_coverage": round(coverage, 4),
            "low_confidence_fields": [field for field in low_fields if field],
        }

    @staticmethod
    def _build_retry_guidance(quality_summary: dict, attempt: int) -> str:
        low_fields = quality_summary.get("low_confidence_fields", [])
        low_fields_text = ", ".join(low_fields[:8]) if low_fields else "key financial fields"
        return (
            "\n\nRETRY_GUIDANCE:\n"
            f"This is extraction retry attempt {attempt}.\n"
            "Focus only on audited annual-report figures, not assumptions.\n"
            f"Prioritize verification for: {low_fields_text}.\n"
            "If a value is not found with citation, return null and explain briefly in reconciliation_log.\n"
            "Do not fabricate values.\n"
        )

    def _extract_structured_spreadsheet_payload(self) -> Optional[dict]:
        best_payload = None
        best_score = -1

        for doc in store.get_documents_for_deal(self.deal_id):
            structured = extract_structured_financials(doc.storage_path, doc.file_type)
            if not structured:
                continue

            extracted_data = structured.get("extracted_data", {})
            score = sum(
                1
                for field in (
                    "historical_revenues",
                    "historical_ebitda_margins",
                    "cash_and_equivalents",
                    "total_borrowings",
                    "shares_outstanding",
                )
                if extracted_data.get(field) not in (None, [], {})
            )
            if score > best_score:
                best_score = score
                best_payload = {**structured, "source_document": doc.filename}

        return best_payload

    @classmethod
    def _build_extraction_checkpoint(
        cls,
        llm_data: dict,
        audit_trail: list,
        auditor_status: str,
        triangulation_result: dict,
        has_uploaded_documents: bool,
        fallback_mode: bool,
        company_context: dict,
    ) -> dict:
        """Validate whether extracted inputs are complete and internally consistent."""
        issues = []
        warnings = []
        checks = []

        def _add_check(name: str, passed: bool, details: str, blocking: bool = False):
            checks.append(
                {
                    "name": name,
                    "passed": passed,
                    "details": details,
                    "blocking": blocking,
                }
            )
            if not passed:
                if blocking:
                    issues.append(f"{name}: {details}")
                else:
                    warnings.append(f"{name}: {details}")

        revenues = llm_data.get("historical_revenues")
        margins = llm_data.get("historical_ebitda_margins")
        borrowings = cls._to_number(llm_data.get("total_borrowings"))
        lease_liabilities = cls._to_number(llm_data.get("lease_liabilities")) or 0.0
        ccps_liability = cls._to_number(llm_data.get("ccps_liability")) or 0.0
        cash = cls._to_number(llm_data.get("cash_and_equivalents"))
        net_debt = cls._to_number(llm_data.get("net_debt"))

        has_core_revenues = (
            isinstance(revenues, list)
            and len(revenues) >= 3
            and all(isinstance(v, (int, float)) and v > 0 for v in revenues)
        )
        _add_check(
            "historical_revenues",
            has_core_revenues,
            "Expected at least 3 positive annual revenue values.",
            blocking=has_uploaded_documents,
        )

        has_core_margins = (
            isinstance(margins, list)
            and len(margins) >= 3
            and all(isinstance(v, (int, float)) and -1.0 < v < 1.0 for v in margins)
        )
        _add_check(
            "historical_ebitda_margins",
            has_core_margins,
            "Expected at least 3 EBITDA margins in decimal form between -1 and 1.",
            blocking=has_uploaded_documents,
        )

        has_debt_cash = borrowings is not None and cash is not None
        _add_check(
            "debt_and_cash_fields",
            has_debt_cash,
            "Both total_borrowings and cash_and_equivalents should be extracted.",
            blocking=has_uploaded_documents,
        )

        has_core_financials = has_core_revenues and has_core_margins and has_debt_cash

        strong_fields = {
            "historical_revenues": cls._field_has_strong_support("historical_revenues", audit_trail, min_confidence=0.70),
            "historical_ebitda_margins": cls._field_has_strong_support("historical_ebitda_margins", audit_trail, min_confidence=0.70),
            "total_borrowings": cls._field_has_strong_support("total_borrowings", audit_trail, min_confidence=0.65),
            "cash_and_equivalents": cls._field_has_strong_support("cash_and_equivalents", audit_trail, min_confidence=0.65),
        }
        enough_strong_support = sum(1 for ok in strong_fields.values() if ok) >= 2
        _add_check(
            "source_confidence",
            enough_strong_support,
            "Too few core fields have strong citation support.",
            blocking=has_uploaded_documents and not fallback_mode,
        )

        if has_debt_cash and net_debt is not None:
            derived_net_debt = (borrowings or 0.0) + lease_liabilities + ccps_liability - (cash or 0.0)
            delta = abs(derived_net_debt - net_debt)
            tolerance = max(abs(derived_net_debt) * 0.10, 50_000_000.0)
            _add_check(
                "net_debt_reconciliation",
                delta <= tolerance,
                f"net_debt mismatch vs derived debt-cash bridge (delta={delta:,.0f}, tolerance={tolerance:,.0f}).",
                blocking=has_uploaded_documents,
            )
        else:
            _add_check(
                "net_debt_reconciliation",
                False,
                "Could not run net-debt reconciliation due to missing fields.",
                blocking=has_uploaded_documents,
            )

        if isinstance(revenues, list) and len(revenues) >= 2 and all(isinstance(v, (int, float)) and v > 0 for v in revenues):
            rounded = {round(v, -7) for v in revenues}
            _add_check(
                "revenue_variability",
                len(rounded) > 1,
                "Extracted revenues appear flat/duplicated across years.",
                blocking=has_uploaded_documents,
            )

        tri_verdict = str(triangulation_result.get("overall_verdict") or "unknown").lower()
        tri_passed = int(triangulation_result.get("passed") or 0)
        tri_total = max(int(triangulation_result.get("total_checks") or 0), 1)
        tri_pass_ratio = tri_passed / tri_total
        _add_check(
            "triangulation",
            tri_verdict != "halt" or (fallback_mode and tri_pass_ratio >= 0.80),
            f"Triangulation verdict is {tri_verdict}.",
            blocking=has_uploaded_documents and not fallback_mode,
        )

        _add_check(
            "auditor",
            str(auditor_status or "").lower() != "rejected",
            f"Auditor status is {auditor_status or 'unknown'}.",
            blocking=has_uploaded_documents,
        )

        if has_uploaded_documents and fallback_mode:
            _add_check(
                "fallback_mode",
                has_core_financials,
                "Deterministic fallback was used instead of direct extraction from documents.",
                blocking=not has_core_financials,
            )

        is_private = bool(company_context.get("is_private_company")) if isinstance(company_context, dict) else False
        shares = cls._to_number(llm_data.get("shares_outstanding"))
        diluted = cls._to_number(llm_data.get("diluted_shares_outstanding"))
        if not is_private:
            _add_check(
                "share_count_presence",
                (shares is not None) or (diluted is not None),
                "Public company context should have shares_outstanding or diluted_shares_outstanding.",
                blocking=False,
            )

        status = "passed" if not issues else "failed"
        return {
            "status": status,
            "blocking_issues": issues,
            "warnings": warnings,
            "checks": checks,
            "summary": (
                "Extraction checkpoint passed."
                if status == "passed"
                else "Extraction checkpoint failed due to blocking data quality issues."
            ),
        }

    @staticmethod
    def _build_synthesis_summary(
        dcf_header: dict,
        comps_snapshot: dict,
        scenario_data: dict,
    ) -> str:
        dcf_ev = dcf_header.get("enterprise_value")
        dcf_eq = dcf_header.get("equity_value")
        dcf_px = dcf_header.get("implied_share_price")
        comps_base = comps_snapshot.get("scenarios", {}).get("base", {})
        comps_eq = comps_base.get("equity_value")
        comps_px = comps_base.get("implied_share_price")

        base = scenario_data.get("base", {}).get("valuation", {})
        bear = scenario_data.get("bear", {}).get("valuation", {})
        bull = scenario_data.get("bull", {}).get("valuation", {})
        base_metric = base.get("share_price") if base.get("share_price") is not None else base.get("equity_value")
        bear_metric = bear.get("share_price") if bear.get("share_price") is not None else bear.get("equity_value")
        bull_metric = bull.get("share_price") if bull.get("share_price") is not None else bull.get("equity_value")

        return (
            "Parallel synthesis complete. "
            f"DCF implies EV={dcf_ev:,.0f} and Equity={dcf_eq:,.0f}" if isinstance(dcf_ev, (int, float)) and isinstance(dcf_eq, (int, float))
            else "Parallel synthesis complete. DCF output available."
        ) + (
            f"; implied price={dcf_px:,.2f}" if isinstance(dcf_px, (int, float)) else ""
        ) + (
            f". Comps base equity={comps_eq:,.0f}" if isinstance(comps_eq, (int, float)) else "."
        ) + (
            f"; comps implied price={comps_px:,.2f}" if isinstance(comps_px, (int, float)) else ""
        ) + (
            f". Scenario range: bear={bear_metric:,.2f}, base={base_metric:,.2f}, bull={bull_metric:,.2f}."
            if all(isinstance(x, (int, float)) for x in [bear_metric, base_metric, bull_metric])
            else ""
        )

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
        deal_industry = getattr(deal, "industry", "") if deal else ""
        has_uploaded_documents = bool(store.get_documents_for_deal(self.deal_id))

        context_header = f"CRITICALLY IMPORTANT: The target company is {company_name} (Deal: {deal_name}).\n"
        context_header += "1. Do not extract data for any other entity.\n"
        context_header += "2. Extract exactly 5 years of historical revenue and EBITDA margins when available.\n"
        context_header += "3. Search thoroughly for total debt, borrowings, lease liabilities, and cash.\n"
        context_header += "   For IT services / technology companies, cash + investments is often 30-60% of revenue.\n"
        context_header += "   Include ALL of: cash, bank balances, current investments, non-current liquid investments, term deposits.\n"
        context_header += "4. Extract CapEx from the cash flow statement and D&A from the profit and loss statement separately.\n"
        context_header += "5. Calculate debt-to-equity from the balance sheet. If the company is debt-free, return 0.0.\n"
        context_header += "6. Extract operating cash flow (net cash from operating activities) from the cash flow statement.\n"
        context_header += "7. Extract Profit After Tax and Basic EPS for shares cross-check.\n\n"
        full_context = context_header + context
        legacy_prompt = PromptBuilder.build_modeling_dcf_prompt(params, full_context)

        generic_defaults = {
            "historical_revenues": [150_000_000_000, 180_000_000_000, 200_000_000_000, 220_000_000_000, 250_000_000_000],
            "historical_ebitda_margins": [0.12, 0.12, 0.12, 0.12, 0.12],
            "net_debt": 0,
            "total_borrowings": 0,
            "ccps_liability": 0,
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

        structured_payload = self._extract_structured_spreadsheet_payload()
        if structured_payload:
            preparer_output = structured_payload
            llm_data = structured_payload.get("extracted_data", {})
            extraction_audit_trail = structured_payload.get("audit_trail", [])
            extraction_mode = structured_payload.get("extraction_mode", "structured_spreadsheet")
            self.observe(
                "Structured spreadsheet extraction captured "
                f"{len(llm_data)} fields from {structured_payload.get('source_document', 'spreadsheet document')}."
            )

        max_extraction_retries = max(1, int(params.get("extraction_retry_limit") or 2))
        quality_threshold = float(params.get("extraction_quality_threshold") or 0.70)
        best_quality_score = -1.0
        best_payload = None
        current_context = full_context
        if not llm_data:
            self.think("[Stage 1/3] Running preparer extraction with evaluator-optimizer retries.")

            for attempt in range(1, max_extraction_retries + 1):
                self.act("preparer_agent", f"Attempt {attempt}: extracting with citations and confidence scores")
                try:
                    attempt_output = PreparerAgent.extract(
                        system_prompt=self.system_prompt,
                        document_context=current_context,
                        params=params,
                        company_name=company_name,
                    )
                    attempt_data = attempt_output.get("extracted_data", {})
                    attempt_audit = attempt_output.get("audit_trail", [])
                    attempt_mode = attempt_output.get("extraction_mode", "llm")

                    quality = self._summarize_preparer_quality(attempt_audit, attempt_data)
                    quality_score = quality["quality_score"]

                    self.observe(
                        f"Preparer attempt {attempt}: fields={len(attempt_data)}, "
                        f"audit={len(attempt_audit)}, quality={quality_score:.2f}."
                    )

                    if quality_score > best_quality_score:
                        best_quality_score = quality_score
                        best_payload = {
                            "preparer_output": attempt_output,
                            "llm_data": attempt_data,
                            "audit_trail": attempt_audit,
                            "extraction_mode": attempt_mode,
                            "quality": quality,
                        }

                    is_fallback_attempt = str(attempt_mode).lower() == "deterministic_fallback"
                    if quality_score >= quality_threshold or is_fallback_attempt:
                        break

                    if has_uploaded_documents:
                        retry_guidance = self._build_retry_guidance(quality, attempt + 1)
                        current_context = full_context + retry_guidance
                except Exception as exc:
                    self.observe(f"Preparer attempt {attempt} failed ({exc}).")

            if best_payload:
                preparer_output = best_payload["preparer_output"]
                llm_data = best_payload["llm_data"]
                extraction_audit_trail = best_payload["audit_trail"]
                extraction_mode = best_payload["extraction_mode"]
                fallback_mode = str(extraction_mode).lower() == "deterministic_fallback"
                fallback_profile = str(llm_data.get("fallback_profile", ""))
                self.observe(
                    f"Selected extraction payload with quality={best_payload['quality']['quality_score']:.2f} "
                    f"(threshold={quality_threshold:.2f})."
                )
            else:
                llm_data = {}
        else:
            self.observe("Skipping LLM preparer because structured spreadsheet extraction already supplied core fields.")

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
            reporting_unit = str(llm_data.get("reporting_unit") or "")

            if llm_data.get("historical_revenues"):
                raw_revenues = llm_data["historical_revenues"]
                llm_data["historical_revenues"] = self._normalize_revenues(raw_revenues, reporting_unit)
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
                    pat = self._to_number(llm_data.get("profit_after_tax"))
                    eps = self._to_number(llm_data.get("basic_eps"))
                    norm_revs = llm_data.get("historical_revenues", [])
                    llm_data[share_field] = self._normalize_shares(raw_shares, pat, eps, norm_revs)
                    if raw_shares != llm_data[share_field]:
                        self.observe(f"Auto-normalized {share_field}: {raw_shares} -> {llm_data[share_field]}")

            # Use normalized revenues as anchor for balance sheet normalization
            normalized_revenues = llm_data.get("historical_revenues", [])

            if llm_data.get("net_debt") is not None:
                raw_nd = llm_data["net_debt"]
                llm_data["net_debt"] = self._normalize_balance_sheet_value(raw_nd, normalized_revenues)
                if raw_nd != llm_data["net_debt"]:
                    self.observe(f"Auto-normalized net_debt: {raw_nd} -> {llm_data['net_debt']}")

            for pct_field in ("cap_ex_percent_rev", "da_percent_rev"):
                if llm_data.get(pct_field) is not None:
                    raw_value = llm_data[pct_field]
                    llm_data[pct_field] = self._normalize_pct_field(raw_value, pct_field)
                    if raw_value != llm_data[pct_field]:
                        self.observe(f"Auto-normalized {pct_field}: {raw_value} -> {llm_data[pct_field]}")

            for debt_field in (
                "total_borrowings",
                "cash_and_equivalents",
                "lease_liabilities",
                "lease_liabilities_current",
                "lease_liabilities_noncurrent",
                "ccps_liability",
            ):
                if llm_data.get(debt_field) is not None:
                    raw_val = llm_data[debt_field]
                    llm_data[debt_field] = self._normalize_balance_sheet_value(raw_val, normalized_revenues)
                    if raw_val != llm_data[debt_field]:
                        self.observe(f"Auto-normalized {debt_field}: {raw_val} -> {llm_data[debt_field]}")

            llm_data = self._enforce_capital_structure_consistency(llm_data)
            if fallback_mode:
                self.observe(f"Using deterministic fallback profile: {fallback_profile or 'default'}")
            self.observe(
                "Normalized extraction payload keys: "
                + ", ".join(sorted(llm_data.keys()))
            )

        if has_uploaded_documents and fallback_mode:
            self.observe(
                "Document extraction fell back to a deterministic profile. "
                "Continuing in fallback mode and marking output as low-confidence."
            )

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

        extraction_checkpoint = self._build_extraction_checkpoint(
            llm_data=llm_data,
            audit_trail=extraction_audit_trail,
            auditor_status=auditor_status,
            triangulation_result=triangulation_result,
            has_uploaded_documents=has_uploaded_documents,
            fallback_mode=fallback_mode,
            company_context=company_context,
        )
        self.observe(
            "Extraction checkpoint "
            + extraction_checkpoint.get("status", "unknown")
            + f" with {len(extraction_checkpoint.get('blocking_issues', []))} blocking issues."
        )

        if extraction_checkpoint.get("status") == "failed" and has_uploaded_documents:
            run_record = store.agent_runs.get(self.run_id)
            if run_record:
                run_record.input_payload["extraction_checkpoint"] = extraction_checkpoint
            issue_summary = "; ".join(extraction_checkpoint.get("blocking_issues", [])[:4])
            self.fail(
                "Extraction checkpoint failed. Required values from documents are incomplete or inconsistent. "
                + issue_summary
            )
            return self.run_id

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

        if has_uploaded_documents:
            missing_required_fields = []
            if historical_revenues == generic_defaults["historical_revenues"]:
                missing_required_fields.append("historical revenues")
            if historical_ebitda_margins == generic_defaults["historical_ebitda_margins"]:
                missing_required_fields.append("historical EBITDA margins")

            if missing_required_fields and not fallback_mode:
                self.fail(
                    "Uploaded documents did not yield verified "
                    + ", ".join(missing_required_fields)
                    + ". DCF aborted instead of using generic company assumptions."
                )
                return self.run_id

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
            # Default: 3.0% aligns to India long-run nominal GDP growth (was 2.5%)
            terminal_growth_rate = params.get("terminal_growth_rate", 0.030)

            terminal_growth_reference = self._to_number(llm_data.get("terminal_growth_reference"))
            if (
                is_private_company
                and terminal_growth_reference is not None
                and 0.0 < terminal_growth_reference < 0.1
                and float(terminal_growth_rate) < terminal_growth_reference
            ):
                terminal_growth_rate = terminal_growth_reference
                data_sources.append(
                    f"terminal_growth_rate: uplifted to extracted reference {terminal_growth_reference * 100:.2f}%"
                )

            risk_overlay = self._infer_public_company_risk_overlay(deal_industry, historical_ebitda_margins)

            # Supplement sector detection with LLM-extracted industry when deal metadata is absent
            if not deal_industry:
                llm_industry = str(llm_data.get("industry_sector", "")).strip()
                if llm_industry:
                    risk_overlay = self._infer_public_company_risk_overlay(llm_industry, historical_ebitda_margins)
                    self.observe(f"Using LLM-extracted industry '{llm_industry}' for risk overlay (deal metadata empty).")
            else:
                llm_industry = str(llm_data.get("industry_sector", "")).strip()

            sector_routing_industry = " ".join(
                part for part in [str(deal_industry or "").strip(), llm_industry] if part
            )
            sector_routing = self._build_sector_routing_profile(
                sector_routing_industry,
                historical_ebitda_margins,
            )
            if sector_routing.get("reasons"):
                self.observe(
                    "Sector routing applied for "
                    f"{sector_routing.get('sector', 'generic')}: "
                    + "; ".join(sector_routing["reasons"])
                )
                data_sources.append(
                    "sector_routing: "
                    + sector_routing.get("sector", "generic").replace("_", " ")
                )

            is_it_services_company = any(
                "IT services sector" in reason for reason in risk_overlay.get("reasons", [])
            ) or sector_routing.get("sector") == "it_services"

            # ── Large-cap revenue guard ────────────────────────────────────────────────
            # Companies with consolidated revenue ≥ ₹50,000 Crore are exchange-traded
            # large-caps.  Size premiums / high specific-risk premiums are only meant for
            # small / illiquid stocks.  Zero them out here regardless of sector overlay.
            if historical_revenues:
                _max_rev = max(historical_revenues)
                if _max_rev >= 500_000_000_000:   # ≥ ₹50,000 Crore (₹5×10^11 absolute)
                    _had_premium = (
                        risk_overlay.get("size_premium", 0) > 0
                        or risk_overlay.get("specific_risk_premium", 0) > 0
                        or risk_overlay.get("beta_floor", 1.0) > 1.10
                    )
                    if _had_premium:
                        risk_overlay = dict(risk_overlay)
                        risk_overlay["size_premium"] = 0.0
                        risk_overlay["specific_risk_premium"] = 0.0
                        risk_overlay["beta_floor"] = min(risk_overlay["beta_floor"], 1.05)
                        risk_overlay["reasons"] = list(risk_overlay.get("reasons", [])) + [
                            f"large-cap guard (rev ₹{_max_rev/1e7:,.0f} Cr ≥ ₹50,000 Cr): "
                            "size & specific premiums zeroed, beta floor capped at 1.05"
                        ]
                        self.observe(
                            f"Large-cap revenue guard: ₹{_max_rev/1e7:,.0f} Cr → "
                            "zeroed size/specific premiums, beta_floor ≤ 1.05."
                        )

            # Apply industry-aware terminal growth premium (e.g. IT services get +0.5%)
            tgr_premium = risk_overlay.get("terminal_growth_premium", 0.0)
            if tgr_premium > 0 and not params.get("terminal_growth_rate"):
                terminal_growth_rate = float(terminal_growth_rate) + tgr_premium
                data_sources.append(
                    f"terminal_growth_rate: industry premium +{tgr_premium * 100:.1f}% applied "
                    f"-> {terminal_growth_rate * 100:.2f}%"
                )

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
                    discount_rate_reference = self._to_number(llm_data.get("discount_rate_reference"))
                    if discount_rate_reference is not None and 0.12 <= discount_rate_reference <= 0.35:
                        wacc_breakdown["reference_discount_rate"] = round(discount_rate_reference, 4)
                        wacc_breakdown["reference_discount_rate_applied"] = True
                        wacc_breakdown["wacc"] = round(discount_rate_reference, 4)
                else:
                    beta, source = self._resolve("beta", params, llm_data, generic_defaults, label="beta")
                    data_sources.append(source)
                    beta = beta if beta else 1.0
                    base_beta = beta
                    beta = max(beta, risk_overlay["beta_floor"])
                    if beta != base_beta:
                        overlay_reason = ", ".join(risk_overlay["reasons"]) or "public-company risk overlay"
                        self.observe(
                            f"Raised beta from {base_beta:.2f}x to {beta:.2f}x due to {overlay_reason}."
                        )
                        data_sources.append(f"beta: floored to {beta:.2f}x ({overlay_reason})")
                    wacc_breakdown = temp_engine.calculate_wacc_breakdown(
                        risk_free_rate=risk_free_rate,
                        equity_risk_premium=equity_risk_premium,
                        beta=beta,
                        cost_of_debt=cost_of_debt,
                        debt_to_equity=debt_to_equity,
                        size_premium=risk_overlay["size_premium"],
                        specific_risk_premium=risk_overlay["specific_risk_premium"],
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

                diluted_shares = llm_data.get("diluted_shares_outstanding")
                if diluted_shares is not None:
                    pat = self._to_number(llm_data.get("profit_after_tax"))
                    eps = self._to_number(llm_data.get("basic_eps"))
                    diluted_shares = self._normalize_shares(diluted_shares, pat, eps, historical_revenues)
                    if diluted_shares and (shares_outstanding is None or diluted_shares > shares_outstanding):
                        shares_outstanding = diluted_shares
                        data_sources.append("shares_outstanding: diluted shares used")
                        self.observe(f"Using diluted shares ({diluted_shares:,.0f}) instead of basic shares.")

                # EPS cross-check: if we have PAT & EPS, verify shares
                pat = self._to_number(llm_data.get("profit_after_tax"))
                eps = self._to_number(llm_data.get("basic_eps"))
                if pat is not None and eps is not None and eps > 0:
                    eps_implied_shares = pat / eps
                    # If PAT is in crores but EPS is per-share, raw ratio is too small.
                    # Try multiplying PAT by crore (1e7) and lakh (1e5) factors.
                    candidates = [eps_implied_shares]
                    if eps_implied_shares < 4_200_000:
                        candidates.append(pat * 1e7 / eps)  # PAT was in Crores
                        candidates.append(pat * 1e5 / eps)  # PAT was in Lakhs
                    for cand in candidates:
                        if 4_200_000 <= cand <= 10_000_000_000:
                            eps_implied_shares = cand
                            break
                    if 4_200_000 <= eps_implied_shares <= 10_000_000_000:
                        if shares_outstanding is None or abs(eps_implied_shares / shares_outstanding - 1) > 0.2:
                            self.observe(
                                f"EPS cross-check: PAT={pat:,.0f} / EPS={eps:.2f} implies "
                                f"{eps_implied_shares:,.0f} shares (was {shares_outstanding:,.0f if shares_outstanding else 'None'})"
                            )
                            if shares_outstanding is None:
                                shares_outstanding = eps_implied_shares
                                data_sources.append("shares_outstanding: computed from PAT/EPS")

                shares_verified = bool(params.get("shares_outstanding")) or self._field_has_strong_support(
                    "shares_outstanding",
                    extraction_audit_trail,
                ) or self._field_has_strong_support(
                    "diluted_shares_outstanding",
                    extraction_audit_trail,
                )

                # For calibrated fallback profiles (non-generic), trust shares at reduced confidence
                is_calibrated_fallback = fallback_mode and fallback_profile and "generic" not in fallback_profile
                if not shares_verified and is_calibrated_fallback and shares_outstanding is not None:
                    shares_verified = True
                    data_sources.append("shares_outstanding: from fallback profile (reduced confidence)")

                if shares_outstanding is not None and shares_verified:
                    shares_for_valuation = float(shares_outstanding)
                else:
                    shares_outstanding = None
                    data_sources.append("shares_outstanding: unverified; per-share valuation suppressed")
            else:
                extracted_shares = llm_data.get("shares_outstanding")
                if extracted_shares is not None:
                    self.observe(
                        "Private company detected; suppressing per-share valuation even though share count was extracted."
                    )

            da_percent_rev, source = self._resolve("da_percent_rev", params, llm_data, generic_defaults, label="da_percent_rev")
            data_sources.append(source)
            da_percent_rev = da_percent_rev if da_percent_rev is not None else 0.056
            da_cap = sector_routing.get("da_cap_percent_rev")
            if da_cap is not None and params.get("da_percent_rev") is None and da_percent_rev > da_cap:
                self.observe(
                    "Sector routing D&A cap applied: "
                    f"{da_percent_rev * 100:.2f}% -> {da_cap * 100:.2f}% of revenue."
                )
                da_percent_rev = da_cap
                data_sources.append(
                    f"da_percent_rev: capped at {da_cap * 100:.1f}% for {sector_routing.get('sector', 'sector profile')}"
                )

            cap_ex_percent_rev, source = self._resolve(
                "cap_ex_percent_rev",
                params,
                llm_data,
                generic_defaults,
                label="cap_ex_percent_rev",
            )
            data_sources.append(source)
            if cap_ex_percent_rev is None:
                # Sector-aware CapEx default:
                #  - Capital-intensive sectors (energy, refinery, telecom, manufacturing, infra):
                #    historically 8–12 % of revenue.
                #  - Asset-light / unknown: 3 % generic fallback.
                _ind_str = " ".join(filter(None, [
                    deal_industry,
                    str(llm_data.get("industry_sector", "")),
                ])).lower()
                _capital_intensive_markers = (
                    "energy", "oil", "gas", "refinery", "refining", "petrochemical",
                    "o2c", "telecom", "telecommunications", "manufacturing", "industrial",
                    "infrastructure", "power", "mining", "steel", "cement",
                    "chemicals", "automotive", "automobile", "engineering",
                )
                _is_capital_intensive = any(m in _ind_str for m in _capital_intensive_markers)
                if _is_capital_intensive:
                    cap_ex_percent_rev = 0.09
                    data_sources.append("cap_ex_percent_rev: 9% sector default (capital-intensive)")
                else:
                    cap_ex_percent_rev = 0.03
                    data_sources.append("cap_ex_percent_rev: 3% generic default")
            capex_cap = sector_routing.get("capex_cap_percent_rev")
            if (
                capex_cap is not None
                and params.get("cap_ex_percent_rev") is None
                and cap_ex_percent_rev is not None
                and cap_ex_percent_rev > capex_cap
            ):
                self.observe(
                    "Sector routing CapEx cap applied: "
                    f"{cap_ex_percent_rev * 100:.2f}% -> {capex_cap * 100:.2f}% of revenue."
                )
                cap_ex_percent_rev = capex_cap
                data_sources.append(
                    f"cap_ex_percent_rev: capped at {capex_cap * 100:.1f}% for {sector_routing.get('sector', 'sector profile')}"
                )

            revenue_cagr_override, source = self._resolve(
                "revenue_cagr_override",
                params,
                llm_data,
                generic_defaults,
                label="revenue_cagr_override",
            )
            data_sources.append(source)

            growth_low = self._to_number(llm_data.get("forecast_revenue_growth_low"))
            growth_high = self._to_number(llm_data.get("forecast_revenue_growth_high"))
            if revenue_cagr_override is None and growth_low is not None and growth_high is not None:
                if 0 < growth_low < 0.5 and 0 < growth_high < 0.5 and growth_high >= growth_low:
                    revenue_cagr_override = (growth_low + growth_high) / 2.0
                    data_sources.append(
                        "revenue_cagr_override: midpoint of extracted growth range "
                        f"({growth_low * 100:.1f}% to {growth_high * 100:.1f}%)"
                    )

            if revenue_cagr_override is not None:
                revenue_cagr_override = self._normalize_pct_field(revenue_cagr_override, "revenue_cagr_override")
            if revenue_cagr_override is None and params.get("revenue_cagr_override_auto") is not None:
                revenue_cagr_override = params["revenue_cagr_override_auto"]
                data_sources.append(f"revenue_cagr_override: auto-capped to {revenue_cagr_override * 100:.1f}%")

            # ── Run-rate anchor (Phase 2 → Phase 3 integration) ────────────────────────
            # If partial-year quarterly data was detected and its implied annual growth
            # diverges from the historical CAGR by more than 3 percentage points,
            # anchor Year 1 growth to the run-rate (takes priority over historical CAGR
            # but yields to any explicit user or LLM-extracted override above).
            if revenue_cagr_override is None and not params.get("revenue_cagr_override"):
                _rr = llm_data.get("partial_year_run_rate")
                # Handle {value: ...} wrapper from LLM preparer vs direct dict from
                # structured spreadsheet extraction.
                if isinstance(_rr, dict) and isinstance(_rr.get("value"), dict):
                    _rr = _rr["value"]
                if isinstance(_rr, dict):
                    _rr_growth = self._to_number(_rr.get("run_rate_growth_vs_last_fy"))
                    if _rr_growth is not None and -0.50 < _rr_growth < 1.0:
                        # Compute historical CAGR for comparison
                        if len(historical_revenues) >= 2 and historical_revenues[0] > 0:
                            _hist_cagr = (
                                (historical_revenues[-1] / historical_revenues[0])
                                ** (1.0 / (len(historical_revenues) - 1))
                            ) - 1
                            _hist_cagr = max(-0.30, min(0.30, _hist_cagr))
                        else:
                            _hist_cagr = 0.08
                        if abs(_rr_growth - _hist_cagr) > 0.03:
                            revenue_cagr_override = max(-0.30, min(0.50, _rr_growth))
                            data_sources.append(
                                f"revenue_cagr_override: run-rate anchor "
                                f"{_rr_growth * 100:.1f}% "
                                f"(historical CAGR={_hist_cagr * 100:.1f}%, "
                                f"Δ={abs(_rr_growth - _hist_cagr) * 100:.1f}pp > 3pp threshold)"
                            )
                            self.observe(
                                f"Run-rate anchor applied: Year 1 CAGR set to "
                                f"{_rr_growth * 100:.1f}% from partial-year data "
                                f"(implied run-rate="
                                f"{_rr.get('implied_annual_run_rate', 0):,.0f} INR, "
                                f"historical CAGR was {_hist_cagr * 100:.1f}%)."
                            )

            nwc_method = str(
                params.get("nwc_method")
                or sector_routing.get("nwc_method")
                or "days"
            ).strip().lower()
            data_sources.append(f"nwc_method: {nwc_method}")

            # NWC: large-cap companies run leaner working capital as % of revenue.
            # ≥ ₹50,000 Cr revenue → 5%; smaller companies → 10% generic default.
            if params.get("nwc_percent_rev") is not None:
                nwc_percent_rev = float(params["nwc_percent_rev"])
                data_sources.append("nwc_percent_rev: user override")
            else:
                _max_rev_nwc = max(historical_revenues) if historical_revenues else 0
                if sector_routing.get("nwc_percent_rev") is not None:
                    nwc_percent_rev = float(sector_routing["nwc_percent_rev"])
                    data_sources.append(
                        f"nwc_percent_rev: {nwc_percent_rev * 100:.1f}% sector routing default"
                    )
                elif _max_rev_nwc >= 500_000_000_000:
                    nwc_percent_rev = 0.05
                    data_sources.append("nwc_percent_rev: 5% (large-cap >= Rs50,000 Cr)")
                else:
                    nwc_percent_rev = 0.10
                    data_sources.append("nwc_percent_rev: 10% generic default")

            base_fy, source = self._resolve("base_fy", params, llm_data, generic_defaults, cast=int, label="base_fy")
            data_sources.append(source)
            base_fy = base_fy if base_fy else 2025

            dso = float(params.get("dso") or 45.0)
            dpo = float(params.get("dpo") or 30.0)
            dio = float(params.get("dio") or 30.0)
            if is_it_services_company:
                if not params.get("dso"):
                    dso = 35.0
                if not params.get("dpo"):
                    dpo = 45.0
                if not params.get("dio"):
                    dio = 0.0
                data_sources.append("working_capital_days: IT services defaults (DSO 35 / DPO 45 / DIO 0)")

            ebitda_margin_override = params.get("ebitda_margin_override")
            if ebitda_margin_override:
                margin_value = float(ebitda_margin_override)
                if margin_value > 1.0:
                    margin_value = margin_value / 100.0
                historical_ebitda_margins = [margin_value] * len(historical_ebitda_margins)

            margin_baseline_override = sector_routing.get("margin_baseline_override")
            if margin_baseline_override is not None and params.get("ebitda_margin_override") is None:
                data_sources.append(
                    "margin_baseline_override: "
                    f"{margin_baseline_override * 100:.1f}% sector routing baseline"
                )

            avg_margin = sum(historical_ebitda_margins) / len(historical_ebitda_margins)
            latest_margin = historical_ebitda_margins[-1]
            is_loss_making = avg_margin < 0 or latest_margin < 0
            if is_loss_making:
                self.observe(f"Warning: negative average EBITDA margin ({avg_margin * 100:.1f}%).")

            self.observe(f"Data source audit: {'; '.join(data_sources)}")

            total_borrowings = llm_data.get("total_borrowings", generic_defaults["total_borrowings"])
            ccps_liability = llm_data.get("ccps_liability", generic_defaults["ccps_liability"])
            lease_liabilities = llm_data.get("lease_liabilities", generic_defaults["lease_liabilities"])
            cash_and_equivalents = llm_data.get("cash_and_equivalents", generic_defaults["cash_and_equivalents"])

            if isinstance(total_borrowings, str):
                total_borrowings = float(total_borrowings)
            if isinstance(ccps_liability, str):
                ccps_liability = float(ccps_liability)
            if isinstance(lease_liabilities, str):
                lease_liabilities = float(lease_liabilities)
            if isinstance(cash_and_equivalents, str):
                cash_and_equivalents = float(cash_and_equivalents)

            total_debt_for_bridge = (total_borrowings or 0) + (lease_liabilities or 0) + (ccps_liability or 0)

            if (
                self._to_number(llm_data.get("total_borrowings")) is not None
                and self._to_number(llm_data.get("cash_and_equivalents")) is not None
            ):
                net_debt = total_debt_for_bridge - (cash_and_equivalents or 0)
                data_sources.append("net_debt: recomputed from borrowings + lease + CCPS - cash")

            projection_years = int(params.get("projection_years") or 5)

            # Industry-aware minimum projection years
            industry_min_years = max(
                risk_overlay.get("min_projection_years", 5),
                sector_routing.get("min_projection_years", 5),
            )
            if projection_years < industry_min_years and not params.get("projection_years"):
                self.observe(
                    f"Industry overlay requires {industry_min_years}+ year forecast; "
                    f"extending from {projection_years} to {industry_min_years} years."
                )
                projection_years = industry_min_years
                data_sources.append(
                    f"projection_years: auto-extended to {industry_min_years} for "
                    + (", ".join(risk_overlay.get("reasons", [])) or "industry profile")
                )

            if is_loss_making and projection_years < 7:
                self.observe(
                    f"Loss-making profile detected; extending explicit forecast period from {projection_years} to 7 years."
                )
                projection_years = 7
                data_sources.append("projection_years: auto-extended to 7 for turnaround profile")

            tax_loss_carryforward = float(
                params.get("tax_loss_carryforward")
                or self._estimate_tax_loss_carryforward(
                    historical_revenues,
                    historical_ebitda_margins,
                    da_percent_rev,
                )
            )

            engine = DCFEngine(
                historical_revenues=historical_revenues,
                historical_ebitda_margins=historical_ebitda_margins,
                tax_rate=tax_rate,
                da_percent_rev=da_percent_rev,
                cap_ex_percent_rev=cap_ex_percent_rev,
                revenue_cagr_override=revenue_cagr_override,
                margin_baseline_override=margin_baseline_override,
                nwc_percent_rev=nwc_percent_rev,
                base_fy=base_fy,
                tax_loss_carryforward=tax_loss_carryforward,
                nwc_method=nwc_method,
                dso=dso,
                dpo=dpo,
                dio=dio,
                total_debt=total_debt_for_bridge,
                cash_and_equivalents=cash_and_equivalents,
            )

            projections_data = engine.build_projections(
                projection_years=projection_years,
                terminal_growth_rate=terminal_growth_rate,
            )
            valuation_data = engine.calculate_valuation(
                ufcf_projections=projections_data["projections"]["ufcf"],
                wacc=wacc,
                terminal_growth_rate=terminal_growth_rate,
                net_debt=net_debt,
                shares_outstanding=shares_for_valuation,
            )
            projections_data["assumptions"]["sector_routing"] = {
                "industry_source": sector_routing_industry or None,
                "profile": sector_routing.get("sector", "generic"),
                "reasons": sector_routing.get("reasons", []),
            }
            self.observe("DCF computed successfully.")

            # ── Post-DCF validation (Phase 3) ──────────────────────────────────────
            dcf_validation_result = {}
            try:
                self.think("Running post-DCF self-check validation.")
                run_rate_data_for_validator = None
                rr = llm_data.get("partial_year_run_rate")
                if isinstance(rr, dict) and rr.get("implied_annual_run_rate"):
                    run_rate_data_for_validator = rr
                elif (
                    isinstance(rr, dict)
                    and isinstance(rr.get("value"), dict)
                    and rr["value"].get("implied_annual_run_rate")
                ):
                    run_rate_data_for_validator = rr["value"]

                dcf_summary_for_validator = {
                    "implied_enterprise_value": valuation_data.get("implied_enterprise_value"),
                    "implied_equity_value": valuation_data.get("implied_equity_value"),
                    "net_debt": valuation_data.get("net_debt"),
                    "projections": {
                        "revenue": projections_data["projections"]["revenue"],
                        "ebitda_margin_pct": projections_data["projections"]["ebitda_margin_pct"],
                    },
                }
                validator_prompt = PromptBuilder.build_dcf_validator_prompt(
                    dcf_output=dcf_summary_for_validator,
                    extracted_data=llm_data,
                    wacc=wacc,
                    run_rate_data=run_rate_data_for_validator,
                )
                validator_system = "You are a DCF quality checker. Return only valid JSON."
                raw_validator_response = ask_llm(validator_system, validator_prompt)
                raw_validator_response = raw_validator_response.strip()
                import re as _re
                raw_validator_response = _re.sub(r"<think>.*?</think>", "", raw_validator_response, flags=_re.DOTALL).strip()
                raw_validator_response = raw_validator_response.replace("```json", "").replace("```", "").strip()
                try:
                    dcf_validation_result = json.loads(raw_validator_response)
                except json.JSONDecodeError:
                    fb = raw_validator_response.find("{")
                    lb = raw_validator_response.rfind("}")
                    if fb != -1 and lb > fb:
                        dcf_validation_result = json.loads(raw_validator_response[fb:lb + 1])

                val_overall = dcf_validation_result.get("overall", "unknown")
                corrections_needed = dcf_validation_result.get("corrections_needed", [])
                self.observe(
                    f"Post-DCF validation: {val_overall}. "
                    + (f"Corrections needed: {corrections_needed}" if corrections_needed else "All checks passed.")
                )
            except Exception as _val_exc:
                self.observe(f"Post-DCF validation skipped ({_val_exc}).")
                dcf_validation_result = {"overall": "skipped", "error": str(_val_exc)}

            private_adjustment_factor = 1.0
            liquidity_discount = 0.0
            control_premium = 0.0
            valuation_basis = "share_price" if shares_for_valuation is not None else "equity_value"
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

            market_sanity = self._build_market_sanity_snapshot(
                valuation_data=valuation_data,
                shares_outstanding=shares_for_valuation,
                params=params,
            )

            ufcf = projections_data["projections"]["ufcf"]
            comps_engine = ComparableAnalysisEngine()
            latest_revenue_for_comps = historical_revenues[-1] if historical_revenues else 0.0
            avg_margin_for_comps = (
                projections_data["assumptions"].get("avg_ebitda_margin")
                if historical_ebitda_margins
                else 0.10
            )

            statement_analyzer = FinancialStatementAnalyzer()
            statement_payload = {
                "revenue": latest_revenue_for_comps,
                "ebitda": latest_revenue_for_comps * avg_margin_for_comps,
                "ebit": latest_revenue_for_comps * max(avg_margin_for_comps - float(da_percent_rev or 0.0), 0.0),
                "net_income": float(llm_data.get("profit_after_tax") or 0.0),
                "current_assets": float(llm_data.get("cash_and_equivalents") or 0.0) + (latest_revenue_for_comps * 0.22),
                "current_liabilities": max(latest_revenue_for_comps * 0.15, 1.0),
                "inventory": latest_revenue_for_comps * 0.04,
                "cash_and_equivalents": float(llm_data.get("cash_and_equivalents") or 0.0),
                "total_debt": float(total_debt_for_bridge or 0.0),
                "shareholders_equity": max((latest_revenue_for_comps * 0.45), 1.0),
                "total_assets": max((latest_revenue_for_comps * 1.25), 1.0),
                "interest_expense": max(float(total_debt_for_bridge or 0.0) * 0.09, 1.0),
                "accounts_receivable": max(latest_revenue_for_comps * 0.18, 1.0),
            }

            historical_periods = []
            if historical_revenues and historical_ebitda_margins:
                history_pairs = list(zip(historical_revenues, historical_ebitda_margins))
                for revenue_hist, margin_hist in history_pairs[-5:]:
                    rev = float(revenue_hist or 0.0)
                    margin = float(margin_hist or 0.0)
                    ebitda_hist = rev * margin
                    ebit_hist = rev * max(margin - float(da_percent_rev or 0.0), 0.0)
                    historical_periods.append({
                        "revenue": rev,
                        "ebitda": ebitda_hist,
                        "ebit": ebit_hist,
                        "net_income": ebit_hist * (1.0 - float(tax_rate or 0.0)),
                        "current_assets": float(llm_data.get("cash_and_equivalents") or 0.0) + (rev * 0.22),
                        "current_liabilities": max(rev * 0.15, 1.0),
                        "inventory": rev * 0.04,
                        "cash_and_equivalents": float(llm_data.get("cash_and_equivalents") or 0.0),
                        "total_debt": float(total_debt_for_bridge or 0.0),
                        "shareholders_equity": max((rev * 0.45), 1.0),
                        "total_assets": max((rev * 1.25), 1.0),
                        "interest_expense": max(float(total_debt_for_bridge or 0.0) * 0.09, 1.0),
                        "accounts_receivable": max(rev * 0.18, 1.0),
                    })

            if historical_periods:
                statement_payload["historical_periods"] = historical_periods

            mc_iterations = int(params.get("monte_carlo_iterations") or 1500)
            mc_var_confidence = float(params.get("monte_carlo_var_confidence_level") or 0.95)
            mc_correlation_matrix = params.get("monte_carlo_correlation_matrix")
            scenario_weights = params.get("scenario_probability_weights") or {
                "bear": 0.25,
                "base": 0.50,
                "bull": 0.25,
            }

            self.think("Running parallel workers for DCF/scenario/comps/financial-statement/Monte Carlo analysis.")
            with ThreadPoolExecutor(max_workers=5) as pool:
                scenario_future = pool.submit(
                    engine.build_full_scenario_analysis,
                    wacc,
                    terminal_growth_rate,
                    float(net_debt),
                    shares_for_valuation,
                    projection_years,
                )
                comps_future = pool.submit(
                    comps_engine.build_comps_snapshot,
                    latest_revenue_for_comps,
                    avg_margin_for_comps,
                    float(net_debt),
                    shares_for_valuation,
                    deal_industry,
                    is_private_company,
                )
                dcf_worker_future = pool.submit(
                    lambda: {
                        "enterprise_value": valuation_data.get("implied_enterprise_value"),
                        "equity_value": valuation_data.get("implied_equity_value"),
                        "implied_share_price": valuation_data.get("implied_share_price"),
                        "wacc": wacc,
                        "terminal_growth_rate": terminal_growth_rate,
                    }
                )
                fs_worker_future = pool.submit(
                    statement_analyzer.analyze,
                    statement_payload,
                    deal_industry,
                )
                monte_carlo_future = pool.submit(
                    engine.run_monte_carlo,
                    ufcf,
                    wacc,
                    terminal_growth_rate,
                    float(net_debt),
                    shares_for_valuation,
                    mc_iterations,
                    int(params.get("monte_carlo_seed") or 42),
                    float(params.get("monte_carlo_growth_volatility") or 0.015),
                    float(params.get("monte_carlo_margin_volatility") or 0.04),
                    float(params.get("monte_carlo_wacc_volatility") or 0.01),
                    float(params.get("monte_carlo_tgr_volatility") or 0.003),
                    mc_correlation_matrix,
                    mc_var_confidence,
                )

                scenario_data = scenario_future.result()
                comps_snapshot = comps_future.result()
                dcf_worker_snapshot = dcf_worker_future.result()
                financial_statement_snapshot = fs_worker_future.result()
                monte_carlo_snapshot = monte_carlo_future.result()

            scenario_planning_snapshot = engine.probability_weighted_scenario_value(
                scenario_data,
                scenario_weights,
            )

            synthesis_summary = self._build_synthesis_summary(
                dcf_worker_snapshot,
                comps_snapshot,
                scenario_data,
            )
            self.observe(
                "Parallel workers completed: DCF summary, comps snapshot, scenario analysis, "
                "financial statement health analysis, and Monte Carlo simulation."
            )

            exit_multiple = float(params.get("exit_multiple") or risk_overlay["terminal_exit_multiple"])
            terminal_ebitda = projections_data["projections"]["ebitda"][-1] if projections_data["projections"]["ebitda"] else None
            tv_crosscheck = engine.terminal_value_crosscheck(
                ufcf,
                terminal_ebitda,
                wacc,
                terminal_growth_rate,
                exit_multiple=exit_multiple,
            )

            if is_private_company:
                for scenario in scenario_data.values():
                    raw_equity_value = scenario["valuation"]["equity_value"]
                    scenario["valuation"]["pre_private_adjustment_equity_value"] = raw_equity_value
                    scenario["valuation"]["equity_value"] = round(raw_equity_value * private_adjustment_factor, 2)
                    scenario["valuation"]["share_price"] = None

            total_projected_revenue = sum(projections_data["projections"]["revenue"])
            sbc_data = engine.calculate_sbc_adjusted(
                valuation_data["implied_equity_value"],
                shares_for_valuation,
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
                metric="share_price" if valuation_basis == "share_price" else "equity_value",
                adjustment_factor=private_adjustment_factor,
            )

            def safe_round(value):
                return round(float(value), 2) if value is not None else None

            if is_private_company:
                ev_bridge = {
                    "enterprise_value": safe_round(valuation_data.get("implied_enterprise_value")),
                    "less_total_debt": safe_round(total_debt_for_bridge),
                    "ccps_liability": safe_round(ccps_liability),
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
                    "ccps_liability": safe_round(ccps_liability),
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
                "sector_routing": projections_data["assumptions"].get("sector_routing", {}),
                "key_field_status": {
                    "shares_verified": shares_for_valuation is not None,
                    "per_share_value_available": shares_for_valuation is not None and not is_private_company,
                    "tax_loss_carryforward_modeled": tax_loss_carryforward > 0,
                },
                "checkpoint": extraction_checkpoint,
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
            if not is_private_company and shares_for_valuation is None:
                warnings.append(
                    "PER-SHARE VALUATION SUPPRESSED: shares outstanding could not be verified from the extraction trail."
                )
            if risk_overlay["reasons"] and not is_private_company:
                warnings.append(
                    "PUBLIC RISK OVERLAY APPLIED: "
                    + "; ".join(risk_overlay["reasons"])
                    + "."
                )
            if sector_routing.get("reasons"):
                warnings.append(
                    "SECTOR ROUTING APPLIED: "
                    + "; ".join(sector_routing["reasons"])
                    + "."
                )
            if market_sanity.get("status") == "flagged":
                warnings.append(
                    "MARKET SANITY CHECK FLAGGED: "
                    + "; ".join(market_sanity.get("reasons", []))
                    + "."
                )
            elif market_sanity.get("status") == "warning":
                warnings.append(
                    "MARKET SANITY CHECK WARNING: "
                    + "; ".join(market_sanity.get("reasons", []))
                    + "."
                )
            if tax_loss_carryforward > 0:
                warnings.append(
                    f"TAX LOSS CARRYFORWARD MODELED: opening NOL estimated at {tax_loss_carryforward:,.0f}."
                )
            if not llm_data:
                warnings.append("EXTRACTION FAILED: using generic fallback values. Results do not reflect the uploaded company's actual financials.")
            fs_health = (
                financial_statement_snapshot.get("analysis", {})
                .get("overall_health", {})
                .get("status")
            )
            if fs_health in {"Poor", "Fair"}:
                warnings.append(
                    f"FINANCIAL HEALTH SIGNAL: {fs_health.upper()} based on ratio benchmark analysis. "
                    "Review leverage, liquidity, and operating profitability assumptions."
                )
            mc_loss_prob = (
                monte_carlo_snapshot.get("summary", {}).get("probability_of_loss")
                if isinstance(monte_carlo_snapshot, dict)
                else None
            )
            if isinstance(mc_loss_prob, (int, float)) and mc_loss_prob >= 0.30:
                warnings.append(
                    f"MONTE CARLO RISK SIGNAL: probability of loss is {mc_loss_prob * 100:.1f}%. "
                    "Stress-case downside appears material."
                )
            if dcf_validation_result.get("overall") == "FAIL":
                failed_checks = dcf_validation_result.get("corrections_needed", [])
                warnings.append(
                    "DCF SELF-CHECK FAILED: "
                    + ("; ".join(failed_checks[:3]) if failed_checks else "model output did not pass all validation checks.")
                )

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
                    "projection_horizon_years": projection_years,
                    "per_share_value_available": shares_for_valuation is not None and not is_private_company,
                },
                "currency": currency,
                "historical": projections_data.get("historical", {}),
                "fy_labels": projections_data["projections"].get("fy_labels", []),
                "scenarios": scenario_data,
                "parallel_analysis": {
                    "dcf_worker": dcf_worker_snapshot,
                    "comps_worker": comps_snapshot,
                    "financial_statement_worker": financial_statement_snapshot,
                    "scenario_planning_worker": scenario_planning_snapshot,
                    "monte_carlo_worker": monte_carlo_snapshot,
                    "synthesis": synthesis_summary,
                },
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
                "market_sanity": market_sanity,
                "dcf_validation": dcf_validation_result,
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
                        "total_borrowings": total_borrowings,
                        "ccps_liability": ccps_liability,
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
