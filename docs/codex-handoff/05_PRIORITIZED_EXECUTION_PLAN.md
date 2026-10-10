# Execution plan

Start by checking the actual clock and repository. This schedule assumes work begins on the evening of 8 October 2026 IST. Budget approximately **8–12 focused engineering hours**, plus user rehearsal, recording and submission. Estimates are planning bounds, not completion promises.

## Work in this order

| Phase | Budget | Task | Exit gate |
| --- | --- | --- | --- |
| 0: Establish baseline | 45–60 min | Inspect checkout/PR, install from docs, run existing checks, start app | Known starting commit and reproducible setup |
| P0: Prove the workflow | 2–3 h | Browser audit, real SerpApi validation when key is available, fix blocking research/review/export defects | A complete usable path, truthful coverage, no key exposure |
| P1: Finish the differentiator | 2–3 h maximum | Persistent Analyst Review Board per implementation spec | Save/refresh/export and authorization tests pass |
| P0: Polish and verify | 1.5–2 h | Responsive UI, meaningful regressions, actual export inspection, docs | Checks green and reviewed artifacts readable |
| P0: Prepare entry | 1 h | Accurate submission copy, contribution disclosure, timed demo rehearsal | Ready-to-record script and explicit final checklist |
| Contingency | 1–2 h | Fix failures, simplify scope, retest affected paths | No new features while blockers remain |

P0 means required for a credible submission. P1 improves the product if P0 is healthy. P2 is limited to minor visual refinements or extra documentation that cannot delay submission.

## Internal milestones (IST)

- **9 October, 18:00:** feature freeze. Stop expanding behavior; use remaining time for defects, live proof and documentation.
- **10 October, morning:** record the live workflow and verify the recording link.
- **10 October, 20:00:** submit and verify confirmation; preserve almost four hours before the official close.
- **10 October, 23:59:** checked official deadline.

If starting late, drop P1 first. Do not trade the live check or recording for an unfinished feature. If the clock passes a milestone, update the remaining plan rather than pretending the original budget is intact.

## Decision rules

| Situation | Action |
| --- | --- |
| Existing baseline fails | Reproduce and repair before extending features |
| No SerpApi key | Continue code/UI/tests/docs; mark live validation blocked and give user precise setup |
| Invalid key or account quota | Show clear failure; stop repeated live calls; resolve account setup with user |
| P1 takes more than three hours | Reduce to manual cited items, three statuses and notes; otherwise omit it cleanly |
| Optional synthesis fails | Keep source-only workflow usable; do not make AI synthesis part of the required demo |
| Narrow UI is broken | Fix core interaction/overflow before cosmetic desktop animation |
| Docker unavailable | Use documented local setup; state Docker is untested rather than adding a deployment detour |
| Time remains after all gates | Improve clarity or run one additional meaningful check, not a new integration |

## Deliverables from Codex

Working application changes on a reviewable branch; passing relevant automated checks; honest live/browser/export validation notes; refreshed README and hackathon docs; ready demo and submission copy; a short human action list.

Record each phase in `PROGRESS.md` using the template in [11_PROGRESS_AND_DONE_CHECKLIST.md](11_PROGRESS_AND_DONE_CHECKLIST.md). Checkpoints should state the exact commit and actual results, not only "done."
