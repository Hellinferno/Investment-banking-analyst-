# AIBAA - AI Investment Banking Analyst Agent

<div align="center">

![Version](https://img.shields.io/badge/version-1.0.0--alpha-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-green.svg)
![Node](https://img.shields.io/badge/node-18+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

**Industry-Grade AI-Powered Financial Analysis Platform**

[Features](#-features)  [Quick Start](#-quick-start)  [Architecture](#-architecture)  [API Reference](#-api-reference)

</div>

---

##  Table of Contents

- [Overview](#-overview)
- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Development Commands](#-development-commands)
- [Troubleshooting](#-troubleshooting)
- [Roadmap](#-roadmap)

---

##  Overview

**AIBAA** (AI Investment Banking Analyst Agent) is an enterprise-grade financial analysis platform built on a sophisticated Multi-Agent architecture. It leverages foundational models to automate complex, time-consuming investment banking tasks.

The current version represents **Version 1.0 (Alpha)** and includes core infrastructure, data persistency, authentication APIs, and the financial modeling engine foundation (DCF and LBO).

---

##  Features

###  Orchestrator & Multi-Agent Framework
- **Task Routing:** Intelligently routes queries to one of six specialized AI agents (Financial Modeling, Pitchbook, Due Diligence, Market Research, Doc Drafter, Coordination).
- **RAG Pipeline (WIP):** Semantic chunking and vector retrieval context.

###  Advanced Financial Engines
- **DCF (Discounted Cash Flow):** Multi-scenario (Base/Bear/Bull) cash flow analysis, WACC calculators, and implied share price ranges.
- **LBO (Leveraged Buyout):** Sources & Uses mechanics, IRR targets, MOIC calculations, and debt scheduling.
- **Excel Generation:** Automated professional IB-quality `.xlsx` models spanning assumptions, scenario heatmaps, and DCF/LBO output formats.

###  Backend & Infrastructure
- **FastAPI Foundation:** Performant API layer with dependency-injected Auth, Idempotency, and Security headers.
- **Database (SQLite/PostgreSQL):** SQLAlchemy managed through Alembic schemas.
- **Docker Ready:** Composable microservices (`api`, `web`, `db`, `redis`, `chroma`).

---

##  Architecture

```text

                         Frontend (Vite/React)                   
      
     Deals       Documents       Agents       Outputs   
      

                               HTTP/REST

                      Backend (FastAPI/Python)                   
      
     Deals        Documents      Agents       Outputs   
      
                                                                
    
                      Agent Orchestrator                       
    
                                                                
      
    Modeling       Pitchbook    Docs         Research   
     Agents         Agent        Agent         Agent    
      

```

---

##  Quick Start

### Prerequisites
- **Docker Compose** (for containerized setup)
- **Python 3.11+**
- **Node.js 18+**

### Clone Repository

```bash
git clone https://github.com/yourusername/UDAI.git
cd UDAI
```

### 1. The Easy Way (Docker)

```bash
# Create an environment file
cp .env.example .env

# Boot the entire stack
make up
```

- **API / Docs:** http://localhost:8000/docs
- **Web App:** http://localhost:3000

### 2. The Local Developer Way (No Docker)

**Backend Setup:**
```bash
# Create and activate Python virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate # Mac/Linux

# Install dependencies
make install

# Apply database migrations
make migrate

# Run API Dev Server
make dev-api
```

**Frontend Setup:**
```bash
# Start frontend Dev Server
make dev-web
```

---

##  Configuration

Create a `.env` file at the root by copying `.env.example`:

```env
# Security & Auth
AIBAA_JWT_SECRET=your_jwt_secret_here
AIBAA_ENV=development

# Database
DATABASE_URL=sqlite:///./aibaa.db
# Or PostgreSQL: postgresql://user:password@localhost/aibaa

# External AI APIs
GEMINI_API_KEY=your_google_ai_key
NVIDIA_API_KEY=your_nvidia_nim_key
```

---

##  Development Commands

The project uses a unified `Makefile` for streamlined tasks:

| Command | Action |
|---------|--------|
| `make up` | Starts all Docker services |
| `make down` | Stops all running services |
| `make logs` | Tails the `api` container logs |
| `make test` | Runs Pytest suite for backend |
| `make lint` | Runs Ruff on Python, ESLint on Frontend |
| `make migrate` | Applies `alembic upgrade head` |

---

##  Roadmap (Per 10-development-phases.md)

- **Phase 0:** Foundation, Auth & Infrastructure *(Completed)*
- **Phase 1:** Core Backend + Data Layer *(In Progress)*
- **Phase 2:** RAG Pipeline + Agent Framework *(Stubbed)*
- **Phase 3:** Computation Engine + First Agent *(DCF/LBO Built)*
- **Phase 4:** Full Agent Suite + PDF/Word Generation
- **Phase 5:** Complete Frontend Workflows

---

