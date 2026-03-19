import uuid
from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from store import store
from agents.orchestrator import OrchestratorAgent
from agents.modeling import FinancialModelingAgent

router = APIRouter(prefix="/deals", tags=["Agents"])

class Meta(BaseModel):
    timestamp: str = ""
    request_id: str

    def __init__(self, **data):
        if "timestamp" not in data:
            data["timestamp"] = datetime.utcnow().isoformat() + "Z"
        super().__init__(**data)

class APIResponse(BaseModel):
    success: bool
    data: Any
    meta: Meta

class AgentRunPayload(BaseModel):
    agent_type: str
    task_name: str
    parameters: Dict[str, Any] = {}

@router.post("/{deal_id}/agents/run", response_model=APIResponse)
async def dispatch_agent(deal_id: str, payload: AgentRunPayload):
    deal = store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    try:
        # Initialize the Orchestrator which acts as the main routing brain
        orchestrator = OrchestratorAgent(
            deal_id=deal_id,
            input_payload=payload.model_dump()
        )
        orch_id = orchestrator.run()
        
        target_agent = payload.agent_type
        if target_agent == 'modeling':
            specialized_agent = FinancialModelingAgent(deal_id, payload.model_dump())
            run_id = specialized_agent.run()
        else:
            run_id = orch_id # fallback if agent not implemented
            
        # Fetch the resulting run log from the store
        run_record = store.agent_runs.get(run_id)
        
        return APIResponse(
            success=True,
            data={
                "run_id": run_id,
                "status": run_record.status if run_record else "unknown",
                "steps": run_record.reasoning_steps if run_record else [],
                "valuation_result": run_record.input_payload.get("valuation_result") if run_record else None
            },
            meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}")
        )
        
    except Exception as e:
        print(f"Agent dispatch failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{deal_id}/agents/runs", response_model=APIResponse)
async def list_agent_runs(deal_id: str):
    deal = store.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")
        
    runs = [run for run in store.agent_runs.values() if run.deal_id == deal_id]
    
    return APIResponse(
        success=True,
        data={
            "runs": [
                {
                    "run_id": run.id,
                    "agent_type": run.agent_type,
                    "task_name": run.task_name,
                    "status": run.status,
                    "created_at": run.created_at.isoformat()
                } for run in runs
            ]
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}")
    )
