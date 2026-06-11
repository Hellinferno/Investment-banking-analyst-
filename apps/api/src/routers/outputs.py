import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db_models import AgentRunModel, DealModel, OutputModel
from dependencies import CurrentUserDep, DbSessionDep, ReviewerUserDep
from models import APIResponse, Meta, OutputReviewUpdate
from persistence import add_output_review_event, sync_output_to_store
from store import store

_OUTPUT_BASE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs"
_REVIEW_EXPORT_DIR = _OUTPUT_BASE / "_review_exports"

deal_router = APIRouter(prefix="/deals", tags=["Outputs"])
output_router = APIRouter(prefix="/outputs", tags=["Outputs"])


def _get_output_for_user(db: Session, output_id: str, tenant_id: str) -> OutputModel | None:
    return (
        db.query(OutputModel)
        .join(DealModel, DealModel.id == OutputModel.deal_id)
        .filter(
            OutputModel.id == output_id,
            DealModel.tenant_id == tenant_id,
            DealModel.is_archived.is_(False),
        )
        .first()
    )


def _draft_export_path(file_path: Path, output_id: str, suffix: str) -> Path:
    _REVIEW_EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    return _REVIEW_EXPORT_DIR / f"{output_id}_draft{suffix}"


def _watermark_pdf(file_path: Path, output_id: str) -> Path:
    export_path = _draft_export_path(file_path, output_id, ".pdf")
    try:
        import fitz

        doc = fitz.open(str(file_path))
        for page in doc:
            page.insert_text(
                (36, 36),
                "DRAFT - NOT REVIEWED",
                fontsize=18,
                color=(0.75, 0.08, 0.08),
                fill_opacity=0.16,
            )
        doc.save(str(export_path))
        doc.close()
        return export_path
    except Exception:
        return file_path


def _stamp_excel(file_path: Path, output_id: str) -> Path:
    export_path = _draft_export_path(file_path, output_id, file_path.suffix)
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill

        wb = openpyxl.load_workbook(file_path)
        for ws in wb.worksheets:
            ws.insert_rows(1)
            ws["A1"] = "DRAFT - NOT REVIEWED"
            ws["A1"].font = Font(bold=True, color="9C0006")
            ws["A1"].fill = PatternFill("solid", fgColor="FFC7CE")
        wb.save(export_path)
        return export_path
    except Exception:
        return file_path


def _review_export_path(file_path: Path, output_record: OutputModel) -> Path:
    if output_record.review_status == "approved":
        return file_path
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return _watermark_pdf(file_path, output_record.id)
    if suffix in {".xlsx", ".xlsm"}:
        return _stamp_excel(file_path, output_record.id)
    return file_path


@deal_router.get("/{deal_id}/outputs", response_model=APIResponse)
async def list_deal_outputs(
    deal_id: str,
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    deal = (
        db.query(DealModel)
        .filter(
            DealModel.id == deal_id,
            DealModel.tenant_id == current_user["tenant_id"],
            DealModel.is_archived.is_(False),
        )
        .first()
    )
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    outputs_list = (
        db.query(OutputModel)
        .filter(OutputModel.deal_id == deal_id)
        .order_by(OutputModel.created_at.desc())
        .all()
    )
    for output in outputs_list:
        sync_output_to_store(output)

    return APIResponse(
        success=True,
        data=[
            {
                "id": out.id,
                "agent_run_id": out.agent_run_id,
                "filename": out.filename,
                "output_type": out.output_type,
                "output_category": out.output_category,
                "review_status": out.review_status,
                "created_at": out.created_at.isoformat(),
            }
            for out in outputs_list
        ],
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@output_router.patch("/{output_id}/review", response_model=APIResponse)
async def review_output(
    output_id: str,
    review: OutputReviewUpdate,
    db: DbSessionDep,
    reviewer_user: ReviewerUserDep,
):
    output_record = _get_output_for_user(db, output_id, reviewer_user["tenant_id"])
    if not output_record:
        raise HTTPException(status_code=404, detail="Output not found")

    status_value = review.resolved_status
    notes = review.resolved_notes

    output_record.review_status = status_value
    output_record.reviewed_by = reviewer_user["user_id"]
    output_record.reviewed_at = datetime.now(timezone.utc)
    output_record.review_comment = notes
    db.commit()
    db.refresh(output_record)
    add_output_review_event(
        db,
        output_id=output_record.id,
        reviewer_id=reviewer_user["user_id"],
        review_status=status_value,
        reviewer_notes=notes,
    )

    sync_output_to_store(output_record)
    if output_record.id in store.outputs:
        stored = store.outputs[output_record.id]
        stored.review_status = output_record.review_status
        stored.reviewed_by = output_record.reviewed_by
        stored.reviewed_at = output_record.reviewed_at
        stored.review_comment = output_record.review_comment
        store.outputs[output_record.id] = stored

    return APIResponse(
        success=True,
        data={
            "id": output_record.id,
            "review_status": output_record.review_status,
            "reviewed_by": output_record.reviewed_by,
            "reviewed_at": output_record.reviewed_at.isoformat() if output_record.reviewed_at else None,
            "review_comment": output_record.review_comment,
            "message": "Output review updated successfully",
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@output_router.get("/{output_id}/download")
async def download_output(
    output_id: str,
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    output_record = _get_output_for_user(db, output_id, current_user["tenant_id"])
    if not output_record:
        raise HTTPException(status_code=404, detail="Output not found")

    file_path = Path(output_record.storage_path).resolve()
    upload_base = Path(__file__).resolve().parent.parent.parent.parent / "data" / "uploads"
    allowed_roots = (_OUTPUT_BASE.resolve(), upload_base.resolve())

    def _within(fp: Path, root: Path) -> bool:
        try:
            fp.relative_to(root)
            return True
        except ValueError:
            return False

    if not any(_within(file_path, root) for root in allowed_roots):
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Physical file missing from disk")

    # If it's a PDF and still in draft/review state, we should ideally watermark it.
    # For now, if strict review gate is on, deny; otherwise let it through.
    import os
    strict_gate = os.environ.get("AIBAA_STRICT_REVIEW_GATE", "false").lower() == "true"
    if strict_gate and output_record.review_status != "approved":
        raise HTTPException(status_code=403, detail="Output must be approved before download in strict mode")

    response_path = _review_export_path(file_path, output_record)

    return FileResponse(
        path=str(response_path),
        filename=output_record.filename,
        media_type="application/octet-stream",
    )


@output_router.get("/review-queue", response_model=APIResponse)
async def get_review_queue(
    db: DbSessionDep,
    reviewer_user: ReviewerUserDep,
):
    """
    Get all outputs across all deals that are in 'draft' or 'in_review' status.
    Requires Reviewer role.
    """
    outputs = (
        db.query(OutputModel, DealModel, AgentRunModel)
        .join(DealModel, DealModel.id == OutputModel.deal_id)
        .outerjoin(AgentRunModel, AgentRunModel.id == OutputModel.agent_run_id)
        .filter(
            DealModel.tenant_id == reviewer_user["tenant_id"],
            DealModel.is_archived.is_(False),
            OutputModel.review_status.in_(["draft", "in_review", "needs_changes"]),
        )
        .order_by(OutputModel.created_at.desc())
        .all()
    )

    result = []
    for out, deal, run in outputs:
        result.append({
            "id": out.id,
            "deal_id": deal.id,
            "deal_name": deal.name,
            "agent_run_id": out.agent_run_id,
            "filename": out.filename,
            "output_type": out.output_type,
            "output_category": out.output_category,
            "review_status": out.review_status,
            "created_at": out.created_at.isoformat(),
            "confidence_score": run.confidence_score if run else None,
            "validator_status": (run.validator_status if run else "pending"),
            "reviewed_by": out.reviewed_by,
            "reviewed_at": out.reviewed_at.isoformat() if out.reviewed_at else None,
            "review_comment": out.review_comment,
        })

    return APIResponse(
        success=True,
        data=result,
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )
