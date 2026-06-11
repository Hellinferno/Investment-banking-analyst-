"""
FootballFieldAgent — generates the classic valuation summary football field chart.

Collects completed valuation ranges from prior agent runs (DCF, comps,
precedent transactions, LBO) and renders a horizontal bar chart PNG.

Outputs:
  1. Football field PNG chart (.png)

The chart is also embedded into IC memos and pitchbooks when available.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from pathlib import Path

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

_OUTPUT_DIR = str(Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs")


class FootballFieldAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: dict, run_id: str | None = None):
        super().__init__(
            agent_type="memo_writer",
            task_name="football_field",
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )

    def run(self) -> str:
        try:
            self.think("Collecting valuation ranges from prior agent runs (DCF, comps, LBO).")

            from tools.football_field import collect_valuation_ranges, render_football_field

            ranges = collect_valuation_ranges(self.deal_id)
            if not ranges:
                self.observe("No completed valuation runs found — cannot generate football field.")
                self.fail("No valuation data available. Run DCF, comps, or LBO first.")
                return self.run_id

            methods = [r["method"] for r in ranges]
            self.observe(f"Found {len(ranges)} valuation methods: {', '.join(methods)}.")

            # Get deal info for filename
            deal_info = self._get_deal_info()
            deal_name = deal_info.get("deal_name", "Deal")
            parameters = self.input_payload.get("parameters", {}) or {}
            current_market_cap = parameters.get("current_market_cap")

            # Try to get market cap from latest DCF if not provided
            if not current_market_cap:
                dcf_result = self._get_latest_dcf_output()
                if dcf_result:
                    header = dcf_result.get("header") or {}
                    current_market_cap = header.get("market_cap")

            if current_market_cap:
                try:
                    current_market_cap = float(current_market_cap)
                except (TypeError, ValueError):
                    current_market_cap = None

            self.act("chart_renderer", "rendering football field chart")
            os.makedirs(_OUTPUT_DIR, exist_ok=True)
            safe_name = re.sub(r"[^\w\-]", "_", deal_name)
            date_str = datetime.now().strftime("%Y%m%d")
            png_path = os.path.join(_OUTPUT_DIR, f"{safe_name}_FootballField_{date_str}.png")

            result_path = render_football_field(
                ranges=ranges,
                path=png_path,
                current_market_cap=current_market_cap,
            )

            if not result_path:
                self.fail("Chart rendering failed — matplotlib may not be installed.")
                return self.run_id

            self._register_output(result_path, output_type="png", output_category="valuation")
            self.update_payload("football_field_result", {
                "chart_path": result_path,
                "methods": methods,
                "ranges": ranges,
                "current_market_cap": current_market_cap,
            })

            self.observe(f"Football field chart saved: {os.path.basename(result_path)}.")
            self.think(f"Football field complete with {len(ranges)} methods plotted.")
            self.complete(confidence=0.9 if len(ranges) >= 3 else 0.7)

        except Exception as exc:
            logger.exception("FootballFieldAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))

        return self.run_id
