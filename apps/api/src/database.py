import os
from threading import Lock

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

# We default to SQLite for immediate local dev compatibility without forcing the user to spin up Docker Postgres immediately,
# but the code is fully Postgres-ready based on the DB_URL format.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./aibaa.db")

# SQLite requires this connect_args flag. Postgres does not.
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)

Base = declarative_base()
_schema_ready = False
_schema_lock = Lock()


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
        _schema_ready = True

def get_db():
    ensure_database_ready()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
