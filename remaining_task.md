# AIBAA — Remaining Tasks Roadmap

> Status as of 2026-06-10, branch `fix/code-review-remediation`.
> This document describes everything left to build for AIBAA to fully cover the
> backend role of an investment banking analyst, in recommended build order.

---

## Current State (what is already done)

The core sell-side analyst workflow is complete and verified:

| Capability | Route | Status |
|---|---|---|
| DCF valuation (extract → audit → triangulate → validate) | `modeling/dcf_model` | ✅ Done |
| LBO model (IRR / MoIC, sources & uses, debt schedule) | `modeling/lbo_model` | ✅ Done |
| Trading comps + precedent transactions | `comps/comps_analysis` | ✅ Done (multiples are LLM-estimated — see Task 1) |
| Merger model (accretion/dilution, deterministic math) | `merger_model/accretion_dilution` | ✅ Done |
| Due diligence risk report + checklist | `due_diligence/dd_report` | ✅ Done |
| Industry brief + buyer universe | `research/industry_brief`, `research/buyer_universe` | ✅ Done |
| CIM drafting | `doc_drafter/cim_draft` | ✅ Done |
| Investment Committee memo (PDF) | `memo_writer/investment_memo` | ✅ Done |
| Pitchbook (PDF) | `pitchbook/generate_pitchbook` | ✅ Done |
| Meeting notes → tasks | `coordination/extract_tasks` | ✅ Done |
| **Autonomous full deal package** (chains all 8 workstreams) | `autopilot/full_deal_package` | ✅ Done |
| Dual LLM providers with automatic failover (Gemini ⇄ NVIDIA NIM / Kimi K2.6) | `engine/llm.py` + model registry | ✅ Done |

### Outstanding security action (do this first, takes 10 minutes)

`apps/api/.env` was previously committed to git with **real API keys** (Gemini,
NVIDIA, TinyFish). The file is now untracked, but the keys remain in git
history (commits `e4ce50c`, `1ad6d8e`).

- [ ] Rotate `GEMINI_API_KEY` at https://aistudio.google.com
- [ ] Rotate `NVIDIA_API_KEY` at https://build.nvidia.com (including the key pasted in chat)
- [ ] Rotate `TINYFISH_API_KEY` at https://agent.tinyfish.ai/api-keys
- [ ] Commit the staged `.env` removal (`git rm --cached` is already staged)
- [ ] If the repo ever goes public, rewrite history first (`git filter-repo --path apps/api/.env --invert-paths`)

---

## Task 1 — Live Market Data → Comps Engine

**Effort:** 1–2 days · **Priority:** Highest (biggest quality jump per hour spent)

### Problem
Comps multiples are currently LLM-estimated and flagged as placeholders. A real
desk pulls EV/EBITDA from live market data. The hook already exists:
`ComparableAnalysisEngine.build_comps_snapshot()` in `apps/api/src/engine/comps.py`
accepts `live_market_data["sector_multiples"]` and prefers it over hardcoded
sector bands — nothing feeds it real data yet.

### Build
1. **New file** `apps/api/src/tools/market_data.py`:
   - `MarketDataClient` with `get_peer_multiples(tickers: list[str]) -> dict`
   - For each ticker: fetch market cap, total debt, cash, EBITDA (TTM) →
     compute `EV = mcap + debt − cash`, `EV/EBITDA`, `EV/Revenue`, `P/E`.
   - In-process cache with TTL (copy the `_LLM_RESPONSE_CACHE` pattern from
     `engine/llm.py`).
   - Graceful degradation: any failure returns `{}` so comps falls back to
     LLM-estimated values (same pattern as `wm_client` / `web_agent`).

2. **Data source options:**
   - **Prototype:** `yfinance` (free, no API key, supports NSE via `RELIANCE.NS`
     suffix). Add `yfinance>=0.2.40` to `requirements.txt`.
   - **Production:** Financial Modeling Prep or Alpha Vantage (free tiers, real
     API contracts). Key goes in `apps/api/.env` as `MARKET_DATA_API_KEY`,
     placeholder in `.env.example`.

3. **Wire into** `apps/api/src/agents/comps.py` (`ValuationCompsAgent.run`):
   - After the LLM returns its peer set, collect `ticker` fields from
     `trading_comps`.
   - Call `MarketDataClient.get_peer_multiples(tickers)`.
   - Replace each peer's estimated `ev_ebitda` / `ev_revenue` / `pe` with live
     values where available; mark `"source": "live"` vs `"source": "estimate"`
     per peer.
   - Derive `recommended_multiple_band` from the **actual peer distribution**
     (25th percentile = bear, median = base, 75th = bull) instead of LLM
     judgment when ≥4 live peers resolve.
   - Pass the live band into `_build_deterministic_snapshot` (already supported).

4. **Excel:** add a "Source" column (LIVE / ESTIMATE) to the Trading Comps tab
   in `WorkbookBuilder.write_comps_analysis`.

