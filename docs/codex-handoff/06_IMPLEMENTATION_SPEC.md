# Engineering specification

This specification describes **proposed changes**, not completed features. Inspect the existing types, database facade, routes and components before choosing the smallest compatible implementation. Use additive changes and current conventions.

## A. P0: close the full workflow

### Company identity and research settings

Show the entered public company name, industry, optional official domain and search country near the results. The existing optional domain is a DNS name, not an arbitrary URL. Preserve validation and do not add a scraper.

A domain filter improves targeting; it does not verify company identity. Let the analyst inspect likely matches. Don't automatically discard every third-party source merely because it differs from the official domain. Include identity ambiguity in open questions when appropriate.

### Research states

Maintain distinct queued/running/completed/failed job states and the existing coverage semantics. A completed job can have partial or empty coverage. Empty success is not provider failure. Display individual query failures and useful next steps.

Separate publication dates from retrieval timestamps. Undated material remains undated. Display explicit demo labels throughout UI/export. For reused data, display the existing cache indication honestly.

Ensure citations remain usable after source filtering: resolve the source and reveal it, or explain why the current filter hides it. Refresh must restore the saved run. Disable accidental duplicate launches and keep errors recoverable.

### Existing safeguards

Do not loosen backend-only keys, public-metadata-only search, tenant authorization, role restrictions, output approval or export filename uniqueness. Search excerpts are untrusted content, including when sent to an optional LLM.

Preserve the four-query plan, maximum two concurrent provider calls, limited retry/attempt budget and timeout. Current defaults are a 30-minute process-local cache, at most eight normalized sources per query, and up to 32 unique sources per run. Check actual constants instead of duplicating them in the UI.

Performance improvements should target observed delay or redundant calls. Report measured time/results when available; do not create unsupported performance claims.

## B. P1: persistent Analyst Review Board

### User behavior

- Add an observation or open question from a research source, or manually link one or more existing source IDs.
- Enter a short title, a concise note, and an optional next action.
- Set one of three statuses: `unreviewed`, `reviewed`, `needs_follow_up`.
- Edit or remove the user's review item with a clear interaction.
- Refresh and see the same review state for that exact saved research run.
- Export a research handoff including the reviewed items and their source references.

No automatic risk score, recommendation, or "fact verified" badge. Show that reviewed means analyst review, not independently verified truth. Initial AI-suggested items, if implemented through existing synthesis, are unreviewed and their citation IDs must be validated.

### Proposed record

Adapt to existing storage rather than adding a new datastore:

| Field | Constraint |
| --- | --- |
| `id` | Stable server-generated identifier |
| `research_run_id` | Existing saved-run identity; do not use only company name |
| `kind` | Observation or question |
| `title` | Required, trimmed, max 160 characters |
| `note` | Plain text, max 2,000 characters |
| `next_action` | Optional plain text, max 500 characters |
| `source_ids` | 1–8 distinct IDs, all belonging to that run |
| `status` | One of the three allowed values |
| `updated_at` | Server timestamp |
| `updated_by` | Authenticated user identity from server context |

Derive tenant/deal ownership from the authenticated request and existing run. Never trust a tenant or editor ID submitted by the client. Bound items to at most 30 per run. Empty state explains how to add a cited item; no fabricated default observations.

### Persistence and API

Read `routers/research.py` and the existing saved payload/state storage first. Use the current persistence mechanism if practical. Returned store dataclasses may be detached; explicit update methods are required. Inspect the DCF persistence fix as a cautionary example.

Add authenticated run-scoped read/create/update/delete operations only as necessary. Follow existing role semantics: use the same reviewer/admin authorization helpers for mutating review actions, and existing deal access controls for reads. Keep review status independent of output approval. Validate source membership server-side. Use existing error formats.

If a new table is genuinely needed, provide an additive Alembic migration and verify it on a fresh database and an existing database. Do not redesign authentication or the database. Reject invalid/oversized payloads; render notes as escaped plain text.

### UI

Extend `ResearchResultsView.tsx` or a small extracted component. Reuse existing controls. Show title, status, source chips/links, note and next action with readable hierarchy.

Use optimistic updates only with rollback/error feedback, or a simple confirmed-save interaction. Clear unsaved/saved status; prevent cross-run edits after changing the selected run. Support keyboard navigation and narrow layouts. A new research run keeps its own board; old boards stay attached to old evidence.

### Exports and immutability

The handoff includes the board snapshot, analyst review status, source IDs/URLs, run identity, coverage, retrieval/publication context and export time. Preserve explicit live/demo and discovery limitations.

Create a **new output version** when exporting changed review notes. An already approved output must keep the same file bytes; never modify its PDF or JSON in place. Newly generated outputs go through the existing approval workflow. The board does not bypass review/download permissions.

Minimum P1 export support: research PDF and JSON. Keep existing diligence XLSX working. Extend XLSX only if it is relevant and within budget; do not delay the main flow to force every export to contain every field.

Reuse current PDF font support and page-layout conventions. Escape formula-like analyst text in any spreadsheet output. Do not expose private notes to the SerpApi search request.

### Acceptance tests for P1

A reviewer can create an item citing a real saved source, change its status, reload, and see the persisted record. A different tenant cannot read or edit it. Unknown source IDs and long payloads fail cleanly. A subsequent run does not inherit old items. Exported review text and source references match the saved snapshot. Re-export produces a new file and leaves the earlier approved bytes unchanged.

## C. Implementation order and files

| Order | Work | Likely files |
| --- | --- | --- |
| 1 | Audit existing state and source payload | research evidence/client, research router, agents |
| 2 | Minimal validated review persistence/API | research router and current store/models; migration only if needed |
| 3 | Board and source interaction | ResearchResultsView, web API client |
| 4 | Versioned snapshot export | research_export, outputs integration |
| 5 | Behavioral regressions | research workflow/export/auth tests |
| 6 | Final setup/product docs | README, SERPAPI.md, HACKATHON.md |

This is a navigation guide, not permission to edit unrelated files. Keep the queue, valuation engines and unrelated agents stable unless an observed defect requires a targeted fix.
