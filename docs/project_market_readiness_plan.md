# AIBAA Market-Readiness Status And Implementation Plan

This document now reflects the current implementation state of the repository, not just the target architecture. It separates completed foundations from the remaining work required to make the platform truly market ready.

## Current Status Snapshot

### Implemented Foundations
- Durable SQLAlchemy-backed persistence is now in place for deals, documents, agent runs, outputs, and review events.
- Tenant-aware deal ownership fields (`tenant_id`, `owner_id`) are now part of the persisted deal model and are enforced in API queries.
- Signed JWT authentication is now required across deal, document, agent-run, and output endpoints.
- Document parsing is asynchronous and gated: the modeling agent is blocked until all attached files are fully parsed.
- Frontend agent runs now support asynchronous polling instead of waiting on one long blocking request.
- Output governance has started: outputs can be reviewed, reviewer/admin approval is role-gated, approval events are stored, and downloads are blocked until approval.
- LLM silent fallback behavior has been hardened so missing/quota-failed model access raises explicit errors instead of fabricating generic results.
- Valuation safety is improved through deterministic spreadsheet extraction, sector routing, mid-year discounting, and market-sanity warning metadata.

### Implemented Files
- `apps/api/src/database.py`
- `apps/api/src/db_models.py`
- `apps/api/src/dependencies.py`
- `apps/api/src/persistence.py`
- `apps/api/src/routers/auth.py`
- `apps/api/src/routers/deals.py`
- `apps/api/src/routers/documents.py`
- `apps/api/src/routers/agents.py`
- `apps/api/src/routers/outputs.py`
- `apps/api/src/agents/base.py`
- `apps/api/src/agents/modeling.py`
- `apps/api/src/engine/dcf.py`
- `apps/api/src/engine/llm.py`
- `apps/web/src/lib/api.ts`
- `apps/web/src/components/workspace/AgentsTab.tsx`
- `apps/web/src/components/workspace/DocumentsTab.tsx`
- `apps/web/src/components/workspace/OutputsTab.tsx`
- `apps/web/src/pages/DealWorkspace.tsx`
- `apps/web/.env.example`

## Phase 1: Intake, Security, And Core Persistence
**Goal:** Transition from a prototype into a durable, tenant-aware system with enforceable access boundaries.

### Completed
- Added relational persistence for core business objects through SQLAlchemy models.
- Added startup hydration and lazy schema initialization for direct agent/test execution paths.
- Added `tenant_id` and `owner_id` to the deal model and enforced tenant filtering in deal, document, run, and output access.
- Added JWT validation, claim extraction, dev-token bootstrap, and propagated JWT usage to the frontend API client.
- Added review-event persistence for auditability of output approvals.
- Added reviewer-role enforcement so only reviewer/admin users can approve outputs.

### Still Missing
- Move from local SQLite defaults to managed PostgreSQL with migrations.
- Encrypt sensitive fields and introduce secrets/key-management patterns.
- Add organization/user provisioning and session management.
- Integrate production OIDC/JWKS identity providers instead of the local HS256/dev bootstrap mode.

### Remaining File-Level Work
- `apps/api/src/dependencies.py`: Integrate production OIDC/JWKS identity providers and richer claim mapping.
- `apps/api/src/database.py`: Introduce environment-specific engine settings and migration tooling.
- `apps/api/src/routers/outputs.py`: Extend from approval gating into richer publication/version governance.

## Phase 2: Ingestion And Asynchronous Execution
**Goal:** Decouple agent workloads from HTTP, make ingestion safe, and provide a reliable long-running execution experience.

### Completed
- Document uploads now persist immediately, parse in a background thread pool, and update status in both DB and API views.
- The modeling run endpoint now returns `202 Accepted` and supports polling by run ID.
- The frontend now polls run status and blocks execution until all uploaded documents report `parse_status="parsed"`.
- The agent base layer now persists runs safely even when used outside app startup.
- Silent LLM fallback behavior has been restricted to explicit failure instead of fabricated defaults.

### Still Missing
- Replace in-process thread pools with a real worker system such as Celery, RQ, or Temporal.
- Add cancel, retry, resume, timeout policy, and dead-letter handling for failed jobs.
- Add malware scanning, document quarantine, and retention/cleanup jobs for uploads.
- Move document and output storage from local disk to object storage such as S3 or Azure Blob Storage.
- Add richer execution progress events beyond coarse status polling.

### Remaining File-Level Work
- `apps/api/src/routers/agents.py`: Hand off background work to an external queue and support cancellation/retry endpoints.
- `apps/api/src/routers/documents.py`: Add malware scanning, storage abstraction, and parse-failure retry semantics.
- `apps/web/src/components/workspace/AgentsTab.tsx`: Surface richer progress states, retry controls, and queue diagnostics.

## Phase 3: Valuation Intelligence, Governance, And Operations
**Goal:** Upgrade the system from a technically functioning valuation runner into an institutional-grade financial operations platform.

### Completed
- Deterministic spreadsheet extraction is now used for supported financial workbooks.
- Sector-specific routing now adjusts assumptions for IT-services profiles.
- Mid-year discounting is now implemented in the DCF engine.
- Market-sanity warning metadata is now generated when optional market-cap or share-price inputs are provided.
- Outputs now require an approval state before download.

### Still Missing
- Integrate live market data for market cap, share price, debt, cash, and current peer multiples.
- Turn the current market-sanity warning into a true critic loop that can block or re-route obviously broken valuations.
- Add explicit published/draft/version workflows with immutable approval history views in the UI.
- Add structured telemetry, trace IDs, prompt/model version tracking, and operational alerting.
- Add benchmark datasets, sector coverage expansion, and regression packs for multiple company archetypes beyond IT services.

### Remaining File-Level Work
- `apps/api/src/engine/comps.py`: Replace static comps assumptions with live or cached market data feeds.
- `apps/api/src/agents/modeling.py`: Add critic-loop escalation, market-data reconciliation, and stronger block conditions.
- `apps/api/src/routers/outputs.py`: Add published/versioned output workflows and review-history retrieval APIs.
- `apps/api/src/main.py`: Introduce structured logging and request/run trace correlation.

## Recommended Next Delivery Order
1. Move uploads and outputs to object storage and add malware scanning.
2. Replace the in-process thread pools with a real background worker queue.
3. Integrate live market data and upgrade the market-sanity warning into a blocking critic loop.
4. Add tracing, metrics, prompt/model versioning, and alerting.
5. Swap the local/dev JWT mode for production OIDC provisioning and org/user lifecycle management.

## Verification Completed In This Pass
- `pytest apps/api/src/test_auth_security.py -q`
- `pytest apps/api/src/test_document_parser_quality.py apps/api/src/test_extraction_checkpoint.py apps/api/src/test_sector_routing.py apps/api/src/test_orchestrator_routing.py apps/api/src/test_dcf_monte_carlo.py apps/api/src/test_financial_statement_analyzer.py apps/api/src/test_triangulator.py -q`
- `python -m compileall apps/api/src`
- `npm run build` in `apps/web`

## Notes
- The platform is now materially stronger than the original prototype, but it is not yet fully enterprise-ready.
- The largest remaining gaps are identity/authorization maturity, externalized job infrastructure, object storage, and live market-data-backed validation.
