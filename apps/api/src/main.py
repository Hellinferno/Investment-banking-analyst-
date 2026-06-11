import sys
import os
import asyncio
import uuid
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Add the src directory to Python path so all modules can be imported
# by name without installing as a package (uvicorn runs from apps/api/).
src_path = Path(__file__).parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic_settings import BaseSettings

from logging_config import configure_logging, get_logger
from middleware import IdempotencyMiddleware, get_limiter
from database import Base, SessionLocal, engine, ensure_database_ready
from db_models import DealModel, DocumentModel
from persistence import hydrate_store_from_db, sync_deal_to_store, sync_document_to_store
from rag.indexing import schedule_rag_indexing, update_document_rag_state
from routers import agents, auth, deals, documents, outputs, tasks
from routers.admin import router as admin_router
from routers.search import router as search_router
from routers.webhooks import router as webhooks_router
from routers.world_monitor import router as world_monitor_router

configure_logging()
logger = get_logger(__name__)

# Ensure database tables are created synchronously on startup
ensure_database_ready()


class Settings(BaseSettings):
    app_name: str = "AIBAA Orchestration API"
    version: str = "1.0.0"
    # Comma-separated list of allowed CORS origins; override via env var.
    allowed_origins: str = (
        "http://localhost:5173,http://localhost:3000,"
        "http://127.0.0.1:5173,http://127.0.0.1:3000"
    )

    model_config = {"env_prefix": "AIBAA_"}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach security-related HTTP response headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # Remove server fingerprint header if present
        if "server" in response.headers:
            del response.headers["server"]
        return response


settings = Settings()

_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]


def _validate_production_security() -> None:
    """Refuse to start in production with insecure defaults.

    Catches the most damaging misconfigurations before the app accepts any
    traffic: a default JWT secret (forgeable cross-tenant admin tokens) and a
    wildcard CORS origin paired with credentialed requests.
    """
    if os.environ.get("AIBAA_ENV", "development").strip().lower() != "production":
        return

    from dependencies import get_auth_settings

    auth_settings = get_auth_settings()
    _DEFAULT_SECRETS = {
        "aibaa-demo-jwt-secret-change-me",
        "aibaa-dev-jwt-secret-change-me",
        "",
    }
    if auth_settings.jwt_secret in _DEFAULT_SECRETS or len(auth_settings.jwt_secret) < 32:
        raise RuntimeError(
            "FATAL: AIBAA_JWT_SECRET is unset, default, or too short (<32 chars) in "
            "production. Set a strong secret (python -c \"import secrets; "
            "print(secrets.token_urlsafe(32))\") before starting."
        )

    if "*" in _origins:
        raise RuntimeError(
            "FATAL: CORS allow_origins contains '*' with credentialed requests "
            "enabled in production. Set AIBAA_ALLOWED_ORIGINS to explicit hosts."
        )

    if not auth_settings.session_cookie_secure:
        logger.warning(
            "AIBAA_SESSION_COOKIE_SECURE is false in production — session cookies "
            "will transmit over plaintext HTTP. Set it to true behind TLS."
        )


_validate_production_security()

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    # Disable /docs and /redoc in production via env; keep on by default for dev.
    docs_url="/docs" if os.environ.get("AIBAA_ENV", "development") != "production" else None,
    redoc_url="/redoc" if os.environ.get("AIBAA_ENV", "development") != "production" else None,
)

# Middleware order matters: outermost first.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    max_age=600,
)

app.add_middleware(IdempotencyMiddleware)

_limiter = get_limiter()
if _limiter:
    try:
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware

        app.state.limiter = _limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)
    except ImportError:
        logger.warning("slowapi unavailable — rate limiting disabled")

app.include_router(deals.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(outputs.deal_router, prefix="/api/v1")
app.include_router(outputs.output_router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(world_monitor_router, prefix="/api/v1")
app.include_router(search_router, prefix="/api/v1")


@app.get("/api/v1/health", tags=["Health"])
async def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Startup: recover deals + documents from disk, then parse in background
# ---------------------------------------------------------------------------

_UPLOAD_BASE = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_ALLOWED_EXTS = {"pdf", "docx", "xlsx", "xls", "csv", "txt", "json"}

_parse_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="doc-parser")


def _parse_in_thread(doc_id: str) -> None:
    """Parse a single document and schedule RAG indexing."""
    from store import store
    from tools.document_parser import parse_document

    doc = store.documents.get(doc_id)
    if not doc or doc.parsed_text:
        return
    doc.parse_status = "parsing"
    text = parse_document(doc.storage_path, doc.file_type)
    doc.parsed_text = text
    doc.parse_status = "parsed" if text else "parse_failed"

    db = SessionLocal()
    try:
        db_doc = db.query(DocumentModel).filter(DocumentModel.id == doc_id).first()
        if db_doc:
            db_doc.parsed_text = text
            db_doc.parse_status = doc.parse_status
            db.commit()
            db.refresh(db_doc)
            sync_document_to_store(db_doc)
    finally:
        db.close()

    if text:
        schedule_rag_indexing(doc_id, doc.deal_id or "")
    else:
        update_document_rag_state(
            doc_id,
            status="failed",
            rag_error="Document parsing failed.",
            rag_indexed_at=None,
        )


@app.on_event("startup")
async def _recover_uploads() -> None:
    """
    On startup, scan the uploads directory and reconstruct in-memory state
    for all deals and documents that already exist on disk.  Each document
    is then parsed in a background thread pool so parsed_text is available
    without blocking the event loop.
    """
    from store import store
    from store import Deal, Document
    from db_models import AgentRunModel

    ensure_database_ready()
    db = SessionLocal()
    try:
        # Reconcile agent runs orphaned by a previous non-graceful shutdown:
        # anything still "running" cannot resume, so mark it failed so the UI
        # stops polling forever and the run is auditable as interrupted.
        stale = (
            db.query(AgentRunModel)
            .filter(AgentRunModel.status == "running")
            .update(
                {
                    AgentRunModel.status: "failed",
                    AgentRunModel.error_message: "Interrupted by server restart while running.",
                },
                synchronize_session=False,
            )
        )
        if stale:
            db.commit()
            logger.warning("Recovered %d agent run(s) stuck in 'running' after restart.", stale)

        hydrate_store_from_db(db)

        if not _UPLOAD_BASE.exists():
            return

        loop = asyncio.get_event_loop()
        to_parse: list[str] = []

        # Disk recovery re-inserts deals under a tenant. Hardcoding one tenant
        # would expose another tenant's restored files; require an explicit
        # opt-in env var, otherwise skip stub creation for unknown deals.
        _recovery_tenant = os.environ.get("AIBAA_RECOVERY_TENANT_ID", "").strip()

        for deal_dir in _UPLOAD_BASE.iterdir():
            if not deal_dir.is_dir():
                continue
            deal_id = deal_dir.name
            if not _UUID_RE.match(deal_id):
                continue

            # Recover deal stub if not already present.
            db_deal = db.query(DealModel).filter(DealModel.id == deal_id).first()
            if db_deal is None:
                if not _recovery_tenant:
                    logger.warning(
                        "Skipping disk recovery for unknown deal %s — set "
                        "AIBAA_RECOVERY_TENANT_ID to enable stub creation.",
                        deal_id,
                    )
                    continue
                db_deal = DealModel(
                    id=deal_id,
                    tenant_id=_recovery_tenant,
                    owner_id="system_recovery",
                    name=f"Recovered Deal ({deal_id[:8]})",
                    company_name="(Restored from disk)",
                )
                db.add(db_deal)
                db.commit()
            sync_deal_to_store(db_deal)

            for fpath in deal_dir.iterdir():
                if not fpath.is_file():
                    continue
                ext = fpath.suffix.lstrip(".").lower()
                if ext not in _ALLOWED_EXTS:
                    continue

                # Filename format: {file_id}_{original_name}
                name_part = fpath.name
                maybe_id = name_part.split("_", 1)[0]
                file_id = maybe_id if _UUID_RE.match(maybe_id) else str(uuid.uuid4())
                original_name = name_part[len(maybe_id) + 1:] if _UUID_RE.match(maybe_id) else name_part

                db_doc = db.query(DocumentModel).filter(DocumentModel.id == file_id).first()
                if db_doc is None:
                    db_doc = DocumentModel(
                        id=file_id,
                        deal_id=deal_id,
                        filename=original_name,
                        file_type=ext,
                        file_size_bytes=fpath.stat().st_size,
                        storage_path=str(fpath),
                        parse_status="pending",
                    )
                    db.add(db_doc)
                    db.commit()
                sync_document_to_store(db_doc)
                to_parse.append(file_id)

        db.commit()
    finally:
        db.close()

    # Fire off parsing in the background — don't await so startup completes fast.
    for doc_id in to_parse:
        loop.run_in_executor(_parse_executor, _parse_in_thread, doc_id)
