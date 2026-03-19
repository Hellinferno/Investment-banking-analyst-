import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from db_models import DealModel, OutputModel
from dependencies import CurrentUserDep, DbSessionDep, ReviewerUserDep
from models import APIResponse, Meta, OutputReviewUpdate
from persistence import add_output_review_event, sync_output_to_store
from store import store

_OUTPUT_BASE = Path(__file__).resolve().parent.parent.parent.parent / "data" / "outputs"

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

    output_record.review_status = review.review_status
    db.commit()
    db.refresh(output_record)
    add_output_review_event(
        db,
        output_id=output_record.id,
        reviewer_id=reviewer_user["user_id"],
        review_status=review.review_status,
        reviewer_notes=review.reviewer_notes,
    )

    sync_output_to_store(output_record)
    if output_record.id in store.outputs:
        store.outputs[output_record.id].review_status = output_record.review_status

    return APIResponse(
        success=True,
        data={
            "id": output_record.id,
            "review_status": output_record.review_status,
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

    if output_record.review_status != "approved":
        raise HTTPException(status_code=409, detail="Output must be approved before download")

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

    return FileResponse(
        path=str(file_path),
        filename=output_record.filename,
        media_type="application/octet-stream",
    )
