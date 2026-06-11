import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db_models import BuyerOutreachModel, DealModel, DocumentModel, OutputModel, TaskModel
from dependencies import get_current_user, get_db
from models import APIResponse, APIResponseList, DealCreate, DealUpdate, Meta
from persistence import get_deal_for_user, sync_deal_to_store
from store import store

router = APIRouter(prefix="/deals", tags=["Deals"])

PROCESS_STAGES = [
    "origination",
    "teaser",
    "nda",
    "cim",
    "ioi",
    "management_meetings",
    "loi",
    "diligence",
    "close",
]
LEGACY_STAGE_MAP = {
    "nda_negotiation": "nda",
    "nda_signed": "nda",
    "teaser_sent": "teaser",
    "cim_sent": "cim",
    "io_received": "ioi",
    "loi_signed": "loi",
    "exclusivity": "diligence",
    "definitive_agreement": "close",
}
OUTREACH_STATUSES = {
    "not_contacted",
    "teaser_sent",
    "nda_signed",
    "cim_sent",
    "ioi_received",
    "passed",
}


def _normalize_process_stage(stage: str | None) -> str | None:
    if stage is None:
        return None
    return LEGACY_STAGE_MAP.get(stage, stage)


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(
    deal_data: DealCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    new_deal = DealModel(
        id=str(uuid.uuid4()),
        tenant_id=current_user["tenant_id"],
        owner_id=current_user["user_id"],
        name=deal_data.name,
        company_name=deal_data.company_name,
        deal_type=deal_data.deal_type,
        industry=deal_data.industry,
        deal_stage=deal_data.deal_stage,
        process_stage=deal_data.process_stage,
        notes=deal_data.notes,
    )
    db.add(new_deal)
    db.commit()
    db.refresh(new_deal)
    sync_deal_to_store(new_deal)

    response_data = {
        "id": new_deal.id,
        "name": new_deal.name,
        "company_name": new_deal.company_name,
        "deal_type": new_deal.deal_type,
        "industry": new_deal.industry,
        "deal_stage": new_deal.deal_stage,
        "process_stage": new_deal.process_stage,
        "stage_last_updated": new_deal.stage_last_updated.isoformat() if new_deal.stage_last_updated else None,
        "notes": new_deal.notes,
        "created_at": new_deal.created_at.isoformat(),
        "document_count": 0,
        "output_count": 0,
    }

    return APIResponse(
        success=True,
        data=response_data,
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("", response_model=APIResponseList)
async def list_deals(
    status_filter: str = "all",
    sort: str = "created_at_desc",
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    limit = max(1, min(limit, 100))
    offset = max(0, offset)

    query = db.query(DealModel).filter(
        DealModel.tenant_id == current_user["tenant_id"],
        DealModel.is_archived.is_(False),
    )
    if status_filter != "all":
        query = query.filter(DealModel.deal_stage == status_filter)

    total = query.count()
    if sort == "created_at_asc":
        query = query.order_by(DealModel.created_at.asc())
    else:
        query = query.order_by(DealModel.created_at.desc())

    deals = query.offset(offset).limit(limit).all()

    response_list = []
    for deal in deals:
        sync_deal_to_store(deal)
        doc_count = db.query(DocumentModel).filter(DocumentModel.deal_id == deal.id).count()
        output_count = db.query(OutputModel).filter(OutputModel.deal_id == deal.id).count()
        response_list.append({
            "id": deal.id,
            "name": deal.name,
            "company_name": deal.company_name,
            "deal_type": deal.deal_type,
            "industry": deal.industry,
            "deal_stage": deal.deal_stage,
            "process_stage": deal.process_stage,
            "stage_last_updated": deal.stage_last_updated.isoformat() if deal.stage_last_updated else None,
            "created_at": deal.created_at.isoformat(),
            "document_count": doc_count,
            "output_count": output_count,
        })

    return APIResponseList(
        success=True,
        data={
            "deals": response_list,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/{deal_id}", response_model=APIResponse)
async def get_deal(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    sync_deal_to_store(deal)
    response_data = {
        "id": deal.id,
        "name": deal.name,
        "company_name": deal.company_name,
        "deal_type": deal.deal_type,
        "industry": deal.industry,
        "deal_stage": deal.deal_stage,
        "process_stage": deal.process_stage,
        "stage_last_updated": deal.stage_last_updated.isoformat() if deal.stage_last_updated else None,
        "notes": deal.notes,
        "created_at": deal.created_at.isoformat(),
    }

    return APIResponse(
        success=True,
        data=response_data,
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.patch("/{deal_id}", response_model=APIResponse)
async def update_deal(
    deal_id: str,
    update_data: DealUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    update_dict = update_data.model_dump(exclude_unset=True)
    force = bool(update_dict.pop("force", False))
    
    from datetime import datetime, timezone
    
    for key, value in update_dict.items():
        if key == "process_stage":
            value = _normalize_process_stage(value)
            if value not in PROCESS_STAGES:
                raise HTTPException(status_code=422, detail=f"Invalid process_stage '{value}'")
            current = _normalize_process_stage(getattr(deal, key))
            if current in PROCESS_STAGES and value in PROCESS_STAGES:
                if PROCESS_STAGES.index(value) < PROCESS_STAGES.index(current) and not force:
                    raise HTTPException(
                        status_code=422,
                        detail="Backward process-stage moves require force=true",
                    )
            if getattr(deal, key) != value:
                deal.stage_last_updated = datetime.now(timezone.utc)
        setattr(deal, key, value)

    db.commit()
    db.refresh(deal)
    sync_deal_to_store(deal)

    return APIResponse(
        success=True,
        data={"id": deal.id, "message": "Deal updated successfully"},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/{deal_id}/process-status", response_model=APIResponse)
async def get_process_status(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    outputs = db.query(OutputModel).filter(OutputModel.deal_id == deal_id).all()
    tasks = db.query(TaskModel).filter(TaskModel.deal_id == deal_id).all()
    buyers = db.query(BuyerOutreachModel).filter(BuyerOutreachModel.deal_id == deal_id).all()

    approved = {o.output_category for o in outputs if o.review_status == "approved"}
    drafted = {o.output_category for o in outputs}
    open_tasks = [t for t in tasks if t.status not in {"done", "completed"}]
    active_buyers = [b for b in buyers if b.outreach_status != "passed"]
    stage = _normalize_process_stage(deal.process_stage) or "origination"

    blockers: list[str] = []
    if stage in {"origination", "teaser"} and "teaser" not in approved:
        blockers.append("Blind teaser is not approved.")
    if stage in {"nda", "cim"} and "cim" not in approved:
        blockers.append("CIM is not approved.")
    if stage in {"ioi", "management_meetings", "loi"} and not active_buyers:
        blockers.append("No active buyer outreach is recorded.")
    if stage in {"diligence", "close"} and open_tasks:
        blockers.append(f"{len(open_tasks)} open diligence/process task(s) remain.")
    if "due_diligence" in drafted and "due_diligence" not in approved:
        blockers.append("Due diligence report exists but is not approved.")

    next_stage = PROCESS_STAGES[min(PROCESS_STAGES.index(stage) + 1, len(PROCESS_STAGES) - 1)] if stage in PROCESS_STAGES else "teaser"
    return APIResponse(
        success=True,
        data={
            "current_stage": stage,
            "next_stage": next_stage,
            "ready_for_next_stage": not blockers,
            "blockers": blockers,
            "open_task_count": len(open_tasks),
            "buyer_count": len(buyers),
            "approved_output_categories": sorted(approved),
            "draft_output_categories": sorted(drafted),
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/{deal_id}/buyers", response_model=APIResponse)
async def list_buyers(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    buyers = (
        db.query(BuyerOutreachModel)
        .filter(BuyerOutreachModel.deal_id == deal_id)
        .order_by(BuyerOutreachModel.buyer_idx.asc())
        .all()
    )
    return APIResponse(
        success=True,
        data=[
            {
                "id": b.id,
                "buyer_idx": b.buyer_idx,
                "name": b.buyer_name,
                "buyer_type": b.buyer_type,
                "outreach_status": b.outreach_status,
                "payload": b.buyer_payload or {},
                "updated_at": b.updated_at.isoformat() if b.updated_at else None,
            }
            for b in buyers
        ],
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.patch("/{deal_id}/buyers/{buyer_idx}", response_model=APIResponse)
async def update_buyer_outreach(
    deal_id: str,
    buyer_idx: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    status_value = str(payload.get("outreach_status") or "").strip()
    if status_value not in OUTREACH_STATUSES:
        raise HTTPException(status_code=422, detail=f"Invalid outreach_status '{status_value}'")

    buyer = (
        db.query(BuyerOutreachModel)
        .filter(BuyerOutreachModel.deal_id == deal_id, BuyerOutreachModel.buyer_idx == buyer_idx)
        .first()
    )
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    buyer.outreach_status = status_value
    db.commit()
    db.refresh(buyer)
    return APIResponse(
        success=True,
        data={
            "buyer_idx": buyer.buyer_idx,
            "name": buyer.buyer_name,
            "outreach_status": buyer.outreach_status,
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.delete("/{deal_id}", response_model=APIResponse)
async def delete_deal(
    deal_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    deal = get_deal_for_user(db, deal_id, current_user["tenant_id"])
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    deal.is_archived = True
    db.commit()
    db.refresh(deal)
    sync_deal_to_store(deal)
    if deal_id in store.deals:
        store.deals[deal_id].is_archived = True

    return APIResponse(
        success=True,
        data={"id": deal_id, "message": "Deal successfully archived"},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )
