from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# --- Request Schemas ---

class DealCreate(BaseModel):
    name: str = Field(..., max_length=80)
    company_name: str = Field(..., max_length=80)
    deal_type: str = Field(..., max_length=30)
    industry: str = Field(..., max_length=60)
    deal_stage: str = Field(default="preliminary", max_length=20)
    notes: Optional[str] = None

class DealUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=80)
    company_name: Optional[str] = Field(None, max_length=80)
    deal_type: Optional[str] = Field(None, max_length=30)
    industry: Optional[str] = Field(None, max_length=60)
    deal_stage: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None

class AgentRunCreate(BaseModel):
    agent_type: str
    task_name: str
    parameters: Dict[str, Any]

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    owner: Optional[str] = None
    priority: str = "medium"
    due_date: Optional[str] = None

class OutputReviewUpdate(BaseModel):
    review_status: str
    reviewer_notes: Optional[str] = None

# --- Response Envelopes ---

class Meta(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    request_id: str

class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    meta: Meta

class APIResponseList(BaseModel):
    success: bool
    data: Dict[str, Any] # e.g. {"deals": [...], "total": 1, "limit": 20, "offset": 0}
    error: Optional[Dict[str, Any]] = None
    meta: Meta
