# 06 — API Contracts
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Overview

This document defines all HTTP API contracts between:
- **React SPA ↔ Orchestration Backend (FastAPI)**
- **ARQ Worker ↔ LLM Provider APIs**

**Base URL:** `http://localhost:8000/api/v1`
**Protocol:** REST + Server-Sent Events (SSE) for streaming
**Content-Type:** `application/json` (except file uploads: `multipart/form-data`)
**Auth:** `Authorization: Bearer <jwt>` on all endpoints except `/auth/*`

### Key API Design Principles (v2.0 changes)

- **Idempotency:** All `POST`, `PUT`, `PATCH` requests accept an `Idempotency-Key` header. Duplicate requests within 24 hours return the original response.
- **Org scoping:** All data is scoped to the authenticated user's `org_id`. Cross-tenant access is structurally impossible.
- **Cursor pagination:** All list endpoints use cursor-based pagination (not offset) for consistency under concurrent inserts.
- **Webhooks:** Registered endpoints receive HMAC-signed payloads on async task completion.
- **Non-blocking agents:** Agent runs always return `202 Accepted` immediately. Results come via SSE stream or webhook.

---

## 2. Standard Response Envelope

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "timestamp": "2025-01-15T10:30:00Z",
    "request_id": "req_abc123",
    "api_version": "2.0"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "AGENT_TIMEOUT",
    "message": "The agent did not complete within the timeout window.",
    "details": {}
  },
  "meta": {
    "timestamp": "2025-01-15T10:30:00Z",
    "request_id": "req_abc123"
  }
}
```

---

## 3. Authentication API

### `POST /auth/login` — Authenticate User

**Request:**
```json
{
  "email": "analyst@firm.com",
  "password": "••••••••"
}
```

**Response `200`:**
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 28800,
    "requires_mfa": false,
    "user": {
      "id": "usr_abc123",
      "email": "analyst@firm.com",
      "org_id": "org_xyz789",
      "role": "analyst"
    }
  }
}
```

**Response `200` (MFA required):**
```json
{
  "success": true,
  "data": {
    "mfa_token": "mfa_temp_abc123",
    "requires_mfa": true
  }
}
```

### `POST /auth/mfa/verify` — Complete MFA

**Request:**
```json
{ "mfa_token": "mfa_temp_abc123", "totp_code": "123456" }
```

**Response `200`:** Same as successful login — issues access_token.

### `POST /auth/logout` — Invalidate Session

Adds token to Redis blocklist. **Response `200`:** `{ "success": true }`.

---

## 4. Deals API

### `POST /deals` — Create a New Deal

**Headers:** `Idempotency-Key: <client-generated-uuid>`

**Request:**
```json
{
  "name": "Project Falcon",
  "company_name": "Nexus Pharma Inc.",
  "deal_type": "ma_sellside",
  "industry": "Healthcare / Pharmaceuticals",
  "deal_stage": "preliminary",
  "notes": "Sell-side mandate for founder-owned pharma, ~$150M revenue"
}
```

**Response `201`:**
```json
{
  "success": true,
  "data": {
    "id": "deal_9f3a1c2d",
    "org_id": "org_xyz789",
    "name": "Project Falcon",
    "company_name": "Nexus Pharma Inc.",
    "deal_type": "ma_sellside",
    "deal_stage": "preliminary",
    "created_at": "2025-01-15T10:30:00Z",
    "document_count": 0,
    "output_count": 0
  }
}
```

**Idempotent replay (duplicate Idempotency-Key within 24h):**
- Returns original `201` response
- Header `X-Idempotent-Replayed: true` is set
- No new deal is created

---

### `GET /deals` — List All Deals (cursor-based pagination)

**Query Parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `stage` | string | all | Filter by stage |
| `limit` | int | 20 | Max results (max 100) |
| `cursor` | string | null | Opaque cursor from previous response |
| `sort` | string | created_at_desc | Sort order |

**Response `200`:**
```json
{
  "success": true,
  "data": {
    "deals": [ ... ],
    "cursor_next": "eyJjcmVhdGVkX2F0IjoiMjAyNS0wMS0xNSJ9",
    "has_more": true,
    "limit": 20
  }
}
```

