from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Any, Dict, TypedDict
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic_settings import BaseSettings
from sqlalchemy.orm import Session

from database import SessionLocal


class UserContext(TypedDict):
    user_id: str
    tenant_id: str
    role: str
    email: str | None
    token_id: str | None
    claims: Dict[str, Any]


class DemoUser(TypedDict):
    username: str
    user_id: str
    tenant_id: str
    role: str
    email: str


class AuthSettings(BaseSettings):
    reviewer_roles: str = "reviewer,admin"
    jwt_secret: str = "aibaa-demo-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "aibaa.local"
    jwt_audience: str = "aibaa-api"
    jwt_expire_minutes: int = 480
    jwt_jwks_url: str | None = None
    session_cookie_name: str = "aibaa_session"
    # Secure by default: cookies only travel over TLS. Local HTTP dev must
    # explicitly opt out with AIBAA_SESSION_COOKIE_SECURE=false.
    session_cookie_secure: bool = True
    session_cookie_samesite: str = "lax"
    demo_password: str = "AIBAA-demo-2026!"
    demo_tenant_id: str = "org_demo"

    model_config = {"env_prefix": "AIBAA_"}

    @property
    def default_tenant_id(self) -> str:
        return self.demo_tenant_id

    @property
    def default_user_id(self) -> str:
        return "usr_demo_analyst"


@lru_cache
def get_auth_settings() -> AuthSettings:
    return AuthSettings()


security = HTTPBearer(auto_error=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _parse_csv_env(raw: str) -> set[str]:
    return {item.strip().lower() for item in (raw or "").split(",") if item.strip()}


def get_demo_users(settings: AuthSettings | None = None) -> dict[str, DemoUser]:
    auth_settings = settings or get_auth_settings()
    tenant_id = auth_settings.demo_tenant_id
    return {
        "analyst": {
            "username": "analyst",
            "user_id": "usr_demo_analyst",
            "tenant_id": tenant_id,
            "role": "analyst",
            "email": "analyst@demo.aibaa.local",
        },
        "reviewer": {
            "username": "reviewer",
            "user_id": "usr_demo_reviewer",
            "tenant_id": tenant_id,
            "role": "reviewer",
            "email": "reviewer@demo.aibaa.local",
        },
        "admin": {
            "username": "admin",
            "user_id": "usr_demo_admin",
            "tenant_id": tenant_id,
            "role": "admin",
            "email": "admin@demo.aibaa.local",
        },
    }


def authenticate_demo_user(username: str, password: str) -> DemoUser:
    settings = get_auth_settings()
    if password != settings.demo_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid demo credentials")

    normalized = username.strip().lower()
    demo_users = get_demo_users(settings)
    for user in demo_users.values():
        if normalized in {user["username"], user["email"], user["role"]}:
            return user

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid demo credentials")


def _claims_to_user_context(claims: Dict[str, Any]) -> UserContext:
    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    tenant_id = str(claims.get("tenant_id") or claims.get("tid") or "").strip()
    role = str(claims.get("role") or "").strip()
    email = claims.get("email")
    token_id = claims.get("jti")

    if not user_id or not tenant_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is missing required claims",
        )

    return {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "email": str(email).strip() if isinstance(email, str) and email.strip() else None,
        "token_id": str(token_id).strip() if isinstance(token_id, str) and token_id.strip() else None,
        "claims": claims,
    }


def _jwt_decode_options(settings: AuthSettings) -> dict[str, Any]:
    options = {
        "require": ["exp", "iat", "sub"],
        "verify_signature": True,
    }
    if not settings.jwt_issuer:
        options["verify_iss"] = False
    if not settings.jwt_audience:
        options["verify_aud"] = False
    return options


@lru_cache
def _get_jwk_client(jwks_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url)


