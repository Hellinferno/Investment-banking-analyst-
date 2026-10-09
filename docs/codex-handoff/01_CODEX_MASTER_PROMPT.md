# Master prompt

Copy everything between START PROMPT and END PROMPT into Codex. Keep this folder available in the project.

START PROMPT

Please finish and optimize my investment banking analyst project for the SerpApi India Hackathon 2026. Execute the work, not just another plan. I am new to Codex; make routine implementation decisions yourself and explain only the decisions I need to understand.

Repository: https://github.com/Hellinferno/Investment-banking-analyst-
Existing branch: feat/serpapi-market-intelligence
Existing draft PR: https://github.com/Hellinferno/Investment-banking-analyst-/pull/1
Handoff: docs/codex-handoff/ (or locate the extracted serpapi-codex-handoff folder)
Track recommendation: Commerce & Market Intelligence
Deadline snapshot: 10 October 2026, 23:59 IST; internal submission target 20:00 IST.

First read the repository's applicable AGENTS.md instructions and all numbered handoff Markdown files. Inspect the actual checkout, branch, uncommitted changes, PR state, setup docs, and current tests. The snapshot is evidence from a previous session, not a substitute for checking current code. Preserve my uncommitted work. Do not reset the repository or blindly replace root instructions.

Continue the existing SerpApi implementation. It already has Google Search/News, cited research and diligence exports, explicit demo mode, coverage/error handling, and regression tests. Do not rebuild these features. If PR #1 has been merged, work from the updated main. Otherwise work from the current feature branch in a separate review branch or worktree as appropriate; never lose its changes.

Follow this order:
1. Reproduce setup and automated checks. Audit the complete research-to-review-to-export workflow and fix reproducible defects.
2. Prove the live SerpApi path with my account if a local key is available. Otherwise complete all independent work and record the live check as blocked. Never fabricate a successful live test.
3. Improve the research interface for an analyst: company identity/context, legible sources, coverage and freshness, clear failures, refresh persistence, and usable desktop/narrow layouts.
4. If P0 is green and the deadline allows it, implement the single P1 feature in the handoff: a persistent Analyst Review Board linking observations, questions, notes, and next actions to existing source IDs. Keep source-only operation usable without an LLM.
5. Complete meaningful tests, inspect actual exports, update setup/contribution docs, and prepare a truthful under-three-minute demo script and submission copy.

Keep deterministic valuation separate from public search discovery. Do not introduce invented financial data, buyer interest, or an automatic risk verdict. Existing sector multiple assumptions must remain labeled illustrative. Search citations identify supporting excerpts; they do not prove every claim.

Use backend-only secrets and explicit live/demo modes. Never expose API keys through frontend settings, logs, exports, screenshots, git, or chat. Send only public company metadata to the new search workflow. Preserve tenant authorization, output approval, and historical exported files.

Timebox the work using 05_PRIORITIZED_EXECUTION_PLAN.md. Reliability, a working live demonstration, and accurate submission materials outrank extra features. Do not add a new vector database, provider, framework, monitoring platform, stock feed, or autonomous execution system. Any new optional feature must be removable without breaking the current pipeline.

Make code changes, run the appropriate checks, and keep docs/codex-handoff/PROGRESS.md updated with completed tasks, evidence, current commit, remaining blockers, and the next step. Distinguish mocked automated tests, explicit demo smoke tests, real provider tests, browser checks, and untested paths.

Do not stop for approval for ordinary reversible implementation decisions. Ask for missing user input only when it blocks dependent work, and continue independent tasks. Prepare commits and a reviewable PR when repository access permits. Do not merge, publicly deploy, upload the recording, submit the competition form, or accept terms on my behalf without a separate explicit instruction.

At completion give me:
- What changed and the exact branch/commit/PR.
- How to run the app.
- Tests and browser/live/export checks actually performed.
- Anything still blocked or unverified.
- A ready demo script and final submission description matching implemented features.
- A short list of the actions I must personally finish.

If the original deadline has passed, say so and proceed with a useful working project rather than implying a submission is still possible.

END PROMPT
