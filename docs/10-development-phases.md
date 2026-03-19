# 10 — Development Phases
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Overview

Development is organised into **6 phases** following a strict dependency order. Unlike v1, security and data infrastructure are built first — not added later. No agent work begins until auth, the database, and the task queue are proven working.

```
Phase 0: Foundation, Auth & Infrastructure     (Days 1–7)
Phase 1: Core Backend + Data Layer             (Days 8–17)
Phase 2: RAG Pipeline + Agent Framework        (Days 18–27)
Phase 3: Computation Engine + First Agent      (Days 28–35)
Phase 4: Full Agent Suite + Output Generation  (Days 36–46)
Phase 5: Frontend + UX                        (Days 47–54)
Phase 6: Integration, Security Hardening & QA (Days 55–60)
```

**Rule:** Each phase has explicit exit criteria. Work on the next phase cannot begin until all criteria are met. This prevents accumulating debt that becomes impossible to retrofit.

---

## 2. Phase 0 — Foundation, Auth & Infrastructure
**Duration:** Days 1–7
**Goal:** All developers can run the full stack via `docker compose up`. Auth works. Database is persistent. Redis and ChromaDB are running.

### 2.1 Tasks

| Task | Day | Deliverable |
|---|---|---|
| Initialise monorepo with full directory structure | 1 | `git init`, all directories, `.gitignore`, `.env.example` |
| `docker-compose.yml` with all services (api, worker, web, db, redis, chroma) | 1 | `docker compose up` starts all services |
| FastAPI skeleton: `GET /health` returns `{"status": "ok"}` | 1 | Health check endpoint |
| Alembic configured; initial migration with all tables | 2 | `alembic upgrade head` runs clean on both SQLite and Postgres |
| JWT auth: `POST /auth/login`, `POST /auth/logout`, `get_current_user` dependency | 2–3 | Returns valid JWT; `401` without token |
| Org_id scoping: all deal/document service methods include org_id param | 3 | Cross-tenant query impossible |
| React SPA shell: Vite + Tailwind + router + `AuthGuard` component | 4 | Login page redirects unauthenticated users |
| Login page + JWT storage in httpOnly cookie | 4–5 | Successful login redirects to dashboard |
| Redis client + ARQ worker skeleton (startup/shutdown hooks) | 5 | Worker starts; `GET /health` on worker returns ok |
| Rate limiting middleware (slowapi, 60 req/min) | 6 | `429` returned on abuse |
| Idempotency middleware (Redis, 24h TTL) | 6 | Duplicate POSTs return original response |
| Security headers middleware (HSTS, CSP, X-Frame-Options) | 7 | Headers present on all responses |
| Sentry SDK initialised (backend) + structlog JSON formatter | 7 | Errors appear in Sentry; logs are structured JSON |
| `make lint && make test` runs clean in CI | 7 | GitHub Actions green |

### 2.2 Exit Criteria
- [ ] `docker compose up` starts all 6 services with no errors
- [ ] `POST /auth/login` with valid credentials returns a JWT
- [ ] Any request to `/deals` without JWT returns `401`
- [ ] Two identical `POST /deals` requests with the same `Idempotency-Key` create only one deal
- [ ] `alembic upgrade head` runs clean on both SQLite and PostgreSQL
- [ ] All tests pass: `make test`

---

## 3. Phase 1 — Core Backend + Data Layer
**Duration:** Days 8–17
**Goal:** All API endpoints are implemented and tested. File upload, parsing, and the audit trail are working.

### 3.1 Milestones

**Milestone 1.1 — Deals + Documents API (Days 8–11)**
- `POST/GET/PATCH/DELETE /deals` (org-scoped, audit-logged)
- `POST /deals/:id/documents` (multipart upload, MNPI field, category)
- File parsing: PDF (PyMuPDF), XLSX (openpyxl), DOCX (python-docx), CSV (pandas)
- `GET /deals/:id/documents`, `PATCH /deals/:id/documents/:id` (update classification)
- Audit logger: `log_event()` with SHA-256 integrity chaining
- Unit tests for all parsers and audit logger

