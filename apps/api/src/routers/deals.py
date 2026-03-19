import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db_models import DealModel, DocumentModel, OutputModel
from dependencies import get_current_user, get_db
from models import APIResponse, APIResponseList, DealCreate, DealUpdate, Meta
from persistence import get_deal_for_user, sync_deal_to_store
from store import store

router = APIRouter(prefix="/deals", tags=["Deals"])


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
    for key, value in update_dict.items():
        setattr(deal, key, value)

    db.commit()
    db.refresh(deal)
    sync_deal_to_store(deal)

    return APIResponse(
        success=True,
        data={"id": deal.id, "message": "Deal updated successfully"},
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