### Acceptance
- Run comps on a deal with Indian listed peers → workbook shows live multiples
  with source column; band derived from peer quartiles; agent reasoning log
  shows how many tickers resolved live.

---

## Task 2 — Football Field Valuation Summary

**Effort:** ~1 day · **Priority:** High (the signature banker exhibit)

### Problem
DCF, comps, precedents, and LBO each produce a value range, but no exhibit
combines them into the classic horizontal range-bar "football field".

### Build
1. **New file** `apps/api/src/tools/football_field.py`:
   - `collect_valuation_ranges(deal_id) -> list[dict]` — reads the latest
     completed run per method from `store.agent_runs`:
     - DCF: bear/base/bull equity values from `valuation_result`
     - Comps: `comps_result.deterministic_snapshot.scenarios`
     - Precedents: apply transaction multiple range × EBITDA
     - LBO: implied entry valuation as the floor
   - `render_football_field(ranges, path)` — horizontal bar chart. Two options:
     - **reportlab `Drawing` + `HorizontalBarChart`** (no new dependency), or
     - matplotlib → PNG (`matplotlib` is pulled in transitively; verify, else add).
   - Draw a vertical dashed line for current market cap if
     `parameters.current_market_cap` was provided.

2. **Expose** as a new task `memo_writer/football_field` (add to
   `AGENT_DISPATCH_MAP`, orchestrator `SUPPORTED_ROUTES`, frontend
   `AGENT_CONFIGS`) **and** embed the image automatically into:
   - the IC memo PDF (`agents/memo.py::_write_pdf`, after "Valuation View")
   - the pitchbook valuation section (`agents/pitchbook.py::_write_pdf`)

3. **Autopilot:** append `football_field` as step 9 in
   `agents/deal_pipeline.py::_build_pipeline_steps` (after the memo, all
   methods have run by then).

### Acceptance
- After an autopilot run, the IC memo contains a football field with 3–4
  method bars and the recommended range highlighted.

---

## Task 3 — Maker-Checker Review Gates

**Effort:** 2–3 days · **Priority:** High (mandatory before any real-world use)

### Problem
All outputs are drafts with confidence scores, but nothing enforces human
approval before an output is treated as final. The scaffolding exists:
outputs are created with `review_status="draft"` and reviewer roles are
defined (`AIBAA_REVIEWER_ROLES=reviewer,admin` in `.env`).

### Build
1. **Backend** (`apps/api/src/routers/outputs.py`):
   - `PATCH /outputs/{output_id}/review` with body
     `{ "decision": "approved" | "rejected" | "needs_changes", "comment": str }`.
   - Guard with a reviewer-role dependency (pattern exists in
     `dependencies.py`; check `current_user["role"]` against
     `AIBAA_REVIEWER_ROLES`).
   - Record `reviewed_by`, `reviewed_at`, `review_comment` on the output row
     (add columns to `OutputModel` in `db_models.py` + Alembic migration).
   - **Download gating:** in the download endpoint, if
     `review_status != "approved"`, stamp "DRAFT — NOT REVIEWED" (PDF: overlay
     via reportlab; Excel: header row note) or return 403 behind a
     `AIBAA_STRICT_REVIEW_GATE=true` flag.

2. **Frontend** (`apps/web/src`):
   - New "Review Queue" tab: lists draft outputs across deals with agent
     confidence score, validator status (`validator_report` is already on the
     run record), and Approve / Reject / Needs-Changes buttons with a comment box.
   - Output list badges: DRAFT (grey) / APPROVED (green) / REJECTED (red).

3. **Autopilot checkpoint (optional flag):**
   `parameters.review_checkpoint=true` → pipeline pauses after valuation steps
   (DCF, comps) with status `awaiting_review`; a reviewer approval resumes
   document generation. Implement by persisting remaining steps in the
   pipeline run payload and adding a `POST /agents/runs/{run_id}/resume`
   endpoint.

### Acceptance
- An analyst-role user cannot approve outputs; a reviewer can; unapproved PDFs
  download with a DRAFT watermark; audit fields populated.

---

## Task 4 — Teaser + Deal Process Tracking

**Effort:** 2–3 days · **Priority:** Medium

### 4a. Anonymized Teaser (one-pager)
1. New task `doc_drafter/teaser_draft` on the existing `DocDrafterAgent`:
   - Prompt constraints (add `build_teaser_prompt` to `PromptBuilder`):
     **no company name** (use a project codename from
     `parameters.project_codename`, default "Project <random bird/mountain>"),
     rounded financials ("revenue of approximately ₹2,800 Cr"), no customer
     names, no exact locations.
   - One-page PDF: investment highlights (5–6 bullets), financial snapshot
     table (rounded), transaction overview, banker contact block. Reuse the
     memo agent's reportlab styling.
2. Register in dispatch map / orchestrator / frontend catalog
   (aliases: `teaser`, `one_pager`, `blind_profile`).

### 4b. Deal Stage & Process Tracking
1. Add `deal_stage` to `DealModel` + Pydantic schemas:
   `origination → teaser → nda → cim → ioi → management_meetings → loi → diligence → close`.
2. `PATCH /deals/{deal_id}` accepts stage transitions (validate ordering;
   allow skip-forward with a `force` flag).
3. New task `coordination/process_status`: reads outputs, tasks, and stage →
   returns "what is blocking the next stage" (e.g. "CIM drafted but not
   approved; 3 DD red flags unresolved").
4. Buyer outreach tracking: extend the buyer-universe JSON with a
   `outreach_status` field per buyer (`not_contacted / teaser_sent / nda_signed
   / cim_sent / ioi_received / passed`) editable via
   `PATCH /deals/{deal_id}/buyers/{buyer_idx}` and shown as a kanban-style
   board in the frontend.

### Acceptance
- Teaser PDF contains zero occurrences of the real company name; deal page
  shows a stage pipeline with the current stage and blockers.

---

## Task 5 — Linked 3-Statement Operating Model

**Effort:** 1–2 weeks · **Priority:** Deepest build — do last unless modeling
fidelity is the demo centerpiece

### Problem
DCF projects revenue → EBITDA → FCF directly. A banker-grade model links a
full income statement, balance sheet, and cash flow statement with working
capital and debt schedules, and the balance sheet must balance every year.

### Build
1. **Extraction upgrades** (`PromptBuilder.build_preparer_prompt`): add fields
   the engine needs — receivables, payables, inventory (→ DSO/DPO/DIO),
   gross PP&E, depreciation schedule basis, interest income/expense split,
   dividend payout ratio, scheduled debt repayments.

2. **New engine** `apps/api/src/engine/three_statement.py` — deterministic,
   no LLM math (same philosophy as the merger model):
   - **Income statement:** revenue (reuse DCF growth logic incl. run-rate
     anchoring) → EBITDA → D&A (% of opening gross PP&E) → EBIT → interest
     (from debt schedule, circularity resolved by iterating 3–5 passes or
     using opening balances) → PBT → tax → PAT.
   - **Working capital schedule:** AR = revenue × DSO/365, AP = COGS × DPO/365,
     inventory = COGS × DIO/365; ΔNWC flows to cash flow.
   - **Debt schedule:** opening debt, scheduled amortization, **revolver plug**
     (draws when cash < minimum, sweeps when above) — this is what makes the
     balance sheet balance.
   - **Balance sheet + CF statement** derived from the above; assert
     `abs(assets − liabilities − equity) < 1` rupee every projected year.

3. **Excel output** `WorkbookBuilder.write_three_statement_model`:
   - Tabs: Assumptions / IS / BS / CF / Debt Schedule / DCF.
   - Write **real Excel formulas as strings** (e.g.
     `ws["C10"] = "=C8*Assumptions!$B$4"`), not just values — so an analyst
     can flex an assumption in Excel and the model recalculates. This is the
     difference between an AI artifact and a model a banker will open.
   - Follow house style already in `WorkbookBuilder`: blue = formula,
     black = hardcode, green = historical actual.

4. **Integration:**
   - New task `modeling/three_statement_model` → dispatch map, orchestrator,
     frontend.
   - Swap the DCF engine's FCF source to the 3-statement output when one
     exists for the deal (one function: pull FCF series from the latest
     `three_statement_result` payload).
   - Insert into autopilot between DCF and comps.

### Acceptance
- Balance sheet ties (assets = liabilities + equity) in every projection year;
  changing terminal growth in the Excel Assumptions tab visibly recalculates
  the DCF tab; revolver draws/sweeps behave correctly in a stress case
  (force Year-2 EBITDA negative and confirm the revolver draws).

---

## Recommended Build Order

```
Security key rotation  (10 min — do immediately)
        │
Task 1  Live comps data        1–2 days   ┐ quality jump,
Task 2  Football field         ~1 day     ┘ small effort
        │
Task 3  Review gates           2–3 days   ← mandatory before real use
        │
Task 4  Teaser + process       2–3 days
        │
Task 5  3-statement model      1–2 weeks  ← deepest build
```

Total: roughly 3–4 weeks of focused work to a genuinely production-shaped
platform.

## Cross-Cutting Notes

- **Pattern to follow for every new agent/task:** agent class extending
  `BaseAgent` → system prompt + builder in `prompt_builder.py` →
  `AGENT_DISPATCH_MAP` in `routers/agents.py` → `SUPPORTED_ROUTES` +
  aliases in `orchestrator.py` → `AGENT_CONFIGS` in
  `apps/web/src/components/workspace/AgentsTab.tsx` → optional autopilot step.
- **LLM usage rule:** LLMs extract and write prose; **all financial math is
  deterministic Python** (see `merger_model.py::_compute_accretion_dilution`
  as the reference pattern).
- **Secrets rule:** keys live only in `apps/api/.env` (gitignored);
  placeholders in `.env.example`; never in code, logs, or chat.
- **Failover:** any new external client should degrade gracefully and return
  empty results on failure (see `wm_client` / `web_agent` patterns) so agents
  always complete with document-only analysis.
