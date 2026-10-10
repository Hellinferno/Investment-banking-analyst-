# Progress and completion checklist

Create or update `docs/codex-handoff/PROGRESS.md` using the template below. Check a box only after the described evidence exists.

## Previous-session baseline — already recorded

- [x] SerpApi-backed research/diligence implementation on feature branch.
- [x] Previous backend suite: 60 tests passed with provider mocks/offline fixtures.
- [x] Previous frontend lint, TypeScript/Vite build passed.
- [x] Clean GitHub CI passed at snapshot feature head.
- [x] Explicit demo-mode API/worker and export approval/download smoke passed.
- [x] Long synthetic PDF inspected across all seven pages.
- [x] Local SQLite Alembic upgrade passed.

These boxes describe prior evidence. They do not mark new work, real provider access, or final submission as complete.

## P0 final gates — complete in the new session

- [ ] Current branch/PR and uncommitted work inspected; feature changes preserved.
- [ ] Setup reproduced from public documentation without hidden local dependencies.
- [ ] Relevant backend tests, lint and build pass after final edits.
- [ ] Real SerpApi source-only research succeeds; source relevance and provider provenance inspected.
- [ ] Real public diligence run and its checklist reviewed.
- [ ] Missing key/quota/partial/empty cases have clear handling.
- [ ] Browser path works at desktop and narrow widths.
- [ ] Citation navigation works with source filters.
- [ ] Refresh/saved-run behavior works.
- [ ] Output approval and authorized downloads work.
- [ ] Actual PDF/JSON/XLSX contents inspected; old approved outputs remain unchanged.
- [ ] New behavior respects tenant/role boundaries and secret handling.
- [ ] README/setup/contribution/limitations describe the final implementation.
- [ ] Demo script rehearsed below three minutes.
- [ ] Final submission copy matches working and demonstrated behavior.

A missing live key or inaccessible browser does not let Codex check the corresponding box. Describe the blocker and precise remaining action.

## P1 optional gate — mark completed or explicitly omitted

- [ ] Minimal cited Analyst Review Board implemented.
- [ ] Items persist for their saved research run after reload.
- [ ] New runs don't inherit old review items.
- [ ] Invalid source references and unauthorized edits rejected.
- [ ] Changed notes export as a new snapshot/version.
- [ ] Previous approved export bytes remain unchanged.
- [ ] Board's browser and API behavior verified.
- [ ] Alternatively: P1 omitted cleanly for schedule; all board claims removed.

Do not require both implementation and omission. Record the chosen outcome.

## Human entry gates

- [ ] Owner reviewed final PR and chosen submitted revision.
- [ ] Public repository revision contains new implementation and runnable instructions.
- [ ] Recording uploaded; link opens privately without sign-in.
- [ ] Eligibility, participant details and terms personally reviewed.
- [ ] Correct track, existing-project and AI-tool disclosures entered.
- [ ] Entry actually submitted, with confirmation saved.
- [ ] Repository/video links rechecked after submission.

## PROGRESS.md template

```markdown
# Hackathon progress

Updated:
Current local date/time and timezone:
Repository:
Working branch:
Current commit:
PR:
Remaining time / next milestone:

## Completed
- Task — commit or evidence — result.

## Validation
| Category | Command/action | Result | Date/revision |
| --- | --- | --- | --- |
| Mocked automated tests | | | |
| Demo-mode runtime | | | |
| Live SerpApi | | | |
| Optional live LLM | | | |
| Browser | | | |
| Export inspection | | | |
| Docker/hosted runtime | | | |

## Open defects or blockers
- What is blocked, why, and the exact next action.
- Do not include credentials or private participant information.

## Scope decision
- P1: planned / in progress / verified / omitted.
- Final features safe to describe:
- Features not safe to claim:

## Next step
One concrete action.

## Human actions remaining
- Key/account setup if needed.
- Review final PR/revision.
- Record/upload video.
- Complete final submission and verify confirmation.
```

## Definition of done

The software handoff is complete when the final revision is reproducible, its changed paths have meaningful checks, the analyst workflow and actual artifacts are usable, and the report accurately identifies any unverified live/browser/container paths.

The hackathon entry is complete only when the owner has finished the human entry gates. Do not call a blocked software handoff "fully verified," or a prepared submission "submitted."
