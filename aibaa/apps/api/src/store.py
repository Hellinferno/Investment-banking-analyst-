from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid

@dataclass
class Output:
    deal_id: str = ""
    agent_run_id: str = ""
    filename: str = ""
    output_type: str = ""
    output_category: str = ""
    storage_path: str = ""
    review_status: str = "draft"
    version: int = 1
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class ExtractionAudit:
    """Per-field audit trail for the maker-checker extraction pipeline."""
    deal_id: str = ""
    agent_run_id: str = ""
    field_name: str = ""
    extracted_value: Any = None
    confidence_score: float = 0.0
    source_citation: str = ""
    reasoning: str = ""
    auditor_status: str = "pending"
    auditor_confidence: float = 0.0
    auditor_reason: str = ""
    triangulation_status: str = "skipped"
    triangulation_details: str = ""
    user_override: Any = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class Task:
    title: str = ""
    status: str = "todo"
    priority: str = "medium"
    owner: str = "AI Agent"
    deal_id: str = ""
    is_ai_generated: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class AgentRun:
    agent_type: str = ""
    task_name: str = ""
    status: str = "queued"
    deal_id: str = ""
    input_payload: Dict[str, Any] = field(default_factory=dict)
    reasoning_steps: List[Dict] = field(default_factory=list)
    confidence_score: Optional[float] = None
    error_message: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class Document:
    filename: str = ""
    file_type: str = ""
    file_size_bytes: int = 0
    storage_path: str = ""
    deal_id: str = ""
    doc_category: Optional[str] = None
    parsed_text: Optional[str] = None
    parse_status: str = "pending"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    uploaded_at: datetime = field(default_factory=datetime.now)

@dataclass
class Deal:
    name: str = ""
    company_name: str = ""
    deal_type: str = "other"
    industry: str = ""
    deal_stage: str = "preliminary"
    notes: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.now)
    is_archived: bool = False

# --- Global In-Memory Store ---

class MemoryStore:
    def __init__(self):
        self.deals: Dict[str, Deal] = {}
        self.documents: Dict[str, Document] = {}
        self.agent_runs: Dict[str, AgentRun] = {}
        self.outputs: Dict[str, Output] = {}
        self.tasks: Dict[str, Task] = {}
        self.extraction_audits: Dict[str, List[ExtractionAudit]] = {}

    def get_deal(self, deal_id: str) -> Optional[Deal]:
        target = self.deals.get(deal_id)
        if target and not target.is_archived:
            return target
            
        # Development hot-reload fallback: Auto-resurrect the deal
        # if the user is still on the deal page but the backend store was wiped
        if not target and deal_id:
            recovered_deal = Deal(id=deal_id, name="Recovered Pipeline (Hot Reload)", company_name="Auto-Restored")
            self.deals[deal_id] = recovered_deal
            return recovered_deal
            
        return None
    
    def get_documents_for_deal(self, deal_id: str) -> List[Document]:
        return [doc for doc in self.documents.values() if doc.deal_id == deal_id]

# Singleton instance
store = MemoryStore()
