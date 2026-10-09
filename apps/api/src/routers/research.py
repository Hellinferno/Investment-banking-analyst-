import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from db_models import AgentRunModel, DealModel, OutputModel, ResearchReviewItemModel
from dependencies import CurrentUserDep, DbSessionDep, ReviewerUserDep
from models import APIResponse, Meta, ResearchReviewItemCreate, ResearchReviewItemUpdate
from tools.research_evidence import research_mode
from tools.research_export import export_research
from tools.serpapi_client import SearchError

router = APIRouter(prefix="/research", tags=["Research"])


@router.get("/status")
def research_status(current_user: CurrentUserDep):
    try:
        mode = research_mode()
    except SearchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    return {"mode": mode, "search_configured": bool(os.getenv("SERPAPI_API_KEY", "").strip()),
            "synthesis_configured": bool(os.getenv("GEMINI_API_KEY") or os.getenv("NVIDIA_API_KEY")),
            "queries_per_run": 4, "max_http_attempts_per_run": 8, "cache_ttl_minutes": 30}


def _get_research_run(db: Session, deal_id: str, run_id: str, tenant_id: str) -> AgentRunModel:
    run = (
        db.query(AgentRunModel)
        .join(DealModel, DealModel.id == AgentRunModel.deal_id)
        .filter(
            AgentRunModel.id == run_id,
            AgentRunModel.deal_id == deal_id,
            AgentRunModel.agent_type.in_(("research", "due_diligence")),
            DealModel.tenant_id == tenant_id,
            DealModel.is_archived.is_(False),
        )
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Research run not found")
    evidence = (run.input_payload or {}).get("research_evidence") or {}
    if not evidence.get("sources"):
        raise HTTPException(status_code=409, detail="This run has no saved sources to review")
    return run


def _known_sources(run: AgentRunModel) -> dict[str, dict]:
    evidence = (run.input_payload or {}).get("research_evidence") or {}
    return {source["id"]: source for source in evidence.get("sources", []) if source.get("id")}


def _validate_source_ids(run: AgentRunModel, source_ids: list[str]) -> None:
    unknown = sorted(set(source_ids) - set(_known_sources(run)))
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown source IDs for this run: {', '.join(unknown)}")


def _serialize_review_item(item: ResearchReviewItemModel, run: AgentRunModel) -> dict:
    sources = _known_sources(run)
    return {
        "id": item.id,
        "research_run_id": item.research_run_id,
        "kind": item.kind,
        "title": item.title,
        "note": item.note,
        "next_action": item.next_action,
        "source_ids": item.source_ids or [],
        "sources": [
            {"id": source_id, "title": sources[source_id]["title"], "url": sources[source_id]["url"]}
            for source_id in (item.source_ids or [])
            if source_id in sources
        ],
        "status": item.status,
        "updated_at": item.updated_at.isoformat(),
        "updated_by": item.updated_by,
        "created_at": item.created_at.isoformat(),
    }


def _get_review_item(db: Session, run: AgentRunModel, item_id: str) -> ResearchReviewItemModel:
    item = (
        db.query(ResearchReviewItemModel)
        .filter(
            ResearchReviewItemModel.id == item_id,
            ResearchReviewItemModel.research_run_id == run.id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item


@router.get("/deals/{deal_id}/runs/{run_id}/review-items", response_model=APIResponse)
def list_review_items(
    deal_id: str,
    run_id: str,
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    run = _get_research_run(db, deal_id, run_id, current_user["tenant_id"])
    items = (
        db.query(ResearchReviewItemModel)
        .filter(ResearchReviewItemModel.research_run_id == run_id)
        .order_by(ResearchReviewItemModel.created_at.asc())
        .all()
    )
    return APIResponse(
        success=True,
        data=[_serialize_review_item(item, run) for item in items],
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.post("/deals/{deal_id}/runs/{run_id}/review-items", response_model=APIResponse, status_code=201)
def create_review_item(
    deal_id: str,
    run_id: str,
    payload: ResearchReviewItemCreate,
    db: DbSessionDep,
    reviewer_user: ReviewerUserDep,
):
    run = _get_research_run(db, deal_id, run_id, reviewer_user["tenant_id"])
    if db.query(ResearchReviewItemModel).filter(ResearchReviewItemModel.research_run_id == run_id).count() >= 30:
        raise HTTPException(status_code=409, detail="A research run can contain at most 30 review items")
    _validate_source_ids(run, payload.source_ids)
    item = ResearchReviewItemModel(
        research_run_id=run_id,
        updated_by=reviewer_user["user_id"],
        **payload.model_dump(),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return APIResponse(
        success=True,
        data=_serialize_review_item(item, run),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.patch("/deals/{deal_id}/runs/{run_id}/review-items/{item_id}", response_model=APIResponse)
def update_review_item(
    deal_id: str,
    run_id: str,
    item_id: str,
    payload: ResearchReviewItemUpdate,
    db: DbSessionDep,
    reviewer_user: ReviewerUserDep,
):
    run = _get_research_run(db, deal_id, run_id, reviewer_user["tenant_id"])
    item = _get_review_item(db, run, item_id)
    changes = payload.model_dump(exclude_unset=True)
    if "source_ids" in changes:
        _validate_source_ids(run, changes["source_ids"])
    for field, value in changes.items():
        setattr(item, field, value)
    item.updated_by = reviewer_user["user_id"]
    db.commit()
    db.refresh(item)
    return APIResponse(
        success=True,
        data=_serialize_review_item(item, run),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.delete("/deals/{deal_id}/runs/{run_id}/review-items/{item_id}", response_model=APIResponse)
def delete_review_item(
    deal_id: str,
    run_id: str,
    item_id: str,
    db: DbSessionDep,
    reviewer_user: ReviewerUserDep,
):
    run = _get_research_run(db, deal_id, run_id, reviewer_user["tenant_id"])
    item = _get_review_item(db, run, item_id)
    db.delete(item)
    db.commit()
    return APIResponse(
        success=True,
        data={"id": item_id, "deleted": True},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.post("/deals/{deal_id}/runs/{run_id}/review-export", response_model=APIResponse, status_code=201)
def export_review_board(
    deal_id: str,
    run_id: str,
    db: DbSessionDep,
    reviewer_user: ReviewerUserDep,
):
    run = _get_research_run(db, deal_id, run_id, reviewer_user["tenant_id"])
    payload = run.input_payload or {}
    evidence = payload.get("research_evidence") or {}
    report = payload.get("research_report") or {}
    if not report:
        raise HTTPException(status_code=409, detail="This run has no saved research report")
    items = (
        db.query(ResearchReviewItemModel)
        .filter(ResearchReviewItemModel.research_run_id == run_id)
        .order_by(ResearchReviewItemModel.created_at.asc())
        .all()
    )
    snapshots = [_serialize_review_item(item, run) for item in items]
    export_id = uuid.uuid4().hex[:12]
    files = export_research(
        evidence.get("company_name") or "Company",
        run_id,
        evidence,
        report,
        diligence=run.agent_type == "due_diligence",
        review_items=snapshots,
        export_id=export_id,
        include_xlsx=False,
    )
    next_version = (
        db.query(func.max(OutputModel.version))
        .filter(OutputModel.agent_run_id == run_id)
        .scalar()
        or 1
    ) + 1
    output_category = "due_diligence" if run.agent_type == "due_diligence" else "research"
    output_records = []
    for file_path, output_type in files:
        output = OutputModel(
            deal_id=deal_id,
            agent_run_id=run_id,
            filename=Path(file_path).name,
            output_type=output_type,
            output_category=output_category,
            storage_path=file_path,
            review_status="draft",
            version=next_version,
        )
        db.add(output)
        output_records.append(output)
    db.commit()
    for output in output_records:
        db.refresh(output)
    return APIResponse(
        success=True,
        data={
            "version": next_version,
            "review_item_count": len(snapshots),
            "outputs": [
                {
                    "id": output.id,
                    "filename": output.filename,
                    "output_type": output.output_type,
                    "review_status": output.review_status,
                    "version": output.version,
                }
                for output in output_records
            ],
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )
