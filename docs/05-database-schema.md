# 05 — Database Schema
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Overview

**v1 Storage Strategy:** SQLAlchemy async ORM with SQLite (local development) or PostgreSQL (production). Switched from environment variable — zero code changes required to promote from SQLite to Postgres.

**v2 Target:** PostgreSQL with read replicas, Redis for caching, ChromaDB for vector storage.

**Key design principles:**
- Every table includes `org_id` for multi-tenant isolation
- `audit_logs` is append-only — no UPDATE or DELETE ever
- `documents` includes `data_classification` for MNPI handling
- `agent_runs` stores `agent_version` for reproducibility
- All UUIDs generated server-side

---

## 2. Entity Relationship Diagram

```
┌─────────────────┐       ┌───────────────────┐       ┌──────────────────┐
│      deals      │──1:N──│     documents      │       │   agent_runs     │
└─────────────────┘       └───────────────────┘       └──────────────────┘
        │                                                       │
        │──1:N──────────────────────────────────────────────▶──┘
        │
        │──1:N──┌───────────────┐
                │    outputs    │
                └───────────────┘
        │
        │──1:N──┌───────────────┐
                │     tasks     │
                └───────────────┘
        │
        │──1:N──┌─────────────────┐
                │  activity_logs  │ (append-only)
                └─────────────────┘

┌──────────────────────┐
│  webhook_endpoints   │ (org-level, not deal-level)
└──────────────────────┘

┌───────────────────────┐
│       settings        │ (org-level configuration)
└───────────────────────┘
```

---

## 3. Table Definitions

### 3.1 `deals`

```sql
CREATE TABLE deals (
    id              UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          VARCHAR(36)  NOT NULL,                -- tenant scoping — all queries filter by this
    name            VARCHAR(80)  NOT NULL,
    company_name    VARCHAR(80)  NOT NULL,
    deal_type       VARCHAR(30)  NOT NULL CHECK (deal_type IN (
                        'ma_buyside', 'ma_sellside', 'ipo',
                        'secondary_offering', 'debt_raise',
                        'lbo', 'growth_equity', 'restructuring', 'other'
                    )),
    industry        VARCHAR(60)  NOT NULL,
    deal_stage      VARCHAR(20)  NOT NULL DEFAULT 'preliminary' CHECK (deal_stage IN (
                        'preliminary', 'active', 'final', 'closed', 'dead'
                    )),
    notes           TEXT,
    created_by      VARCHAR(36)  NOT NULL,                -- user_id of creator
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_archived     BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_deals_org_id      ON deals (org_id);
CREATE INDEX idx_deals_deal_type   ON deals (deal_type);
CREATE INDEX idx_deals_deal_stage  ON deals (deal_stage);
CREATE INDEX idx_deals_created_at  ON deals (created_at DESC);

-- Row-level security (PostgreSQL production)
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;
CREATE POLICY deals_org_isolation ON deals
    USING (org_id = current_setting('app.current_org_id'));
```

---

### 3.2 `documents`

```sql
CREATE TABLE documents (
    id                  UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id             UUID         NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    org_id              VARCHAR(36)  NOT NULL,
    filename            VARCHAR(255) NOT NULL,
    original_name       VARCHAR(255) NOT NULL,
    file_type           VARCHAR(10)  NOT NULL CHECK (file_type IN (
                            'pdf', 'docx', 'xlsx', 'csv', 'txt'
                        )),
    file_size_bytes     BIGINT       NOT NULL,
    storage_path        TEXT         NOT NULL,            -- local path (dev) or S3 key (prod)
    doc_category        VARCHAR(50),                      -- 'financial', 'legal', 'corporate', 'tax', 'operational'

    -- Data classification (MNPI handling)
    data_classification VARCHAR(20)  NOT NULL DEFAULT 'internal' CHECK (data_classification IN (
                            'public', 'internal', 'confidential', 'mnpi'
                        )),

    -- Parsing
    parsed_text         TEXT,                             -- full extracted text (stored for RAG indexing)
    parse_status        VARCHAR(20)  NOT NULL DEFAULT 'pending' CHECK (parse_status IN (
                            'pending', 'processing', 'completed', 'failed'
                        )),
    parse_error         TEXT,

    -- RAG indexing status (NEW)
    rag_status          VARCHAR(20)  NOT NULL DEFAULT 'pending' CHECK (rag_status IN (
                            'pending', 'indexing', 'indexed', 'failed'
                        )),
    rag_chunk_count     INTEGER,
    rag_error           TEXT,

    uploaded_by         VARCHAR(36)  NOT NULL,            -- user_id
    uploaded_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_deal_id          ON documents (deal_id);
CREATE INDEX idx_documents_org_id           ON documents (org_id);
CREATE INDEX idx_documents_doc_category     ON documents (doc_category);
CREATE INDEX idx_documents_data_class       ON documents (data_classification);
CREATE INDEX idx_documents_rag_status       ON documents (rag_status);
```

