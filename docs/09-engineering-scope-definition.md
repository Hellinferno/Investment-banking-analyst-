# 09 — Engineering Scope Definition
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Purpose

This document defines precisely **what will be built** vs. **what will not be built** in the MVP (v1.0). It is the primary reference for sprint planning.

**Key change from v1:** Authentication, persistent database, task queue, RAG pipeline, and audit logging are **not deferred to v2**. They are v1.0 requirements. Building financial software without these is not an MVP — it is a prototype that cannot be used professionally.

---

## 2. Engineering Boundaries

### 2.1 IN SCOPE — v1.0 MVP

#### Authentication & Security
| # | Feature | Reference |
|---|---|---|
| SEC-01 | JWT authentication (login, logout, token expiry) | US-000 |
| SEC-02 | Auth middleware on all protected routes | US-000 |
| SEC-03 | Org_id scoping on all database queries | US-000 |
| SEC-04 | Prompt injection detection + content delimiting | Fix 9 |
| SEC-05 | MNPI document flagging + consent enforcement | US-002, US-015 |
| SEC-06 | Rate limiting (slowapi, 60 req/min default) | Fix 9 |
| SEC-07 | Idempotency keys on all mutating endpoints | Fix 10 |
| SEC-08 | Security response headers (HSTS, CSP, X-Frame-Options) | Best practice |
| SEC-09 | JWT stored in httpOnly cookie (not localStorage) | Fix 2 |

#### Frontend (React SPA)
| # | Feature | Reference |
|---|---|---|
| FE-01 | Login page + MFA verification page | US-000 |
| FE-02 | AuthGuard component (redirects unauthenticated users) | US-000 |
| FE-03 | Dashboard with org-scoped deal list | US-001 |
| FE-04 | New Deal form + validation | US-001 |
| FE-05 | Deal workspace with 5 tabs | US-001 |
| FE-06 | File upload zone (drag-and-drop, MNPI flag toggle, RAG index status) | US-002 |
| FE-07 | Document list with parse status + index status badges | US-002 |
| FE-08 | Agent cards (6 agents) with MNPI consent banner | US-003–US-012 |
| FE-09 | Agent input panels (context-sensitive per agent) | US-003–US-012 |
| FE-10 | SSE reasoning panel with reconnect (Last-Event-ID) | US-015 |
| FE-11 | Progress indicator during agent runs | US-006 |
| FE-12 | Output file list with download, preview, confidence badge | US-003 |
| FE-13 | PDF in-browser preview | US-006 |
| FE-14 | PPTX thumbnail preview (new) | US-006 |
| FE-15 | Approve / Request Revision on outputs | US-003 |
| FE-16 | Task tracker board (Kanban) with overdue highlighting | US-013 |
| FE-17 | Activity log in deal overview | US-013 |
| FE-18 | Global Settings page | - |
| FE-19 | Admin: Audit Trail view (org admin only) | US-016 |
| FE-20 | B&W UI chrome + financial semantic colour palette | US-014 |
| FE-21 | Sensitivity table with green→red heatmap | US-003 |
| FE-22 | Risk badges with semantic colours (High/Medium/Low) | US-008 |
| FE-23 | Hallucination warning badge on outputs | US-015 |
| FE-24 | Error states (backend down, timeout, MNPI consent) | 03-IA sec. 9 |
| FE-25 | Empty states for all list views | 03-IA sec. 8 |
| FE-26 | Responsive layout (min 1280px) | US-014 |

#### Backend (FastAPI Orchestration)
| # | Feature | Reference |
|---|---|---|
| BE-01 | `POST /auth/login` + `POST /auth/mfa/verify` + `POST /auth/logout` | US-000 |
| BE-02 | JWT middleware (all protected routes) | US-000 |
| BE-03 | Idempotency middleware (Redis) | Fix 10 |
| BE-04 | Rate limiting middleware (slowapi) | Fix 9 |
| BE-05 | `POST/GET/PATCH/DELETE /deals` | US-001 |
| BE-06 | `POST/GET /deals/:id/documents` + MNPI patch | US-002 |
| BE-07 | File parsing: PDF, DOCX, XLSX, CSV | US-002 |
| BE-08 | RAG indexing background job (enqueue on upload) | Fix 5 |
| BE-09 | `POST /deals/:id/agents/run` (enqueues ARQ job, returns 202) | US-003–US-012 |
| BE-10 | MNPI pre-flight check on agent run | US-002, SEC-05 |
| BE-11 | `GET /agents/runs/:id/stream` (SSE with reconnect + replay) | US-015 |
| BE-12 | `GET /agents/runs/:id` | - |
| BE-13 | `GET /deals/:id/outputs` + `GET /outputs/:id/download` | US-003 |
| BE-14 | `PATCH /outputs/:id/review` + `POST /outputs/:id/revise` | US-003 |
| BE-15 | Tasks CRUD | US-013 |
| BE-16 | `POST/GET/DELETE /webhooks` | Fix 10 |
| BE-17 | Webhook HMAC delivery + retry | Fix 10 |
| BE-18 | `GET/PUT /settings/:key` | - |
| BE-19 | `GET /admin/audit` + `GET /admin/audit/export` | US-016 |
| BE-20 | Append-only audit logger (integrity-chained) | Fix 8 |
| BE-21 | Sentry error tracking + structlog JSON logging | Fix 12 |
| BE-22 | Alembic migrations (SQLite dev / PostgreSQL prod) | Fix 3 |

#### Worker (ARQ)
| # | Feature | Reference |
|---|---|---|
| WK-01 | ARQ worker process (separate from API) | Fix 4 |
| WK-02 | `run_agent_task()` — executes agents, publishes SSE events | Fix 4 |
| WK-03 | `run_rag_indexing()` — chunks, embeds, stores in ChromaDB | Fix 5 |
| WK-04 | Webhook dispatcher (fires on task completion) | Fix 10 |

#### RAG Pipeline
| # | Feature | Reference |
|---|---|---|
| RAG-01 | Semantic chunker (512 tokens, 64 overlap, paragraph-aware) | Fix 5 |
| RAG-02 | Embedder (BAAI/bge-base-en-v1.5) | Fix 5 |
| RAG-03 | ChromaDB indexer (per-deal collections) | Fix 5 |
| RAG-04 | Retriever (top-K cosine similarity) | Fix 5 |
| RAG-05 | RAG status tracking in documents table | Fix 5 |

#### Agents (Python)
| # | Agent | Tasks In Scope |
|---|---|---|
| AG-01 | Orchestrator | Route to correct sub-agent |
| AG-02 | Financial Modeling | DCF (mid-year, Hamada beta), LBO (numpy_financial IRR), CCA |
| AG-03 | Pitchbook | Full pitchbook — PDF and PPTX output |
| AG-04 | Due Diligence | Full DD review, risk summary, DD checklist — semantic colour risk ratings |
| AG-05 | Market Research | Industry overview brief, buyer universe |
| AG-06 | Doc Drafter | CIM draft (4 sections), executive summary, deal teaser |
| AG-07 | Coordination | Process meeting notes, extract action items, deal status report |

All agents use RAG retrieval — no full-document injection.

#### Computation Engine
| # | Module | Key Fixes in v2 |
|---|---|---|
| CE-01 | DCF Engine | Mid-year discounting, Hamada beta, `_frange` defined, TV% sanity check |
| CE-02 | LBO Engine | `numpy_financial.irr()` on full cash flow series, DSCR check |
| CE-03 | CCA Engine | 25th/75th percentile benchmarks, < 6 comp warning |
| CE-04 | Hallucination Guard | Typed field registry — DOCUMENT_EXTRACTED vs COMPUTED |
| CE-05 | Output Verification | Extended checklist including TV%, DSCR, IRR convergence |

#### Document Templates
| # | Template | Format | Notes |
|---|---|---|---|
| TP-01 | DCF model skeleton | XLSX | Mid-year convention, Hamada beta, sensitivity heatmap |
| TP-02 | LBO model skeleton | XLSX | Full cash flow series, numpy IRR |
| TP-03 | CCA model skeleton | XLSX | Percentile benchmarks, semantic colour highlighting |
| TP-04 | Pitchbook template | PDF + PPTX | Semantic colour charts, editable PPTX |
| TP-05 | DD risk report | PDF | Semantic traffic-light risk ratings |
| TP-06 | Research brief | PDF | |
| TP-07 | CIM document | DOCX | |

All generated outputs embed a compliance disclaimer on the last page.

---

### 2.2 OUT OF SCOPE — v1.0

