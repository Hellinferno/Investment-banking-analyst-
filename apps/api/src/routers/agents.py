import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db_models import AgentRunModel, DealModel, DocumentModel
from dependencies import get_current_user, get_db
from models import APIResponse, Meta
from persistence import (
    get_deal_for_user,
    persist_run_bundle,
    sync_deal_to_store,
    sync_document_to_store,
)
from store import store
from agents.base import BaseAgent
from agents.orchestrator import OrchestratorAgent
from agents.modeling import FinancialModelingAgent
from agents.lbo_modeling import LBOModelingAgent
from agents.pitchbook import PitchbookAgent
from agents.due_diligence import DueDiligenceAgent
from agents.research import ResearchAgent
from agents.doc_drafter import DocDrafterAgent
from agents.coordination import CoordinationAgent
from database import SessionLocal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/deals", tags=["Agents"])

_agent_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="agent_run")


class AgentRunPayload(BaseModel):
    agent_type: str = Field(..., min_length=1, max_length=40)
    task_name: str = Field(..., min_length=1, max_length=80)
    parameters: Dict[str, Any] = Field(default_factory=dict)


def _sanitize_reasoning_steps(steps: list[dict]) -> list[dict]:
    safe_steps = []
    for step in steps or []:
        safe_steps.append({
            "step": step.get("step"),
            "type": step.get("type"),
        })
    return safe_steps


def _serialize_run(run_record) -> dict:
    payload = run_record.input_payload or {}
    return {
        "run_id": run_record.id,
        "status": run_record.status,
        "steps": _sanitize_reasoning_steps(run_record.reasoning_steps),
        "valuation_result": payload.get("valuation_result"),
        "lbo_result": payload.get("lbo_result"),
        "error_message": run_record.error_message,
        "confidence_score": run_record.confidence_score,
    }


# ------------------------------------------------------------------
# Agent dispatch table — maps (agent_type, task_name) to agent factory
# ------------------------------------------------------------------
AGENT_DISPATCH_MAP: dict[tuple[str, str], Any] = {
    ("modeling", "dcf_model"):            lambda d, p: FinancialModelingAgent(d, p),
    ("modeling", "lbo_model"):            lambda d, p: LBOModelingAgent(d, p),
    ("pitchbook", "generate_pitchbook"):  lambda d, p: PitchbookAgent(d, p),
    ("due_diligence", "dd_report"):       lambda d, p: DueDiligenceAgent(d, p),
    ("research", "industry_brief"):       lambda d, p: ResearchAgent(d, p),
    ("research", "buyer_universe"):       lambda d, p: ResearchAgent(d, p),
    ("doc_drafter", "cim_draft"):         lambda d, p: DocDrafterAgent(d, p),
    ("coordination", "extract_tasks"):    lambda d, p: CoordinationAgent(d, p),
}


def _execute_agent_run(agent: BaseAgent) -> None:
    """Generic background executor for any BaseAgent subclass."""
    db = SessionLocal()
    try:
        agent.run()
        persist_run_bundle(db, agent.run_id)
    except Exception:
        logger.exception("Background agent execution failed for run %s", agent.run_id)
        persist_run_bundle(db, agent.run_id)
    finally:
        db.close()


def _execute_modeling_run(agent: FinancialModelingAgent) -> None:
    """Kept for backward compatibility — delegates to generic executor."""
    _execute_agent_run(agent)


def _ensure_documents_ready_for_run(db: Session, deal_id: str) -> None:
    docs = (
        db.query(DocumentModel)
        .filter(DocumentModel.deal_id == deal_id)
        .order_by(DocumentModel.uploaded_at.asc())
        .all()
    )
    for doc in docs:
        sync_document_to_store(doc)

    blocked = [doc.filename for doc in docs if doc.parse_status != "parsed"]
    if blocked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Documents are still being parsed or failed parsing. "
                "Wait until all parse_status values are 'parsed' before running the agent. "
                f"Blocked files: {', '.join(blocked[:5])}"
            ),
        )