**Field Notes:**
- `data_classification = 'mnpi'` triggers a consent check before any agent uses this document with an external LLM.
- `rag_status` tracks background indexing. Agents should only run after relevant docs are `indexed`.
- `parsed_text` is kept for re-indexing if the embedding model changes.

---

### 3.3 `agent_runs`

```sql
CREATE TABLE agent_runs (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id          UUID         NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    org_id           VARCHAR(36)  NOT NULL,
    initiated_by     VARCHAR(36)  NOT NULL,               -- user_id
    agent_type       VARCHAR(30)  NOT NULL CHECK (agent_type IN (
                         'orchestrator', 'modeling', 'pitchbook',
                         'due_diligence', 'research', 'doc_drafter', 'coordination'
                     )),
    agent_version    VARCHAR(20)  NOT NULL DEFAULT '1.0.0', -- NEW: for reproducibility + audit
    task_name        VARCHAR(100) NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'queued' CHECK (status IN (
                         'queued', 'running', 'completed', 'failed', 'cancelled'
                     )),
    input_payload    JSONB        NOT NULL DEFAULT '{}',
    llm_backend      VARCHAR(30)  NOT NULL DEFAULT 'anthropic', -- which provider was used
    llm_model        VARCHAR(60),                          -- e.g. 'claude-opus-4-6'
    llm_prompt       TEXT,                                 -- stored for audit (encrypted in prod)
    llm_response     TEXT,                                 -- raw response (encrypted in prod)
    reasoning_steps  JSONB        NOT NULL DEFAULT '[]',
    rag_chunks_used  JSONB        NOT NULL DEFAULT '[]',   -- NEW: which chunks were retrieved
    mnpi_consent     BOOLEAN      NOT NULL DEFAULT FALSE,  -- NEW: was MNPI consent given?
    confidence_score FLOAT CHECK (confidence_score BETWEEN 0 AND 1),
    error_message    TEXT,
    arq_job_id       VARCHAR(100),                         -- NEW: links to ARQ queue job
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_runs_deal_id    ON agent_runs (deal_id);
CREATE INDEX idx_agent_runs_org_id     ON agent_runs (org_id);
CREATE INDEX idx_agent_runs_status     ON agent_runs (status);
CREATE INDEX idx_agent_runs_agent_type ON agent_runs (agent_type);
CREATE INDEX idx_agent_runs_created_at ON agent_runs (created_at DESC);
```

**Field Notes:**
- `agent_version` enables audit: "this output was produced by modeling agent v1.2.0 using prompt template v3".
- `rag_chunks_used` stores the chunk IDs that were retrieved — allows tracing exactly which source text influenced the output.
- `mnpi_consent` is `TRUE` only if the user explicitly confirmed the MNPI consent banner.
- `llm_prompt` and `llm_response` should be encrypted at rest in production (column-level encryption or envelope encryption via AWS KMS).

---

### 3.4 `outputs`