def decode_access_token(token: str, settings: AuthSettings | None = None) -> Dict[str, Any]:
    auth_settings = settings or get_auth_settings()
    algorithm = auth_settings.jwt_algorithm.strip().upper()
    options = _jwt_decode_options(auth_settings)

    try:
        if auth_settings.jwt_jwks_url and algorithm.startswith("RS"):
            signing_key = _get_jwk_client(auth_settings.jwt_jwks_url).get_signing_key_from_jwt(token).key
            return jwt.decode(
                token,
                signing_key,
                algorithms=[algorithm],
                audience=auth_settings.jwt_audience or None,
                issuer=auth_settings.jwt_issuer or None,
                options=options,
            )

        return jwt.decode(
            token,
            auth_settings.jwt_secret,
            algorithms=[algorithm],
            audience=auth_settings.jwt_audience or None,
            issuer=auth_settings.jwt_issuer or None,
            options=options,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: {exc}",
        ) from exc


def create_access_token(
    *,
    user_id: str,
    tenant_id: str,
    role: str,
    email: str | None = None,
    settings: AuthSettings | None = None,
) -> tuple[str, datetime]:
    auth_settings = settings or get_auth_settings()
    if not auth_settings.jwt_algorithm.strip().upper().startswith("HS"):
        raise RuntimeError("Local token issuing only supports HS* JWT algorithms")

    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=max(5, auth_settings.jwt_expire_minutes))
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "email": email,
        "iss": auth_settings.jwt_issuer,
        "aud": auth_settings.jwt_audience,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": f"tok_{uuid4().hex}",
    }
    token = jwt.encode(payload, auth_settings.jwt_secret, algorithm=auth_settings.jwt_algorithm)
    return token, expires_at


_blocklist_redis = None


def _get_blocklist_client():
    global _blocklist_redis
    if _blocklist_redis is not None:
        return _blocklist_redis
    try:
        import redis as redis_sync

        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        _blocklist_redis = redis_sync.from_url(url, decode_responses=True)
        _blocklist_redis.ping()
        return _blocklist_redis
    except Exception:
        _blocklist_redis = None
        return None


def _is_token_blocklisted(token_id: str | None) -> bool:
    if not token_id:
        return False
    client = _get_blocklist_client()
    if client is None:
        return False
    try:
        return client.exists(f"blocklist:{token_id}") > 0
    except Exception:
        return False


def revoke_token(token_id: str | None, ttl_seconds: int) -> None:
    if not token_id:
        return
    client = _get_blocklist_client()
    if client is None:
        return
    try:
        client.setex(f"blocklist:{token_id}", max(ttl_seconds, 60), "1")
    except Exception:
        return


def set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_auth_settings()
    max_age = max(60, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_auth_settings()
    response.delete_cookie(key=settings.session_cookie_name, path="/")


def _get_request_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    settings = get_auth_settings()
    cookie_token = request.cookies.get(settings.session_cookie_name)
    if cookie_token:
        return cookie_token.strip()
    if credentials and credentials.credentials:
        return credentials.credentials.strip()
    return None


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserContext:
    token = _get_request_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
        )

    settings = get_auth_settings()
    claims = decode_access_token(token, settings)
    user = _claims_to_user_context(claims)

    if _is_token_blocklisted(user.get("token_id")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been revoked",
        )

    return user


def require_roles(*allowed_roles: str):
    normalized_roles = {role.strip().lower() for role in allowed_roles if role.strip()}

    def dependency(current_user: UserContext = Depends(get_current_user)) -> UserContext:
        if current_user["role"].strip().lower() not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user['role']}' is not allowed to perform this action",
            )
        return current_user

    return dependency


def require_reviewer_role(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    reviewer_roles = _parse_csv_env(get_auth_settings().reviewer_roles)
    if current_user["role"].strip().lower() not in reviewer_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user['role']}' is not allowed to approve outputs",
        )
    return current_user


DbSessionDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[UserContext, Depends(get_current_user)]
ReviewerUserDep = Annotated[UserContext, Depends(require_reviewer_role)]
AdminReviewerDep = Annotated[UserContext, Depends(require_roles("admin", "reviewer"))]
AdminDep = Annotated[UserContext, Depends(require_roles("admin"))]