*Cursor-based pagination ensures consistent results even as new deals are inserted between pages.*

---

### `GET /deals/:deal_id` — Get Deal Details
### `PATCH /deals/:deal_id` — Update Deal
### `DELETE /deals/:deal_id` — Archive Deal (soft-delete)

---

## 5. Documents API

### `POST /deals/:deal_id/documents` — Upload Documents

**Headers:** `Idempotency-Key: <uuid>`

**Request:** `multipart/form-data`

| Field | Type | Description |
|---|---|---|
| `files` | File[] | One or more files (.pdf, .docx, .xlsx, .csv) |
| `category` | string | Optional: 'financial', 'legal', 'corporate', 'tax', 'operational' |
| `data_classification` | string | Optional: 'public', 'internal', 'confidential', 'mnpi' — defaults to 'internal' |

**Response `201`:**
```json
{
  "success": true,
  "data": {
    "uploaded": [
      {
        "id": "doc_a1b2c3",
        "filename": "income_statement_2024.xlsx",
        "file_type": "xlsx",
        "file_size_bytes": 45231,
        "data_classification": "confidential",
        "parse_status": "processing",
        "rag_status": "pending",
        "uploaded_at": "2025-01-15T10:35:00Z"
      }
    ],
    "failed": []
  }
}
```

RAG indexing begins as a background job after parse completes. Poll `GET /deals/:id/documents` for `rag_status = 'indexed'` before running agents.

### `PATCH /deals/:deal_id/documents/:doc_id` — Update Document Metadata

Used to update `data_classification` (e.g., flag as MNPI post-upload).

**Request:** `{ "data_classification": "mnpi" }`

---

### `GET /deals/:deal_id/documents` — List Documents
### `DELETE /deals/:deal_id/documents/:doc_id` — Delete Document
### `GET /deals/:deal_id/documents/:doc_id/text` — Get Parsed Text (internal use)

---

## 6. Agent API

### `POST /deals/:deal_id/agents/run` — Trigger Agent Run

**Headers:** `Idempotency-Key: <uuid>`

**Request:**
```json
{
  "agent_type": "modeling",
  "task_name": "dcf_model",
  "mnpi_consent": false,
  "parameters": {
    "model_type": "dcf",
    "projection_years": 5,
    "wacc_override": null,
    "terminal_growth_rate": 0.025,
    "use_mid_year_discounting": true,
    "document_ids": ["doc_a1b2c3"],
    "additional_context": "High-growth SaaS, 35% YoY revenue growth"
  }
}
```

**`mnpi_consent` field:**
- If any document in scope has `data_classification = 'mnpi'`, the server returns `403 MNPI_CONSENT_REQUIRED` unless `mnpi_consent: true` is set.
- Setting `mnpi_consent: true` records the consent in the agent_run and audit log.

**Valid `agent_type` + `task_name` matrix:**

| agent_type | task_name options |
|---|---|
| modeling | `dcf_model`, `lbo_model`, `comparable_analysis` |
| pitchbook | `full_pitchbook`, `executive_summary_slides`, `single_slide_revision` |
| due_diligence | `full_dd_review`, `dd_checklist`, `risk_summary` |
| research | `industry_overview`, `buyer_universe`, `target_universe`, `comp_transactions` |
| doc_drafter | `cim_draft`, `executive_summary`, `deal_teaser`, `market_overview_section` |
| coordination | `process_meeting_notes`, `generate_task_list`, `deal_status_report` |

**Response `202 Accepted`:**
```json
{
  "success": true,
  "data": {
    "run_id": "run_x7y8z9",
    "arq_job_id": "arq_job_abc123",
    "agent_type": "modeling",
    "task_name": "dcf_model",
    "status": "queued",
    "stream_url": "/api/v1/agents/runs/run_x7y8z9/stream",
    "created_at": "2025-01-15T10:36:00Z"
  }
}
```

**Response `403` (MNPI consent required):**
```json
{
  "success": false,
  "error": {
    "code": "MNPI_CONSENT_REQUIRED",
    "message": "This run uses documents classified as MNPI. Resend with mnpi_consent: true to confirm.",
    "details": {
      "mnpi_documents": ["doc_a1b2c3"]
    }
  }
}
```

---

