# 04 — System Architecture
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Architecture Philosophy

AIBAA is designed around four principles:

1. **Agent-First Design** — Every core feature is an AI agent with defined inputs, tools, and outputs.
2. **Swappable LLM Backend** — An abstraction layer decouples agent logic from the LLM provider. The system works with Anthropic Claude (default), OpenAI, or a self-hosted Colab/Unsloth model — set by a single environment variable.
3. **Persistent-First Storage** — SQLAlchemy with SQLite (development) or PostgreSQL (production) from day one. No in-memory-only state.
4. **Security by Default** — JWT auth, org-scoped data, encrypted uploads, immutable audit logs, and prompt injection protection are not v2 features — they are built in from the first commit.

> **Note on architecture consistency:** Earlier iterations of this documentation described two conflicting architectures (Colab/Llama vs. Gemini/DeepSeek cloud APIs). This document supersedes both. The canonical architecture uses an **abstracted LLM client** that defaults to the Anthropic API and supports optional self-hosted inference. There is one codebase, one architecture.

---

## 2. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                       CLIENT LAYER                           │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │     React SPA (B&W Chrome + Financial Semantic UI)   │   │
│   │  Dashboard | Deal Workspace | Agent Panel            │   │
│   │  Document Upload | Output Preview | Audit Trail      │   │
│   └───────────────────────┬─────────────────────────────┘   │
└───────────────────────────┼─────────────────────────────────┘
                            │ HTTPS / REST + SSE
┌───────────────────────────▼─────────────────────────────────┐
│                   ORCHESTRATION LAYER                         │
│                                                              │
│   ┌─────────────────────────────────────────────────────┐   │
│   │            FastAPI Backend (Python 3.11)             │   │
│   │   JWT Auth Middleware | Rate Limiting | CORS         │   │
│   │   Idempotency Middleware | Prompt Injection Guard    │   │
│   │                                                      │   │
│   │   ┌──────────────────────────────────────────────┐  │   │
│   │   │            Orchestrator Agent                │  │   │
│   │   │   (Routes tasks → selects sub-agent)         │  │   │
│   │   └──────────────────────────────────────────────┘  │   │
│   │                                                      │   │
│   │   Sub-Agent Registry:                                │   │
│   │   ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │   │
│   │   │ Modeling │ │Pitchbook │ │  Due Diligence    │  │   │
│   │   └──────────┘ └──────────┘ └───────────────────┘  │   │
│   │   ┌──────────┐ ┌──────────┐ ┌───────────────────┐  │   │
│   │   │ Research │ │  Doc     │ │  Coordination     │  │   │
│   │   │  Agent   │ │ Drafter  │ │  Agent            │  │   │
│   │   └──────────┘ └──────────┘ └───────────────────┘  │   │
│   │                                                      │   │
│   │   Tool Registry:                                     │   │
│   │   RAG Retrieval | File Parser | Doc Generator        │   │
│   │   Python Executor | Excel Writer | PDF Generator     │   │
│   └───────────────────────┬──────────────────────────┘  │   │
└───────────────────────────┼─────────────────────────────────┘
                            │ Enqueue / Dequeue
