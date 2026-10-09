# Product strategy: evidence an analyst can act on

Working title: **AIBAA Deal Intelligence**.

One-sentence promise: **Gather public company evidence, show its coverage and sources, and turn it into a reviewable analyst handoff inside the deal workspace.**

The primary user is an analyst preparing early company research or public diligence. The immediate job is deciding what to investigate next and collecting evidence for a colleague. Avoid promising investment advice, automated deal decisions, or a finished valuation from snippets.

## The hero workflow

1. Create a deal with a public company name and industry.
2. Run Company Intelligence using focused SerpApi Search/News queries.
3. Inspect the query coverage, retrieval time, company matches and source excerpts.
4. Capture a few observations and open questions on an Analyst Review Board.
5. Add a next action, link its sources, and record analyst review status.
6. Generate a versioned research handoff; approve and download it through the existing output workflow.
7. Optionally show a source-linked diligence checklist.

DCF/LBO remain supporting functionality. They should be correct and usable, but they are not the first two minutes of the submission.

## One differentiator to finish

The **Analyst Review Board** is the sole P1 addition. It closes the gap between a search result list and a useful research handoff.

Example, using hypothetical wording rather than a claim about a real company:

| Observation/question | Evidence | Analyst action |
| --- | --- | --- |
| A search result mentions an acquisition | Existing source S03 with date and link | Read the announcement and verify transaction details |
| Revenue mix is unclear from discovery excerpts | Existing source S07 | Locate the annual report and reconcile segments |
| A news result may describe a different company | Existing source S09 | Confirm identity or exclude the source |

The board must work through manual analyst input without an LLM key. Optional AI suggestions remain unreviewed until a person assesses them. A review status means the analyst handled the item; it never certifies a search claim as true.

## Product quality priorities

| Improvement | Why it helps |
| --- | --- |
| Clear company name/domain context | Prevents an impressive-looking brief about the wrong entity |
| Coverage and per-query failures | Shows where additional investigation is needed |
| Publication date vs retrieval time | Makes stale or undated material visible |
| Direct source/citation navigation | Lets a reviewer inspect an observation |
| Saved research and review notes | Makes the output useful after refresh |
| Versioned exports | Preserves the reviewed handoff and its source context |
| Useful source-only mode | Demonstrates the actual SerpApi contribution |

## Do not expand the scope

No stock-price feed, Google Finance integration, full-site crawler, vector database, chat-with-every-document rewrite, autonomous investment recommendation, monitoring service, new model provider, or custom authentication overhaul.

Do not turn discovered transaction mentions into a ranked buyer-interest list. Do not show made-up sentiment accuracy, risk scores, analyst hours saved, or live market comps. If a measured speed comparison is available, describe the exact task, sample and limitations.

## Visual direction

Use the existing app's visual system. Improve hierarchy, spacing, labels, empty/error states and source readability before decoration. Favor a compact summary followed by coverage, review items and the source list. Keep long URLs out of titles; allow accessible source links and focus states.

Do not spend the remaining sprint replacing the entire interface. Demonstrate one coherent path with convincing data and a clean export.
