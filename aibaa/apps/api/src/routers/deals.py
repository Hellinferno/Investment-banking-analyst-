from fastapi import APIRouter, HTTPException, status
from typing import List
import uuid

from models import DealCreate, DealUpdate, APIResponse, APIResponseList, Meta
from store import store, Deal

router = APIRouter(prefix="/deals", tags=["Deals"])

@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
async def create_deal(deal_data: DealCreate):
    # Create the internal dataclass Deal
    new_deal = Deal(
        name=deal_data.name,
        company_name=deal_data.company_name,
        deal_type=deal_data.deal_type,
        industry=deal_data.industry,
        deal_stage=deal_data.deal_stage,
        notes=deal_data.notes,
        id=str(uuid.uuid4())
    )
    
    # Save to memory store
    store.deals[new_deal.id] = new_deal
    
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
        "output_count": 0
    }
    
    return APIResponse(
        success=True,
        data=response_data,
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}")
    )

@router.get("", response_model=APIResponseList)
async def list_deals(status_filter: str = "all", sort: str = "created_at_desc", limit: int = 20, offset: int = 0):
    all_deals = [d for d in store.deals.values() if not d.is_archived]
    
    # Filter by deal stage status
    if status_filter != "all":
        all_deals = [d for d in all_deals if d.deal_stage == status_filter]
        
    # Sort
    if sort == "created_at_desc":
        all_deals.sort(key=lambda d: d.created_at, reverse=True)
    elif sort == "created_at_asc":
        all_deals.sort(key=lambda d: d.created_at, reverse=False)
        
    # Pagination
    paginated_deals = all_deals[offset : offset + limit]
    
    response_list = []
    for deal in paginated_deals:
        # Calculate counts
        doc_count = len(store.get_documents_for_deal(deal.id))
        
        response_list.append({
            "id": deal.id,
            "name": deal.name,
            "company_name": deal.company_name,
            "deal_type": deal.deal_type,
            "deal_stage": deal.deal_stage,
            "created_at": deal.created_at.isoformat(),
            "document_count": doc_count,
            "output_count": 0, # Mocked for now until outputs route is built
        })
        
    return APIResponseList(
        success=True,
        data={
            "deals": response_list,
            "total": len(all_deals),
            "limit": limit,
            "offset": offset
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}")
    )

@router.get("/{deal_id}", response_model=APIResponse)
async def get_deal(deal_id: str):
    deal = store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
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
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}")
    )

@router.patch("/{deal_id}", response_model=APIResponse)
async def update_deal(deal_id: str, update_data: DealUpdate):
    deal = store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        setattr(deal, key, value)
        
    # Re-save to store
    store.deals[deal_id] = deal
    
    return APIResponse(
        success=True,
        data={"id": deal.id, "message": "Deal updated successfully"},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}")
    )

@router.delete("/{deal_id}", response_model=APIResponse)
async def delete_deal(deal_id: str):
    deal = store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    deal.is_archived = True
    store.deals[deal_id] = deal
    
    return APIResponse(
        success=True,
        data={"id": deal_id, "message": "Deal successfully archived"},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}")
    )
