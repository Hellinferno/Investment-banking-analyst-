import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db_models import AgentRunModel, DealModel, DocumentModel
from dependencies import CurrentUserDep, DbSessionDep, get_current_user, get_db
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
    mnpi_consent: bool = Field(False, description="Required true if deal contains MNPI documents")


def _sanitize_reasoning_steps(steps: list[dict]) -> list[dict]:
    return [{"step": s.get("step"), "type": s.get("type")} for s in (steps or [])]


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


AGENT_DISPATCH_MAP: dict[tuple[str, str], type[BaseAgent]] = {
    ("modeling", "dcf_model"): FinancialModelingAgent,
    ("modeling", "lbo_model"): LBOModelingAgent,
    ("pitchbook", "generate_pitchbook"): PitchbookAgent,
    ("due_diligence", "dd_report"): DueDiligenceAgent,
    ("research", "industry_brief"): ResearchAgent,
    ("research", "buyer_universe"): ResearchAgent,
    ("doc_drafter", "cim_draft"): DocDrafterAgent,
    ("coordination", "extract_tasks"): CoordinationAgent,
}


def _execute_agent_run(agent: BaseAgent) -> None:
    db = SessionLocal()
    try:
        agent.run()
        persist_run_bundle(db, agent.run_id)
    except Exception:
        logger.exception("Background agent execution failed for run %s", agent.run_id)
        persist_run_bundle(db, agent.run_id)
    finally:
        db.close()


def _check_mnpi_consent(db: Session, deal_id: str, mnpi_consent: bool | None) -> None:
    """Block agent runs on deals with MNPI documents unless explicit consent is given."""
    if mnpi_consent is True:
        return
    mnpi_docs = (
        db.query(DocumentModel)
        .filter(DocumentModel.deal_id == deal_id, DocumentModel.is_mnpi.is_(True))
        .all()
    )
    if not mnpi_docs:
        return
    for doc in mnpi_docs:
        if not doc.mnpi_consent_given:
            raise HTTPException(
                status_code=403,
                detail=(
                    "MNPI_CONSENT_REQUIRED: This deal contains MNPI-flagged documents. "
                    "Set mnpi_consent: true in the request body to proceed. "
                    f"MNPI files: {', '.join(d.filename for d in mnpi_docs[:3])}"
                ),
                headers={"X-MNPI-Consent-Required": "true"},
            )


def _ensure_documents_ready_for_run(db: Session, deal_id: str) -> None:
    docs = (
        db.query(DocumentModel)
        .filter(DocumentModel.deal_id == deal_id)
        .order_by(DocumentModel.uploaded_at.asc())
        .all()
    )
    for doc in docs:
        sync_document_to_store(doc)
    blocked = [d.filename for d in docs if d.parse_status != "parsed"]
    if blocked:
        raise HTTPException(
            status_code=409,
            detail=(
                "Documents are still being parsed or failed parsing. "
                "Wait until all parse_status values are 'parsed'. "
                f"Blocked: {', '.join(blocked[:5])}"
            ),
        )


async def _sse_generator(run_id: str, last_event_id: int):
    import redis.asyncio as redis

    try:
        r = redis.from_url("redis://localhost:6379/0", decode_responses=True)
        await r.ping()
    except Exception:
        logger.warning("Redis unavailable — SSE stream will have limited events")
        yield "event: error\ndata: {\"message\":\"Redis unavailable\"}\n\n"
        return

    pubsub = r.pubsub()
    await pubsub.subscribe(f"run:{run_id}")

    try:
        yield "event: connected\ndata: {}\n\n"
        seq = last_event_id
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=5.0)
            if msg:
                seq += 1
                try:
                    event_data = json.loads(msg["data"])
                except Exception:
                    continue
                event_name = event_data.get("event", "message")
                yield f"id: {seq}\nevent: {event_name}\ndata: {json.dumps(event_data.get('data', {}))}\n\n"
                if event_name in ("run.completed", "run.failed"):
                    break
            await asyncio.sleep(0.1)
    finally:
        await pubsub.unsubscribe(f"run:{run_id}")
        await r.aclose()


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/{deal_id}/agents/runs/{run_id}/stream")
async def stream_agent_run(
    deal_id: str,
    run_id: str,
    db: DbSessionDep,
    current_user: CurrentUserDep,
    last_event_id: int = Query(0, ge=0),
):
    """
    Server-Sent Events stream for agent run progress.
    Clients send Last-Event-ID header for replay on disconnect.
    """
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    return StreamingResponse(
        _sse_generator(run_id, last_event_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{deal_id}/agents/run", response_model=APIResponse, status_code=202)
async def dispatch_agent(
    deal_id: str,
    payload: AgentRunPayload,
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    sync_deal_to_store(deal)
    _check_mnpi_consent(db, deal_id, payload.mnpi_consent)

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
                data={**_serialize_run(run_record), "route": route},
                meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
            )

        run_record = store.agent_runs.get(orch_id)
        return APIResponse(
            success=True,
            data={**_serialize_run(run_record), "route": route},
            meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Agent dispatch failed for deal %s", deal_id)
        raise HTTPException(status_code=500, detail="Agent execution failed.")


@router.get("/{deal_id}/agents/runs", response_model=APIResponse)
async def list_agent_runs(
    deal_id: str,
    db: DbSessionDep,
    current_user: CurrentUserDep,
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
                    "run_id": r.id,
                    "agent_type": r.agent_type,
                    "task_name": r.task_name,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in runs
            ]
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/{deal_id}/agents/runs/{run_id}", response_model=APIResponse)
async def get_agent_run(
    deal_id: str,
    run_id: str,
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    run_record = store.agent_runs.get(run_id)
    if run_record and run_record.deal_id == deal_id:
        data = _serialize_run(run_record)
        data["route"] = run_record.input_payload.get("route_decision", {})
        return APIResponse(success=True, data=data, meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"))

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