| Feature | Reason Deferred | Target Version |
|---|---|---|
| SSO (SAML / OIDC) | Complex IdP integration | v2 |
| Real Bloomberg / Capital IQ API | Licensed, cost, complexity | v2 |
| Real-time web search (live) | API key + rate limiting | v2 |
| Mobile responsive design | Desktop financial tool | v2 |
| Deal sharing / export to Google Drive | Not in core workflow | v2 |
| Real-time multi-user collaboration | Complex infra | v3 |
| Vector DB migration (Pinecone / Weaviate) | ChromaDB sufficient for v1 | v2 |
| Fine-tuning pipeline UI | Power user feature | v2 |
| Slack / email task notifications | External integrations | v2 |
| Custom pitchbook colour themes | B&W chrome + semantic palette sufficient | v2 |
| Audit trail export to SIEM | Enterprise compliance feature | v3 |
| Virus scanning on upload | Security hardening | v2 |
| Column-level encryption for LLM prompts | Requires KMS setup | v2 |
| White-labelling | Enterprise | v3 |
| Self-hosted Colab fine-tuning | Nice-to-have; Anthropic API is primary | v2 |

---

## 3. Technical Constraints

| Constraint | Detail |
|---|---|
| **LLM Backend** | Anthropic Claude (default). OpenAI supported via env switch. Colab optional for fine-tune experiments only. |
| **Database** | SQLite (dev) — Postgres (prod). One codebase, zero code changes to promote. |
| **Vector Store** | ChromaDB (local persistent). Sufficient for v1 deal volumes. |
| **Inference Latency** | Complex tasks may take 2–4 minutes; SSE handles gracefully with reconnect support. |
| **Context Window** | RAG retrieval caps context per agent run at top-K chunks (default K=8). Never inject full documents. |
| **Single Org/User** | v1 auth supports multi-user orgs (schema-ready) but complex permission hierarchies are v2. |
| **Python 3.11** | Target version for all backend code. |
| **Node 18+** | Target version for frontend build. |
| **Docker** | All services containerised from day one. `docker compose up` is the only required setup command. |

---

## 4. Definition of Done (DoD)

A feature is **Done** when:

1. ✅ All acceptance criteria from doc `02` pass
2. ✅ Unit tests pass with ≥ 80% coverage on new code (100% on computation engine)
3. ✅ API contract matches spec in doc `06` exactly
4. ✅ Auth middleware applied — endpoint returns `401` without a valid JWT
5. ✅ All DB queries include org_id scoping
6. ✅ Sensitive operations logged to audit trail
7. ✅ No unhandled exceptions surface to the user
8. ✅ UI renders correctly at 1280px and 1440px
9. ✅ All generated file outputs include a compliance disclaimer
10. ✅ `docker compose up && make test` passes on a clean clone

---

## 5. Engineering Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM API rate limits / outages | Medium | High | Exponential backoff + retry in LLM client; error surfaced to user via SSE |
| RAG retrieval misses key financial data | Medium | High | Increase top-K; add query expansion; allow user to manually select docs |
| Hallucination on extracted figures | High | Critical | Hallucination Guard v2 with typed field registry; human review badge |
| ChromaDB performance on large deal rooms | Medium | Medium | Index during upload (background); don't block agent runs |
| ARQ worker crashes mid-job | Low | Medium | ARQ persists job state in Redis; worker auto-resumes on restart |
| PDF/PPTX generation formatting issues | Medium | High | Build templates in isolation; validate early against real deal data |
| Prompt injection via uploaded documents | Medium | Critical | sanitize_user_input() wraps all user-provided content; content delimiters in prompts |
| MNPI data accidentally sent to LLM API | Low | Critical | Pre-flight MNPI check enforced at API level; consent logged; cannot be bypassed |
| Audit log chain breaks | Very Low | High | Integrity hash verified on export; any tampering detected immediately |

---

## 6. Estimation Summary

| Area | Story Points | Estimated Dev Days |
|---|---|---|
| Auth + Security (JWT, MNPI, rate limiting, audit) | 21 | 4 days |
| Frontend (React SPA — all 26 features) | 55 | 11 days |
| Backend API (FastAPI — 22 endpoints) | 34 | 7 days |
| ARQ Worker + Redis queue | 13 | 3 days |
| RAG pipeline (chunker + embedder + ChromaDB) | 21 | 4 days |
| Agent implementations (6 agents) | 55 | 11 days |
| Computation Engine (DCF/LBO/CCA — v2 fixes) | 21 | 4 days |
| Tools (8 tools inc. PPTX) | 21 | 4 days |
| Document templates (7 templates) | 21 | 4 days |
| Compliance (disclaimers, data classification) | 8 | 2 days |
| Testing + QA | 21 | 4 days |
| **Total** | **291** | **~58 days (solo dev)** |

> A 2-person team (1 frontend, 1 backend/AI) reduces this to ~32 days.

---

*End of Document — 09-engineering-scope-definition.md*
