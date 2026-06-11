from __future__ import annotations

import logging
from typing import Any, Dict

from agents.base import BaseAgent
from engine.three_statement import ThreeStatementEngine
from tools.excel_writer import WorkbookBuilder

logger = logging.getLogger(__name__)

class ThreeStatementModelAgent(BaseAgent):
    def __init__(self, deal_id: str, input_payload: Dict[str, Any], run_id: str | None = None):
        super().__init__(
            agent_type="three_statement",
            task_name="three_statement_model",
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )

    def run(self) -> str:
        try:
            self.think("Starting 3-Statement Model generation.")
            deal_info = self._get_deal_info()
            
            # Use DCF output for baseline historical extraction or use raw extractions.
            # Usually DCF runs first and saves historical extractions to the deal context.
            # We'll pull from the latest DCF run.
            dcf_data = self._get_latest_dcf_output()
            
            if not dcf_data:
                self.fail("Missing DCF output. Run DCF Model first to establish baseline financials.")
                return self.run_id
                
            historical_data = dcf_data.get("historical", {})
            assumptions = dcf_data.get("assumptions", {})
            
            historical_revenues = (
                historical_data.get("revenue")
                or historical_data.get("revenues")
                or dcf_data.get("historical_revenues")
            )
            historical_ebitda_margins = (
                historical_data.get("ebitda_margins")
                or historical_data.get("ebitda_margin")
                or dcf_data.get("historical_ebitda_margins")
            )
            
            if not historical_revenues or not historical_ebitda_margins:
                self.fail("Could not find historical revenue/margin data in DCF output.")
                return self.run_id

            # Parse parameters specific to this agent if they exist.
            params = self.input_payload.get("parameters", {})
            
            engine = ThreeStatementEngine(
                historical_revenues=historical_revenues,
                historical_ebitda_margins=historical_ebitda_margins,
                tax_rate=assumptions.get("tax_rate", 0.25),
                cap_ex_percent_rev=assumptions.get("cap_ex_percent_rev", 0.04),
                da_percent_rev=assumptions.get("da_percent_rev", 0.05),
                base_fy=assumptions.get("base_fy", 2025),
                # Working capital defaults
                dso=params.get("dso", 45.0),
                dpo=params.get("dpo", 30.0),
                dio=params.get("dio", 30.0),
                # Starting structure defaults
                opening_cash=params.get("opening_cash", 50.0),
                revolver_balance=params.get("revolver_balance", 0.0),
                term_loan_balance=params.get("term_loan_balance", 100.0),
            )
            
            self.act("calculate", "Projecting 3-statement model")
            projections = engine.build_projections(projection_years=5)
            
            self.update_payload("three_statement_result", projections)
            
            self.act("draft_document", "Writing 3-Statement Model Excel workbook")
            wb_builder = WorkbookBuilder()
            filepath = wb_builder.write_three_statement_model(
                deal_name=deal_info["company_name"],
                three_statement_result=projections,
                currency=dcf_data.get("currency", "INR"),
            )
            
            self._register_output(filepath, output_type="xlsx", output_category="three_statement_model")
            
            self.observe("3-Statement Model projections generated successfully.")
            
            self.complete(confidence=1.0)
            
        except Exception as exc:
            logger.exception("ThreeStatementModelAgent failed for deal %s", self.deal_id)
            self.fail(str(exc))
            
        return self.run_id
