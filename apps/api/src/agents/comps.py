"""
ValuationCompsAgent — trading comps + precedent transactions analysis.

Combines:
  1. LLM-selected peer set and multiple band (analyst judgment)
  2. Deterministic ComparableAnalysisEngine snapshot (sector-band triangulation)

Outputs:
  1. JSON comps analysis (.json)
  2. Excel comps workbook (.xlsx)
"""
from __future__ import annotations

import json
import logging
import re

from agents.base import BaseAgent, parse_llm_json
from agents.prompt_builder import PromptBuilder
from engine.comps import ComparableAnalysisEngine
from engine.llm import ask_llm

logger = logging.getLogger(__name__)


class ValuationCompsAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict, run_id: str | None = None):
        super().__init__(
            agent_type="comps",
            task_name="comps_analysis",
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )
        self.system_prompt = PromptBuilder.get_system_prompt("comps")

    def run(self) -> str:
        try:
            self.think("Loading deal documents and prior valuation work for comps analysis.")
            doc_context = self._extract_document_context()
            deal_info = self._get_deal_info()
            deal_name = deal_info.get("deal_name", "Deal")
            dcf_result = self._get_latest_dcf_output()

            financial_snapshot = self._build_financial_snapshot(dcf_result)

            self.act("ask_llm", "selecting peer set and multiple band via LLM")
            prompt = PromptBuilder.build_comps_prompt(deal_info, doc_context, financial_snapshot)
            raw = ask_llm(self.system_prompt, prompt)
            self.observe(f"LLM response received ({len(raw)} chars). Parsing comps data.")
            comps_data = self._parse_comps_data(raw)

            # Replace LLM-estimated multiples with live market data where available
            self.act("market_data", "fetching live peer multiples")
            live_count = self._enrich_with_live_multiples(comps_data)
            if live_count:
                self.observe(f"Live market data resolved for {live_count} peers.")
            else:
                self.observe("No live market data resolved — using analyst-estimated multiples.")

            # Deterministic triangulation using the sector-band engine
            self.act("comps_engine", "computing deterministic EV/EBITDA scenario snapshot")
            snapshot = self._build_deterministic_snapshot(deal_info, financial_snapshot, comps_data)
            if snapshot:
                comps_data["deterministic_snapshot"] = snapshot
                self.observe(
                    f"Deterministic snapshot built (band source: {snapshot.get('multiples_source')})."
                )
            else:
                self.observe("No extracted financials available — skipping deterministic snapshot.")

            # Output 1: JSON
            self.act("file_writer", "writing comps analysis JSON")
            import os
            from datetime import datetime
            from pathlib import Path

            output_dir = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs")
            os.makedirs(output_dir, exist_ok=True)
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)
            date_str = datetime.now().strftime("%Y%m%d")
            json_path = os.path.join(output_dir, f"{safe_name}_CompsAnalysis_{date_str}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(comps_data, f, indent=2, ensure_ascii=False)
            self._register_output(json_path, output_type="json", output_category="valuation")

            # Output 2: Excel workbook
            self.act("excel_writer", "generating comps analysis Excel workbook")
            from tools.excel_writer import WorkbookBuilder
            wb = WorkbookBuilder()
            excel_path = wb.write_comps_analysis(deal_name, comps_data)
            self._register_output(excel_path, output_type="xlsx", output_category="valuation")

            self.update_payload("comps_result", comps_data)

            peer_count = len(comps_data.get("trading_comps", []))
            tx_count = len(comps_data.get("precedent_transactions", []))
            self.think(f"Comps complete: {peer_count} trading peers, {tx_count} precedent transactions.")
            confidence = 0.8 if doc_context.strip() else 0.5
            self.complete(confidence=confidence)

        except Exception as exc:
            logger.exception("ValuationCompsAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id

    def _enrich_with_live_multiples(self, comps_data: dict) -> int:
        """Overwrite LLM-estimated peer multiples with live market data.

        Returns the number of peers resolved live. On any failure the comps
        data is left untouched (estimates remain, marked as such).
        """
        try:
            from tools.market_data import market_data_client

            peers = comps_data.get("trading_comps") or []
            tickers = [p.get("ticker") for p in peers if isinstance(p, dict)]
            live = market_data_client.get_peer_multiples([t for t in tickers if t])
        except Exception as exc:
            logger.debug("Live market data enrichment failed: %s", exc)
            for peer in comps_data.get("trading_comps") or []:
                if isinstance(peer, dict):
                    peer.setdefault("source", "estimate")
            return 0

        live_count = 0
        for peer in peers:
            if not isinstance(peer, dict):
                continue
            ticker = (peer.get("ticker") or "").strip().upper()
            data = live.get(ticker)
            if data:
                for key in ("ev_ebitda", "ev_revenue", "pe"):
                    if data.get(key) is not None:
                        peer[key] = data[key]
                peer["source"] = "live"
                live_count += 1
            else:
                peer["source"] = "estimate"

        # With enough live peers, derive the band from the actual distribution
        # (25th pct / median / 75th pct) instead of analyst judgment.
        try:
            from tools.market_data import MarketDataClient
            band = MarketDataClient.band_from_peers(live)
        except Exception:
            band = None
        if band:
            comps_data["recommended_multiple_band"] = {
                "metric": "EV/EBITDA",
                "bear": band["bear"],
                "base": band["base"],
                "bull": band["bull"],
                "justification": (
                    f"Derived from live peer distribution (n={band['sample_size']}): "
                    "25th percentile / median / 75th percentile of trading EV/EBITDA."
                ),
                "source": "live_peer_distribution",
            }
            comps_data["multiples_data_source"] = "live"
        else:
            comps_data["multiples_data_source"] = "estimate"

        return live_count

    @staticmethod
    def _build_financial_snapshot(dcf_result: dict) -> dict:
        """Pull key target financials from a prior DCF run, if available."""
        if not dcf_result:
            return {}
        base = dcf_result.get("base", dcf_result) or {}
        return {
            "latest_revenue": base.get("latest_revenue") or dcf_result.get("latest_revenue"),
            "latest_ebitda": base.get("latest_ebitda") or dcf_result.get("latest_ebitda"),
            "avg_ebitda_margin": base.get("avg_ebitda_margin") or dcf_result.get("avg_ebitda_margin"),
            "net_debt": base.get("net_debt") or dcf_result.get("net_debt"),
            "shares_outstanding": base.get("shares_outstanding") or dcf_result.get("shares_outstanding"),
            "dcf_equity_value": (base.get("valuation") or {}).get("equity_value"),
        }

    def _build_deterministic_snapshot(
        self, deal_info: dict, financial_snapshot: dict, comps_data: dict
    ) -> dict | None:
        latest_revenue = financial_snapshot.get("latest_revenue")
        if not latest_revenue:
            return None

        margin = financial_snapshot.get("avg_ebitda_margin") or 0.12
        net_debt = financial_snapshot.get("net_debt") or 0.0
        shares = financial_snapshot.get("shares_outstanding")

        # Feed the LLM-recommended band through as "live" data so the engine
        # prefers analyst judgment over hardcoded sector defaults when present.
        band = comps_data.get("recommended_multiple_band") or {}
        live_market_data = None
        if all(isinstance(band.get(k), (int, float)) for k in ("bear", "base", "bull")):
            live_market_data = {
                "sector_multiples": {
                    deal_info.get("industry", "default"): (band["bear"], band["base"], band["bull"]),
                }
            }

        engine = ComparableAnalysisEngine()
        return engine.build_comps_snapshot(
            latest_revenue=float(latest_revenue),
            avg_ebitda_margin=float(margin),
            net_debt=float(net_debt),
            shares_outstanding=float(shares) if shares else None,
            industry=deal_info.get("industry", ""),
            private_company=not shares,
            live_market_data=live_market_data,
        )

    def _parse_comps_data(self, raw: str) -> dict:
        data = parse_llm_json(raw, required_keys=("trading_comps", "recommended_multiple_band"))
        if data is not None:
            return data

        logger.warning("ValuationCompsAgent: could not parse valid comps JSON, using fallback structure.")
        return {
            "peer_selection_rationale": "Automated parsing failed — manual review required.",
            "trading_comps": [],
            "precedent_transactions": [],
            "recommended_multiple_band": {},
            "caveats": ["LLM output could not be parsed", raw[:300]],
        }
