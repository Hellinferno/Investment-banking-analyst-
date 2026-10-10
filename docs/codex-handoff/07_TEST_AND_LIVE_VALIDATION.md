# Setup and validation

Use current repository instructions as the authority if these commands diverge. Do not overwrite an existing populated environment file.

## Local setup

From the repository root, create `.env` from `.env.example` and the web environment file from its provided example. Keep both uncommitted. The root backend settings include:

```dotenv
SERPAPI_API_KEY=
AIBAA_RESEARCH_MODE=live
```

The user fills the key locally. Do not print it. Do not put it in a `VITE_` variable. No LLM key is needed for source-only research.

For synthetic rehearsal only, set `AIBAA_RESEARCH_MODE=demo`; restart the API when switching modes. Demo success is not live validation.

### Python and database

From the repository root:

```bash
python -m venv .venv
```

Activate on macOS/Linux:

```bash
source .venv/bin/activate
```

Or Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install and start:

```bash
python -m pip install -r apps/api/requirements-dev.txt
cd apps/api
python -m alembic upgrade head
python -m uvicorn src.main:app --reload --host 127.0.0.1 --port 8000
```

Use a separate terminal for the frontend:

```bash
cd apps/web
npm ci
npm run dev -- --host 127.0.0.1
```

Open `http://localhost:5173`; API docs are at `http://localhost:8000/docs`. Read the existing development authentication instructions; the bootstrap token is a local development convenience. Do not expose a development-auth server publicly.

If the setup specifies other prerequisites, follow those rather than upgrading all dependencies. The pandas compatibility pin is deliberate.

## Automated gates after changes

Run backend checks from the root with the virtual environment activated:

```bash
python -m pytest -q
```

Run in `apps/web`:

```bash
npm run lint
npm run build
```

The previous baseline was 60 backend tests. New behavior may increase the count; do not target a number instead of meaningful coverage. Tests with provider mocks do not establish provider connectivity.

Cover changed behavior: tenant/role restrictions, invalid source references, persistence after reload/restart, partial and empty research, invalid key/quota via mocks, duplicate jobs, optional synthesis failure, citation navigation, unique exports and old-file immutability. Add tests for concrete behavior, not assertions mirroring every implementation line.

## Real provider check

Budget live calls deliberately. Start with one Company Intelligence run and one Diligence Discovery run on the same public company. Only if useful, try two more companies: **at most four runs for this validation pass**, each with the existing four-query plan. The code's retry cap can allow up to eight outbound attempts per run; do not confuse this with guaranteed billed credits. Check your account's available credits separately.

Possible company candidates: Infosys, TCS, HCLTech. Verify the exact entity and official domain before using one. These are demonstration subjects, not investment recommendations.

For each live run record:

| Item | Record |
| --- | --- |
| Run context | Public name, industry, country, date range, official-domain setting |
| Mode/provider | Live mode and engines actually requested |
| Provider evidence | Search IDs where returned; no credentials or raw request URLs with keys |
| Coverage | Query successes/failures, normalized/unique source counts |
| Freshness | Retrieval time and publication dates where supplied |
| Cache | Which responses were reused |
| Time | Observed end-to-end duration and test conditions |
| Quality | Manual check of entity match and at least 3 useful source links |
| Artifacts | PDF/JSON/XLSX paths generated, approved and downloaded |
| Limitations | Missing dates, irrelevant sources, empty topics or provider failures |

If authentication/quota fails, stop repeat calls, keep the failure visible, and resolve the account setup. Never silently substitute synthetic sources. Preserve redacted observations, not API secrets.

If showcasing optional synthesis, separately test a real LLM call, inspect semantic support for each displayed claim, and disclose which model/provider actually ran. Otherwise keep it disabled.

## Browser walkthrough

Test a real browser at roughly 1366px desktop and 390px narrow width. Check:

- Deal creation, research settings, queued/running/finished/error states and one working live run.
- Source filters and citation navigation, including a citation hidden by the active filter.
- Long titles/URLs, undated items, partial coverage, empty results and no-key error.
- Refresh restores the saved run; polling stops when finished; retries don't create accidental duplicates.
- P1 review item create/edit/status/delete, source linking, error feedback and reload persistence if implemented.
- Approval and authorized PDF/JSON/XLSX download; wrong-tenant access is denied.
- Keyboard focus, readable contrast and no horizontal overflow in the core path.
- A second run preserves old outputs; a new review export does not change approved file bytes.

Record actual results and unresolved defects. If browser access is unavailable, give the user a reproducible checklist and mark it unverified.

## Export inspection

Open actual downloaded artifacts. Render PDFs and inspect every page for clipped titles, split tables, empty pages, broken citations and Unicode. Check JSON source IDs/URLs, coverage and mode. Open the XLSX and check sensible columns, text safety and links. Use both a realistic live example and a long fixture when changing layout.

Do not claim "all exports verified" based only on file existence or response status.

## Container path

If using Docker for the final demonstration, run the documented Compose build/start and test its web-to-API proxy, fonts and persistent paths. Docker was unavailable in the earlier environment, so this gate remains unverified until someone actually runs it. Local setup is the preferred fallback; do not make a last-minute hosting detour mandatory.
