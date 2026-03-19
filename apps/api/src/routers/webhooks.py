"""Webhook management: CRUD + HMAC-signed delivery service."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db_models import WebhookModel
from dependencies import CurrentUserDep, DbSessionDep, get_current_user
from models import APIResponse, Meta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


class WebhookCreate(BaseModel):
    url: str = Field(..., min_length=1, max_length=500)
    event_types: list[str] = Field(default_factory=lambda: ["output.created", "agent_run.completed"])
    description: str | None = Field(None, max_length=200)
    is_active: bool = True


class WebhookUpdate(BaseModel):
    url: str | None = Field(None, max_length=500)
    event_types: list[str] | None = None
    description: str | None = Field(None, max_length=200)
    is_active: bool | None = None


def _generate_secret() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[:16]


def _sign_payload(payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def deliver_webhook(
    webhook: WebhookModel,
    event_type: str,
    payload: dict[str, Any],
    timeout: float = 10.0,
) -> tuple[bool, str]:
    """Fire a single webhook. Returns (success, error_message)."""
    if not webhook.is_active:
        return False, "webhook inactive"

    body = json.dumps(payload, default=str).encode()
    signature = _sign_payload(body, webhook.secret or "")

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                webhook.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-AIBAA-Signature": signature,
                    "X-AIBAA-Event": event_type,
                    "User-Agent": "AIBAA-Webhook/1.0",
                },
            )
            if resp.status_code < 400:
                logger.info("webhook_delivered", webhook_id=webhook.id, event=event_type, status=resp.status_code)
                return True, ""
            else:
                msg = f"HTTP {resp.status_code}: {resp.text[:200]}"
                logger.warning("webhook_failed", webhook_id=webhook.id, event=event_type, error=msg)
                return False, msg
    except httpx.TimeoutException:
        msg = "request timed out"
        logger.warning("webhook_timeout", webhook_id=webhook.id, event=event_type)
        return False, msg
    except Exception as exc:
        msg = str(exc)[:200]
        logger.error("webhook_error", webhook_id=webhook.id, event=event_type, error=msg)
        return False, msg


@router.post("", response_model=APIResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreate,
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    webhook = WebhookModel(
        tenant_id=current_user["tenant_id"],
        url=payload.url,
        secret=_generate_secret(),
        event_types=payload.event_types,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)

    from audit import log_security_event
    log_security_event(
        db=db, action="webhook.created",
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        resource_type="webhook", resource_id=webhook.id,
    )

    return APIResponse(
        success=True,
        data={
            "id": webhook.id,
            "url": webhook.url,
            "secret": webhook.secret,
            "event_types": webhook.event_types,
            "description": webhook.description,
            "is_active": webhook.is_active,
            "created_at": webhook.created_at.isoformat(),
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("", response_model=APIResponse)
async def list_webhooks(
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    hooks = (
        db.query(WebhookModel)
        .filter(WebhookModel.tenant_id == current_user["tenant_id"])
        .order_by(WebhookModel.created_at.desc())
        .all()
    )
    return APIResponse(
        success=True,
        data={
            "webhooks": [
                {
                    "id": h.id,
                    "url": h.url,
                    "event_types": h.event_types,
                    "description": h.description,
                    "is_active": h.is_active,
                    "created_at": h.created_at.isoformat(),
                }
                for h in hooks
            ]
        },
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.delete("/{webhook_id}", response_model=APIResponse)
async def delete_webhook(
    webhook_id: str,
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    hook = (
        db.query(WebhookModel)
        .filter(WebhookModel.id == webhook_id, WebhookModel.tenant_id == current_user["tenant_id"])
        .first()
    )
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    db.delete(hook)
    db.commit()

    from audit import log_security_event
    log_security_event(
        db=db, action="webhook.deleted",
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        resource_type="webhook", resource_id=webhook_id,
    )

    return APIResponse(success=True, data={"deleted": webhook_id}, meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"))


@router.post("/{webhook_id}/test", response_model=APIResponse)
async def test_webhook(
    webhook_id: str,
    db: DbSessionDep,
    current_user: CurrentUserDep,
):
    hook = (
        db.query(WebhookModel)
        .filter(WebhookModel.id == webhook_id, WebhookModel.tenant_id == current_user["tenant_id"])
        .first()
    )
    if not hook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    success, error = await deliver_webhook(
        hook,
        event_type="webhook.test",
        payload={
            "event": "webhook.test",
            "webhook_id": hook.id,
            "tenant_id": current_user["tenant_id"],
            "message": "This is a test webhook from AIBAA.",
        },
    )

    return APIResponse(
        success=True,
        data={"delivered": success, "error": error or None},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )
