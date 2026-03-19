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

import db_models  # noqa: F401 - ensure ORM models are registered
from database import Base, SessionLocal, engine
from db_models import DealModel, DocumentModel
from persistence import hydrate_store_from_db, sync_deal_to_store, sync_document_to_store
from routers import agents, auth, deals, documents, outputs, tasks

# Ensure database tables are created synchronously on startup
Base.metadata.create_all(bind=engine)


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

app.include_router(deals.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(agents.router, prefix="/api/v1")
app.include_router(outputs.deal_router, prefix="/api/v1")
app.include_router(outputs.output_router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(tasks.router, prefix="/api/v1")


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
    """Parse a single document in a background thread; update store in-place."""
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
    finally:
        db.close()


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

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    hydrate_store_from_db(db)

    if not _UPLOAD_BASE.exists():
        db.close()
        return

    loop = asyncio.get_event_loop()
    to_parse: list[str] = []

    for deal_dir in _UPLOAD_BASE.iterdir():
        if not deal_dir.is_dir():
            continue
        deal_id = deal_dir.name
        if not _UUID_RE.match(deal_id):
            continue

        # Recover deal stub if not already present.
        db_deal = db.query(DealModel).filter(DealModel.id == deal_id).first()
        if db_deal is None:
            db_deal = DealModel(
                id=deal_id,
                tenant_id="org_cyberbank",
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
    db.close()

    # Fire off parsing in the background — don't await so startup completes fast.
    for doc_id in to_parse:
        loop.run_in_executor(_parse_executor, _parse_in_thread, doc_id)
