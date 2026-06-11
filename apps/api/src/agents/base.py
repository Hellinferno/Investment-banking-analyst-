import json
import logging
import os
import re
import uuid
from typing import Any, Dict, Optional

from database import SessionLocal, ensure_database_ready
from db_models import AgentRunModel

logger = logging.getLogger(__name__)


def parse_llm_json(raw: str, required_keys: tuple[str, ...] = ()) -> dict | None:
    """Extract a JSON object from an LLM response and validate its shape.

    Returns the parsed dict only when it is a JSON object AND contains at least
    one of ``required_keys`` (when provided). A valid-JSON-but-wrong-schema
    response — e.g. ``{"error": "context too long"}`` — returns None so callers
    can fail or retry instead of silently completing with empty output.
    """
    if not raw:
        return None
    match = re.search(r"\{[\s\S]*\}", raw.strip())
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if required_keys and not any(k in data for k in required_keys):
        logger.warning(
            "LLM JSON parsed but missing all required keys %s — treating as invalid.",
            required_keys,
        )
        return None
    return data


def _sanitize_agent_error(message: str) -> str:
    """Redact secrets and absolute paths from an agent error before it is
    persisted to the DB or returned via the API."""
    msg = str(message)
    # Long token/key-like sequences (40+ chars)
    msg = re.sub(r"[A-Za-z0-9_\-]{40,}", "[REDACTED]", msg)
    # Bearer tokens / api-key query params
    msg = re.sub(r"(?i)(bearer\s+|api[_-]?key=)[^\s&]+", r"\1[REDACTED]", msg)
    # Windows and Unix absolute paths
    msg = re.sub(r"[A-Za-z]:[\\/][^\s]+", "[PATH]", msg)
    msg = re.sub(r"(?<![\w])/(?:home|app|srv|var|etc|root|Users)/[\w./\-]+", "[PATH]", msg)
    return msg[:500]


class BaseAgent:
    def __init__(
        self,
        agent_type: str,
        task_name: str,
        deal_id: str,
        input_payload: Dict[str, Any],
        run_id: Optional[str] = None,
    ):
        self.agent_type = agent_type
        self.task_name = task_name
        self.deal_id = deal_id
        self.input_payload = input_payload

        ensure_database_ready()
        with SessionLocal() as db:
            if run_id:
                existing = db.get(AgentRunModel, run_id)
                if existing is None:
                    raise ValueError(f"Agent run {run_id} does not exist")
                existing.deal_id = self.deal_id
                existing.agent_type = self.agent_type
                existing.task_name = self.task_name
                existing.input_payload = dict(existing.input_payload or self.input_payload)
                self.run_id = existing.id
                db.commit()
                db.refresh(existing)
                self.run_record = existing
            else:
                self.run_id = str(uuid.uuid4())
                self.run_record = AgentRunModel(
                    id=self.run_id,
                    deal_id=self.deal_id,
                    agent_type=self.agent_type,
                    task_name=self.task_name,
                    status="running",
                    input_payload=self.input_payload,
                    reasoning_steps=[],
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
                db_record.model_provider = self.run_record.model_provider
                db_record.model_name = self.run_record.model_name
                db_record.prompt_version = self.run_record.prompt_version
                db_record.validator_status = self.run_record.validator_status
                db_record.validator_report = self.run_record.validator_report
                db_record.checkpoint_status = self.run_record.checkpoint_status
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

    def set_status(self, status: str):
        self.run_record.status = status
        self._sync_to_db()

    def set_run_metadata(
        self,
        *,
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None,
        prompt_version: Optional[str] = None,
        validator_status: Optional[str] = None,
        validator_report: Optional[Dict[str, Any]] = None,
        checkpoint_status: Optional[str] = None,
    ):
        if model_provider is not None:
            self.run_record.model_provider = model_provider
        if model_name is not None:
            self.run_record.model_name = model_name
        if prompt_version is not None:
            self.run_record.prompt_version = prompt_version
        if validator_status is not None:
            self.run_record.validator_status = validator_status
        if validator_report is not None:
            self.run_record.validator_report = validator_report
        if checkpoint_status is not None:
            self.run_record.checkpoint_status = checkpoint_status
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
        # Sanitize before persisting/returning: raw exception text from LLM/HTTP
        # SDKs can carry API-key fragments or filesystem paths, and error_message
        # is surfaced via the API and stored in the DB.
        safe_message = _sanitize_agent_error(error_message)
        self.run_record.status = "failed"
        self.run_record.error_message = safe_message
        self._log_step("error", safe_message)
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