### `GET /agents/runs/:run_id/stream` — Stream Agent Progress (SSE)

**Protocol:** Server-Sent Events
**Content-Type:** `text/event-stream`
**Auth:** Bearer token in query param `?token=<jwt>` (SSE cannot send custom headers)

**Reconnect behaviour:** On reconnect, client sends `Last-Event-ID` header. Server replays all events since that ID. If `Last-Event-ID` is absent, replays all events from the start of the run.

**Event Types:**
```
id: evt_001
event: step
data: {"step": 1, "type": "thought", "content": "Retrieving context for DCF model..."}

id: evt_002
event: step
data: {"step": 2, "type": "rag_retrieval", "content": "Retrieved 10 chunks from income_statement_2024.xlsx", "chunk_count": 10}

id: evt_003
event: step
data: {"step": 3, "type": "action", "content": "Calling tool: computation_engine.dcf"}

id: evt_004
event: step
data: {"step": 4, "type": "observation", "content": "DCF computed: EV = $285M, implied share price = $28.50"}

id: evt_005
event: progress
data: {"percent_complete": 80, "current_step": "Building sensitivity table"}

id: evt_006
event: complete
data: {"run_id": "run_x7y8z9", "status": "completed", "output_id": "out_p1q2r3", "confidence_score": 0.87, "hallucination_flags": 0}

id: evt_007
event: error
data: {"run_id": "run_x7y8z9", "status": "failed", "error_code": "LLM_UNAVAILABLE", "message": "LLM service returned 503"}
```

---

### `GET /agents/runs/:run_id` — Get Run Details

**Response `200`:**
```json
{
  "success": true,
  "data": {
    "id": "run_x7y8z9",
    "deal_id": "deal_9f3a1c2d",
    "agent_type": "modeling",
    "agent_version": "1.0.0",
    "task_name": "dcf_model",
    "status": "completed",
    "llm_backend": "anthropic",
    "llm_model": "claude-opus-4-6",
    "reasoning_steps": [
      {"step": 1, "type": "thought", "content": "..."},
      {"step": 2, "type": "rag_retrieval", "chunk_count": 10},
      {"step": 3, "type": "action", "tool": "dcf_engine"}
    ],
    "rag_chunks_used": ["doc_a1b2c3_chunk_0", "doc_a1b2c3_chunk_3"],
    "confidence_score": 0.87,
    "mnpi_consent": false,
    "started_at": "2025-01-15T10:36:05Z",
    "completed_at": "2025-01-15T10:37:42Z",
    "duration_seconds": 97,
    "output_ids": ["out_p1q2r3"]
  }
}
```

---

## 7. Outputs API

### `GET /deals/:deal_id/outputs` — List Outputs
### `GET /outputs/:output_id` — Get Output Metadata
### `GET /outputs/:output_id/download` — Download Output File

**Response:** Binary file stream with `Content-Type` and `Content-Disposition: attachment` headers.

### `PATCH /outputs/:output_id/review` — Update Review Status

**Headers:** `Idempotency-Key: <uuid>`

**Request:**
```json
{
  "review_status": "approved",
  "reviewer_notes": "Verified against source — approved for client delivery"
}
```

### `POST /outputs/:output_id/revise` — Request Revision

**Request:**
```json
{
  "revision_instructions": "Change WACC assumption from 10% to 12%",
  "sections": ["assumptions", "sensitivity_table"]
}
```

**Response `202`:** New `AgentRun` object — same structure as `/agents/run` response.

---

## 8. Tasks API

### `GET /deals/:deal_id/tasks` — List Tasks

**Query Parameters:** `status` (filter), `limit`, `cursor`

### `POST /deals/:deal_id/tasks` — Create Manual Task

**Headers:** `Idempotency-Key: <uuid>`

**Request:**
```json
{
  "title": "Send NDA to potential buyer",
  "owner": "John Smith",
  "priority": "high",
  "due_date": "2025-01-20"
}
```

### `PATCH /tasks/:task_id` — Update Task

---

## 9. Webhook API *(NEW)*

### `POST /webhooks` — Register Webhook Endpoint

**Request:**
```json
{
  "name": "Slack Notifications",
  "url": "https://hooks.slack.com/services/...",
  "events": ["agent.completed", "output.approved", "agent.failed"]
}
```