```sql
CREATE TABLE outputs (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id          UUID         NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    org_id           VARCHAR(36)  NOT NULL,
    agent_run_id     UUID         NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    filename         VARCHAR(255) NOT NULL,
    output_type      VARCHAR(10)  NOT NULL CHECK (output_type IN (
                         'xlsx', 'pdf', 'docx', 'pptx', 'md', 'json'
                     )),
    output_category  VARCHAR(50)  NOT NULL CHECK (output_category IN (
                         'financial_model', 'pitchbook', 'dd_report',
                         'research_brief', 'deal_document', 'task_tracker', 'other'
                     )),
    storage_path     TEXT         NOT NULL,
    file_size_bytes  BIGINT,
    review_status    VARCHAR(30)  NOT NULL DEFAULT 'draft' CHECK (review_status IN (
                         'draft', 'approved', 'revision_requested', 'archived'
                     )),
    reviewer_id      VARCHAR(36),                          -- user_id of approver
    reviewer_notes   TEXT,
    disclaimer_embedded BOOLEAN   NOT NULL DEFAULT FALSE,  -- NEW: was disclaimer added to output?
    version          INT          NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_outputs_deal_id       ON outputs (deal_id);
CREATE INDEX idx_outputs_org_id        ON outputs (org_id);
CREATE INDEX idx_outputs_review_status ON outputs (review_status);
CREATE INDEX idx_outputs_output_type   ON outputs (output_type);
```

---

### 3.5 `tasks`

```sql
CREATE TABLE tasks (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    deal_id          UUID         NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    org_id           VARCHAR(36)  NOT NULL,
    agent_run_id     UUID         REFERENCES agent_runs(id) ON DELETE SET NULL,
    title            VARCHAR(200) NOT NULL,
    description      TEXT,
    owner            VARCHAR(100),
    assigned_to      VARCHAR(36),                          -- user_id (if in-system user)
    status           VARCHAR(20)  NOT NULL DEFAULT 'todo' CHECK (status IN (
                         'todo', 'in_progress', 'completed', 'blocked', 'cancelled'
                     )),
    priority         VARCHAR(10)  NOT NULL DEFAULT 'medium' CHECK (priority IN (
                         'low', 'medium', 'high', 'critical'
                     )),
    due_date         DATE,
    completed_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    is_ai_generated  BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_tasks_deal_id   ON tasks (deal_id);
CREATE INDEX idx_tasks_org_id    ON tasks (org_id);
CREATE INDEX idx_tasks_status    ON tasks (status);
CREATE INDEX idx_tasks_due_date  ON tasks (due_date);
```

---

### 3.6 `audit_logs` *(append-only — no UPDATE or DELETE)*

```sql
CREATE TABLE audit_logs (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           VARCHAR(36)  NOT NULL,
    user_id          VARCHAR(36),                          -- NULL for system/background events
    event_type       VARCHAR(60)  NOT NULL,
    entity_type      VARCHAR(30),
    entity_id        VARCHAR(36),
    description      VARCHAR(500) NOT NULL,
    metadata         JSONB        NOT NULL DEFAULT '{}',
    ip_address       VARCHAR(45),                          -- IPv6-safe length
    integrity_hash   VARCHAR(64)  NOT NULL,                -- SHA-256 chain hash (tamper detection)
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_org_id      ON audit_logs (org_id);
CREATE INDEX idx_audit_event_type  ON audit_logs (event_type);
CREATE INDEX idx_audit_user_id     ON audit_logs (user_id);
CREATE INDEX idx_audit_created_at  ON audit_logs (created_at DESC);

-- CRITICAL: Prevent any modification of audit records
-- Apply this in PostgreSQL production:
REVOKE UPDATE, DELETE ON audit_logs FROM aibaa_app_user;

-- Standard event_type values:
-- user_login, user_login_failed, user_mfa_passed, user_logout
-- deal_created, deal_updated, deal_archived
-- document_uploaded, document_deleted, document_mnpi_flagged
-- rag_indexing_started, rag_indexing_completed
-- agent_run_queued, agent_run_started, agent_run_completed, agent_run_failed
-- mnpi_consent_given
-- output_generated, output_approved, output_revision_requested
-- flag_reviewed, flag_dismissed
-- setting_updated
-- webhook_delivered, webhook_failed
-- prompt_injection_attempt
```

---

### 3.7 `webhook_endpoints` *(NEW)*

