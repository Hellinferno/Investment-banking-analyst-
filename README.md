# AIBAA | SerpApi Deal Intelligence

AI Investment Banking Analyst Agent combines public company discovery with an existing analyst workspace. The SerpApi workflow searches company filings, industry context, transactions, and recent news, then produces a source-backed research brief and diligence review checklist.

**Hackathon demo:** create a deal, run Company Intelligence, inspect citations and search coverage, run Diligence Discovery, and approve/download the reports. Research works without uploading private documents and without an LLM key.

## Implemented workflows

| Workflow | Inputs | Outputs |
| --- | --- | --- |
| Company Intelligence | Public company name, industry, country, optional known domain | Search evidence, cited observations, persistent Analyst Review Board, PDF and JSON |
| Buyer Discovery | Same public metadata | Transaction/buyer mentions for review; interest is not established |
| Diligence Discovery | Same public metadata | Public-source observations, PDF, JSON, Excel review checklist |
| DCF / LBO | Financial documents and analyst assumptions; extraction may require an LLM key | Deterministic calculations and Excel models |
| Other existing agents | Deal documents / model context | Pitchbook, CIM draft, meeting notes |

Search uses SerpApi Google Search and Google News. Source IDs, URLs, publisher, publication date when available, query, retrieval time, search ID, and cache status are persisted with each run. Optional AI interpretation requires Gemini or NVIDIA configuration; invalid output falls back to source excerpts.

Search excerpts are discovery evidence. They do not establish financial inputs, company identity, buyer interest, or legal/risk conclusions. Existing comparable multiples are preset sector assumptions, explicitly labeled as illustrative.

## Quick start: local development

Use Python 3.11+ and Node.js 22. Run these commands from the repository root:

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env
python -m venv .venv
```

Activate the environment:

- macOS/Linux: `source .venv/bin/activate`
- Windows PowerShell: `.venv\Scripts\Activate.ps1`

Install dependencies and configure **SERPAPI_API_KEY in the root .env**, keeping `AIBAA_RESEARCH_MODE=live`:

```bash
python -m pip install -r apps/api/requirements-dev.txt
cd apps/api
python -m alembic upgrade head
python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1
```

Open http://localhost:5173. API docs: http://localhost:8000/docs.

The development frontend exchanges its bootstrap token for a JWT, using the reviewer role so outputs can be approved. Development credentials are local-only. Keep SerpApi and LLM keys in the backend; never add them to a VITE variable.

### Offline rehearsal

Set `AIBAA_RESEARCH_MODE=demo` and restart the API. This explicitly uses synthetic fixtures with visible demo labels. It exercises research UI and exports, makes no SerpApi calls, and does not enable offline LLM generation for other agents. Use live mode for a real SerpApi demonstration.

### Docker Compose

```bash
cp .env.example .env
# Configure backend keys in .env
docker compose up --build
```

Web: http://localhost:3000. API: http://localhost:8000.

Compose runs PostgreSQL and a same-origin Nginx API proxy. Runtime uploads/outputs persist under apps/data; the database uses a named volume. This is a development stack, with development authentication enabled. Before public deployment, supply strong authentication/secrets, disable development bootstrap, and configure the intended origins.

## Research flow

1. Create a deal with the public company name and industry.
2. Open Agents → Company Intelligence.
3. Choose country and news window; optionally enter a known domain such as company.com.
4. Confirm the public-metadata search selection and run.
5. Review complete/partial/empty search coverage, queries, citations, and source links.
6. Save observations or open questions to the run-specific Analyst Review Board, link 1–8 sources, and record a next action and review status.
7. Export a new PDF/JSON board snapshot. Earlier approved export bytes are never overwritten.
8. Run Diligence Discovery for a source-linked Excel checklist.
9. In Outputs, approve the desired draft version as reviewer before downloading.

Uploaded documents and deal notes are excluded from search queries. If AI interpretation is selected, normalized public search excerpts are sent to the configured LLM provider. Other existing agents may send uploaded document context to an LLM.

## Validation

```bash
python -m pytest -q
cd apps/web
npm run lint
npm run build
```

The default suite includes existing backend checks, offline historical modeling regressions, mocked SerpApi HTTP behavior, research and review-board persistence, immutable versioned exports, authentication, and tenant boundaries. It isolates its database and disables real API keys. Historical company profiles are injected only by tests; they are not live financial data.

CI runs backend tests and frontend lint/build. A live SerpApi key check, browser walkthrough, and container deployment check remain environment-specific validation.

## Structure and documentation

- apps/api/src: FastAPI, agents, deterministic modeling engines, evidence and export tools
- apps/api/tests: research workflow and historical modeling regression coverage
- apps/web: React 19 / Vite workspace
- [SerpApi integration](docs/SERPAPI.md): search plan, API parameters, failure handling, limits
- [Hackathon guide](docs/HACKATHON.md): existing-work disclosure, demo sequence, remaining live checks
- [Documentation index](docs/README.md): broader design notes; some describe future functionality

Local environments, uploaded documents, generated outputs, databases, and build artifacts are ignored by Git.