**Milestone 1.2 — Agent Run API (Days 12–14)**
- `POST /deals/:id/agents/run` (validates MNPI consent, enqueues ARQ job, returns 202)
- `GET /agents/runs/:id/stream` (SSE with `Last-Event-ID` replay)
- `GET /agents/runs/:id` (run details with reasoning steps)
- ARQ worker: `run_agent_task()` with mock agent (logs steps, emits SSE events, marks complete)
- Integration test: trigger run → stream 5 events → complete → output record created

**Milestone 1.3 — Outputs, Tasks, Webhooks, Admin (Days 15–17)**
- `GET/PATCH /outputs/*` and `POST /outputs/:id/revise`
- Tasks CRUD
- `POST/GET/DELETE /webhooks` + HMAC delivery service
- `GET /admin/audit` + `GET /admin/audit/export` (with chain validation)
- Settings API

### 3.2 Exit Criteria
- [ ] Full httpx test suite passes for all 22 endpoints
- [ ] File upload of sample PDF, XLSX, DOCX → text extracted and stored
- [ ] Audit log has an integrity-chained entry for every mutating operation
- [ ] MNPI flag on a document causes `POST /agents/run` to return `403 MNPI_CONSENT_REQUIRED`
- [ ] Resending with `mnpi_consent: true` succeeds and logs consent to audit trail
- [ ] Webhook delivery sends HMAC-signed payload to a test ngrok endpoint

---

## 4. Phase 2 — RAG Pipeline + Agent Framework
**Duration:** Days 18–27
**Goal:** Document indexing works. The base agent framework is working with RAG retrieval. No full-document injection anywhere.

### 4.1 Milestones

**Milestone 2.1 — RAG Pipeline (Days 18–21)**
- `chunker.py`: semantic-aware chunking (512 tokens, 64 overlap, paragraph boundaries)
- `embedder.py`: BAAI/bge-base-en-v1.5 sentence-transformers
- `indexer.py`: ChromaDB per-deal collections; `index_document(doc_id, deal_id, text)`
- `retriever.py`: `retrieve_context(deal_id, query, top_k)` returning ranked chunks
- ARQ worker task: `run_rag_indexing()` — triggered after parse completes
- `documents.rag_status` updated: `pending → indexing → indexed / failed`
- Unit tests: verify chunk count, verify retrieval returns relevant content

**Milestone 2.2 — Base Agent Framework (Days 22–24)**
- `base_agent.py`: abstract class with `run()`, `think()`, `act()`, `observe()`
- `orchestrator/agent.py`: routing logic by task_name
- `prompt_builder.py`: one system prompt per agent type
- `security/prompt_guard.py`: `sanitize_user_input()` called on all user-provided text
- `security/mnpi_checker.py`: pre-flight check used by agent service
- ReAct loop: reasoning steps logged with step type (thought / rag_retrieval / action / observation)

**Milestone 2.3 — Integration Test (Days 25–27)**
- Upload sample financial PDF → RAG indexing completes → status = 'indexed'
- Trigger a stub agent run → RAG retrieval returns relevant chunks → chunks logged to `agent_runs.rag_chunks_used`
- Prompt injection test: upload document with injection string → sanitiser detects and neutralises → logs `prompt_injection_attempt` audit event
- MNPI test: mark document as MNPI → agent run blocked → consent given → agent runs → consent in audit log

### 4.2 Exit Criteria
- [ ] `GET /deals/:id/documents` shows `rag_status: "indexed"` after upload
- [ ] `retrieve_context()` returns relevant chunks for "revenue EBITDA income statement" query on a financial document
- [ ] Agent run reasoning steps include at least one `rag_retrieval` step
- [ ] Prompt injection string in uploaded document is sanitised and logged

---

## 5. Phase 3 — Computation Engine + Financial Modeling Agent
**Duration:** Days 28–35
**Goal:** DCF, LBO, and CCA engines are correct and produce verified Excel outputs.