```sql
CREATE TABLE webhook_endpoints (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           VARCHAR(36)  NOT NULL,
    name             VARCHAR(100) NOT NULL,
    url              VARCHAR(500) NOT NULL,
    events           JSONB        NOT NULL DEFAULT '[]',   -- e.g. ["agent.completed", "output.approved"]
    secret           VARCHAR(64)  NOT NULL,                -- HMAC signing secret (stored hashed)
    is_active        BOOLEAN      NOT NULL DEFAULT TRUE,
    failure_count    INTEGER      NOT NULL DEFAULT 0,      -- disabled after 5 consecutive failures
    last_success_at  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_webhooks_org_id ON webhook_endpoints (org_id);
```

---

### 3.8 `settings`

```sql
CREATE TABLE settings (
    org_id           VARCHAR(36)  NOT NULL,
    key              VARCHAR(100) NOT NULL,
    value            TEXT         NOT NULL,
    value_type       VARCHAR(20)  NOT NULL DEFAULT 'string' CHECK (value_type IN (
                         'string', 'integer', 'float', 'boolean', 'json'
                     )),
    description      TEXT,
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (org_id, key)
);

-- Default seed data (applied per org on creation):
-- ('llm_backend',            'anthropic',   'string',  'LLM provider: anthropic | openai | colab')
-- ('llm_model',              'claude-opus-4-6', 'string', 'Model name for the selected provider')
-- ('llm_max_tokens',         '4096',        'integer', 'Max tokens per LLM completion')
-- ('llm_temperature',        '0.2',         'float',   'Temperature (lower = more deterministic)')
-- ('hallucination_guard',    'true',        'boolean', 'Enable numerical verification step')
-- ('max_upload_size_mb',     '50',          'integer', 'Maximum file upload size in MB')
-- ('data_retention_days',    '2555',        'integer', '7 years regulatory minimum')
-- ('mnpi_consent_required',  'true',        'boolean', 'Require consent before using MNPI docs')
-- ('rag_chunk_size',         '512',         'integer', 'Chunk size for RAG indexing (tokens)')
-- ('rag_top_k',              '8',           'integer', 'Number of chunks to retrieve per query')
-- ('dcf_mid_year_discount',  'true',        'boolean', 'Use mid-year discounting convention')
```

---

## 4. SQLAlchemy Python Implementation

```python
# apps/api/src/database.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, sessionmaker
import os

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./aibaa.db"   # dev default — swap for postgres in prod
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# apps/api/src/models/deal.py
from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
import uuid

class DealModel(Base):
    __tablename__ = "deals"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id      = Column(String(36), nullable=False, index=True)
    name        = Column(String(80), nullable=False)
    company_name = Column(String(80), nullable=False)
    deal_type   = Column(String(30), nullable=False)
    deal_stage  = Column(String(20), nullable=False, default="preliminary")
    notes       = Column(Text)
    created_by  = Column(String(36), nullable=False)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())
    is_archived = Column(Boolean, default=False, nullable=False)
```

---

## 5. Data Retention Policy

| Data Type | Retention | Notes |
|---|---|---|
| Deal metadata | Until archived + retention period | Default 7 years (configurable) |
| Uploaded documents | Per org retention policy (min 7 yrs for MNPI) | Secure deletion after expiry |
| Generated outputs | Per org retention policy | Never auto-deleted while deal is active |
| Agent run logs | 7 years minimum | Regulatory requirement |
| LLM prompts/responses | 7 years (encrypted at rest) | Required for audit |
| Audit logs | Permanent — never deleted | Append-only; legal requirement |
| Webhook delivery logs | 90 days | Operational only |
| Idempotency keys (Redis) | 24 hours | Operational cache |

---

## 6. Alembic Migration Setup

```bash
# Initialise (run once)
alembic init alembic

# Create a new migration after schema changes
alembic revision --autogenerate -m "add_rag_fields_to_documents"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

Every schema change goes through Alembic. No `CREATE TABLE` or `ALTER TABLE` statements are ever run manually — this ensures the SQLite dev environment and PostgreSQL prod environment stay in sync.

---

*End of Document — 05-database-schema.md*
