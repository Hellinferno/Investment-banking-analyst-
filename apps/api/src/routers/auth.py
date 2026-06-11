import hmac
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

logger = logging.getLogger(__name__)

# Roles the dev-token endpoint may mint. Privilege-escalation to admin is never
# allowed through this bootstrap path — admin must be provisioned out-of-band.
_DEV_TOKEN_ALLOWED_ROLES = {"analyst", "reviewer"}
_WELL_KNOWN_DEV_TOKENS = {"dev-local-token", "dev-token", "changeme", ""}
_MIN_DEV_TOKEN_LEN = 32

from audit import log_security_event
from dependencies import (
    CurrentUserDep,
    DbSessionDep,
    authenticate_demo_user,
    clear_session_cookie,
    create_access_token,
    get_demo_users,
    revoke_token,
    set_session_cookie,
)
from models import (
    APIResponse,
    AuthTokenResponse,
    CurrentUserResponse,
    DevAuthTokenRequest,
    LoginRequest,
    LoginResponse,
    Meta,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/dev-token", response_model=APIResponse)
async def issue_dev_token(
    payload: DevAuthTokenRequest,
    x_dev_api_token: str | None = Header(default=None, alias="X-Dev-API-Token"),
):
    """Issue a local JWT for tests and development role switching.

    Fail-closed: this endpoint is OPT-IN. It is reachable only when
    ``AIBAA_ENV`` is explicitly ``development`` or ``test`` AND a strong,
    non-default ``AIBAA_DEV_BOOTSTRAP_TOKEN`` (>= 32 chars) is configured.
    Any other state returns 404 so the route is indistinguishable from absent.
    It can never mint an ``admin`` token.
    """
    env = os.environ.get("AIBAA_ENV", "").strip().lower()
    if env not in ("development", "test"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    expected = os.environ.get("AIBAA_DEV_BOOTSTRAP_TOKEN", "")
    if expected in _WELL_KNOWN_DEV_TOKENS or len(expected) < _MIN_DEV_TOKEN_LEN:
        logger.warning(
            "Dev-token endpoint hit but AIBAA_DEV_BOOTSTRAP_TOKEN is unset, default, "
            "or too short (<%d chars) — refusing.", _MIN_DEV_TOKEN_LEN,
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    # Constant-time comparison to avoid leaking the token via timing.
    if not hmac.compare_digest(x_dev_api_token or "", expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid dev token")

    role = payload.requested_role.strip().lower()
    if role not in _DEV_TOKEN_ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Dev tokens may only be issued for roles: {sorted(_DEV_TOKEN_ALLOWED_ROLES)}",
        )
    demo_user = get_demo_users().get(role)
    if not demo_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported demo role")

    user_id = payload.user_id or demo_user["user_id"]
    tenant_id = payload.tenant_id or demo_user["tenant_id"]
    email = payload.email or demo_user["email"]
    token, expires_at = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        email=email,
    )

    return APIResponse(
        success=True,
        data=AuthTokenResponse(
            access_token=token,
            expires_at=expires_at.isoformat(),
            user=CurrentUserResponse(
                user_id=user_id,
                tenant_id=tenant_id,
                role=role,
                email=email,
                token_id=None,
            ),
        ),
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )


@router.post("/login", response_model=APIResponse)
async def login(payload: LoginRequest, response: Response, request: Request, db: DbSessionDep):
    demo_user = authenticate_demo_user(payload.username, payload.password)
    token, expires_at = create_access_token(
        user_id=demo_user["user_id"],
        tenant_id=demo_user["tenant_id"],
        role=demo_user["role"],
        email=demo_user["email"],
    )
    set_session_cookie(response, token, expires_at)
    log_security_event(
        db=db,
        action="auth.login",
        tenant_id=demo_user["tenant_id"],
        user_id=demo_user["user_id"],
        resource_type="session",
        resource_id=demo_user["user_id"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        details={"username": demo_user["username"], "role": demo_user["role"]},
    )
    return APIResponse(
        success=True,
        data=LoginResponse(
            user=CurrentUserResponse(
                user_id=demo_user["user_id"],
                tenant_id=demo_user["tenant_id"],
                role=demo_user["role"],
                email=demo_user["email"],
                token_id=None,
            ),
            session_expires_at=expires_at.isoformat(),
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
async def logout(
    response: Response,
    request: Request,
    current_user: CurrentUserDep,
    db: DbSessionDep,
):
    if current_user.get("token_id"):
        now = datetime.now(timezone.utc).timestamp()
        exp = float(current_user["claims"].get("exp", now + 3600))
        revoke_token(current_user["token_id"], int(exp - now))

    clear_session_cookie(response)
    log_security_event(
        db=db,
        action="auth.logout",
        tenant_id=current_user["tenant_id"],
        user_id=current_user["user_id"],
        resource_type="session",
        resource_id=current_user.get("token_id"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return APIResponse(
        success=True,
        data={"message": "Logged out successfully"},
        meta=Meta(request_id=f"req_{uuid.uuid4().hex[:8]}"),
    )
