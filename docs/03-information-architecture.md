# 03 — Information Architecture (IA)
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Overview

This document defines the structural organisation of the AIBAA application — pages, components, navigation hierarchy, content taxonomy, and data flows. The IA is designed to be minimal, expert-facing, and optimised for speed-to-output in a financial workflow, while meeting enterprise-grade security and compliance requirements.

---

## 2. Site Map

```
AIBAA Application
│
├── 🔐 Auth (/auth)
│   ├── Login (/auth/login)
│   ├── MFA Verification (/auth/mfa)
│   └── Invite Acceptance (/auth/invite/:token)
│
├── 🏠 Dashboard (/) [auth required]
│   ├── Active Deals List
│   ├── Recent Outputs
│   └── Quick Start Panel
│
├── ➕ New Deal (/deals/new)
│   ├── Deal Setup Form
│   └── Document Upload (optional at creation)
│
├── 📁 Deal Workspace (/deals/:dealId)
│   │
│   ├── Overview Tab
│   │   ├── Deal Summary Card
│   │   ├── Task Tracker Board
│   │   └── Activity Log
│   │
│   ├── Documents Tab (/deals/:dealId/documents)
│   │   ├── Upload Zone
│   │   ├── Document List (with MNPI flag, index status)
│   │   └── Document Preview Panel
│   │
│   ├── Agents Tab (/deals/:dealId/agents)
│   │   ├── Financial Modeling Agent
│   │   ├── Pitchbook Agent
│   │   ├── Due Diligence Agent
│   │   ├── Market Research Agent
│   │   ├── Deal Documentation Agent
│   │   └── Deal Coordination Agent
│   │
│   ├── Outputs Tab (/deals/:dealId/outputs)
│   │   ├── Generated Files List
│   │   ├── In-browser Preview
│   │   └── Download / Share
│   │
│   └── Settings Tab (/deals/:dealId/settings)
│       ├── Deal Configuration
│       ├── Agent Behaviour Settings
│       └── Disclaimer & Compliance Notes
│
├── ⚙️ Global Settings (/settings)
│   ├── LLM Backend Configuration
│   ├── Webhook Endpoints
│   ├── Default Preferences
│   └── Export Format Preferences
│
├── 🔒 Admin (/admin) [org admin only]
│   ├── User Management
│   ├── Audit Trail
│   ├── Data Retention Policy
│   └── MFA Enforcement
│
└── ❓ Help (/help)
    ├── Agent Capability Guide
    ├── Input Format Instructions
    ├── MNPI Handling Guide
    └── FAQ
```

---

## 3. Navigation Model

### Primary Navigation (Left Sidebar)
| Icon | Label | Route | Auth Required |
|---|---|---|---|
| 🏠 | Dashboard | `/` | Yes |
| 📁 | Deals | `/deals` | Yes |
| ⚙️ | Settings | `/settings` | Yes |
| 🔒 | Admin | `/admin` | Org Admin only |
| ❓ | Help | `/help` | Yes |

### Contextual Navigation (Deal Workspace — Top Tabs)
| Tab | Purpose |
|---|---|
| Overview | High-level deal status and task board |
| Documents | Data room / document upload, MNPI flagging, RAG index status |
| Agents | Trigger and configure each AI agent |
| Outputs | All generated files and previews |
| Settings | Deal-specific configuration |

### Breadcrumb Structure
```
Dashboard > Deal Name > [Active Tab]
e.g., Dashboard > Nexus Pharma Acquisition > Agents > Financial Modeling
```

---

## 4. Page-Level Content Inventory

### 4.1 Dashboard (`/`)

| Component | Content | Source |
|---|---|---|
| Header | "AIBAA" wordmark + user greeting | Static / Auth |
| Deal Cards | Deal name, type, status, last modified | Deal Store (org-scoped) |
| Quick Stats | # Active Deals, # Outputs Generated, # Pending Reviews | Aggregated |
| New Deal CTA | Prominent black button: "+ New Deal" | UI Action |
| Recent Activity Feed | Last 5 agent actions across all deals | Event Log |

---

### 4.2 New Deal Form (`/deals/new`)

| Field | Type | Validation |
|---|---|---|
| Deal Name | Text input | Required, max 80 chars |
| Company Name | Text input | Required, max 80 chars |
| Deal Type | Dropdown: M&A / IPO / Fundraising / Restructuring / Other | Required |
| Industry | Dropdown (20+ sectors) | Required |
| Deal Stage | Dropdown: Preliminary / Active / Final | Required |
| Notes / Context | Textarea | Optional, max 500 chars |

---

### 4.3 Documents Tab — Enhanced Fields

Each document row shows:
- **Filename** and **file type**
- **Upload timestamp** and **file size**
- **RAG Index Status**: Pending / Indexing / Indexed / Failed (with chunk count when indexed)
- **MNPI Flag**: Toggle — when ON, a consent prompt is shown before any LLM agent uses this document
- **Category**: auto-classified or manually set (Financial / Legal / Corporate / Tax / Operational)

---

### 4.4 Deal Workspace — Agents Tab (`/deals/:dealId/agents`)

Each agent card contains:
- **Agent Name** (e.g., "Financial Modeling Agent")
- **Description** (one-line capability summary)
- **Status Badge** (Idle / Queued / Running / Completed / Error)
- **Input Panel** (context-sensitive: text prompt, file selector, parameters)
- **MNPI Consent Banner** (shown when an indexed MNPI document is in scope)
- **Run Button** (enqueues task in ARQ worker — non-blocking)
- **Reasoning Panel** (collapsible: shows RAG retrieval summary + chain-of-thought steps)
- **Confidence Badge** (green ≥ 0.8 / yellow 0.6–0.79 / red < 0.6)
- **Output Preview** (inline text or file link)

---

### 4.5 Outputs Tab (`/deals/:dealId/outputs`)

| Column | Content |
|---|---|
| File Name | e.g., "NexusPharma_DCF_Model_v1.xlsx" |
| Agent | Which agent generated it |
| Type | XLSX / PDF / DOCX / PPTX / MD |
| Generated At | Timestamp |
| Confidence Score | 0.0–1.0 with colour badge |
| Status | Draft / Approved / Archived |
| Disclaimer | Confirmation that disclaimer was embedded in output |
| Actions | Preview / Download / Approve / Request Revision |

---

### 4.6 Admin — Audit Trail (`/admin/audit`)

| Column | Content |
|---|---|
| Timestamp | UTC ISO 8601 |
| User | Display name + user_id |
| Event Type | e.g., `document_uploaded`, `agent_run_completed`, `output_approved` |
| Entity | Type and ID of the affected object |
| Description | Human-readable summary |
| Integrity Hash | SHA-256 chain hash — allows tamper detection |

Export button generates a signed CSV. Audit logs are read-only; no delete or edit controls exist.

---

## 5. Content Taxonomy

### 5.1 Deal Type Taxonomy
```
├── Mergers & Acquisitions (M&A)
│   ├── Buy-Side Advisory
│   └── Sell-Side Advisory
├── Capital Markets
│   ├── IPO
│   ├── Secondary Offering
│   └── Debt Raise
├── Private Equity
│   ├── LBO
│   └── Growth Equity
├── Restructuring
│   ├── In-Court
│   └── Out-of-Court
└── Other
```

### 5.2 Document Type Taxonomy (Data Room)
```
├── Financial Statements
│   ├── Income Statement
│   ├── Balance Sheet
│   └── Cash Flow Statement
├── Corporate Documents
│   ├── Certificate of Incorporation
│   ├── Cap Table
│   └── Shareholder Agreements
├── Contracts
│   ├── Customer Contracts
│   ├── Supplier Agreements
│   └── Employment Agreements
├── Tax Documents
│   ├── Tax Returns (3-yr)
│   └── Tax Schedules
├── Legal
│   ├── IP Registrations
│   ├── Litigation History
│   └── Regulatory Filings
└── Operational
    ├── Org Chart
    ├── Product / Service Overview
    └── Customer List
```

### 5.3 Data Classification Taxonomy *(NEW)*
Every document must have one of these classifications:
```
├── PUBLIC          — Freely available (press releases, public filings)
├── INTERNAL        — Internal company data, not publicly disclosed
├── CONFIDENTIAL    — Restricted to deal participants
└── MNPI            — Material Non-Public Information
                      Strictest handling: consent required before LLM use,
                      encrypted at rest, 7-year retention, access logged.
```

### 5.4 Agent Output Type Taxonomy
```
├── Financial Models
│   ├── DCF Model (.xlsx)           — includes mid-year discounting, re-levered beta
│   ├── LBO Model (.xlsx)           — includes full cash flow IRR, debt schedule
│   └── Comparable Company Analysis (.xlsx)
├── Presentations
│   ├── Pitchbook (.pdf)
│   └── Pitchbook (.pptx)           — editable slides, NEW
├── Due Diligence Reports
│   ├── Risk Summary (.pdf)         — semantic colour risk ratings
│   └── DD Checklist (.xlsx)
├── Research Briefs
│   ├── Industry Overview (.pdf)
│   └── Buyer/Target Universe (.pdf / .xlsx)
├── Deal Documents
│   ├── CIM Draft (.docx / .pdf)
│   ├── Executive Summary (.docx)
│   └── Deal Teaser (.pdf)
└── Coordination Artifacts
    ├── Meeting Summary (.md / .pdf)
    └── Deal Task Tracker (.md / .xlsx)
```

---

## 6. User Flow Diagrams

### Flow 1: First-Time User Starting a Deal
```
Land on Login Page
→ Authenticate (JWT issued)
→ Land on Dashboard
→ Click "+ New Deal"
→ Fill Deal Setup Form
→ Upload & Index Documents
→ Redirected to Deal Workspace → Overview Tab
→ Click "Agents" tab
→ Select "Financial Modeling Agent"
→ (If MNPI doc in scope → show consent banner)
→ Input deal parameters
→ Click "Run Agent" → task enqueued to ARQ worker
→ Watch Reasoning Panel update via SSE
→ Output file appears in Outputs tab
→ Review confidence badge → approve or revise
→ Preview → Approve → Download
```

### Flow 2: Due Diligence Workflow
```
Open Deal Workspace → Documents Tab
→ Bulk upload data room (RAG indexing runs in background)
→ Flag any MNPI documents
→ Navigate to Agents Tab → Due Diligence Agent
→ Click "Run Due Diligence" → task queued
→ Agent retrieves relevant chunks via RAG (not full-text injection)
→ Risk Report generated → Outputs Tab
→ Review flags with semantic colour ratings
→ Mark flags as Reviewed (logged to audit trail)
→ DD Checklist auto-populated
→ Download final Risk Report as PDF (with disclaimer page)
```

### Flow 3: Pitchbook Generation
```
Open Deal Workspace → Agents Tab → Pitchbook Agent
→ Enter deal brief (or auto-pulled from deal context)
→ Set Pitchbook Settings: purpose, tone, format (PDF/PPTX), slides to include
→ Click "Generate Pitchbook" → task queued
→ SSE progress: "Slide 1 of 12…"
→ In-browser preview opens (PDF viewer or PPTX thumbnail grid)
→ Review each slide — financial charts show semantic colours
→ Request revision on any slide (revision logged)
→ Final approval → Download PDF or PPTX
```

---

## 7. Colour System

The UI uses a two-tier colour system. UI chrome is strictly black and white. Data visualisation uses a semantic financial palette.

### Chrome (UI structure — no exceptions)
| Token | Hex | Use |
|---|---|---|
| `--color-bg` | `#FFFFFF` | Page and card backgrounds |
| `--color-text` | `#0A0A0A` | Primary text |
| `--color-muted` | `#6B6B6B` | Secondary text, placeholders |
| `--color-border` | `#E5E5E5` | Borders and dividers |

### Financial Semantic Palette (data only)
| Token | Hex | Use |
|---|---|---|
| `--color-fin-positive` | `#1A7A4A` | Gains, positive returns, IRR upside |
| `--color-fin-positive-bg` | `#EBF5EF` | Positive background fills |
| `--color-fin-negative` | `#C0392B` | Losses, negative returns, risk flags |
| `--color-fin-negative-bg` | `#FDECEA` | Negative background fills |
| `--color-fin-neutral` | `#2C5F8A` | Neutral data, informational |
| `--color-fin-neutral-bg` | `#EAF0F6` | Neutral background fills |
| `--color-risk-high` | `#C0392B` | High severity DD flags |
| `--color-risk-medium` | `#D68910` | Medium severity flags |
| `--color-risk-low` | `#1A7A4A` | Low severity flags |

---

## 8. Empty States

| Screen | Empty State Message |
|---|---|
| Dashboard (no deals) | "No deals yet. Create your first deal to get started." + CTA |
| Documents Tab (no uploads) | "No documents uploaded. Drag and drop files here or click to browse." |
| Documents Tab (indexing) | "Documents uploaded. RAG indexing in progress — agents will be available shortly." |
| Outputs Tab (no outputs) | "No outputs yet. Head to the Agents tab to run your first analysis." |
| Task Tracker (no tasks) | "No tasks yet. Tasks are created automatically when agents run." |
| Audit Trail (no events) | "No audit events recorded yet." |

---

## 9. Error States

| Scenario | Error Message |
|---|---|
| LLM backend unreachable | "AI service is temporarily unavailable. Please try again in a moment." (No internal URLs or provider names exposed to the user) |
| File parse failure | "We couldn't read this file. Please check the format and try again." |
| RAG indexing failure | "Document indexing failed. The document is uploaded but agents cannot use it. Please re-upload." |
| Agent timeout (> 5 min) | "The agent is taking longer than expected. It will continue in the background — you'll see the output in the Outputs tab when it completes." |
| Hallucination guard trigger | "⚠ Numbers in this output could not be verified against source documents. Human review required before use." |
| MNPI consent required | "This run uses documents classified as MNPI. Please confirm you consent to using these documents in this analysis." |
| Worker queue down | "Background processing is temporarily unavailable. Your request has been saved and will resume automatically." |

---

*End of Document — 03-information-architecture.md*
