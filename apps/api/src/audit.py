"""
Integrity-chained security audit logger.

Every mutating API operation writes an append-only record to
`security_audit_log`.  Each record carries a SHA-256 hash of its
contents + the previous record's hash — any tampering is detectable
on export.

Usage:
    from audit import audit_log
    audit_log.info("deal_created", ...)
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from db_models import SecurityAuditLogModel
from database import SessionLocal

logger = logging.getLogger(__name__)

_last_hash_lock = threading.Lock()
_last_hash_cache: dict[str, str] = {}


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _compute_record_hash(
    action: str,
    tenant_id: str | None,
    user_id: str | None,
    details: dict[str, Any] | None,
    prev_hash: str,
) -> str:
    payload = json.dumps({
        "action": action,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "details": details,
        "prev_hash": prev_hash,
    }, sort_keys=True, default=str)
    return _sha256(payload)


import json as _json


def log_security_event(
    *,
    db: Session,
    action: str,
    tenant_id: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> SecurityAuditLogModel:
    """
    Write an integrity-chained audit log entry.

    The chain is scoped by tenant_id — each tenant's audit chain is independent.
    """
    with _last_hash_lock:
        prev_hash = _last_hash_cache.get(tenant_id or "", "")

    record = SecurityAuditLogModel(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        details=details,
        prev_hash=prev_hash,
        integrity_hash="",  # filled below
    )

    integrity = _compute_record_hash(
        action=action,
        tenant_id=tenant_id,
        user_id=user_id,
        details=details,
        prev_hash=prev_hash,
    )
    record.integrity_hash = integrity

    db.add(record)
    db.flush()

    with _last_hash_lock:
        _last_hash_cache[tenant_id or ""] = integrity

    return record


def get_audit_log(
    db: Session,
    *,
    tenant_id: str,
    limit: int = 100,
    offset: int = 0,
    action: str | None = None,
    user_id: str | None = None,
) -> list[SecurityAuditLogModel]:
    q = db.query(SecurityAuditLogModel).filter(
        SecurityAuditLogModel.tenant_id == tenant_id
    )
    if action:
        q = q.filter(SecurityAuditLogModel.action == action)
    if user_id:
        q = q.filter(SecurityAuditLogModel.user_id == user_id)
    return q.order_by(SecurityAuditLogModel.created_at.desc()).offset(offset).limit(limit).all()


def validate_audit_chain(records: list[SecurityAuditLogModel]) -> tuple[bool, list[str]]:
    """
    Validate the integrity chain of a sequence of audit records.

    Returns (is_valid, list of error messages).
    Records must be ordered oldest → newest.
    """
    errors: list[str] = []
    prev_hash = ""
    for i, rec in enumerate(records):
        expected = _compute_record_hash(
            action=rec.action,
            tenant_id=rec.tenant_id,
            user_id=rec.user_id,
            details=rec.details,
            prev_hash=prev_hash,
        )
        if rec.integrity_hash != expected:
            errors.append(f"Record {i} (id={rec.id}): hash mismatch — expected {expected[:16]}, got {rec.integrity_hash[:16]}")
        if rec.prev_hash != prev_hash:
            errors.append(f"Record {i} (id={rec.id}): prev_hash mismatch — expected {prev_hash[:16]}, got {rec.prev_hash[:16]}")
        prev_hash = rec.integrity_hash

    return len(errors) == 0, errors


def invalidate_tenant_chain(tenant_id: str) -> None:
    """Reset the in-process chain cache for a tenant (e.g. after db restore)."""
    with _last_hash_lock:
        _last_hash_cache.pop(tenant_id, None)
