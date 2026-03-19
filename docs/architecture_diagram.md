# AI Investment Banking Analyst Agent (AIBAA)
## System Architecture Overview

This document provides a highly visual and logically structured breakdown of the system architecture empowering the AIBAA platform. The architecture is segregated into modular layers, ensuring scalability, maintainability, and clear separation of concerns.

### High-Level Component Diagram

```mermaid
flowchart TB
    %% Styling
    classDef frontend fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff
    classDef backend fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff
    classDef agent fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff
    classDef external fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff
    classDef storage fill:#64748b,stroke:#334155,stroke-width:2px,color:#fff

    subgraph Client [Client Tier]
        UI[React.js + Vite Web Interface]:::frontend
        Dashboard[Interactive Valuation Dashboards]:::frontend
        Upload[Virtual Data Room Uploader]:::frontend
    end

    subgraph API [API Services Tier]
        FastAPI[FastAPI Backend Server]:::backend
        API_Routes[RESTful Endpoint Routers]:::backend
        VDR_Store[Virtual Data Room Manager]:::storage
        
        UI <-->|HTTP / REST| API_Routes
        API_Routes <--> FastAPI
        FastAPI <--> VDR_Store
    end

    subgraph Agents [Agentic Intelligence Tier]
        Orchestrator[Orchestration Agent]:::agent
        Modeller[Financial Modeling Agent]:::agent
        Extractor[Data Extraction Agent]:::agent
        
        FastAPI <-->|Task Requests| Orchestrator
        Orchestrator --> Modeller
        Orchestrator --> Extractor
    end

    subgraph Engines [Math & Export Engines]
        DCF[Discounted Cash Flow Engine]:::backend
        CCA[Comparable Company Engine]:::backend
        ExcelWriter[Excel Template Generator]:::storage
        
        Modeller <--> DCF
        Modeller <--> CCA
        Modeller --> ExcelWriter
    end

    subgraph External [External Cognitive Services]
        GoogleGemini[Google Gemini Flash / Pro API]:::external
        DeepSeek[DeepSeek Reasoner API]:::external
        
        Extractor <-->|Raw Text| GoogleGemini
        Modeller <-->|Financial Parameters| GoogleGemini
        Modeller <-->|Complex Reasoning| DeepSeek
    end
```

### 1. Client Tier (Frontend)
- **Technology**: React.js, Vite, Tailwind CSS, Lucide Icons.
- **Responsibility**: Provides an intuitive, enterprise-grade dark-themed UI for investment bankers. It handles file uploads (Virtual Data Room), visualizes the outputs of financial models (Enterprise Value bridges, sensitivity matrices), and tracks agent task status in real-time.

### 2. API Services Tier (Backend)
- **Technology**: Python, FastAPI, Uvicorn.
- **Responsibility**: Securely handles client HTTP requests. It acts as the gateway to the agentic system. It also manages in-memory data states via `store.py` (simulating a database for prototype speed) and organizes uploaded financials.

### 3. Agentic Intelligence Tier (AI Core)
- **Technology**: Custom Python Agent Framework (`agents/`).
- **Responsibility**: Mimics the workflow of human analysts.
  - **Orchestrator**: Determines which specialized agent is needed for a user request.
  - **Extractor**: Reads raw scraped text from PDFs/JSONs, normalizing and sanitizing the context.
  - **Modeller**: Acts as the senior financial analyst. It prompts the LLMs to extract core variables (Shares, Debt, EBITDA, CapEx), auto-normalizes mismatched units (Crores vs Absolute), and feeds them into the deterministic math engines.

### 4. Math & Export Engines
- **Technology**: Pyndantic, OpenPyXL, Python Math libraries.
- **Responsibility**: While LLMs are great at text, they hallucinate math. The `dcf.py` engine takes structured data from the Modeller and runs rigorous, error-free Discounted Cash Flow math. Outputs are then serialized into professional `.xlsx` artifacts using `excel_writer.py`.

### 5. External Cognitive Services
- **Technology**: Direct LLM API integrations (`llm.py`).
- **Responsibility**: Provides the "brain". The backend sends highly engineered prompts along with financial context to Google Gemini (or NVIDIA/DeepSeek endpoints) to intelligently extract and infer data.

---

### Sequence: How a Financial Model is Built

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API
    participant ModelingAgent
    participant LLM
    participant DCFEngine
    participant ExcelWriter

    User->>Frontend: Uploads Annual Report + Clicks "Run DCF"
    Frontend->>API: POST /deals/{id}/agents/run
    API->>ModelingAgent: Dispatch Task (Mode: DCF)
    ModelingAgent->>LLM: Pass VDR Context + Schema Prompt
    LLM-->>ModelingAgent: JSON: Extracted Financials (e.g. EBITDA, CapEx, Shares)
    ModelingAgent->>ModelingAgent: Auto-Normalize Data (Crores -> Absolute)
    ModelingAgent->>DCFEngine: Inject params into deterministic math formulas
    DCFEngine-->>ModelingAgent: Return computed WACC, EV, Share Price
    ModelingAgent->>ExcelWriter: Send projected numbers to write
    ExcelWriter-->>ModelingAgent: Save dcf_model_output.xlsx
    ModelingAgent-->>API: Task Completed + DCF JSON Payload
    API-->>Frontend: Return Payload
    Frontend-->>User: Display Valuation Dashboard & Download Link
```
