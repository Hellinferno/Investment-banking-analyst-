from typing import Dict, Any, Optional, Tuple
from agents.base import BaseAgent
# In a real system, we'd import the specific agents here.
# from .modeling import FinancialModelingAgent


class OrchestratorAgent(BaseAgent):
    # Canonical routes that the API can execute today.
    SUPPORTED_ROUTES = {
        "modeling":      {"dcf_model", "lbo_model"},
        "pitchbook":     {"generate_pitchbook"},
        "due_diligence": {"dd_report"},
        "research":      {"industry_brief", "buyer_universe"},
        "doc_drafter":   {"cim_draft"},
        "coordination":  {"extract_tasks"},
    }

    TASK_ALIASES = {
        # DCF
        "dcf": "dcf_model",
        "dcf_valuation": "dcf_model",
        "valuation": "dcf_model",
        "financial_model": "dcf_model",
        # LBO
        "lbo": "lbo_model",
        "leveraged_buyout": "lbo_model",
        "buyout": "lbo_model",
        # Pitchbook
        "pitchbook": "generate_pitchbook",
        "pitch": "generate_pitchbook",
        "pitch_deck": "generate_pitchbook",
        # Due Diligence
        "dd": "dd_report",
        "due_diligence": "dd_report",
        "diligence": "dd_report",
        # Research
        "research": "industry_brief",
        "market_research": "industry_brief",
        "buyers": "buyer_universe",
        "buyer_list": "buyer_universe",
        # CIM
        "cim": "cim_draft",
        "memo": "cim_draft",
        "information_memo": "cim_draft",
        # Coordination
        "tasks": "extract_tasks",
        "meeting_notes": "extract_tasks",
        "action_items": "extract_tasks",
    }

    TASK_TO_AGENT_HINTS = {
        # DCF
        "dcf_model": "modeling",
        "dcf": "modeling",
        "valuation": "modeling",
        "model": "modeling",
        "triangulate": "modeling",
        # LBO
        "lbo_model": "modeling",
        "lbo": "modeling",
        "leveraged_buyout": "modeling",
        # Pitchbook
        "generate_pitchbook": "pitchbook",
        "pitchbook": "pitchbook",
        "pitch": "pitchbook",
        # DD
        "dd_report": "due_diligence",
        "dd": "due_diligence",
        "due_diligence": "due_diligence",
        # Research
        "industry_brief": "research",
        "buyer_universe": "research",
        "research": "research",
        # CIM
        "cim_draft": "doc_drafter",
        "cim": "doc_drafter",
        # Coordination
        "extract_tasks": "coordination",
        "tasks": "coordination",
        "meeting_notes": "coordination",
    }

    def __init__(self, deal_id: str, input_payload: Dict[str, Any]):
        super().__init__(
            agent_type="orchestrator",
            task_name="route_task",
            deal_id=deal_id,
            input_payload=input_payload
        )

    @staticmethod
    def _normalize_token(value: Optional[str]) -> str:
        return str(value or "").strip().lower().replace("-", "_")

    @classmethod
    def _canonicalize_task(cls, task_name: str) -> str:
        if task_name in cls.TASK_ALIASES:
            return cls.TASK_ALIASES[task_name]
        return task_name

    @classmethod
    def _infer_agent_from_task(cls, task_name: str) -> Optional[str]:
        for key, agent in cls.TASK_TO_AGENT_HINTS.items():
            if key in task_name:
                return agent
        return None

    @classmethod
    def _is_supported(cls, agent_type: str, task_name: str) -> bool:
        return task_name in cls.SUPPORTED_ROUTES.get(agent_type, set())

    @classmethod
    def _build_route_decision(
        cls,
        raw_agent: str,
        raw_task: str,
    ) -> Tuple[Dict[str, Any], Optional[str]]:
        requested_agent = cls._normalize_token(raw_agent)
        requested_task = cls._canonicalize_task(cls._normalize_token(raw_task))

        if not requested_task:
            return {}, "Missing required task_name for routing."

        resolved_agent = requested_agent or cls._infer_agent_from_task(requested_task)
        if not resolved_agent:
            return {}, "Could not infer target agent. Provide agent_type explicitly."

        if not cls._is_supported(resolved_agent, requested_task):
            return {}, (
                f"Unsupported route: agent_type='{resolved_agent}', task_name='{requested_task}'. "
                f"Supported routes: {cls.SUPPORTED_ROUTES}"
            )

        confidence = 1.0 if requested_agent == resolved_agent else 0.8
        reason = (
            "direct user route"
            if requested_agent == resolved_agent
            else "inferred from task_name using orchestrator routing rules"
        )

        decision = {
            "requested_agent": requested_agent or None,
            "requested_task": requested_task,
            "target_agent": resolved_agent,
            "target_task": requested_task,
            "confidence": confidence,
            "reason": reason,
        }
        return decision, None

    def run(self) -> str:
        self.think("Analyzing input payload to determine target agent route.")
        raw_agent = self.input_payload.get("agent_type")
        raw_task = self.input_payload.get("task_name")

        route_decision, error = self._build_route_decision(raw_agent, raw_task)
        if error:
            self.fail(error)
            return self.run_id

        self.input_payload["route_decision"] = route_decision
        self.observe(
            "Request routed to -> "
            f"Agent: {route_decision['target_agent']} | Task: {route_decision['target_task']} "
            f"(confidence={route_decision['confidence']:.2f}, reason={route_decision['reason']})"
        )

        self.think(f"Delegation plan ready for {route_decision['target_agent']}.")
        try:
            self.complete(confidence=float(route_decision["confidence"]))
        except Exception as e:
            self.fail(str(e))

        return self.run_id
