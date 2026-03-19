import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import redis
from fastapi import APIRouter, HTTPException

from dependencies import CurrentUserDep, DevBootstrapTokenDep, issue_dev_access_token
from models import APIResponse, AuthTokenResponse, CurrentUserResponse, DevAuthTokenRequest, Meta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Auth"])

_redis_client: Optional[redis.Redis] = None


def _get_redis() -> Optional[redis.Redis]:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.from_url(url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None


@router.post("/dev-token", response_model=APIResponse)
async def create_dev_token(
    payload: DevAuthTokenRequest,
    x_dev_api_token: DevBootstrapTokenDep,
):
    token, expires_at, user = issue_dev_access_token(
        requested_role=payload.requested_role,
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        email=payload.email,
        x_dev_api_token=x_dev_api_token,
    )
    return APIResponse(
        success=True,
        data=AuthTokenResponse(
            access_token=token,
            expires_at=expires_at.isoformat(),
            user=CurrentUserResponse(
                user_id=user["user_id"],
                tenant_id=user["tenant_id"],
                role=user["role"],
                email=user["email"],
                token_id=user["token_id"],
            ),
        ),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.get("/me", response_model=APIResponse)
async def get_me(current_user: CurrentUserDep):
    return APIResponse(
        success=True,
        data=CurrentUserResponse(
            user_id=current_user["user_id"],
            tenant_id=current_user["tenant_id"],
            role=current_user["role"],
            email=current_user["email"],
            token_id=current_user["token_id"],
        ),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.post("/logout", response_model=APIResponse)
async def logout(current_user: CurrentUserDep):
    """Invalidate the current token by adding it to a Redis blocklist."""
    token_id = current_user.get("token_id")
    if not token_id:
        raise HTTPException(status_code=400, detail="No token_id in session")

    r = _get_redis()
    if r is not None:
        try:
            import jwt as _jwt
            from dependencies import get_auth_settings
            settings = get_auth_settings()
            try:
                payload = _jwt.decode(
                    r.credentials if hasattr(r, "credentials") else "",
                    settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": False},
                )
            except Exception:
                pass
            # Add token_id to Redis blocklist with 8h TTL
            r.setex(f"blocklist:{token_id}", 28800, "1")
            logger.info("token_blocklisted", token_id=token_id, user_id=current_user["user_id"])
        except Exception as exc:
            logger.warning("Redis blocklist write failed: %s", exc)

    from audit import log_security_event
    from database import SessionLocal
    db = SessionLocal()
    try:
        log_security_event(
            db=db,
            action="auth.logout",
            tenant_id=current_user["tenant_id"],
            user_id=current_user["user_id"],
        )
    finally:
        db.close()

    return APIResponse(success=True, data={"message": "Logged out successfully"}, meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"))

