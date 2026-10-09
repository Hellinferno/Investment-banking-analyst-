# Hackathon implementation and demo

## Project positioning

AIBAA: source-backed company intelligence for investment banking analysts.

Problem: preparing a company brief means switching between filings, news, industry searches, and working files. The new workflow gathers public discovery evidence, exposes its coverage and citations, and produces reviewable research and diligence artifacts inside the existing deal workspace.

The strongest submission story is the complete research workflow. Keep DCF/LBO as supporting context; do not describe search snippets as verified financial inputs or the preset sector multiples as live market comps.

## Existing work disclosure

This is an existing repository. The pre-hackathon baseline contains deal/document management, FastAPI/React, authentication and review controls, DCF/LBO engines, spreadsheet generation, and LLM-based analyst agents.

The hackathon contribution adds:
- SerpApi Google Search / Google News client and bounded search plan.
- Normalized evidence, provenance, citations, coverage, caching, and safe failure handling.
- Reworked research and public diligence discovery agents.
- Source review/filtering UI, search settings, explicit demo mode, and saved-run restoration.
- Persistent run-specific Analyst Review Board for cited observations, questions, review statuses, and next actions.
- Immutable versioned PDF/JSON board snapshots that preserve linked source context.
- Cited PDF/JSON exports and a diligence Excel checklist.
- DCF result/checkpoint persistence fix, distinct filenames for repeat exports, explicit comps labels, shared runtime paths, setup/proxy fixes, regression checks, and CI.

The old LLM-only research and risk-scoring diligence flows are replaced by public-source discovery and analyst review. Other existing agents remain separate workflows.

Use the change branch/PR to substantiate the contribution. Check the organizer's current rules and exact track selection before submitting; this file is not an eligibility confirmation.

## Local rehearsal

1. Follow the root README and start both services.
2. Use demo mode only for an offline rehearsal; synthetic labels must stay visible.
3. For the recorded submission, configure SERPAPI_API_KEY and AIBAA_RESEARCH_MODE=live; restart the API.
4. Create a deal for a public company, using its public name and industry.
5. Start Company Intelligence without an LLM key first. This makes the SerpApi contribution easy to demonstrate.
6. Verify real source links, dates, search IDs, and useful coverage before recording.
7. Rehearse Diligence Discovery and approval/download of each export.

Optional AI interpretation can be shown after the source-only workflow works. Never hide partial search coverage or claim that source-ID validation proves every AI statement is true.

## Demo sequence: under three minutes

| Time | Show | Explain |
| --- | --- | --- |
| 0:00-0:20 | Deal workspace | Analysts need a traceable company brief, not disconnected search tabs |
| 0:20-0:50 | Company Intelligence settings and a live run | Four focused Google Search/News queries; public metadata only |
| 0:50-1:25 | Coverage, source links, excerpts, citation jumps/filter | View where observations came from and which queries were incomplete |
| 1:25-1:55 | Analyst Review Board | Save a cited open question, next action, and analyst review status |
| 1:55-2:20 | Diligence Discovery | Source-linked checklist for human investigation; no invented risk score |
| 2:20-2:45 | Outputs, approve, PDF/JSON/XLSX | Versioned artifacts preserve the reviewed source context |
| 2:40-2:55 | Existing DCF/LBO context and contribution disclosure | New search-backed intelligence extends the existing analyst workspace |

For predictable timing, rehearse the same public company first and disclose when a response is cached. Do not present an offline fixture as a live search.

## Validation and remaining checks

Automated tests use mocked SerpApi and explicit offline modeling fixtures, with keys disabled. They cover retries, quota/authentication errors, caching, nested news, source handling, partial/empty results, citation validation, exports, persistence, access controls, and historical financial regressions. Frontend TypeScript/build and ESLint checks are included.

Before submission, still complete:
- A real SerpApi run using your account, and a real LLM run if demonstrating synthesis.
- A browser walkthrough at desktop and narrow widths, including refresh/resume and output approval.
- Docker Compose build/run if using containers for the presentation.
- A recording within the organizer's limit and the required submission fields/links.
- Current event rules, eligibility, track, deadline, and public-repository requirements.

Known scope: discovery excerpts rather than full-page verification; no live stock-price feed or sourced financial comparable calculations; single-process background jobs; no auto-refresh monitoring or cancellation. No hackathon submission or public deployment is performed by these changes.
