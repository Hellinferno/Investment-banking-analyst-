import logging
import os
import uuid
from typing import Any, Dict

from database import SessionLocal, ensure_database_ready
from db_models import AgentRunModel

logger = logging.getLogger(__name__)


class BaseAgent:
    def __init__(self, agent_type: str, task_name: str, deal_id: str, input_payload: Dict[str, Any]):
        self.agent_type = agent_type
        self.task_name = task_name
        self.deal_id = deal_id
        self.input_payload = input_payload
        
        # Initialize run tracking
        self.run_id = str(uuid.uuid4())

        ensure_database_ready()
        with SessionLocal() as db:
            self.run_record = AgentRunModel(
                id=self.run_id,
                deal_id=self.deal_id,
                agent_type=self.agent_type,
                task_name=self.task_name,
                status="running",
                input_payload=self.input_payload,
                reasoning_steps=[]
            )
            db.add(self.run_record)
            db.commit()

    def _sync_to_db(self):
        """Helper to sync current state to database."""
        ensure_database_ready()
        with SessionLocal() as db:
            db_record = db.get(AgentRunModel, self.run_id)
            if db_record:
                # Using SQLAlchemy JSON columns requires reassignment for modification tracking sometimes
                db_record.reasoning_steps = list(self.run_record.reasoning_steps)
                db_record.status = self.run_record.status
                db_record.input_payload = dict(self.run_record.input_payload)
                db_record.confidence_score = self.run_record.confidence_score
                db_record.error_message = self.run_record.error_message
                db.commit()

    def _log_step(self, step_type: str, content: str):
        """Append a step to the reasoning logs."""
        step_number = len(self.run_record.reasoning_steps) + 1
        new_step = {
            "step": step_number,
            "type": step_type,
            "content": content
        }
        # Explicit copy to force JSON change detection
        steps_copy = list(self.run_record.reasoning_steps)
        steps_copy.append(new_step)
        self.run_record.reasoning_steps = steps_copy
        
        self._sync_to_db()
        logger.debug("[%s] %s: %s", self.agent_type, step_type.upper(), content)

    def update_payload(self, key: str, value: Any):
        """Safely update input_payload for persistence."""
        payload_copy = dict(self.run_record.input_payload)
        payload_copy[key] = value
        self.run_record.input_payload = payload_copy
        self._sync_to_db()

    def think(self, context: str):
        self._log_step("thought", context)

    def act(self, tool_name: str, tool_input: Any):
        self._log_step("action", f"Calling tool: {tool_name} with {tool_input}")

    def observe(self, observation: str):
        self._log_step("observation", observation)

    def complete(self, confidence: float = 0.9):
        self.run_record.status = "completed"
        self.run_record.confidence_score = confidence
        self._log_step("completion", "Task completed successfully.")
        self._sync_to_db()

    def fail(self, error_message: str):
        self.run_record.status = "failed"
        self.run_record.error_message = error_message
        self._log_step("error", error_message)
        self._sync_to_db()

    def _extract_document_context(self) -> str:
        """Returns last 400K chars of all parsed documents for this deal."""
        from store import store
        MAX_CHARS = 400_000
        docs = [d for d in store.documents.values()
                if d.deal_id == self.deal_id and d.parse_status == "parsed"]
        combined = "\n\n---\n\n".join(d.parsed_text or "" for d in docs)
        return combined[-MAX_CHARS:] if len(combined) > MAX_CHARS else combined

    def _get_deal_info(self) -> dict:
        """Returns dict with company_name, deal_type, industry, deal_name."""
        from store import store
        deal = store.deals.get(self.deal_id)
        if not deal:
            return {}
        return {
            "company_name": getattr(deal, "company_name", ""),
            "deal_type": getattr(deal, "deal_type", ""),
            "industry": getattr(deal, "industry", ""),
            "deal_name": getattr(deal, "name", ""),
        }

    def _register_output(self, file_path: str, output_type: str, output_category: str) -> None:
        """Adds output to store so persist_run_bundle() picks it up."""
        from store import store, Output
        output = Output(
            id=str(uuid.uuid4()),
            deal_id=self.deal_id,
            agent_run_id=self.run_id,
            filename=os.path.basename(file_path),
            storage_path=file_path,
            output_type=output_type,
            output_category=output_category,
            review_status="draft",
        )
        store.outputs[output.id] = output

    def _get_latest_dcf_output(self) -> dict:
        """Returns valuation_result from the most recent completed DCF run for this deal."""
        from store import store
        dcf_runs = [
            r for r in store.agent_runs.values()
            if r.deal_id == self.deal_id
            and r.agent_type == "modeling"
            and r.status == "completed"
        ]
        if not dcf_runs:
            return {}
        latest = max(dcf_runs, key=lambda r: getattr(r, "created_at", "") or "")
        return (latest.input_payload or {}).get("valuation_result", {})

    def run(self):
        """Abstract method to be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement run()")
