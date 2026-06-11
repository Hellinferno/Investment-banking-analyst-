"""Autonomous full deal package pipeline."""
from __future__ import annotations

import logging
from typing import Any, Dict

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


def _build_pipeline_steps() -> list[dict]:
    from agents.comps import ValuationCompsAgent
    from agents.doc_drafter import DocDrafterAgent
    from agents.due_diligence import DueDiligenceAgent
    from agents.football_field import FootballFieldAgent
    from agents.lbo_modeling import LBOModelingAgent
    from agents.memo import InvestmentMemoAgent
    from agents.merger_model import MergerModelAgent
    from agents.modeling import FinancialModelingAgent
    from agents.pitchbook import PitchbookAgent
    from agents.research import ResearchAgent
    from agents.three_statement import ThreeStatementModelAgent

    return [
        {"key": "dcf_bootstrap", "agent_cls": FinancialModelingAgent, "agent_type": "modeling", "task_name": "dcf_model"},
        {"key": "three_statement_model", "agent_cls": ThreeStatementModelAgent, "agent_type": "three_statement", "task_name": "three_statement_model"},
        {
            "key": "dcf_refresh",
            "agent_cls": FinancialModelingAgent,
            "agent_type": "modeling",
            "task_name": "dcf_model",
            "parameters": {"use_three_statement_fcf": True},
        },
        {"key": "lbo_model", "agent_cls": LBOModelingAgent, "agent_type": "modeling", "task_name": "lbo_model"},
        {"key": "comps_analysis", "agent_cls": ValuationCompsAgent, "agent_type": "comps", "task_name": "comps_analysis"},
        {"key": "accretion_dilution", "agent_cls": MergerModelAgent, "agent_type": "merger_model", "task_name": "accretion_dilution"},
        {"key": "football_field", "agent_cls": FootballFieldAgent, "agent_type": "football_field", "task_name": "football_field"},
        {"key": "dd_report", "agent_cls": DueDiligenceAgent, "agent_type": "due_diligence", "task_name": "dd_report"},
        {"key": "industry_brief", "agent_cls": ResearchAgent, "agent_type": "research", "task_name": "industry_brief"},
        {"key": "buyer_universe", "agent_cls": ResearchAgent, "agent_type": "research", "task_name": "buyer_universe"},
        {"key": "teaser_draft", "agent_cls": DocDrafterAgent, "agent_type": "doc_drafter", "task_name": "teaser_draft"},
        {"key": "cim_draft", "agent_cls": DocDrafterAgent, "agent_type": "doc_drafter", "task_name": "cim_draft"},
        {"key": "investment_memo", "agent_cls": InvestmentMemoAgent, "agent_type": "memo_writer", "task_name": "investment_memo"},
        {"key": "generate_pitchbook", "agent_cls": PitchbookAgent, "agent_type": "pitchbook", "task_name": "generate_pitchbook"},
    ]


class AutonomousDealPipeline(BaseAgent):
    def __init__(self, deal_id: str, input_payload: Dict[str, Any], run_id: str | None = None):
        super().__init__(
            agent_type="autopilot",
            task_name="full_deal_package",
            deal_id=deal_id,
            input_payload=input_payload,
            run_id=run_id,
        )

    def _select_steps(self, parameters: dict[str, Any], all_steps: list[dict]) -> list[dict]:
        if parameters.get("resume_after_checkpoint"):
            remaining_keys = set(self.run_record.input_payload.get("checkpoint_remaining_steps") or [])
            if remaining_keys:
                return [s for s in all_steps if s["key"] in remaining_keys]

        requested_steps = parameters.get("steps")
        if isinstance(requested_steps, list) and requested_steps:
            requested = set(requested_steps)
            return [s for s in all_steps if s["key"] in requested or s["task_name"] in requested]
        return all_steps

    def run(self) -> str:
        from database import SessionLocal
        from persistence import persist_run_bundle
        from store import store

        parameters = self.input_payload.get("parameters", {}) or {}
        resume_after_checkpoint = bool(parameters.get("resume_after_checkpoint"))

        all_steps = _build_pipeline_steps()
        steps = self._select_steps(parameters, all_steps)

        self.think(
            f"Autonomous deal package started: {len(steps)} workstreams queued "
            f"({', '.join(s['key'] for s in steps)})."
        )

        step_results: list[dict] = list(self.run_record.input_payload.get("pipeline_results") or [])
        completed = sum(1 for r in step_results if r.get("status") == "completed") if resume_after_checkpoint else 0

        for index, step in enumerate(steps, start=1):
            key = step["key"]
            self.act("dispatch_subagent", f"[{index}/{len(steps)}] {step['agent_type']}/{key}")

            try:
                step_params = dict(parameters)
                step_params.update(step.get("parameters", {}))
                child_payload = {
                    "agent_type": step["agent_type"],
                    "task_name": step["task_name"],
                    "parameters": step_params,
                    "parent_run_id": self.run_id,
                }
                child = step["agent_cls"](self.deal_id, child_payload)
                child.run()

                with SessionLocal() as db:
                    persist_run_bundle(db, child.run_id)

                child_record = store.agent_runs.get(child.run_id)
                child_status = getattr(child_record, "status", "unknown")
                child_error = getattr(child_record, "error_message", None)

                if child_status == "completed":
                    completed += 1
                    self.observe(f"{key} completed (run {child.run_id}).")
                else:
                    self.observe(f"{key} ended with status '{child_status}': {child_error or 'no detail'}")

                step_results.append({
                    "step": key,
                    "agent_type": step["agent_type"],
                    "task_name": step["task_name"],
                    "run_id": child.run_id,
                    "status": child_status,
                    "error": child_error,
                })

                if (
                    parameters.get("review_checkpoint")
                    and not resume_after_checkpoint
                    and key == "football_field"
                ):
                    remaining = [s["key"] for s in steps[index:]]
                    self.update_payload("pipeline_results", step_results)
                    self.update_payload("checkpoint_remaining_steps", remaining)
                    self.set_run_metadata(checkpoint_status="awaiting_review")
                    self.set_status("awaiting_review")
                    self.think(
                        "Valuation checkpoint reached. Review approval is required before document generation resumes."
                    )
                    return self.run_id
            except Exception as exc:
                logger.exception("Pipeline step %s failed for deal %s", key, self.deal_id)
                self.observe(f"{key} raised an exception and was skipped: {exc}")
                step_results.append({
                    "step": key,
                    "agent_type": step["agent_type"],
                    "task_name": step["task_name"],
                    "run_id": None,
                    "status": "failed",
                    "error": str(exc)[:300],
                })

        self.update_payload("pipeline_results", step_results)
        self.update_payload("checkpoint_remaining_steps", [])
        self.set_run_metadata(checkpoint_status="completed")

        summary = f"Deal package finished: {completed}/{len(step_results) or len(steps)} workstreams completed."
        self.think(summary)

        required = {"dcf_bootstrap", "dcf_refresh", "comps_analysis", "investment_memo", "generate_pitchbook"}
        required_completed = {
            r["step"] for r in step_results
            if r.get("step") in required and r.get("status") == "completed"
        }
        if not required_completed:
            self.fail(f"All required valuation/document steps failed. {summary}")
        else:
            denominator = max(len(step_results), 1)
            self.complete(confidence=round(completed / denominator, 2))

        return self.run_id
