# Submission drafts

These describe the implemented core at the snapshot. Codex must revise them to the final tested state. Add the board paragraph **only if P1 is implemented and verified**. Delete drafting instructions from the actual submission.

## Title

AIBAA Deal Intelligence — SerpApi-powered company research

## Short description

AIBAA helps analysts gather public company, transaction and news evidence inside a deal workspace. SerpApi Google Search and Google News power a bounded research workflow with source citations, visible coverage and reviewable exports.

## Longer description

Preparing an early company brief requires moving between filings, industry searches, transaction announcements and news. AIBAA brings this discovery work into an existing investment banking analyst workspace.

The new workflow uses SerpApi Google Search and Google News to collect focused public evidence. It normalizes source links, excerpts and provenance, distinguishes complete, partial and empty coverage, and preserves a saved research run. Analysts can inspect citations, save run-specific observations and open questions on an Analyst Review Board, and generate PDF/JSON research handoffs and a public diligence Excel checklist through the workspace's approval workflow.

SerpApi supplies the core discovery evidence. The source-only workflow works without an LLM; optional AI interpretation is separate and remains subject to analyst review. Search excerpts are investigation leads, not verified financial inputs or an automatic diligence verdict.

This hackathon entry extends an existing project. The repository documents the pre-existing workspace, the new search integration, setup, tests and limitations.

The Analyst Review Board turns cited sources into observations, open questions and next actions. Review notes and statuses persist with the research run, and a new export preserves their snapshot without overwriting an earlier approved artifact.

## Existing-project disclosure

The baseline already contained FastAPI/React deal and document management, authentication/review controls, DCF/LBO engines, spreadsheet generation and LLM analyst agents.

The hackathon contribution adds SerpApi Search/News orchestration, normalized evidence and citations, coverage/cache/failure handling, research and public diligence discovery, source-review UI, saved runs, a persistent cited Analyst Review Board, immutable versioned board snapshots, cited PDF/JSON/XLSX outputs and explicit demo mode. It also fixes targeted modeling persistence, repeat-output filenames, setup/proxy issues and dependency compatibility, with regression checks and CI.

Use final commits/PR history as evidence; do not invent dates or pretend the entire baseline was built during the hackathon.

## AI-tool disclosure draft

ChatGPT/Codex assisted with planning, implementation, debugging, tests and documentation for the new integration and final optimization. The project also supports optional Gemini/NVIDIA runtime synthesis; specify which provider was actually used in the demonstrated workflow, or state that the demonstration used source-only research.

Edit this to reflect actual assistance and your participation. Do not claim an optional provider was used simply because its configuration exists.

## Technical usage explanation

The backend sends focused public-company discovery queries to SerpApi's `google` and `google_news` engines. Results become normalized sources with IDs, URLs, excerpts and provenance. Query coverage, bounded retries/concurrency, caching and visible errors support a repeatable research workflow. The outputs and diligence checklist depend on this evidence, making SerpApi a core product component.

The integration uses the existing HTTP-client approach; do not claim an SDK, Google Finance engine, full-page crawler, or live financial data feed unless the final code genuinely adds and verifies it.

## Useful reviewer answers

| Question | Honest answer |
| --- | --- |
| Why this track? | Company and transaction discovery is a market-intelligence task for analysts. |
| Why SerpApi? | Search and news supply the current public evidence used by the research workflow. |
| Is an LLM required? | No for source-only research; optional synthesis requires its own provider setup. |
| Are these live financial comps? | No. Existing preset sector multiples are illustrative assumptions. |
| Does a citation prove the claim? | It identifies the discovery source; the analyst still checks relevance and support. |
| Is buyer interest confirmed? | No. Buyer Discovery identifies public transaction mentions and investigation leads. |
| Is this production-scale? | The demonstration uses a single-process job/cache design. |
| Was the project pre-existing? | Yes; the contribution section and git history separate new work. |
| Did live testing pass? | Replace with the actual validation outcome, account-free evidence and date. |

## Final-copy gate

Remove unsupported features, placeholder results, unmeasured speed claims and "guaranteed winner" language. Ensure the submitted repository revision, recorded UI, described features and setup commands match.
