# 07 — Monorepo Structure
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Overview

AIBAA uses a **monorepo** structure. All packages (frontend, backend, agents, tools, shared utilities) live in a single repository.

**Repository Name:** `aibaa`
**Package Manager:** `pnpm` (frontend) + `pip` / `uv` (Python)
**Language:** TypeScript (frontend) + Python 3.11 (backend/agents)
**Containerisation:** Docker + docker-compose from day one

---

## 2. Full Directory Tree

```
aibaa/
│
├── README.md
├── .gitignore
├── .env.example                          # Template — never commit real values
├── docker-compose.yml                    # Full local stack: api + worker + web + db + redis + chroma
├── docker-compose.override.yml          # Developer overrides (hot reload mounts)
├── Makefile                              # Unified dev commands
│
├── apps/
│   ├── web/                              # React SPA (Frontend)
│   └── api/                              # FastAPI Orchestration Backend
│
├── worker/                               # ARQ Worker process (NEW — separate from API)
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── main.py                       # WorkerSettings + startup/shutdown hooks
│       └── tasks/
│           └── agent_tasks.py            # run_agent_task(), run_rag_indexing()
│
├── packages/
│   ├── shared-types/                     # Shared TypeScript type definitions
│   └── ui-components/                    # Reusable React UI components (design system)
│
├── agents/                               # All AI agent implementations
│   ├── base_agent.py
│   ├── orchestrator/
│   ├── modeling/
│   ├── pitchbook/
│   ├── due_diligence/
│   ├── research/
│   ├── doc_drafter/
│   └── coordination/
│
├── tools/                                # Agent tools (callable functions)
│   ├── file_parser/
│   ├── excel_writer/
│   ├── pdf_generator/
│   ├── pptx_generator/                  # NEW — PPTX output support
│   ├── doc_generator/
│   ├── python_executor/
│   └── web_search/
│
├── rag/                                  # RAG pipeline (NEW)
│   ├── chunker.py
│   ├── embedder.py
│   ├── indexer.py
│   └── retriever.py
│
├── security/                             # Security utilities (NEW)
│   ├── prompt_guard.py                   # Prompt injection detection + sanitisation
│   ├── mnpi_checker.py                   # Pre-flight MNPI consent enforcement
│   └── audit_logger.py                   # Integrity-chained audit log writer
│
├── computation/                          # Deterministic financial calculation engine
│   ├── dcf.py
│   ├── lbo.py
│   ├── cca.py
│   ├── hallucination_guard.py
│   └── verification.py
│
├── templates/                            # Output document templates
│   ├── excel/
│   ├── pdf/
│   ├── pptx/                             # NEW — PPTX templates
│   └── docx/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── llm_eval/
│   ├── e2e/
│   └── fixtures/
│
└── docs/
    ├── 02-user-stories-and-acceptance-criteria.md
    ├── 03-information-architecture.md
    ├── 04-system-architecture.md
    ├── 05-database-schema.md
    ├── 06-api-contracts.md
    ├── 07-monorepo-structure.md
    ├── 08-computation-engine-spec.md
    ├── 09-engineering-scope-definition.md
    ├── 10-development-phases.md
    ├── 11-environment-and-devops.md
    └── 12-testing-strategy.md
```

---

## 3. Detailed Package Breakdown

### `apps/web/` — React SPA

```
apps/web/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── Dockerfile
├── index.html
│
└── src/
    ├── main.tsx
    ├── App.tsx
    │
    ├── pages/
    │   ├── auth/
    │   │   ├── Login.tsx
    │   │   └── MFAVerify.tsx
    │   ├── Dashboard.tsx
    │   ├── NewDeal.tsx
    │   ├── DealWorkspace.tsx
    │   │   ├── OverviewTab.tsx
    │   │   ├── DocumentsTab.tsx
    │   │   ├── AgentsTab.tsx
    │   │   ├── OutputsTab.tsx
    │   │   └── SettingsTab.tsx
    │   ├── admin/
    │   │   ├── AuditTrail.tsx
    │   │   ├── UserManagement.tsx
    │   │   └── RetentionPolicy.tsx
    │   ├── GlobalSettings.tsx
    │   └── Help.tsx
    │
    ├── components/
    │   ├── layout/
    │   │   ├── Sidebar.tsx
    │   │   ├── TopBar.tsx
    │   │   └── Breadcrumb.tsx
    │   ├── auth/
    │   │   ├── AuthGuard.tsx             # Redirects unauthenticated users
    │   │   └── AdminGuard.tsx            # Restricts admin-only routes
    │   ├── deals/
    │   │   ├── DealCard.tsx
    │   │   ├── DealForm.tsx
    │   │   └── DealStatusBadge.tsx
    │   ├── agents/
    │   │   ├── AgentCard.tsx
    │   │   ├── AgentInputPanel.tsx
    │   │   ├── ReasoningPanel.tsx
    │   │   ├── ProgressStream.tsx
    │   │   └── MNPIConsentBanner.tsx     # NEW — shown when MNPI docs in scope
    │   ├── documents/
    │   │   ├── DocumentUploadZone.tsx
    │   │   ├── DocumentList.tsx
    │   │   ├── DocumentPreview.tsx
    │   │   ├── MNPIFlagToggle.tsx        # NEW
    │   │   └── RAGIndexStatus.tsx        # NEW — shows indexing progress
    │   ├── outputs/
    │   │   ├── OutputCard.tsx
    │   │   ├── OutputPreview.tsx
    │   │   ├── ReviewActions.tsx
    │   │   └── ConfidenceBadge.tsx       # NEW — colour-coded confidence score
    │   ├── charts/                       # NEW — financial semantic colour charts
    │   │   ├── SensitivityTable.tsx      # Heatmap: green → red
    │   │   ├── WaterfallChart.tsx
    │   │   └── RiskBadge.tsx             # High/Medium/Low with semantic colours
    │   ├── tasks/
    │   │   ├── TaskBoard.tsx
    │   │   ├── TaskCard.tsx
    │   │   └── TaskForm.tsx
    │   └── common/
    │       ├── Button.tsx
    │       ├── Modal.tsx
    │       ├── Toast.tsx
    │       ├── Badge.tsx
    │       ├── Spinner.tsx
    │       ├── EmptyState.tsx
    │       └── ErrorBoundary.tsx
    │
    ├── hooks/
    │   ├── useAuth.ts                    # JWT management + refresh
    │   ├── useDeals.ts
    │   ├── useAgentRun.ts
    │   ├── useSSEStream.ts               # Handles reconnect + Last-Event-ID
    │   ├── useDocuments.ts
    │   └── useOutputs.ts
    │
    ├── store/
    │   ├── authStore.ts                  # NEW — user/token state
    │   ├── dealStore.ts
    │   ├── agentStore.ts
    │   └── settingsStore.ts
    │
    ├── api/
    │   ├── client.ts                     # Axios + JWT interceptor + 401 redirect
    │   ├── auth.ts
    │   ├── deals.ts
    │   ├── documents.ts
    │   ├── agents.ts
    │   ├── outputs.ts
    │   ├── webhooks.ts                   # NEW
    │   ├── admin.ts                      # NEW
    │   └── settings.ts
    │
    ├── types/
    │   └── index.ts
    │
    └── styles/
        ├── globals.css
        └── design-tokens.css             # B&W chrome + financial semantic palette
```

---

### `apps/api/` — FastAPI Orchestration Backend

```
apps/api/
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── Dockerfile
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_schema.py
│
└── src/
    ├── main.py                           # FastAPI app, middleware registration
    ├── config.py                         # Pydantic Settings (reads from env)
    │
    ├── auth/
    │   ├── dependencies.py               # get_current_user, require_admin
    │   ├── jwt.py                        # create_access_token, verify_token
    │   └── router.py                     # /auth/* endpoints
    │
    ├── middleware/
    │   ├── idempotency.py                # Redis-backed request deduplication
    │   ├── rate_limiting.py              # slowapi token bucket
    │   └── security_headers.py          # HSTS, CSP, X-Frame-Options
    │
    ├── routers/
    │   ├── deals.py
    │   ├── documents.py
    │   ├── agents.py
    │   ├── outputs.py
    │   ├── tasks.py
    │   ├── webhooks.py                   # NEW
    │   ├── admin.py                      # NEW
    │   └── settings.py
    │
    ├── models/
    │   ├── deal.py
    │   ├── document.py
    │   ├── agent_run.py
    │   ├── output.py
    │   ├── task.py
    │   ├── audit_log.py
    │   ├── webhook.py                    # NEW
    │   └── settings.py
    │
    ├── services/
    │   ├── deal_service.py
    │   ├── document_service.py
    │   ├── agent_service.py              # Enqueues ARQ jobs
    │   ├── output_service.py
    │   ├── task_service.py
    │   ├── webhook_service.py            # NEW — HMAC delivery
    │   └── audit_service.py             # NEW — append-only logger
    │
    ├── database.py                       # SQLAlchemy engine + get_db()
    ├── redis.py                          # Redis client + get_redis()
    │
    ├── llm/
    │   ├── base_client.py                # BaseLLMClient ABC
    │   ├── anthropic_client.py           # AnthropicClient (default)
    │   ├── openai_client.py              # OpenAIClient (optional)
    │   ├── colab_client.py               # ColabClient (fine-tune testing only)
    │   ├── factory.py                    # get_llm_client() — reads LLM_BACKEND env
    │   └── prompt_builder.py             # System prompts per agent type
    │
    └── utils/
        ├── file_utils.py
        ├── error_handlers.py
        └── logging_config.py             # structlog JSON formatter
```

---

### `worker/` — ARQ Task Worker *(NEW — separate process)*

```
worker/
├── Dockerfile
├── requirements.txt
│
└── src/
    ├── main.py                           # WorkerSettings, startup, shutdown
    └── tasks/
        ├── agent_tasks.py                # run_agent_task()
        └── indexing_tasks.py             # run_rag_indexing()
```

