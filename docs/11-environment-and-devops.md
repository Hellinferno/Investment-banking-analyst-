# 11 — Environment & DevOps
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Overview

This document covers all environment configurations, tooling, local development setup, and deployment procedures. The entire stack runs via `docker compose up` — no manual Python virtualenv setup, no manual database creation, no "works on my machine."

---

## 2. Development Environments

| Environment | Purpose | Infrastructure |
|---|---|---|
| `local` | Daily development | Docker Compose (all services) |
| `staging` (v2) | Pre-production testing | Railway / Render / Fly.io |
| `production` (v2+) | Live deployment | AWS / GCP with managed Postgres, Redis, S3 |

---

## 3. System Requirements (Host Machine)

| Component | Minimum | Recommended |
|---|---|---|
| OS | macOS 13 / Ubuntu 22.04 / Windows 11 + WSL2 | macOS 14 / Ubuntu 24.04 |
| RAM | 8 GB | 16 GB |
| Disk | 15 GB free | 30 GB free |
| Docker Desktop | 4.20+ | Latest |
| Git | 2.40+ | Latest |

No Python, Node, or PostgreSQL installation required on the host — Docker handles everything.

---

## 4. Docker Compose Configuration

```yaml
# docker-compose.yml
version: "3.9"

services:

  api:
    build:
      context: .
      dockerfile: apps/api/Dockerfile
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://aibaa:secret@db:5432/aibaa
      - REDIS_URL=redis://redis:6379
      - CHROMA_HOST=chroma
      - CHROMA_PORT=8001
    depends_on:
      db:     { condition: service_healthy }
      redis:  { condition: service_healthy }
      chroma: { condition: service_started }
    volumes:
      - ./uploads:/app/uploads
      - ./outputs:/app/outputs

  worker:
    build:
      context: .
      dockerfile: worker/Dockerfile
    command: python -m arq worker.src.main.WorkerSettings
    env_file: .env
    environment:
      - DATABASE_URL=postgresql+asyncpg://aibaa:secret@db:5432/aibaa
      - REDIS_URL=redis://redis:6379
      - CHROMA_HOST=chroma
      - CHROMA_PORT=8001
    depends_on:
      db:    { condition: service_healthy }
      redis: { condition: service_healthy }
    volumes:
      - ./uploads:/app/uploads
      - ./outputs:/app/outputs
      # Mount shared Python packages from monorepo root
      - ./agents:/app/agents
      - ./tools:/app/tools
      - ./rag:/app/rag
      - ./security:/app/security
      - ./computation:/app/computation

  web:
    build:
      context: apps/web
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - VITE_API_BASE_URL=http://localhost:8000/api/v1

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: aibaa
      POSTGRES_USER: aibaa
      POSTGRES_PASSWORD: secret
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aibaa"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  chroma:
    image: chromadb/chroma:0.4.18
    ports:
      - "8001:8000"
    volumes:
      - chroma_data:/chroma/.chroma

volumes:
  postgres_data:
  redis_data:
  chroma_data:
```

```yaml
# docker-compose.override.yml (development — hot reload)
services:
  api:
    command: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
    volumes:
      - ./apps/api/src:/app/src      # Hot reload Python
      - ./agents:/app/agents
      - ./tools:/app/tools
      - ./rag:/app/rag
      - ./security:/app/security
      - ./computation:/app/computation
  web:
    command: pnpm dev --host
    volumes:
      - ./apps/web/src:/app/src      # Hot reload TypeScript
```

---

## 5. Dockerfiles

### `apps/api/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc curl && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared packages from monorepo root
COPY agents/ ./agents/
COPY tools/ ./tools/
COPY rag/ ./rag/
COPY security/ ./security/
COPY computation/ ./computation/

COPY apps/api/src/ ./src/
COPY apps/api/alembic/ ./alembic/
COPY apps/api/alembic.ini .

# Run database migrations on startup, then start server
CMD alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000

RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser
```

### `worker/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/ ./agents/
COPY tools/ ./tools/
COPY rag/ ./rag/
COPY security/ ./security/
COPY computation/ ./computation/
COPY worker/src/ ./worker/src/

CMD ["python", "-m", "arq", "worker.src.main.WorkerSettings"]

RUN useradd -m -u 1001 appuser && chown -R appuser /app
USER appuser
```

### `apps/web/Dockerfile`

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
RUN npm install -g pnpm
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ .
RUN pnpm build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY apps/web/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

---

## 6. Environment Variables

### `.env` (copy from `.env.example`, never commit)

```bash
# ============================================================
# AIBAA — Environment Variables
# ============================================================

