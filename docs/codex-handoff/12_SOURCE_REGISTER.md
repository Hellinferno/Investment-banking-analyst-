# Sources and evidence register

Checked for this plan on **8 October 2026**. URLs are public references, not embedded credentials. Recheck changing rules and account interfaces before the final entry.

## Organizer sources

| Reference | Purpose |
| --- | --- |
| https://serpapi.github.io/serpapi-india-hackathon-2026/ | Event, tracks, deadline and submission overview |
| https://serpapi.github.io/serpapi-india-hackathon-2026/rules.html | Eligibility, existing projects, required materials, AI disclosure and judging criteria |
| https://serpapi.github.io/serpapi-india-hackathon-2026/terms.html | Governing terms and participant obligations |

The rules/terms describe eligibility in terms of India residency; do not replace that with a citizenship assumption from promotional copy. This pack does not independently verify participant eligibility. The Commerce & Market Intelligence recommendation is our interpretation of the product's purpose.

## Project evidence

| Reference | Purpose |
| --- | --- |
| https://github.com/Hellinferno/Investment-banking-analyst- | Existing project and history |
| https://github.com/Hellinferno/Investment-banking-analyst-/tree/feat/serpapi-market-intelligence | Search-backed implementation branch |
| https://github.com/Hellinferno/Investment-banking-analyst-/pull/1 | Previously prepared draft integration PR |
| https://github.com/Hellinferno/Investment-banking-analyst-/actions/runs/37807810790 | Successful PR CI at snapshot head |
| https://github.com/Hellinferno/Investment-banking-analyst-/actions/runs/37807804105 | Successful push CI at snapshot head |

Repository docs to inspect: README.md, docs/SERPAPI.md, docs/HACKATHON.md, .env.example and current CI configuration. Paths in the engineering guide refer to repository files, not files bundled in this ZIP.

The previous test/demo evidence is recorded in [02_PROJECT_SNAPSHOT.md](02_PROJECT_SNAPSHOT.md). It is not a claim that real API credentials or browser/container checks were available.

## Technical documentation

- [OpenAI getting-started guide](https://developers.openai.com/codex/quickstart/) — official entry point; currently redirects to the ChatGPT Learn quickstart. The first-time instructions here use the documented software-development project workflow.
- [SerpApi Google Search API](https://serpapi.com/search-api) — consult before changing query/result semantics.
- [SerpApi Google News API](https://serpapi.com/google-news-api) — consult before changing news requests/parsing.
- [SerpApi API status/errors](https://serpapi.com/api-status-and-error-codes) — consult for provider error handling.

These technical links are references to consult during implementation, not evidence that this plan exhaustively checked every current parameter or response shape. The existing tested code is the starting point; use official docs to resolve specific uncertainty.

## Planning provenance

The product focus, review-board design, time budgets, internal milestones, proposed implementation and demonstration script are recommendations authored for this handoff. They are not organizer requirements or implemented features. No prize probability, criterion weights, performance benchmark or live provider success has been invented.
