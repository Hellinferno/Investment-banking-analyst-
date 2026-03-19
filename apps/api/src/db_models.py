from sqlalchemy import Boolean, Column, String, Integer, Float, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from database import Base

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

class DealModel(Base):
    __tablename__ = "deals"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String, index=True, nullable=True) # For multi-tenant isolation
    owner_id = Column(String, index=True, nullable=True)  # For User PBAC
    
    name = Column(String, index=True)
    company_name = Column(String, index=True)
    deal_type = Column(String, default="other")
    industry = Column(String)
    deal_stage = Column(String, default="preliminary")
    notes = Column(String, nullable=True)
    
    created_at = Column(DateTime, default=_utcnow)
    is_archived = Column(Boolean, default=False)
    
    documents = relationship("DocumentModel", back_populates="deal", cascade="all, delete-orphan")
    agent_runs = relationship("AgentRunModel", back_populates="deal", cascade="all, delete-orphan")
    outputs = relationship("OutputModel", back_populates="deal", cascade="all, delete-orphan")


class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id = Column(String, ForeignKey("deals.id"))
    
    filename = Column(String)
    file_type = Column(String)
    file_size_bytes = Column(Integer, default=0)
    storage_path = Column(String)
    doc_category = Column(String, nullable=True)
    parsed_text = Column(String, nullable=True)
    parse_status = Column(String, default="pending")
    uploaded_at = Column(DateTime, default=_utcnow)
    
    deal = relationship("DealModel", back_populates="documents")


class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id = Column(String, ForeignKey("deals.id"))
    
    agent_type = Column(String)
    task_name = Column(String)
    status = Column(String, default="queued")
    
    input_payload = Column(JSON, default=dict)
    reasoning_steps = Column(JSON, default=list) # Using JSON for Postgres/SQLite compat
    confidence_score = Column(Float, nullable=True)
    error_message = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    
    deal = relationship("DealModel", back_populates="agent_runs")


class OutputModel(Base):
    __tablename__ = "outputs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id = Column(String, ForeignKey("deals.id"))
    agent_run_id = Column(String, ForeignKey("agent_runs.id"), nullable=True)
    
    filename = Column(String)
    output_type = Column(String)
    output_category = Column(String)
    storage_path = Column(String)
    review_status = Column(String, default="draft")
    version = Column(Integer, default=1)
    
    created_at = Column(DateTime, default=_utcnow)
    
    deal = relationship("DealModel", back_populates="outputs")


class ExtractionAuditModel(Base):
    __tablename__ = "extraction_audits"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id = Column(String, ForeignKey("deals.id"))
    agent_run_id = Column(String, ForeignKey("agent_runs.id"))
    
    field_name = Column(String)
    extracted_value = Column(JSON, nullable=True) # Store complex values like lists as JSON
    confidence_score = Column(Float, default=0.0)
    source_citation = Column(String)
    reasoning = Column(String)
    
    auditor_status = Column(String, default="pending")
    auditor_confidence = Column(Float, default=0.0)
    auditor_reason = Column(String)
    
    triangulation_status = Column(String, default="skipped")
    triangulation_details = Column(String)
    user_override = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, default=_utcnow)


class TaskModel(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id = Column(String, ForeignKey("deals.id"))
    
    title = Column(String)
    status = Column(String, default="todo")
    priority = Column(String, default="medium")
    owner = Column(String, default="AI Agent")
    is_ai_generated = Column(Boolean, default=True)
    created_at = Column(DateTime, default=_utcnow)


class OutputReviewEventModel(Base):
    __tablename__ = "output_review_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    output_id = Column(String, ForeignKey("outputs.id"), index=True)
    reviewer_id = Column(String, index=True)
    review_status = Column(String, default="draft")
    reviewer_notes = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
