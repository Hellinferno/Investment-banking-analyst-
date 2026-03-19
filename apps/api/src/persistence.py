from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from db_models import (
    AgentRunModel,
    DealModel,
    DocumentModel,
    ExtractionAuditModel,
    OutputModel,
    OutputReviewEventModel,
)
from store import AgentRun, Deal, Document, ExtractionAudit, Output, store


def _deal_from_model(model: DealModel) -> Deal:
    return Deal(
        id=model.id,
        name=model.name,
        company_name=model.company_name,
        deal_type=model.deal_type,
        industry=model.industry,
        deal_stage=model.deal_stage,
        notes=model.notes,
        tenant_id=model.tenant_id,
        owner_id=model.owner_id,
        created_at=model.created_at,
        is_archived=bool(model.is_archived),
    )


def _document_from_model(model: DocumentModel) -> Document:
    return Document(
        id=model.id,
        deal_id=model.deal_id,
        filename=model.filename,
        file_type=model.file_type,
        file_size_bytes=model.file_size_bytes,
        storage_path=model.storage_path,
        doc_category=model.doc_category,
        parsed_text=model.parsed_text,
        parse_status=model.parse_status,
        uploaded_at=model.uploaded_at,
    )


def _run_from_model(model: AgentRunModel) -> AgentRun:
    return AgentRun(
        id=model.id,
        deal_id=model.deal_id,
        agent_type=model.agent_type,
        task_name=model.task_name,
        status=model.status,
        input_payload=model.input_payload or {},
        reasoning_steps=model.reasoning_steps or [],
        confidence_score=model.confidence_score,
        error_message=model.error_message,
        created_at=model.created_at,
    )


def _output_from_model(model: OutputModel) -> Output:
    return Output(
        id=model.id,
        deal_id=model.deal_id,
        agent_run_id=model.agent_run_id or "",
        filename=model.filename,
        output_type=model.output_type,
        output_category=model.output_category,
        storage_path=model.storage_path,
        review_status=model.review_status,
        version=model.version,
        created_at=model.created_at,
    )


def _audit_from_model(model: ExtractionAuditModel) -> ExtractionAudit:
    return ExtractionAudit(
        id=model.id,
        deal_id=model.deal_id,
        agent_run_id=model.agent_run_id,
        field_name=model.field_name,
        extracted_value=model.extracted_value,
        confidence_score=model.confidence_score,
        source_citation=model.source_citation,
        reasoning=model.reasoning,
        auditor_status=model.auditor_status,
        auditor_confidence=model.auditor_confidence,
        auditor_reason=model.auditor_reason,
        triangulation_status=model.triangulation_status,
        triangulation_details=model.triangulation_details,
        user_override=model.user_override,
        created_at=model.created_at,
    )


def hydrate_store_from_db(db: Session) -> None:
    audits_by_run: dict[str, list[ExtractionAudit]] = {}
    for audit in db.query(ExtractionAuditModel).all():
        audits_by_run.setdefault(audit.agent_run_id, []).append(_audit_from_model(audit))
    store.extraction_audits = audits_by_run


def sync_deal_to_store(model: DealModel) -> Deal:
    deal = _deal_from_model(model)
    store.deals[deal.id] = deal
    return deal


def sync_document_to_store(model: DocumentModel) -> Document:
    document = _document_from_model(model)
    store.documents[document.id] = document
    return document


def sync_run_to_store(model: AgentRunModel) -> AgentRun:
    run = _run_from_model(model)
    store.agent_runs[run.id] = run
    return run


def sync_output_to_store(model: OutputModel) -> Output:
    output = _output_from_model(model)
    store.outputs[output.id] = output
    return output


def get_deal_for_user(db: Session, deal_id: str, tenant_id: str) -> Optional[DealModel]:
    return (
        db.query(DealModel)
        .filter(
            DealModel.id == deal_id,
            DealModel.tenant_id == tenant_id,
            DealModel.is_archived.is_(False),
        )
        .first()
    )


def persist_run_bundle(db: Session, run_id: str) -> Optional[AgentRunModel]:
    run_record = store.agent_runs.get(run_id)
    if not run_record:
        return None

    run_model = db.query(AgentRunModel).filter(AgentRunModel.id == run_id).first()
    if run_model is None:
        run_model = AgentRunModel(id=run_record.id, deal_id=run_record.deal_id)
        db.add(run_model)

    run_model.agent_type = run_record.agent_type
    run_model.task_name = run_record.task_name
    run_model.status = run_record.status
    run_model.input_payload = run_record.input_payload
    run_model.reasoning_steps = run_record.reasoning_steps
    run_model.confidence_score = run_record.confidence_score
    run_model.error_message = run_record.error_message
    db.flush()

    for output in store.outputs.values():
        if output.agent_run_id != run_id:
            continue
        output_model = db.query(OutputModel).filter(OutputModel.id == output.id).first()
        if output_model is None:
            output_model = OutputModel(id=output.id)
            db.add(output_model)
        output_model.deal_id = output.deal_id
        output_model.agent_run_id = output.agent_run_id or None
        output_model.filename = output.filename
        output_model.output_type = output.output_type
        output_model.output_category = output.output_category
        output_model.storage_path = output.storage_path
        output_model.review_status = output.review_status
        output_model.version = output.version

    existing_audits = (
        db.query(ExtractionAuditModel)
        .filter(ExtractionAuditModel.agent_run_id == run_id)
        .all()
    )
    for existing in existing_audits:
        db.delete(existing)

    for audit in store.extraction_audits.get(run_id, []):
        db.add(
            ExtractionAuditModel(
                id=audit.id,
                deal_id=audit.deal_id,
                agent_run_id=audit.agent_run_id,
                field_name=audit.field_name,
                extracted_value=audit.extracted_value,
                confidence_score=audit.confidence_score,
                source_citation=audit.source_citation,
                reasoning=audit.reasoning,
                auditor_status=audit.auditor_status,
                auditor_confidence=audit.auditor_confidence,
                auditor_reason=audit.auditor_reason,
                triangulation_status=audit.triangulation_status,
                triangulation_details=audit.triangulation_details,
                user_override=audit.user_override,
            )
        )

    db.commit()
    db.refresh(run_model)
    return run_model


def add_output_review_event(
    db: Session,
    *,
    output_id: str,
    reviewer_id: str,
    review_status: str,
    reviewer_notes: str | None,
) -> OutputReviewEventModel:
    event = OutputReviewEventModel(
        output_id=output_id,
        reviewer_id=reviewer_id,
        review_status=review_status,
        reviewer_notes=reviewer_notes,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event