# Application
APP_ENV=local                           # local | staging | production
LOG_LEVEL=INFO

# ── LLM Backend ──────────────────────────────────────────────
LLM_BACKEND=anthropic                   # anthropic | openai | colab
ANTHROPIC_API_KEY=sk-ant-...            # Required if LLM_BACKEND=anthropic
OPENAI_API_KEY=sk-...                   # Required if LLM_BACKEND=openai
LLM_MODEL=claude-opus-4-6               # Model name for the selected provider
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.2
# LLM_ENDPOINT_URL=                     # Only needed if LLM_BACKEND=colab

# ── Auth ─────────────────────────────────────────────────────
JWT_SECRET_KEY=                         # Generate: openssl rand -hex 32
JWT_ALGORITHM=HS256
JWT_EXPIRY_HOURS=8

# ── Database ─────────────────────────────────────────────────
# Overridden by docker-compose.yml for local dev
DATABASE_URL=sqlite+aiosqlite:///./aibaa.db

# ── Redis ────────────────────────────────────────────────────
REDIS_URL=redis://localhost:6379

# ── ChromaDB ─────────────────────────────────────────────────
CHROMA_HOST=localhost
CHROMA_PORT=8001

# ── File Storage ─────────────────────────────────────────────
UPLOAD_DIR=./uploads
OUTPUT_DIR=./outputs
MAX_UPLOAD_SIZE_MB=50
DATA_RETENTION_DAYS=2555                # 7 years regulatory minimum

# ── Security ─────────────────────────────────────────────────
CORS_ORIGINS=http://localhost:3000      # Comma-separated; never * in production
RATE_LIMIT_REQUESTS_PER_MINUTE=60
MNPI_CONSENT_REQUIRED=true

# ── Compliance ───────────────────────────────────────────────
HALLUCINATION_GUARD_ENABLED=true

# ── Observability ────────────────────────────────────────────
SENTRY_DSN=                             # Leave blank to disable

# ── Webhooks ─────────────────────────────────────────────────
WEBHOOK_MAX_RETRIES=5
WEBHOOK_RETRY_DELAYS_SECONDS=60,300,1800,7200,86400
```

### `.env.example` (committed to repo — safe template)

```bash
LLM_BACKEND=anthropic
ANTHROPIC_API_KEY=                      # Your Anthropic API key
JWT_SECRET_KEY=                         # openssl rand -hex 32
DATABASE_URL=sqlite+aiosqlite:///./aibaa.db
REDIS_URL=redis://localhost:6379
CHROMA_HOST=localhost
CHROMA_PORT=8001
UPLOAD_DIR=./uploads
OUTPUT_DIR=./outputs
CORS_ORIGINS=http://localhost:3000
SENTRY_DSN=
```

**Rules:**
- `.env` is in `.gitignore`. Never commit it.
- Production secrets are injected via the deployment platform (Railway env vars, AWS Parameter Store, etc.) — never via `.env` files on servers.
- `git secrets --scan` runs in pre-commit hook to catch accidental secret commits.

---

## 7. Makefile Commands

```makefile
.PHONY: help up down build test lint migrate clean secrets-check

help:
	@echo "AIBAA Development Commands"
	@echo "  make up          — Start all services (docker compose up)"
	@echo "  make down        — Stop all services"
	@echo "  make build       — Rebuild all Docker images"
	@echo "  make test        — Run all tests (inside containers)"
	@echo "  make lint        — Run all linters"
	@echo "  make migrate     — Run Alembic migrations"
	@echo "  make clean       — Remove containers, volumes, and temp files"
	@echo "  make secrets-check — Scan for accidentally committed secrets"

up:
	docker compose up --build -d
	@echo "Services running:"
	@echo "  API:    http://localhost:8000"
	@echo "  Web:    http://localhost:3000"
	@echo "  ChromaDB: http://localhost:8001"

down:
	docker compose down

build:
	docker compose build --no-cache

test:
	docker compose exec api pytest tests/ -v --cov=src --cov-report=term-missing
	docker compose exec web pnpm test -- --run

lint:
	docker compose exec api ruff check . && ruff format --check .
	docker compose exec web pnpm lint

migrate:
	docker compose exec api alembic upgrade head

clean:
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true

secrets-check:
	git secrets --scan
