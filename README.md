# AIBAA

AI Investment Banking Analyst Agent is a monorepo for an analyst workflow platform built with FastAPI and React. The current tracked source of truth lives under `apps/`, with supporting design and implementation notes in `docs/` and lightweight fixtures in `tests/`.

This branch is intentionally cleaned for GitHub. Generated uploads, runtime spreadsheets, local databases, duplicate prototype folders, and personal one-off scripts are not committed. If a document in `docs/` describes architecture that is broader than what you see in `apps/`, treat the README and the checked-in code as the current implementation baseline.

## Current State

- Backend: FastAPI API with routers for deals, documents, agents, outputs, auth, and tasks.
- Modeling engine: deterministic Python modules for DCF, LBO, comparables, triangulation, and financial statement analysis.
- Frontend: React 19 + Vite workspace for dashboard and deal workflows.
- Persistence: SQLite for local development, PostgreSQL via Docker Compose.
- Document flow: file upload handling, document parsing, and startup recovery from the local uploads area.

## Repository Map

```text
.
|-- apps/
|   |-- api/        FastAPI backend, migrations, modeling engines, tests
|   |-- web/        React/Vite frontend
|   `-- data/       Local data helpers and runtime storage paths
|-- docs/           Product, architecture, API, and delivery documentation
|-- tests/          Shared fixtures and integration tests
|-- .env.example    Local environment template
|-- docker-compose.yml
|-- Makefile
`-- README.md
```

## Prerequisites

- Python 3.11
- Node.js 22 recommended
- Docker Desktop with Compose support for the containerized stack
- GNU Make if you want to use the repo shortcuts instead of raw commands

## Clone

```bash
git clone https://github.com/Hellinferno/Investment-banking-analyst-.git
cd Investment-banking-analyst-
```

## Quick Start

### Option 1: Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Useful endpoints:

- API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Web app: `http://localhost:3000`

If you have `make` available, `make up` wraps the same startup flow.

### Option 2: Local Development

Backend:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r apps/api/requirements.txt
cd apps/api
python -m alembic upgrade head
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

Notes:

- The `Makefile` assumes a repo-root `.venv` and Windows-style `.venv\Scripts` paths.
- `apps/web/README.md` documents the frontend dev-auth bootstrap flow.
- Use `.env.example` as the starting point for local configuration.

## Common Commands

```bash
make up          # docker compose up --build -d
make down        # stop local containers
make logs        # tail API logs
make migrate     # alembic upgrade head
make test        # backend pytest suite
make dev-api     # local FastAPI server
make dev-web     # local Vite server
```

If you do not have `make`, run the underlying `docker compose`, `python`, or `npm` commands directly.

## Branch Strategy

- `main`: cleaned public baseline
- `develop`: integration branch for ongoing work
- `archive/legacy-snapshot`: pre-cleanup historical snapshot
- `feature/*`: short-lived branches for active changes

## Documentation

Start with [docs/README.md](docs/README.md) for a guide to the documentation set.

Key docs:

- [System architecture](docs/04-system-architecture.md)
- [API contracts](docs/06-api-contracts.md)
- [Monorepo structure notes](docs/07-monorepo-structure.md)
- [Development phases](docs/10-development-phases.md)
- [Testing strategy](docs/12-testing-strategy.md)

## What Is Not Committed

The cleaned repo keeps source, docs, and small fixtures only. These stay out of Git by default:

- uploaded source documents
- generated Excel outputs and temporary report files
- local SQLite databases
- build logs and local caches
- duplicate prototype directories

## Contributing

Open work from `develop` or a `feature/*` branch. Keep the root README aligned with the real checked-in structure whenever the repo layout or onboarding flow changes.