### 5.1 Milestones

**Milestone 3.1 — DCF Engine v2 (Days 28–30)**
- `_frange()` defined and tested
- WACC with Hamada equation (unlever + re-lever beta)
- Mid-year discounting (`year - 0.5` exponent)
- Terminal value sanity check (TV% range)
- Sensitivity table using `_frange` (9×5 grid)
- `dcf_template.xlsx` updated with mid-year convention
- Unit tests: known-answer verification ±0.1%; sensitivity table is 9×5

**Milestone 3.2 — LBO + CCA Engines (Days 31–32)**
- `numpy_financial.irr()` on full cash flow series
- DSCR check per projection year
- Sources & Uses balance validation
- CCA with 25th/75th percentile + warning when < 6 comps

**Milestone 3.3 — Hallucination Guard v2 (Day 33)**
- `FIELD_REGISTRY` populated for all DCF/LBO/CCA fields
- `verify()` only flags DOCUMENT_EXTRACTED fields
- Unit tests: fabricated revenue flagged; WACC not flagged; EBITDA margin not flagged

**Milestone 3.4 — Financial Modeling Agent End-to-End (Days 34–35)**
- Agent connects to DCF Engine + RAG + Hallucination Guard + Excel Writer
- End-to-end test: upload income statement → run DCF agent → download XLSX → verify numbers match engine output exactly
- Disclaimer embedded on last sheet

### 5.2 Exit Criteria
- [ ] DCF unit test passes on known-answer case within ±0.1%
- [ ] IRR unit test: `irr([-100, 0, 0, 0, 0, 200])` ≈ 14.87% within ±0.01%
- [ ] Sensitivity table is always 9×5 (cells with TGR ≥ WACC marked None, not crash)
- [ ] `HallucinationGuard.verify()` does not flag `wacc`, `enterprise_value`, or `irr`
- [ ] End-to-end DCF produces downloadable XLSX with mid-year discounting confirmed

---

## 6. Phase 4 — Full Agent Suite + Output Generation
**Duration:** Days 36–46
**Goal:** All 6 agents produce downloadable outputs. PPTX export works. Semantic colour palette applied throughout.

### 6.1 Build Order

```
Day 36:    LBO Excel output (Financial Modeling Agent, task 2)
Day 37:    CCA Excel output (Financial Modeling Agent, task 3)
Day 38–39: PDF Generator + Pitchbook template (semantic colour charts)
Day 40–41: PPTX Generator + Pitchbook agent (PDF and PPTX output)
Day 42:    Due Diligence agent + semantic risk ratings (High/Medium/Low)
Day 43:    Market Research agent + buyer universe builder
Day 44:    Doc Drafter agent + Word Generator + CIM template
Day 45:    Coordination agent + meeting notes processor
Day 46:    Disclaimer embedding in all output types
```

### 6.2 Per-Agent Minimum Viable Output

| Agent | Minimum Output |
|---|---|
| Financial Modeling (DCF) | XLSX: Revenue, EBITDA, UFCF, DCF (mid-year), Sensitivity (9×5 heatmap), Disclaimer |
| Financial Modeling (LBO) | XLSX: Sources & Uses (balanced), Debt Schedule, Returns (numpy IRR), Disclaimer |
| Financial Modeling (CCA) | XLSX: Comps table, Percentile benchmarks, Implied EV range, Disclaimer |
| Pitchbook | PDF + PPTX: 12 slides, semantic colour financial charts, disclaimer page |
| Due Diligence | PDF: Risk report with High/Medium/Low semantic colour ratings, disclaimer page |
| Market Research | PDF: Industry overview, market size, key players, buyer universe, disclaimer page |
| Doc Drafter | DOCX: CIM draft with 4 sections, all figures traceable to source chunks |
| Coordination | MD: Meeting summary, decisions, action items, open questions |