@router.post("/{deal_id}/agents/run", response_model=APIResponse, status_code=status.HTTP_202_ACCEPTED)
async def dispatch_agent(
    deal_id: str,
    payload: AgentRunPayload,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    sync_deal_to_store(deal)

    try:
        orchestrator = OrchestratorAgent(
            deal_id=deal_id,
            input_payload=payload.model_dump(),
        )
        orch_id = orchestrator.run()
        with SessionLocal() as persist_db:
            persist_run_bundle(persist_db, orch_id)

        orchestrator_record = store.agent_runs.get(orch_id)
        if not orchestrator_record:
            raise HTTPException(status_code=500, detail="Orchestrator run record not found")
        if orchestrator_record.status != "completed":
            raise HTTPException(
                status_code=422,
                detail=orchestrator_record.error_message or "Routing failed",
            )

        route = orchestrator_record.input_payload.get("route_decision", {})
        target_agent = route.get("target_agent")
        target_task = route.get("target_task")

        route_key = (target_agent, target_task)
        if route_key in AGENT_DISPATCH_MAP:
            _ensure_documents_ready_for_run(db, deal_id)
            specialized_payload = payload.model_dump()
            specialized_payload["agent_type"] = target_agent
            specialized_payload["task_name"] = target_task
            specialized_agent = AGENT_DISPATCH_MAP[route_key](deal_id, specialized_payload)
            with SessionLocal() as persist_db:
                persist_run_bundle(persist_db, specialized_agent.run_id)
            _agent_pool.submit(_execute_agent_run, specialized_agent)

            run_record = store.agent_runs.get(specialized_agent.run_id)
            return APIResponse(
                success=True,
                data={
                    **_serialize_run(run_record),
                    "route": route,
                },
                meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
            )

        run_record = store.agent_runs.get(orch_id)
        return APIResponse(
            success=True,
            data={
                **_serialize_run(run_record),
                "route": route,
            },
            meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Agent dispatch failed for deal %s", deal_id)
        raise HTTPException(status_code=500, detail="Agent execution failed. Check server logs for details.")


@router.get("/{deal_id}/agents/runs", response_model=APIResponse)
async def list_agent_runs(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    runs = (
        db.query(AgentRunModel)
        .filter(AgentRunModel.deal_id == deal_id)
        .order_by(AgentRunModel.created_at.desc())
        .all()
    )
    return APIResponse(
        success=True,
        data={
            "runs": [
                {
                    "run_id": run.id,
                    "agent_type": run.agent_type,
                    "task_name": run.task_name,
                    "status": run.status,
                    "created_at": run.created_at.isoformat(),
                }
                for run in runs
            ]
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/{deal_id}/agents/runs/{run_id}", response_model=APIResponse)
async def get_agent_run(
    deal_id: str,
    run_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    run_record = store.agent_runs.get(run_id)
    if run_record and run_record.deal_id == deal_id:
        payload = _serialize_run(run_record)
        payload["route"] = run_record.input_payload.get("route_decision", {})
        return APIResponse(
            success=True,
            data=payload,
            meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
        )

    db_run = (
        db.query(AgentRunModel)
        .filter(AgentRunModel.id == run_id, AgentRunModel.deal_id == deal_id)
        .first()
    )
    if not db_run:
        raise HTTPException(status_code=404, detail="Run not found")

    return APIResponse(
        success=True,
        data={
            "run_id": db_run.id,
            "status": db_run.status,
            "steps": [],
            "valuation_result": (db_run.input_payload or {}).get("valuation_result"),
            "lbo_result": (db_run.input_payload or {}).get("lbo_result"),
            "error_message": db_run.error_message,
            "confidence_score": db_run.confidence_score,
            "route": (db_run.input_payload or {}).get("route_decision", {}),
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )
