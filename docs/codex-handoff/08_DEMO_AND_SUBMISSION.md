# Demo and submission runbook

Target a **2 minute 45 second** screen recording. Keep it below the organizer's three-minute limit. Use a public company, no private deal files, and no visible keys. A live hosted app is not required by the checked submission rules; a working local recording and public reproducible code are sufficient.

## Before recording

Complete the live test and browser checks. Choose a company whose search results are relevant and useful. Clean the visible workspace, enlarge small text and close terminals showing environment settings.

Prepare a live research run with optional synthesis disabled. A warmed cache or saved live result can improve timing, but explicitly say what is cached/saved. Do not describe a previously saved run as a fresh provider call. Keep demo mode labels intact in rehearsal; the submission should show real SerpApi evidence.

Practice once with a stopwatch. If waiting consumes too much time, trim or speed the waiting segment and disclose it, then show the actual completed run. Never manufacture provider results.

## Recording script

| Time | Screen | Suggested narration |
| --- | --- | --- |
| 0:00–0:15 | Deal workspace, company context | "Early company research means switching between filings, market searches and news. AIBAA brings that evidence into a reviewable deal workspace." |
| 0:15–0:45 | Company Intelligence settings and run | "The new workflow uses SerpApi Google Search and Google News with four focused queries. This run uses public company metadata and does not need an LLM." |
| 0:45–1:15 | Coverage, query provenance, sources | "Here are the sources, publication dates where available and retrieval context. Coverage makes missing or failed searches visible. I can open the evidence behind an observation." |
| 1:15–1:45 | Analyst Review Board, if complete | "I turn a source into a question, add the next investigation step, and save the review status. Reloading preserves this handoff." |
| 1:45–2:15 | Diligence checklist or research export | "The evidence also supports a public diligence checklist. These are investigation leads, not an automatic risk verdict." |
| 2:15–2:35 | Approve and open an actual export | "The existing approval workflow produces a cited PDF and reusable structured output. Exported versions preserve the reviewed context." |
| 2:35–2:45 | Contribution summary, repository | "This extends an existing analyst workspace with the new SerpApi research pipeline. The repository includes setup, tests, and a clear contribution disclosure." |

If P1 was dropped, replace 1:15–1:45 with source filtering, a saved-run refresh and cited PDF navigation. Remove all board claims from the description. If you show cache reuse, mention it during the run segment.

Don't spend time on sign-in, installing packages, every navigation tab, synthetic financial comps, or an optional model that has not been tested.

## Final repository preparation

The new implementation was on an unmerged draft PR at the snapshot. Judges opening default main may otherwise see the older app.

Have Codex prepare the final tested PR and explanation. The owner reviews and chooses whether to merge before submission. After merging, verify a fresh checkout of the submitted revision installs and contains the documented features. If submitting an unmerged branch, use a precise branch URL and explicit checkout instructions, but recognize that a default-main repository is easier for reviewers. Do not assume any organizer preference beyond the public/runnable-code requirement.

Check README first-screen content: product purpose, track, setup, required environment variables without values, exact SerpApi engines, demo/live difference, feature scope, known limitations and contribution disclosure. Confirm secrets/data/recordings are not accidentally tracked.

## Human submission steps

1. Confirm eligibility and team details against the current rules/terms.
2. Upload the recording using an accessible public or unlisted URL. Open it in a private browser window to confirm it works without your account.
3. Open the official event's submission dashboard and authenticate with GitHub.
4. Fill the final title, description, track, repository and video link. Supply requested lead/team contact and occupation/experience details directly; do not store those in this pack.
5. Disclose the existing project and AI tools accurately. Review and accept the terms yourself.
6. Submit the project. Confirm the dashboard shows a submitted entry, not merely a saved draft.
7. Save the confirmation/reference and final links. Recheck them after submission.

Use [09_SUBMISSION_DRAFTS.md](09_SUBMISSION_DRAFTS.md) as editable copy. Match it to the final implemented state and actual demonstration.

## Contingency

If the recording fails, repeat the shorter proven source-only path. If a provider outage blocks a fresh run, accurately label saved evidence and include the recorded live-validation details; do not claim a call succeeded when it did not. Resolve account problems early, before the recording window.

Submit by the internal target in [05_PRIORITIZED_EXECUTION_PLAN.md](05_PRIORITIZED_EXECUTION_PLAN.md). No final feature is worth missing the entry deadline.
