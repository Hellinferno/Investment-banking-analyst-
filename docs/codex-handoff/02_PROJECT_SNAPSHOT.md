# Project snapshot — verify before editing

Snapshot date: 8 October 2026. This describes the previously completed implementation, not work newly executed by this ZIP.

## Repository state

| Item | Snapshot |
| --- | --- |
| Repository | https://github.com/Hellinferno/Investment-banking-analyst- |
| Feature branch | `feat/serpapi-market-intelligence` |
| Draft PR | https://github.com/Hellinferno/Investment-banking-analyst-/pull/1 |
| Remote feature head | `62d3eb50eef2a8cee8f865705620797872e03227` |
| Main baseline | `c94c053b52221970c7400901a3ce049f55e5529b` |
| Implemented file tree | `c44866ba7bd909eb9bcbd29d3b67705a4509e771` |
| Merge state | Draft, unmerged at snapshot |

A previous local checkout used HEAD `5ce866122ea69c7f7f6bbcdb8d48106fd940ef46` with the same file tree; commit metadata differed. Use the remote branch as the transferable starting point. Do not assume main already contains the integration.

## Already implemented

- Existing FastAPI/React deal and document workspace, authentication, tenant boundaries, reviewer approval, DCF/LBO and spreadsheet generation.
- Backend SerpApi Google Search and Google News using the fixed search endpoint. Four planned queries per run cover filings, industry/peers, transactions or diligence topics, and news.
- Bounded concurrency, request timeout, limited retries, process-local response cache, normalized source IDs and URLs, date/retrieval provenance, deduplication, and visible complete/partial/empty coverage.
- Company Intelligence, Buyer Discovery, and public Diligence Discovery backed by the new evidence workflow.
- Optional Gemini/NVIDIA synthesis with structured output and citation-ID checks; source-only fallback remains usable.
- PDF/JSON exports and a diligence XLSX checklist, source citations, spreadsheet formula escaping, and distinct filenames per run.
- Frontend research settings, source filtering/citation links, coverage badges, polling, and restoration of the latest saved run.
- Explicit synthetic `demo` mode. No silent conversion of a failed live run into demo data.
- Bounded background job queue, single running job per deal, interrupted-job handling on restart.
- Modeling checkpoint/DCF persistence fixes, illustrative comps labels, consistent environment/data paths, Docker proxy fixes, CI.
- Dependency repair: `pandas>=2.2,<3` matches the existing LlamaIndex file-reader constraints.

## Evidence already recorded

| Check | Previous result | Meaning |
| --- | --- | --- |
| Backend tests | 60 passed | Mocked providers and controlled offline fixtures |
| Frontend lint/build | Passed | ESLint, TypeScript and Vite compilation |
| GitHub clean install/CI | Passed at remote feature head | Dependency installation reproduced in CI |
| API + worker smoke | Passed in explicit demo mode | Research/diligence and five export approval/download paths |
| PDF long-fixture inspection | All 7 pages inspected | Synthetic long content rendered without observed layout breakage |
| SQLite migration | Alembic upgrade passed | Local database setup checked |

CI links:
- https://github.com/Hellinferno/Investment-banking-analyst-/actions/runs/37807810790
- https://github.com/Hellinferno/Investment-banking-analyst-/actions/runs/37807804105

These are baseline results. Rerun relevant checks after your changes.

## Still unverified

Real SerpApi account/key and results; optional live LLM synthesis; an actual browser walkthrough; Docker build/run; hosted deployment; demo recording; final submission. There was no live provider key available in the earlier work. Do not claim those checks passed.

## Implementation map

| Area | Read first |
| --- | --- |
| Setup/contribution | `README.md`, `docs/SERPAPI.md`, `docs/HACKATHON.md`, `.env.example` |
| Provider/bounded calls | `apps/api/src/tools/serpapi_client.py` |
| Sources/provenance | `apps/api/src/tools/research_evidence.py` |
| Export generation | `apps/api/src/tools/research_export.py` |
| Research/diligence agents | `apps/api/src/agents/research.py`, `due_diligence.py` |
| Agent state/persistence | `apps/api/src/agents/base.py`, `modeling.py` |
| API routes | `apps/api/src/routers/agents.py`, `research.py`, `outputs.py` |
| Research interface | `apps/web/src/components/workspace/AgentsTab.tsx`, `ResearchResultsView.tsx` |
| Web API client | `apps/web/src/lib/api.ts` |
| Tests/CI | `apps/api/tests/test_research*.py`, `test_modeling_regressions.py`, `conftest.py`, `pytest.ini`, `.github/workflows/ci.yml` |

## Boundaries worth preserving

Research sends public company name/industry to search, not private deal notes or uploaded documents. Other older agents can send documents to their configured LLM: do not make a blanket privacy claim about the entire app.

Discovery excerpts are not full-page verification, real-time market prices, audited financial inputs, or proven buyer interest. Diligence gives investigation questions, not a reliable risk score. Citation-ID validation is structural, not semantic fact checking.

Jobs and the 30-minute/128-entry search cache are process-local. The intended demonstration is a single API process. Do not scale to multiple workers or add distributed infrastructure during the final sprint.
