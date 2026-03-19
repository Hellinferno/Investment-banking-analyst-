"""Admin router: audit trail query, chain validation, and CSV/JSON export."""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from audit import get_audit_log, validate_audit_chain
from db_models import SecurityAuditLogModel
from dependencies import AdminDep, AdminReviewerDep, CurrentUserDep, DbSessionDep
from models import APIResponse, Meta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/audit", response_model=APIResponse)
async def get_audit_trail(
    db: DbSessionDep,
    current_user: AdminReviewerDep,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    action: str | None = None,
    user_id: str | None = None,
):
    records = get_audit_log(
        db,
        tenant_id=current_user["tenant_id"],
        limit=limit,
        offset=offset,
        action=action,
        user_id=user_id,
    )

    return APIResponse(
        success=True,
        data={
            "records": [
                {
                    "id": r.id,
                    "action": r.action,
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "user_id": r.user_id,
                    "ip_address": r.ip_address,
                    "request_id": r.request_id,
                    "details": r.details,
                    "integrity_hash": r.integrity_hash,
                    "prev_hash": r.prev_hash,
                    "created_at": r.created_at.isoformat(),
                }
                for r in records
            ],
            "limit": limit,
            "offset": offset,
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/audit/validate", response_model=APIResponse)
async def validate_audit_chain_endpoint(
    db: DbSessionDep,
    current_user: AdminReviewerDep,
    limit: int = Query(500, ge=1, le=5000),
    action: str | None = None,
    user_id: str | None = None,
):
    """Validate the integrity chain of the most recent audit records."""
    records = get_audit_log(
        db,
        tenant_id=current_user["tenant_id"],
        limit=limit,
        offset=0,
        action=action,
        user_id=user_id,
    )
    # Chain validation requires oldest-first ordering
    records_sorted = sorted(records, key=lambda r: r.created_at)
    is_valid, errors = validate_audit_chain(records_sorted)

    return APIResponse(
        success=True,
        data={
            "is_valid": is_valid,
            "records_checked": len(records),
            "errors": errors,
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/audit/export")
async def export_audit_trail(
    db: DbSessionDep,
    current_user: AdminDep,
    format: str = Query("json", pattern="^(json|csv)$"),
    limit: int = Query(10000, ge=1, le=50000),
    action: str | None = None,
    user_id: str | None = None,
):
    """Export audit trail as JSON or CSV with chain validation."""
    records = get_audit_log(
        db,
        tenant_id=current_user["tenant_id"],
        limit=limit,
        offset=0,
        action=action,
        user_id=user_id,
    )
    records_sorted = sorted(records, key=lambda r: r.created_at)
    is_valid, errors = validate_audit_chain(records_sorted)

    records_data = [
        {
            "id": r.id,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "user_id": r.user_id,
            "ip_address": r.ip_address,
            "request_id": r.request_id,
            "details": r.details,
            "integrity_hash": r.integrity_hash,
            "prev_hash": r.prev_hash,
            "created_at": r.created_at.isoformat(),
        }
        for r in records_sorted
    ]

    if format == "csv":
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "id", "action", "resource_type", "resource_id",
                "user_id", "ip_address", "request_id", "details",
                "integrity_hash", "prev_hash", "created_at",
            ],
        )
        writer.writeheader()
        writer.writerows(records_data)
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
            },
        )

    # JSON
    return APIResponse(
        success=True,
        data={
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "records_checked": len(records),
            "chain_valid": is_valid,
            "chain_errors": errors,
            "records": records_data,
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )
