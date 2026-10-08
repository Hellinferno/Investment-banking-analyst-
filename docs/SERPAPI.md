# SerpApi integration

## Integration boundary

Company Intelligence, Buyer Discovery, and Diligence Discovery use the backend client at apps/api/src/tools/serpapi_client.py. The fixed provider endpoint is https://serpapi.com/search.json. The browser never receives the provider key or raw provider response.

Reference documentation:
- https://serpapi.com/search-api
- https://serpapi.com/google-news-api

## Search plan

Each run issues four planned queries, with India as the default country and English results:

| Purpose | Engine | Query pattern |
| --- | --- | --- |
| Company filings | google | Optional site:domain, quoted company name, investor relations annual report |
| Industry and peers | google | Quoted company name, industry, competitors industry |
| Transactions / diligence | google | Acquisition merger strategic buyers, or regulatory disclosures litigation |
| Recent news | google_news | Quoted company name and when:Nd |

The news window is a query constraint, not a guarantee every returned date falls within it. Publication dates are retained as supplied. A known domain constrains the filings query; a domain match is not proof of ownership or content verification.

Names and industries are length-bounded and cleaned before query construction. Deal notes and uploaded documents are never included. Search returns excerpts and links; the integration does not retrieve full source documents.

## Request and result

Authenticated research configuration: GET /api/v1/research/status.

Dispatch: POST /api/v1/deals/{deal_id}/agents/run

```json
{
  "agent_type": "research",
  "task_name": "industry_brief",
  "parameters": {
    "country": "in",
    "news_days": 30,
    "official_domain": "company.com",
    "synthesize": false
  }
}
```

Use buyer_universe for Buyer Discovery, or agent_type due_diligence / task_name dd_report for diligence.

Parameters reject unknown fields. Country requires two lowercase letters; news_days is 1-365; the domain excludes protocols/paths. Run details are available at GET /api/v1/deals/{deal_id}/agents/runs/{run_id} and include research_evidence and research_report. Existing JWT and tenant checks apply.

Evidence persists normalized source records and per-query coverage. Google News top-level, highlight, and nested stories are supported. URLs are deduplicated; unsafe clickable schemes/private IPs and credential-like query fields are excluded. Source IDs are local to each run.

Coverage is complete only if every planned live query yields usable normalized evidence; partial retains usable evidence when another query fails or is empty. Empty results produce no factual conclusions and a failed run with reviewable evidence/exports where collection finished. Demo coverage refers only to a fixture exercise.

## Limits and reliability

- Two in-flight provider requests per run; four planned queries.
- One retry per query for server/network failures: at most eight HTTP attempts.
- No automatic retry of authentication or quota errors.
- HTTP timeout: 20 seconds per operation. Optional synthesis has separate LLM timeouts/retries.
- At most eight normalized results per query; at most 32 unique sources.
- Process-local cache: 128 responses, 30-minute TTL, partitioned by a hash of the API key and query parameters. Concurrent identical cache misses may both make a request.
- Existing agent worker pool: two workers, at most four admitted specialized jobs including queued jobs. One active run per deal in the single-process app.
- Restart marks interrupted in-process runs failed; completed evidence and output records remain in the database.

Provider billing depends on account rules and provider cache behavior; the request bound is not a cost guarantee. This hackathon backend is designed for a single API process. Distributed job execution, per-tenant quotas, and cancellation are future work.

## Optional AI interpretation

Set a backend GEMINI_API_KEY or NVIDIA_API_KEY and select AI interpretation. The LLM receives at most 24 normalized source excerpts, titles, dates, purposes, and IDs. No uploaded documents are supplied by this research path.

Output is schema-checked and every citation ID must exist. Unknown-ID observations are removed; invalid/empty output falls back to excerpts. Citation existence does not verify semantic support. Every AI observation is labeled analyst_interpretation and requires review.

## Exports and configuration

Research produces a PDF and JSON; diligence also produces XLSX. Filenames include the run ID. PDFs contain references and provenance; spreadsheets escape formula-like source text. Exports use existing draft/reviewer approval/download controls.

Docker includes DejaVu fonts for PDF text, including the rupee symbol. Local installs can set AIBAA_PDF_FONT_DIR to a directory containing DejaVuSans.ttf and DejaVuSans-Bold.ttf; otherwise ReportLab's standard fonts are used. JSON preserves original Unicode text. Non-Latin scripts and uncommon glyphs still need visual review.

Root .env and apps/api/.env are loaded consistently, with existing process environment taking priority. API-specific .env takes priority over root .env. Restart after changing keys. AIBAA_DATA_DIR controls uploads, outputs, and the default absolute SQLite location. Alembic uses the same database configuration.

Live research fails clearly without SERPAPI_API_KEY; it never silently substitutes demo fixtures. AIBAA_RESEARCH_MODE=demo must be set explicitly.