```

---

## 8. Pre-Commit Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/charliermarsh/ruff-pre-commit
    rev: v0.1.8
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-eslint
    rev: v8.55.0
    hooks:
      - id: eslint
        files: \.[jt]sx?$

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-json
      - id: check-yaml
      - id: no-commit-to-branch
        args: [--branch, main]

  - repo: https://github.com/awslabs/git-secrets
    rev: 1.3.0
    hooks:
      - id: git-secrets           # Blocks commits containing AWS keys, private keys, etc.
```

---

## 9. CI/CD Pipeline (GitHub Actions)

```yaml
# .github/workflows/test.yml
name: CI

on:
  push:
    branches: [main, develop, 'feat/*']
  pull_request:
    branches: [main]

jobs:
  test-backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: aibaa_test
          POSTGRES_USER: aibaa
          POSTGRES_PASSWORD: secret
        options: >-
          --health-cmd pg_isready
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with: { python-version: '3.11' }
      - name: Install dependencies
        run: pip install -r apps/api/requirements.txt -r apps/api/requirements-dev.txt
      - name: Run migrations
        run: cd apps/api && alembic upgrade head
        env:
          DATABASE_URL: postgresql+asyncpg://aibaa:secret@localhost/aibaa_test
      - name: Lint
        run: ruff check .
      - name: Test
        run: pytest tests/unit tests/integration -v --cov=src --cov-fail-under=80
        env:
          DATABASE_URL: postgresql+asyncpg://aibaa:secret@localhost/aibaa_test
          REDIS_URL: redis://localhost:6379
          JWT_SECRET_KEY: test_secret_key_for_ci_only
          LLM_BACKEND: mock                # Use mock LLM client in CI — no real API calls
          ANTHROPIC_API_KEY: ""

  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: npm install -g pnpm
      - run: cd apps/web && pnpm install
      - run: cd apps/web && pnpm lint
      - run: cd apps/web && pnpm test -- --run

  secrets-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: trufflesecurity/trufflehog@main
        with:
          path: ./
          base: ${{ github.event.repository.default_branch }}
          head: HEAD
```

---

## 10. Data Retention & Cleanup

```python
# apps/api/src/utils/cleanup.py
import os, time
from pathlib import Path
from sqlalchemy import text

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "./outputs"))
RETENTION_DAYS = int(os.getenv("DATA_RETENTION_DAYS", "2555"))  # 7 years default

async def cleanup_expired_documents(db):
    """
    Hard-deletes document files that have exceeded the retention period.
    Leaves a tombstone record in the database (filename + deletion timestamp).
    Never deletes MNPI documents without explicit legal hold check.
    Never deletes audit log entries.
    """
    cutoff = time.time() - (RETENTION_DAYS * 86400)
    
    expired = await db.execute(text("""
        SELECT id, storage_path, data_classification
        FROM documents
        WHERE uploaded_at < :cutoff
          AND parse_status != 'deleted'
          AND data_classification != 'mnpi'   -- MNPI requires separate legal review
    """), {"cutoff": cutoff})
    
    deleted_count = 0
    for row in expired:
        path = Path(row.storage_path)
        if path.exists():
            # Secure delete: overwrite with zeros before unlinking
            size = path.stat().st_size
            with open(path, "wb") as f:
                f.write(b'\x00' * size)
            path.unlink()
        
        # Mark as deleted in DB (tombstone — never hard-delete the row)
        await db.execute(text("""
            UPDATE documents SET parse_status='deleted', parsed_text=NULL
            WHERE id = :id
        """), {"id": row.id})
        deleted_count += 1
    
    return deleted_count
```

This runs as a nightly ARQ scheduled task, not a fixed 24-hour timer.

---

## 11. Logging Configuration

```python
# apps/api/src/utils/logging_config.py
import structlog, logging, sys, os

def setup_logging():
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()    # Machine-parseable JSON in production
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
    )

# Usage throughout the codebase:
import structlog
logger = structlog.get_logger()

# In every agent run:
log = logger.bind(run_id=run_id, deal_id=deal_id, agent=agent_type, org_id=org_id)
log.info("agent_run_started")
log.info("rag_retrieval_complete", chunk_count=8, query_tokens=24)
log.info("llm_call_complete", tokens_used=1240, latency_ms=3200)
log.info("agent_run_complete", confidence=0.87, output_type="xlsx")
log.error("agent_run_failed", error=str(e), error_type=type(e).__name__)

# Never log: LLM prompts, document content, financial figures, user PII
# (These may be MNPI or sensitive — Sentry's before_send scrubs them too)
```

---

*End of Document — 11-environment-and-devops.md*
