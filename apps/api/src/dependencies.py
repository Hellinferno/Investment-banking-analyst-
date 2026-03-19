from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Annotated, Any, Dict, TypedDict
from uuid import uuid4

import jwt
from fastapi import Depends, Header, HTTPException, status
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


class AuthSettings(BaseSettings):
    api_bootstrap_token: str = "dev-local-token"
    default_tenant_id: str = "org_cyberbank"
    default_user_id: str = "usr_proto123"
    default_user_role: str = "analyst"
    default_user_email: str = "demo.user@aibaa.local"
    reviewer_roles: str = "reviewer,admin"
    dev_auth_enabled: bool = True
    dev_allowed_roles: str = "analyst,reviewer,admin"
    jwt_secret: str = "aibaa-dev-jwt-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "aibaa.local"
    jwt_audience: str = "aibaa-api"
    jwt_expire_minutes: int = 480
    jwt_jwks_url: str | None = None

    model_config = {"env_prefix": "AIBAA_"}


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


def _extract_role(claims: Dict[str, Any]) -> str | None:
    direct_role = claims.get("role")
    if isinstance(direct_role, str) and direct_role.strip():
        return direct_role.strip()

    roles = claims.get("roles")
    if isinstance(roles, list):
        for value in roles:
            if isinstance(value, str) and value.strip():
                return value.strip()

    realm_access = claims.get("realm_access")
    if isinstance(realm_access, dict):
        realm_roles = realm_access.get("roles")
        if isinstance(realm_roles, list):
            for value in realm_roles:
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


def _claims_to_user_context(claims: Dict[str, Any]) -> UserContext:
    user_id = str(claims.get("sub") or claims.get("user_id") or "").strip()
    tenant_id = str(
        claims.get("tenant_id")
        or claims.get("tid")
        or claims.get("org_id")
        or claims.get("tenant")
        or ""
    ).strip()
    role = str(_extract_role(claims) or "").strip()
    email = claims.get("email")
    token_id = claims.get("jti")

    if not user_id or not tenant_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT is missing required claims (sub, tenant_id, role)",
            headers={"WWW-Authenticate": "Bearer"},
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
            headers={"WWW-Authenticate": "Bearer"},
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


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UserContext:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()
    settings = get_auth_settings()
    if token == settings.api_bootstrap_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bootstrap token cannot access API routes directly. Exchange it for a JWT first.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = decode_access_token(token, settings)
    return _claims_to_user_context(claims)


def require_roles(*allowed_roles: str):
    normalized_roles = {role.strip().lower() for role in allowed_roles if role.strip()}

    def dependency(current_user: UserContext = Depends(get_current_user)) -> UserContext:
        current_role = current_user["role"].strip().lower()
        if current_role not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user['role']}' is not allowed to perform this action",
            )
        return current_user

    return dependency


def require_reviewer_role(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    reviewer_roles = _parse_csv_env(get_auth_settings().reviewer_roles)
    current_role = current_user["role"].strip().lower()
    if current_role not in reviewer_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user['role']}' is not allowed to approve outputs",
        )
    return current_user


def issue_dev_access_token(
    *,
    requested_role: str,
    tenant_id: str | None,
    user_id: str | None,
    email: str | None,
    x_dev_api_token: str | None,
) -> tuple[str, datetime, UserContext]:
    settings = get_auth_settings()
    env_name = os.environ.get("AIBAA_ENV", "development").strip().lower()
    if not settings.dev_auth_enabled or env_name == "production":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dev auth is disabled")
    if not x_dev_api_token or x_dev_api_token.strip() != settings.api_bootstrap_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid dev bootstrap token")

    allowed_roles = _parse_csv_env(settings.dev_allowed_roles)
    resolved_role = (requested_role or settings.default_user_role).strip().lower()
    if resolved_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requested role '{requested_role}' is not allowed for dev auth",
        )

    resolved_tenant = (tenant_id or settings.default_tenant_id).strip()
    resolved_user = (user_id or settings.default_user_id).strip()
    resolved_email = (email or settings.default_user_email or "").strip() or None
    token, expires_at = create_access_token(
        user_id=resolved_user,
        tenant_id=resolved_tenant,
        role=resolved_role,
        email=resolved_email,
        settings=settings,
    )
    user = _claims_to_user_context(decode_access_token(token, settings))
    return token, expires_at, user


DbSessionDep = Annotated[Session, Depends(get_db)]
CurrentUserDep = Annotated[UserContext, Depends(get_current_user)]
ReviewerUserDep = Annotated[UserContext, Depends(require_reviewer_role)]
DevBootstrapTokenDep = Annotated[str | None, Header(alias="X-Dev-API-Token")]