### 6.3 Exit Criteria for Phase 4
- [ ] All 6 agents produce outputs for their core task
- [ ] Pitchbook downloads as both PDF and editable PPTX
- [ ] Financial charts in PDF/PPTX use semantic colour palette (green/red/blue for data)
- [ ] DD report risk badges use semantic colours (High=red, Medium=amber, Low=green)
- [ ] Every generated file has a disclaimer on the last page/sheet
- [ ] Hallucination Guard runs on all agents that output financial figures

---

## 7. Phase 5 — Frontend + UX
**Duration:** Days 47–54
**Goal:** Full working UI. All workflows completable without touching the API directly.

### 7.1 Build Order

```
Day 47: Auth pages (login, MFA) + AuthGuard
Day 48: Dashboard + New Deal form
Day 49: Deal workspace shell (tabs, routing)
Day 50: Documents tab (upload, MNPI toggle, RAG index status)
Day 51: Agents tab (cards, input panels, MNPI consent banner, Run button)
Day 52: SSE integration (reasoning panel, RAG step display, reconnect)
Day 53: Outputs tab (PDF preview, PPTX preview, confidence badge, approve/revise)
Day 54: Task board, Admin audit trail, Settings, Error/Empty states
```

### 7.2 Design Compliance Checklist
- [ ] All UI chrome: background `#FFFFFF`, text `#0A0A0A`, muted `#6B6B6B`, border `#E5E5E5`
- [ ] Financial data (charts, percentages, returns): uses semantic palette (`--color-fin-positive`, etc.)
- [ ] Risk badges: High=`#C0392B`, Medium=`#D68910`, Low=`#1A7A4A`
- [ ] Sensitivity table: green→red heatmap across WACC/TGR grid
- [ ] Confidence badge: green ≥ 0.8, yellow 0.6–0.79, red < 0.6
- [ ] No financial data displayed in black/white when colour communicates meaning

---

## 8. Phase 6 — Integration, Security Hardening & QA
**Duration:** Days 55–60
**Goal:** All P0 user stories pass. Security review complete. System ready for professional use.

### 8.1 Schedule

| Day | Focus |
|---|---|
| 55 | End-to-end: full DCF workflow (login → upload → index → run → download) |
| 56 | End-to-end: pitchbook (PDF + PPTX) + DD review workflow |
| 57 | Security: prompt injection test suite, MNPI bypass attempts, auth boundary tests |
| 58 | Load test: all 6 agents back-to-back; measure latency; verify worker survives restart |
| 59 | Bug bash: all error states, edge cases, empty states, audit log chain validation |
| 60 | Final polish: copy, tooltips, README, deployment guide |

### 8.2 Launch Readiness Checklist
- [ ] All P0 user stories pass their acceptance criteria
- [ ] No critical bugs open
- [ ] `docker compose up && make test` passes on a clean clone
- [ ] Audit log chain is unbroken (export validates correctly)
- [ ] Prompt injection test suite: all 10 patterns detected and logged
- [ ] MNPI bypass attempt blocked at API level (consent required even with valid JWT)
- [ ] README contains 5-minute quick-start guide
- [ ] Sample deal with all 6 agent outputs generated end-to-end in < 45 minutes
- [ ] All generated outputs have disclaimers
- [ ] No hardcoded secrets anywhere in codebase (`git secrets --scan`)

---

## 9. Version Roadmap

| Version | Timeline | Key Additions |
|---|---|---|
| v1.0 (MVP) | Weeks 1–12 | Auth, persistent DB, RAG, all agents, ARQ queue, semantic UI, PPTX |
| v1.1 | +4 weeks | Fine-tuned model (Unsloth LoRA), improved output quality |
| v2.0 | +3 months | SSO (SAML/OIDC), S3 file storage, real market data (yFinance), Pinecone vector DB, column-level encryption |
| v2.1 | +1 month | Multi-user permissions, deal sharing, Slack/email notifications, virus scanning |
| v3.0 | +6 months | Bloomberg API, enterprise compliance features (SOC2, GDPR DPA), audit SIEM export |

---

*End of Document — 10-development-phases.md*