┌───────────────────────────▼─────────────────────────────────┐
│                     TASK QUEUE LAYER (NEW)                    │
│                                                              │
│   ┌──────────────────────┐  ┌────────────────────────────┐  │
│   │   Redis (ARQ queue)  │  │   ARQ Worker Process(es)   │  │
│   │   Job storage        │  │   Executes agent runs      │  │
│   │   Pub/Sub for SSE    │  │   Survives API restarts    │  │
│   └──────────────────────┘  └────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │ HTTP (provider API or ngrok)
┌───────────────────────────▼─────────────────────────────────┐
│                    LLM INFERENCE LAYER                        │
│                                                              │
│   ┌──────────────────────────────────────────────────────┐  │
│   │              BaseLLMClient (abstraction)              │  │
│   │                                                       │  │
│   │   ┌─────────────────┐   ┌──────────────────────────┐ │  │
│   │   │  AnthropicClient │   │  OpenAIClient            │ │  │
│   │   │  (default)       │   │  (optional)              │ │  │
│   │   └─────────────────┘   └──────────────────────────┘ │  │
│   │                                                       │  │
│   │   ┌──────────────────────────────────────────────┐   │  │
│   │   │  ColabClient (optional — for fine-tune work) │   │  │
│   │   │  Exposes same interface; swap via env var     │   │  │
│   │   └──────────────────────────────────────────────┘   │  │
│   └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────┐
│                      STORAGE LAYER                            │
│                                                              │
│   PostgreSQL (prod) / SQLite (dev):                          │
│   - deals, documents, agent_runs, outputs, tasks             │
│   - audit_logs (append-only, integrity-chained)              │
│   - webhook_endpoints, settings                              │
│                                                              │
│   Redis:                                                     │
│   - ARQ job queue                                            │
│   - Idempotency key cache (24h TTL)                          │
│   - SSE pub/sub channels                                     │
│                                                              │
│   ChromaDB (vector store):                                   │
│   - Document chunks + embeddings (per deal collection)       │
│   - Powers RAG retrieval for all agents                      │
│                                                              │
│   Local filesystem (dev) / S3 (prod):                        │
│   - Raw uploaded files (encrypted at rest in prod)           │
│   - Generated output files (XLSX, PDF, DOCX, PPTX)          │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Component Breakdown

### 3.1 React SPA (Frontend)
| Component | Technology | Responsibility |
|---|---|---|
| UI Framework | React 18 + Vite | Component rendering, routing |
| Styling | Tailwind CSS (B&W chrome + semantic finance tokens) | Visual design system |
| File Upload | react-dropzone | Drag-and-drop document upload |
| PDF Preview | react-pdf | Inline PDF rendering |
| PPTX Preview | pptx-preview or thumbnail grid | Inline PPTX rendering |
| SSE Client | native EventSource API | Real-time agent progress streaming |
| State Management | Zustand | Client-side deal/agent state |
| HTTP Client | Axios (with auth interceptor) | API calls with JWT header injection |
| Routing | React Router v6 | Page navigation + auth guards |
| Auth | JWT stored in httpOnly cookie (not localStorage) | Prevents XSS token theft |

### 3.2 Orchestration Backend (FastAPI)
| Component | Technology | Responsibility |
|---|---|---|
| API Framework | FastAPI (Python 3.11) | REST endpoints, SSE streaming |
| Auth Middleware | python-jose + passlib | JWT validation on every protected route |
| Rate Limiting | slowapi (token bucket) | Prevent abuse; 60 req/min default |
| Idempotency | Custom Redis middleware | Deduplicate mutating requests |
| Prompt Guard | Custom sanitiser | Detect and neutralise injection attempts |
| Orchestrator | Custom agent loop | Task routing and agent lifecycle |
| File Parsing | PyMuPDF, python-docx, openpyxl | Read uploaded documents |
| RAG Pipeline | sentence-transformers + ChromaDB | Chunk, embed, and retrieve document context |
| Output Generation | openpyxl, python-docx, ReportLab, python-pptx | Create XLSX, DOCX, PDF, PPTX outputs |
| Task Queue Client | arq (async Redis queue) | Enqueue agent runs |
| Database | SQLAlchemy (async) + Alembic | ORM + migrations |
| Audit Logger | Custom append-only service | Integrity-chained audit trail |
| Observability | Sentry SDK + structlog | Error tracking + structured logging |

### 3.3 ARQ Worker
| Component | Technology | Responsibility |
|---|---|---|
| Queue Worker | arq | Executes agent runs in a separate process |
| LLM Client | BaseLLMClient (Anthropic / OpenAI / Colab) | LLM inference calls |
| Computation Engine | Custom Python | DCF, LBO, CCA deterministic calculations |
| Webhook Dispatcher | httpx | Notify external endpoints on task completion |
| SSE Publisher | Redis pub/sub | Push live progress to connected clients |

### 3.4 LLM Client Abstraction
| Backend | Class | When to Use |
|---|---|---|
| Anthropic Claude | `AnthropicClient` | Default production backend — best reasoning quality |
| OpenAI GPT-4o | `OpenAIClient` | Alternative production backend |
| Colab / Unsloth | `ColabClient` | Local fine-tuning experiments only — not for production |

Switch via: `LLM_BACKEND=anthropic` (or `openai` or `colab`) in `.env`.

---

