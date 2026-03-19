from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid

# We keep the Pydantic/dataclasses strictly for type hints where agents expect them.
# The store will now act as a facade over DB.
from database import SessionLocal, ensure_database_ready
from db_models import DealModel, DocumentModel, AgentRunModel, OutputModel, TaskModel

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

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
    created_at: datetime = field(default_factory=_utcnow)

@dataclass
class ExtractionAudit:
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
    created_at: datetime = field(default_factory=_utcnow)

@dataclass
class Task:
    title: str = ""
    status: str = "todo"
    priority: str = "medium"
    owner: str = "AI Agent"
    deal_id: str = ""
    is_ai_generated: bool = True
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=_utcnow)

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
    created_at: datetime = field(default_factory=_utcnow)

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
    uploaded_at: datetime = field(default_factory=_utcnow)

@dataclass
class Deal:
    name: str = ""
    company_name: str = ""
    deal_type: str = "other"
    industry: str = ""
    deal_stage: str = "preliminary"
    notes: Optional[str] = None
    tenant_id: Optional[str] = None
    owner_id: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=_utcnow)
    is_archived: bool = False


# ---------------------------------------------------------------------------
# Global In-Memory Store Facade (Migrating to SessionLocal)
# ---------------------------------------------------------------------------

class DictFacade:
    def __init__(self, model_class, dataclass_type):
        self.model_class = model_class
        self.dataclass_type = dataclass_type
        
    def _to_dataclass(self, orm_obj):
        if not orm_obj: return None
        d = {}
        for c in orm_obj.__table__.columns:
            d[c.name] = getattr(orm_obj, c.name)
        # Drop DB-only cols not in dataclass
        valid_keys = self.dataclass_type.__dataclass_fields__.keys()
        filtered = {k: v for k, v in d.items() if k in valid_keys}
        return self.dataclass_type(**filtered)

    def _to_orm(self, dc_obj):
        d = vars(dc_obj)
        return self.model_class(**d)

    def get(self, key, default=None):
        ensure_database_ready()
        with SessionLocal() as db:
            obj = db.get(self.model_class, key)
            return self._to_dataclass(obj) if obj else default

    def __getitem__(self, key):
        res = self.get(key)
        if not res: raise KeyError(key)
        return res

    def __setitem__(self, key, value):
        ensure_database_ready()
        with SessionLocal() as db:
            # Check if exists
            obj = db.get(self.model_class, key)
            if obj:
                for k, v in vars(value).items():
                    if hasattr(obj, k):
                        setattr(obj, k, v)
            else:
                db.add(self._to_orm(value))
            db.commit()

    def __delitem__(self, key):
        ensure_database_ready()
        with SessionLocal() as db:
            obj = db.get(self.model_class, key)
            if obj:
                db.delete(obj)
                db.commit()
            else:
                raise KeyError(key)

    def __contains__(self, key):
        ensure_database_ready()
        with SessionLocal() as db:
            return db.get(self.model_class, key) is not None

    def values(self):
        ensure_database_ready()
        with SessionLocal() as db:
            objs = db.query(self.model_class).all()
            return [self._to_dataclass(o) for o in objs]

    def clear(self):
        ensure_database_ready()
        with SessionLocal() as db:
            db.query(self.model_class).delete()
            db.commit()

    def pop(self, key, default=None):
        try:
            value = self[key]
        except KeyError:
            return default
        del self[key]
        return value

class MemoryStore:
    def __init__(self):
        self.deals = DictFacade(DealModel, Deal)
        self.documents = DictFacade(DocumentModel, Document)
        self.agent_runs = DictFacade(AgentRunModel, AgentRun)
        self.outputs = DictFacade(OutputModel, Output)
        self.tasks = DictFacade(TaskModel, Task)
        # Extraction audits are accessed as run_id -> [ExtractionAudit, ...] during a run.
        self.extraction_audits: Dict[str, List[ExtractionAudit]] = {}

    def get_deal(self, deal_id: str) -> Optional[Deal]:
        deal = self.deals.get(deal_id)
        if deal and not getattr(deal, "is_archived", False):
            return deal
        return None

    def get_documents_for_deal(self, deal_id: str) -> List[Document]:
        return [doc for doc in self.documents.values() if getattr(doc, "deal_id", None) == deal_id]

store = MemoryStore()

