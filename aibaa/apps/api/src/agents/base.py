import uuid
import time
from typing import Dict, Any, List

from store import store, AgentRun

class BaseAgent:
    def __init__(self, agent_type: str, task_name: str, deal_id: str, input_payload: Dict[str, Any]):
        self.agent_type = agent_type
        self.task_name = task_name
        self.deal_id = deal_id
        self.input_payload = input_payload
        
        # Initialize run tracking
        self.run_id = str(uuid.uuid4())
        self.run_record = AgentRun(
            id=self.run_id,
            deal_id=self.deal_id,
            agent_type=self.agent_type,
            task_name=self.task_name,
            status="running",
            input_payload=self.input_payload
        )
        store.agent_runs[self.run_id] = self.run_record

    def _log_step(self, step_type: str, content: str):
        """Append a step to the reasoning logs."""
        step_number = len(self.run_record.reasoning_steps) + 1
        self.run_record.reasoning_steps.append({
            "step": step_number,
            "type": step_type,
            "content": content
        })
        print(f"[{self.agent_type}] {step_type.upper()}: {content}")

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

    def fail(self, error_message: str):
        self.run_record.status = "failed"
        self.run_record.error_message = error_message
        self._log_step("error", error_message)

    def run(self):
        """Abstract method to be overridden by subclasses."""
        raise NotImplementedError("Subclasses must implement run()")