## 4. Security Architecture

### 4.1 Authentication & Authorisation
```
Request
  → JWT Middleware (validates token, extracts user_id + org_id)
  → Route Handler (receives user context as dependency injection)
  → Service Layer (all DB queries scoped: WHERE org_id = :org_id)
  → Response
```

Every database query is scoped by `org_id`. Cross-tenant data access is structurally impossible — a query for deal data always includes `AND org_id = :current_user_org_id`.

### 4.2 Prompt Injection Protection
```
User Input (notes, document content, revision instructions)
  → sanitize_user_input() — regex detection of injection patterns
  → Detected threats logged to audit trail
  → Content wrapped in <user_provided_content> delimiters
  → System prompt reinforced with boundary instruction
  → LLM receives isolated, clearly-delimited user content
```

### 4.3 MNPI Document Handling
```
Document uploaded with MNPI flag
  → Stored in database with data_classification = 'mnpi'
  → On agent run: pre-flight check scans deal documents
  → If any MNPI doc is in scope → frontend shows consent banner
  → User confirms consent → consent logged to audit trail
  → Agent proceeds; MNPI usage is recorded in agent_run metadata
```

### 4.4 Audit Log Integrity
```
Each audit log entry:
  → Reads previous entry's integrity_hash from DB
  → Computes: SHA-256(prev_hash + current_event_json)
  → Stores new_hash alongside the event
  
Tamper detection:
  → Re-compute the entire chain at any time
  → Any deleted or modified row breaks the hash chain
  → Export function validates chain before generating CSV
```

---

## 5. Agent Architecture

Each sub-agent follows the **RAG-augmented ReAct (Reason + Act)** pattern:

```
System Prompt (Agent Role)
→ RAG Retrieval: retrieve_context(deal_id, task_query, top_k=8)
   [Returns the most relevant document chunks — never the full document]
→ Input Context (deal info + retrieved chunks, NOT raw full documents)
→ Think: "What do I need to do? Do I have enough context?"
→ Act: Call Tool (parse_file / run_python / format_output)
→ Observe: Tool result
→ Think: "Does this meet the requirement? Are numbers verifiable?"
→ Hallucination Guard: verify extracted figures against source chunks
→ Repeat or Finalise
→ Output: Structured result + confidence score + verification report
```

### Agent Definitions

| Agent | System Prompt Role | Primary Tools | Output |
|---|---|---|---|
| Orchestrator | Route user requests to the correct analyst agent | All agents | Task assignment |
| Financial Modeling | Senior IB analyst building financial models | rag_retrieval, computation_engine, excel_writer | XLSX model |
| Pitchbook | IB analyst creating client pitch presentations | rag_retrieval, doc_generator, pptx_builder | PDF / PPTX |
| Due Diligence | Legal/financial due diligence reviewer | rag_retrieval, risk_classifier | PDF report |
| Market Research | Equity research analyst | rag_retrieval, data_formatter | PDF brief |
| Doc Drafter | CIM and deal document drafter | rag_retrieval, doc_template | DOCX / PDF |
| Coordinator | Deal coordination specialist | rag_retrieval, task_extractor | MD / XLSX |

---

## 6. RAG Pipeline Architecture

```
Document Upload
  → File Parser (PyMuPDF / openpyxl / python-docx)
  → Text Extraction → stored in documents.parsed_text
  → Background job enqueued: index_document(doc_id, deal_id, text)
     ↓
  Chunking (semantic-aware: paragraph boundaries, 512-token chunks, 64-token overlap)
     ↓
  Embedding (sentence-transformers: BAAI/bge-base-en-v1.5)
     ↓
  ChromaDB storage (collection per deal: deal_{deal_id})
     ↓
  documents.rag_status = 'indexed', chunk_count = N

Agent Run
  → retrieve_context(deal_id, query, top_k=8)
     ↓
  Query embedding → ChromaDB similarity search
     ↓
  Top-K chunks returned with source document metadata
     ↓
  Context formatted: "[Source: doc_id]\n{chunk_text}\n---"
     ↓
  Injected into LLM prompt — never the full document
```

---

## 7. Data Flow for a Typical Task

### Example: User requests DCF model

