import os
from threading import Lock

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

# We default to SQLite for immediate local dev compatibility without forcing the user to spin up Docker Postgres immediately,
# but the code is fully Postgres-ready based on the DB_URL format.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aibaa.db")

# SQLite requires this connect_args flag. Postgres does not.
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Allow writers to wait for the lock instead of failing immediately.
    connect_args["timeout"] = 30

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # WAL lets concurrent background threads (agent pool, parser pools) write
    # without "database is locked" errors. Set per-connection via event hook
    # so pooled connections all get it.
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)

Base = declarative_base()
_schema_ready = False
_schema_lock = Lock()


def _ensure_nullable_column(table_name: str, column_name: str, ddl: str) -> None:
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        return

    existing = {col["name"] for col in inspector.get_columns(table_name)}
    if column_name in existing:
        return

    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))


def _ensure_schema_compatibility() -> None:
    """Apply lightweight additive schema fixes for local/dev databases."""
    _ensure_nullable_column("documents", "rag_indexed_at", "DATETIME")
    _ensure_nullable_column("documents", "rag_error", "VARCHAR")


def ensure_database_ready() -> None:
    """Create tables lazily for direct module/test usage outside FastAPI startup."""
    global _schema_ready
    if _schema_ready:
        return

    with _schema_lock:
        if _schema_ready:
            return
        import db_models  # noqa: F401 - ensure metadata is registered before create_all

        Base.metadata.create_all(bind=engine)
        _ensure_schema_compatibility()
        _reconcile_sqlite_schema()
        _schema_ready = True


def _reconcile_sqlite_schema() -> None:
    """Patch local SQLite DBs created before Alembic migrations were added.

    Production deployments should run Alembic. This is intentionally limited
    to SQLite so tests and developer databases do not fail on additive columns.
    """
    if not SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    additions: dict[str, list[tuple[str, str]]] = {
        "deals": [
            ("process_stage", "VARCHAR"),
            ("stage_last_updated", "DATETIME"),
        ],
        "agent_runs": [
            ("model_provider", "VARCHAR"),
            ("model_name", "VARCHAR"),
            ("prompt_version", "VARCHAR"),
            ("validator_status", "VARCHAR"),
            ("validator_report", "JSON"),
            ("checkpoint_status", "VARCHAR"),
        ],
        "outputs": [
            ("reviewed_by", "VARCHAR"),
            ("reviewed_at", "DATETIME"),
            ("review_comment", "VARCHAR"),
        ],
        "documents": [
            ("is_mnpi", "BOOLEAN DEFAULT 0"),
            ("mnpi_consent_given", "BOOLEAN DEFAULT 0"),
            ("rag_status", "VARCHAR DEFAULT 'pending'"),
        ],
        "tasks": [
            ("description", "VARCHAR"),
            ("due_date", "DATETIME"),
        ],
    }

    with engine.begin() as conn:
        for table_name, cols in additions.items():
            if table_name not in tables:
                continue
            existing = {col["name"] for col in inspector.get_columns(table_name)}
            for column_name, column_type in cols:
                if column_name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")

def get_db():
    ensure_database_ready()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