The worker runs in its own Docker container. It shares the same codebase as the API (mounted as a volume) but runs the ARQ worker entrypoint instead of uvicorn. This means agent tasks survive API server restarts — they are persisted in Redis and picked up by any available worker.

---

### `rag/` — RAG Pipeline *(NEW)*

```
rag/
├── __init__.py
├── chunker.py                            # Semantic-aware chunking (512 tokens, 64 overlap)
├── embedder.py                           # sentence-transformers: BAAI/bge-base-en-v1.5
├── indexer.py                            # ChromaDB collection management
└── retriever.py                          # retrieve_context(deal_id, query, top_k)
```

---

### `security/` — Security Utilities *(NEW)*

```
security/
├── __init__.py
├── prompt_guard.py                       # Injection detection + content delimiting
├── mnpi_checker.py                       # Pre-flight MNPI consent enforcement
└── audit_logger.py                       # log_event() with SHA-256 integrity chaining
```

---

### `computation/` — Financial Calculation Engine

```
computation/
├── __init__.py
├── dcf.py                                # DCFEngine — mid-year discounting, Hamada beta, _frange
├── lbo.py                                # LBOEngine — numpy_financial IRR, full cash flow series
├── cca.py                                # CCAEngine — multiples, percentile benchmarks
├── hallucination_guard.py                # Typed field registry: DOCUMENT_EXTRACTED vs COMPUTED
└── verification.py                       # Output verification checklist (TV%, DSCR, IRR sanity)
```

---

## 4. Docker Compose Architecture

```yaml
# docker-compose.yml (see 11-environment-and-devops.md for full spec)
services:
  api:       FastAPI — port 8000
  worker:    ARQ worker — consumes jobs from Redis
  web:       React Vite dev server — port 3000
  db:        PostgreSQL 16 — port 5432
  redis:     Redis 7 — port 6379
  chroma:    ChromaDB — port 8001
```

`docker compose up` gives any developer the entire stack. No manual Python environment setup. No "works on my machine."

---

## 5. Package Dependencies

### Frontend (`apps/web/package.json`)
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "zustand": "^4.4.0",
    "axios": "^1.6.0",
    "react-dropzone": "^14.2.0",
    "react-pdf": "^7.5.0",
    "@tanstack/react-query": "^5.0.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "typescript": "^5.2.0",
    "tailwindcss": "^3.3.0",
    "@types/react": "^18.2.0",
    "vitest": "^1.0.0",
    "@testing-library/react": "^14.0.0",
    "@playwright/test": "^1.40.0"
  }
}
```

### Backend (`apps/api/requirements.txt`)
```
fastapi==0.104.0
uvicorn[standard]==0.24.0
pydantic==2.5.0
pydantic-settings==2.1.0
sqlalchemy[asyncio]==2.0.23
aiosqlite==0.19.0              # SQLite async driver (dev)
asyncpg==0.29.0                # PostgreSQL async driver (prod)
alembic==1.12.0
httpx==0.25.0
python-multipart==0.0.6
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
slowapi==0.1.9
arq==0.25.0
redis[asyncio]==5.0.0
anthropic==0.16.0
openai==1.6.0
PyMuPDF==1.23.0
python-docx==1.1.0
python-pptx==0.6.23
openpyxl==3.1.2
reportlab==4.0.7
pandas==2.1.0
numpy==1.26.0
numpy-financial==1.0.0
sentence-transformers==2.2.2
chromadb==0.4.18
structlog==23.2.0
sentry-sdk[fastapi]==1.38.0
aiofiles==23.2.1
pyotp==2.9.0
```

### Worker (`worker/requirements.txt`)
```
arq==0.25.0
redis[asyncio]==5.0.0
anthropic==0.16.0
openai==1.6.0
numpy-financial==1.0.0
sentence-transformers==2.2.2
chromadb==0.4.18
# (shares computation/, rag/, agents/, tools/, security/ from monorepo root)
```

---

## 6. Naming Conventions

| Artifact | Convention | Example |
|---|---|---|
| Python files | `snake_case.py` | `agent_service.py` |
| Python classes | `PascalCase` | `FinancialModelingAgent` |
| Python functions | `snake_case` | `build_dcf_model()` |
| TypeScript files | `PascalCase.tsx` / `camelCase.ts` | `AgentCard.tsx`, `useAgentRun.ts` |
| CSS class names | `kebab-case` | `agent-card__reasoning-panel` |
| API routes | `kebab-case` | `/agent-runs/:id` |
| Environment variables | `SCREAMING_SNAKE_CASE` | `LLM_BACKEND` |
| Git branches | `type/description` | `feat/rag-pipeline` |
| Commit messages | Conventional Commits | `feat: add RAG retrieval to modeling agent` |
| Docker images | `aibaa-{service}` | `aibaa-api`, `aibaa-worker`, `aibaa-web` |

---

*End of Document — 07-monorepo-structure.md*