```
1. User fills DCF parameters → clicks "Run"
2. React SPA → POST /api/v1/deals/{id}/agents/run
   Headers: { Authorization: Bearer <jwt>, Idempotency-Key: <uuid> }
3. FastAPI:
   a. JWT middleware validates token, extracts org_id
   b. Idempotency middleware checks Redis — no duplicate found
   c. Prompt injection guard sanitises any user-provided text
   d. Agent run record created with status='queued'
   e. ARQ job enqueued: run_agent_task(run_id, deal_id, 'modeling', params)
   f. Returns 202 Accepted with run_id + stream_url
4. ARQ Worker (separate process):
   a. Updates agent_run status to 'running'
   b. Calls retrieve_context(deal_id, "revenue EBITDA income statement", top_k=10)
   c. RAG returns 10 relevant chunks from indexed financials
   d. Builds LLM prompt with retrieved context (not full document)
   e. Calls AnthropicClient.generate(system, user_prompt)
   f. LLM returns structured JSON with DCF parameters
   g. HallucinationGuard.verify() — checks DOCUMENT_EXTRACTED fields only
   h. DCFEngine.compute() — deterministic calculation (never LLM arithmetic)
   i. ExcelWriter builds .xlsx from computed outputs
   j. Output saved to filesystem; output record created in DB
   k. Publishes completion event to Redis pub/sub: run:{run_id}
   l. Webhook dispatcher fires for any registered endpoints
5. FastAPI SSE Handler:
   a. Subscribed to Redis pub/sub channel run:{run_id}
   b. Forwards progress events to connected browser client
6. React SPA:
   a. SSE updates reasoning panel in real-time
   b. On 'complete' event: fetches output metadata
   c. File preview + download link shown to user
```

---

## 8. Communication Protocols

| Connection | Protocol | Details |
|---|---|---|
| React SPA ↔ FastAPI | REST (HTTPS) + SSE | REST for requests, SSE for streaming; all requests carry JWT |
| FastAPI ↔ ARQ Worker | Redis job queue | FastAPI enqueues; worker dequeues |
| Worker ↔ LLM Provider | HTTPS | POST to Anthropic/OpenAI API; or ngrok for Colab |
| Worker ↔ FastAPI (SSE) | Redis pub/sub | Worker publishes events; FastAPI SSE handler forwards to browser |
| File Upload | Multipart HTTPS | Files sent as form-data; stored server-side |
| Webhook Delivery | HTTPS POST | HMAC-SHA256 signed payloads to registered endpoints |

---

## 9. Security Considerations

| Risk | Mitigation |
|---|---|
| Unauthenticated access | JWT auth middleware on every protected route — no exceptions |
| Cross-tenant data access | All DB queries scoped by org_id via dependency injection |
| Prompt injection | sanitize_user_input() + content delimiters + system prompt reinforcement |
| MNPI data sent to external LLM | Pre-flight MNPI check + explicit user consent required + consent logged |
| XSS token theft | JWT stored in httpOnly cookie, not localStorage |
| Sensitive data in error reports | Sentry before_send hook scrubs request bodies and LLM prompts |
| Audit log tampering | SHA-256 integrity chain; append-only table; no DELETE/UPDATE permitted |
| Rate abuse | slowapi token bucket; 60 req/min default; configurable per route |
| Secrets in plaintext | All secrets via environment variables; never committed to repo; Docker secrets in prod |
| File upload abuse | MIME type validation + file size limit + virus scan hook (v2) |

---

## 10. Scalability Path

| Concern | v1 Approach | v2 Path |
|---|---|---|
| LLM Backend | Anthropic API (default) | Multi-provider routing; fallback chain |
| Storage | SQLite (dev) / PostgreSQL (prod) | Already on Postgres — add read replicas |
| File Storage | Local filesystem | S3 with server-side encryption |
| Worker Scaling | Single ARQ worker | Multiple ARQ workers; Redis cluster |
| Multi-user | JWT + org scoping (from day 1) | Add SSO (SAML/OIDC) for enterprise |
| Vector Store | ChromaDB (local) | Pinecone or Weaviate for scale |
| Real market data | Stub/mock | Bloomberg API / yFinance / Alpha Vantage |
| Observability | Sentry + structlog | Add Datadog APM or Grafana stack |

---

*End of Document — 04-system-architecture.md*
