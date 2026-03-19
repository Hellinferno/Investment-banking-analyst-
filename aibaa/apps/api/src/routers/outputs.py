import uuid
import os
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from store import store

# Two routers here: one for Deal-specific outputs, one for direct Output downloads
deal_router = APIRouter(prefix="/deals", tags=["Outputs"])
output_router = APIRouter(prefix="/outputs", tags=["Outputs"])

class Meta(BaseModel):
    request_id: str

class APIResponse(BaseModel):
    success: bool
    data: Any
    meta: Meta

@deal_router.get("/{deal_id}/outputs", response_model=APIResponse)
async def list_deal_outputs(deal_id: str):
    deal = store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    # Get outputs for this deal
    outputs_list = []
    for out in store.outputs.values():
        if out.deal_id == deal_id:
            outputs_list.append({
                "id": out.id,
                "agent_run_id": out.agent_run_id,
                "filename": out.filename,
                "output_type": out.output_type,
                "output_category": out.output_category,
                "review_status": out.review_status,
                "created_at": out.created_at.isoformat()
            })
            
    return APIResponse(
        success=True,
        data=outputs_list,
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}")
    )

@output_router.get("/{output_id}/download")
async def download_output(output_id: str):
    output_record = store.outputs.get(output_id)
    if not output_record:
        raise HTTPException(status_code=404, detail="Output not found")
        
    if not os.path.exists(output_record.storage_path):
        raise HTTPException(status_code=404, detail="Physical file missing from disk")
        
    return FileResponse(
        path=output_record.storage_path,
        filename=output_record.filename,
        media_type='application/octet-stream'
    )
