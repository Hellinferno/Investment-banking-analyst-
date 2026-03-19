# AIBAA: Project Details & Evolution Design

The AI Investment Banking Analyst Agent (AIBAA) is an ambitious project designed to automate the heavy lifting of financial modeling, due diligence, and pitchbook generation. 

This document outlines the user-friendly design principles and the sequential phases of the project lifecycle.

---

## 🎨 Design Philosophy and User Experience (UX)

The platform is designed exclusively for high-finance professionals. The UX principles are:

1. **"Zero-Math-Hallucination" Guarantee**: The system never relies on AI to do math calculation. AI is purely used for reading (data extraction). All mathematical modeling (DCF, WACC, CAGR) is executed by hardcoded Python deterministic engines.
2. **Auditability**: Analysts must trust the numbers. Every financial metric generated is accompanied by an "Extraction Quality" audit trail indicating exactly where the data came from (User Override vs. LLM Extraction vs. Generic Default).
3. **Enterprise Institutional Aesthetics**: The UI avoids "start-up" or "playful" themes. It utilizes a terminal-inspired, heavy-contrast dark mode representing serious enterprise software. 
4. **Graceful Fallbacks**: If an Annual Report is too messy or lacking certain granular data points, the system auto-resolves using conservative industry defaults to ensure the math engines do not crash.

---

## 🚀 Lifecycle Phases of the Project

The project is structured into **Five Core Phases**, tracking from foundational setup to advanced multi-agent networking.

### Phase 1: Foundation & VDR Ingestion (Completed)
**Goal:** Establish the application backbone and allow users to securely upload documents.
- **Backend Setup**: Scaffolding the FastAPI server.
- **Frontend Skeleton**: Launching the React/Vite interface.
- **Virtual Data Room (VDR)**: Implementing the file upload mechanisms for JSON pipelines and PDF ingestion, simulating a secure data storage room where context lives.

### Phase 2: Agent Architecture & Deterministic DCF (Completed)
**Goal:** Build the primary AI abstraction and the first flagship financial model.
- **Agent Orchestrator**: Creating the routing engine to handle different agent tasks.
- **Financial Modeling Agent**: Developing the autonomous loop that instructs LLMs based on VDR context.
- **DCF Engine (`dcf.py`)**: Building fully reliable Python functions capable of determining terminal value, computing Weighted Average Cost of Capital (WACC), and enterprise value bridges.
- **Auto-Normalization Layer**: Intelligently handling unit mismatches common with LLMs (e.g., automatically scaling "24.89 Crores" to "248,900,000", or converting "13.69%" into "0.1369").

### Phase 3: Premium UI & Excel Export Visualization (Completed)
**Goal:** Making the raw data beautifully accessible and exportable.
- **Valuation Dashboards**: Delivering dynamic React screens for Enterprise Value bridges and Sensitivity Matrices that react in real-time to the DCF outputs.
- **Excel Writer (`excel_writer.py`)**: Injecting the backend matrix data into standard Wall Street formatted Excel templates so analysts can download and tweak formulas natively.
- **Audit Trails**: Adding visual badges to indicate the health and source of LLM data extractions.

### Phase 4: Advanced Scenarios & Extended Modeling (In Progress)
**Goal:** Expanding the analyst capabilities beyond simple DCF.
- **Comparable Companies Analysis (CCA)**: Expanding the `modeling.py` to compare against public market multiples.
- **LBO / M&A Modeling**: Adding leveraged buyout mathematical logic to the engines.
- **Scenario Toggles**: Allowing the user to instantly swap between "Base", "Bull", and "Bear" case revenue growth projections directly from the UI.

### Phase 5: Productionization & Security (Planned)
**Goal:** Preparing the prototype for live secure production.
- **Database Migration**: Moving off `store.py` (in-memory) to a robust relational database (PostgreSQL) for persistence across instances.
- **Authentication**: Implementing OAuth2 / JWT for user login and strict Deal / Workspace isolation so data doesn't bleed.
- **Cloud Deployment**: Containerizing the frontend (Nginx) and backend (Docker) and deploying to AWS/GCP clusters with rate limiting and secrets management.