**Response `201`:**
```json
{
  "success": true,
  "data": {
    "id": "wh_abc123",
    "name": "Slack Notifications",
    "url": "https://hooks.slack.com/...",
    "events": ["agent.completed", "output.approved", "agent.failed"],
    "secret": "whsec_abcdefg123456",
    "is_active": true
  }
}
```

The `secret` is returned only on creation. Store it — it is used to verify HMAC signatures on delivered payloads.

### `GET /webhooks` — List Webhook Endpoints
### `DELETE /webhooks/:webhook_id` — Delete Webhook

### Webhook Payload Format

Delivered via `POST` to the registered URL:

```json
{
  "event": "agent.completed",
  "timestamp": "2025-01-15T10:37:42Z",
  "data": {
    "run_id": "run_x7y8z9",
    "deal_id": "deal_9f3a1c2d",
    "agent_type": "modeling",
    "task_name": "dcf_model",
    "status": "completed",
    "output_id": "out_p1q2r3",
    "confidence_score": 0.87
  }
}
```

**Signature verification:**
```
X-AIBAA-Signature: sha256=<hex>
X-AIBAA-Event: agent.completed
X-AIBAA-Delivery: del_abc123
```

Compute: `HMAC-SHA256(webhook_secret, raw_request_body)` and compare to the `sha256=` value.

**Retry policy:** On non-2xx response, retry at 1min, 5min, 30min, 2hr intervals. After 5 consecutive failures, the endpoint is deactivated and the org is notified.

---

## 10. Admin API *(NEW)*

### `GET /admin/audit` — List Audit Events (org admin only)

**Query Parameters:** `event_type`, `user_id`, `from`, `to`, `cursor`, `limit`

### `GET /admin/audit/export` — Export Audit Trail as signed CSV

**Response:** CSV file with all audit events and integrity hashes. The server validates the hash chain before generating the export — if any tampering is detected, the response includes a `chain_integrity_warning`.

### `GET /admin/users` — List Org Users
### `POST /admin/users/invite` — Invite User to Org
### `DELETE /admin/users/:user_id` — Deactivate User

---

## 11. Settings API

### `GET /settings` — Get All Settings for Current Org
### `PUT /settings/:key` — Update a Setting

**Request:** `{ "value": "anthropic" }`

---

## 12. Error Codes Reference

| Code | HTTP Status | Description |
|---|---|---|
| `VALIDATION_ERROR` | 422 | Request body failed validation |
| `UNAUTHORIZED` | 401 | Missing or invalid JWT |
| `FORBIDDEN` | 403 | Authenticated but not authorised for this resource |
| `MNPI_CONSENT_REQUIRED` | 403 | Run uses MNPI documents — consent required |
| `DEAL_NOT_FOUND` | 404 | Deal ID does not exist (or belongs to different org) |
| `DOCUMENT_NOT_FOUND` | 404 | Document ID does not exist |
| `RUN_NOT_FOUND` | 404 | Agent run ID does not exist |
| `OUTPUT_NOT_FOUND` | 404 | Output ID does not exist |
| `UNSUPPORTED_FILE_TYPE` | 400 | Uploaded file type not supported |
| `FILE_TOO_LARGE` | 413 | File exceeds 50MB limit |
| `DOCUMENTS_NOT_INDEXED` | 409 | Relevant documents are still being indexed — retry shortly |
| `AGENT_UNAVAILABLE` | 503 | LLM provider is offline or unreachable |
| `AGENT_TIMEOUT` | 504 | Agent did not complete in time |
| `AGENT_ERROR` | 500 | Agent encountered an internal error |
| `HALLUCINATION_GUARD` | 200 | Output flagged for low confidence (non-blocking) |
| `PARSE_FAILED` | 422 | Document could not be parsed |
| `PROMPT_INJECTION_DETECTED` | 400 | Input contained likely prompt injection — sanitised |
| `RATE_LIMIT_EXCEEDED` | 429 | Too many requests — includes `Retry-After` header |
| `IDEMPOTENCY_CONFLICT` | 409 | Idempotency key already used with different request body |

---

*End of Document — 06-api-contracts.md*
