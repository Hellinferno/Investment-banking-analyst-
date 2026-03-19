# 02 — User Stories & Acceptance Criteria
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## Format Convention

Each story follows:
```
AS A [persona]
I WANT TO [action]
SO THAT [benefit]
```

Acceptance Criteria follow the **Given / When / Then** format.

Priority Levels: `P0` = Must-Have (MVP) | `P1` = Should-Have | `P2` = Nice-to-Have

---

## Epic 0: Authentication & Organisation Setup *(NEW — required before all other epics)*

---

### US-000 — User Registration & Login
**Priority:** P0

> As a **new user**,
> I want to register with my work email and log in securely,
> so that my deal data is protected and scoped to my organisation.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I am on the login page | I enter valid credentials | I receive a JWT access token (8-hour expiry) and am redirected to my dashboard |
| AC-2 | I enter an incorrect password | I click "Sign In" | An error states "Invalid credentials" — no hint about which field is wrong |
| AC-3 | My JWT has expired | I make any API request | I receive `401 Unauthorized` and am redirected to the login page |
| AC-4 | I am logged in | I view my dashboard | I only see deals belonging to my organisation (org_id scoping enforced) |
| AC-5 | A request is made without a token | Any protected endpoint is called | The server returns `401` — no data is returned |

---

### US-000B — Multi-Factor Authentication
**Priority:** P1

> As an **organisation admin**,
> I want to enforce MFA for all users in my org,
> so that deal data is protected even if passwords are compromised.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | MFA is enabled for my org | A user logs in with correct password | They are prompted for a TOTP code before receiving a token |
| AC-2 | A user enters an invalid TOTP | They click "Verify" | Login fails and the attempt is logged in the audit trail |

---

## Epic 1: Onboarding & Deal Setup

---

### US-001 — Create a New Deal
**Priority:** P0

> As an **Independent Sponsor**,
> I want to create a new deal workspace by entering a company name and deal type,
> so that all subsequent agent outputs are organised under this deal.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I am on the dashboard | I click "New Deal" | A modal appears asking for Deal Name, Company Name, Deal Type (M&A / IPO / Fundraising / Restructuring / Other), Industry, and Deal Stage |
| AC-2 | I have filled all required fields | I click "Create Deal" | A new deal workspace is created, its creation is written to the audit log, and I am redirected to its overview page |
| AC-3 | I leave "Company Name" blank | I click "Create Deal" | An inline validation error appears: "Company Name is required" |
| AC-4 | I submit a `POST /deals` request twice with the same `Idempotency-Key` header | Second request arrives | The server returns the original `201` response without creating a duplicate deal |
| AC-5 | Deal is created | I view the dashboard | The new deal appears with status "Active" and creation timestamp |

---

### US-002 — Upload Supporting Documents
**Priority:** P0

> As a **Boutique IB Associate**,
> I want to upload financial statements and company documents to a deal,
> so that the AI agents can analyse them as part of their work.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I am inside a deal workspace | I click "Upload Files" | A file picker opens accepting .pdf, .docx, .xlsx, .csv |
| AC-2 | I upload a valid file | Upload completes | A success toast appears, the file is listed under "Deal Documents", and it is queued for background RAG indexing |
| AC-3 | I upload a file over 50MB | Upload is attempted | An error states: "File exceeds 50MB limit" |
| AC-4 | I upload an unsupported file type | Upload is attempted | An error states: "Unsupported file type" |
| AC-5 | RAG indexing completes | I view the document list | The document shows "Indexed" status with chunk count |
| AC-6 | I mark a document as containing MNPI | I toggle the MNPI flag | The document is tagged; any agent that would send it to an external LLM API shows a consent prompt first |
| AC-7 | Upload completes | Audit log is checked | An `document_uploaded` event is recorded with user_id, org_id, filename, and timestamp |

---

## Epic 2: Financial Modeling

---

### US-003 — Generate a DCF Model
**Priority:** P0

> As an **Independent Sponsor**,
> I want to describe a target company and upload its financials,
> so that the AI builds a Discounted Cash Flow model I can download.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I have uploaded and indexed a financial Excel file | I click "Build DCF Model" | The system enqueues the task and returns a `run_id` immediately (non-blocking) |
| AC-2 | Processing completes | The model finishes | A downloadable .xlsx appears in "Outputs" with DCF, Assumptions, Sensitivity, and Comparables tabs |
| AC-3 | I open the DCF tab | I inspect the model | Revenue projections use mid-year discounting convention; WACC is computed with re-levered beta (Hamada equation) |
| AC-4 | Terminal value is > 85% of total EV | Model completes | A yellow warning badge states: "Terminal value dominates EV — review projection period and TGR" |
| AC-5 | Terminal growth rate ≥ WACC | I request a DCF | The system rejects the inputs with: "Terminal growth rate must be below WACC" |
| AC-6 | The Hallucination Guard runs | Model completes | Only DOCUMENT_EXTRACTED fields are verified against source; COMPUTED and INDUSTRY_DEFAULT fields are exempt |
| AC-7 | No financials are uploaded | I request a DCF | The system prompts: "Please upload and index financial statements to continue" |
| AC-8 | Output is generated | I inspect it | The last page of the Excel output contains the standard DCF disclaimer |

---

### US-004 — Generate an LBO Model
**Priority:** P1

> As a **Financial Consultant**,
> I want to generate an LBO model by inputting acquisition price and debt structure,
> so that I can evaluate private equity return scenarios.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I enter acquisition price, debt/equity split, hold period, and annual FCF projections | I click "Build LBO" | The agent generates an LBO model using `numpy_financial.irr()` on the full cash flow series |
| AC-2 | Sources & Uses are computed | I download the output | .xlsx contains: Sources & Uses (balanced to zero), Income Statement, Debt Schedule, Returns Summary with IRR and MOIC |
| AC-3 | I change the hold period | I regenerate | The IRR recalculates using the correct cash flow series for the new period |
| AC-4 | Debt service coverage ratio < 1.0x in any year | Model completes | A high-severity flag states: "DSCR below 1.0x in Year N — debt service concern" |

---

### US-005 — Comparable Company Analysis (CCA)
**Priority:** P1

> As a **Family Office Analyst**,
> I want the system to identify comparable public companies and pull their trading multiples,
> so that I can benchmark a target company's valuation.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I provide a company name and industry | I request CCA | The agent returns a table of 5–10 comparable companies with EV/EBITDA, P/E, EV/Revenue |
| AC-2 | Fewer than 6 comps are found | CCA completes | A warning states: "Fewer than 6 comparables — statistical reliability is limited" |
| AC-3 | CCA is generated | I download output | .xlsx contains a formatted comps table with median/mean/25th/75th percentile benchmarks highlighted in the financial semantic colour palette (green = high, red = low) |

---

## Epic 3: Pitchbook Generation

---

### US-006 — Generate a Full Pitchbook
**Priority:** P0

> As a **Boutique IB Associate**,
> I want to input a deal brief and have the AI generate a full pitchbook,
> so that I can present to a client within hours instead of days.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I have an active deal with indexed docs | I click "Generate Pitchbook" | The agent asks: purpose (sell-side / buy-side / capital raise) and format (PDF / PPTX) |
| AC-2 | I confirm purpose and format | Processing begins | The system displays a live progress indicator via SSE: "Building slide 3 of 12…" |
| AC-3 | Generation is complete | I open the preview | A PDF or PPTX preview renders in-browser; financial data uses the semantic colour palette (positive returns = green, negative = red, risk ratings = traffic-light) |
| AC-4 | I click "Download" | File downloads | The file is a well-formatted .pdf or .pptx with a compliance disclaimer on the final page |
| AC-5 | I dislike a slide | I click "Revise Slide" and provide a note | The agent regenerates only that slide; revision is logged in the audit trail |
| AC-6 | I request PPTX format | Output is generated | Individual slides are editable in PowerPoint without breaking the template |

---

### US-007 — Customise Pitchbook Tone and Structure
**Priority:** P1

> As a **Financial Consultant**,
> I want to specify tone and required slide types,
> so that the pitchbook matches my client's preferences.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | Before generating | I open "Pitchbook Settings" | I can select: tone (conservative / balanced / aggressive), include/exclude slide types, colour theme (B&W professional / financial semantic) |
| AC-2 | I exclude "Market Overview" | I generate | The pitchbook does not include that section |
| AC-3 | I select "aggressive" tone | I generate | The narrative uses stronger deal rationale language and higher valuation multiples |

---

## Epic 4: Due Diligence

---

### US-008 — Run Due Diligence on Uploaded Documents
**Priority:** P0

> As an **Independent Sponsor**,
> I want to upload a data room bundle and receive a due diligence risk report,
> so that I can identify red flags before making an offer.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I have uploaded and indexed 5+ documents | I click "Run Due Diligence" | The agent processes documents using RAG retrieval, not full-text injection |
| AC-2 | Analysis completes | I view the report | A categorised report shows: Financial Risks, Legal Risks, Operational Risks, each with severity ratings displayed in the semantic colour palette (High = red, Medium = amber, Low = green) |
| AC-3 | A red flag is detected | I click on it | The agent shows the source document, page reference, and retrieved chunk that triggered the flag |
| AC-4 | I dismiss a flag | I click "Mark as Reviewed" | The flag is archived with timestamp, reviewer user_id, and a note — logged in the audit trail |
| AC-5 | No documents are uploaded | I click "Run DD" | System blocks: "Please upload and index documents to the data room first" |

---

### US-009 — DD Checklist Completion Tracking
**Priority:** P1

> As a **Boutique IB Associate**,
> I want a standard DD checklist pre-populated by the agent,
> so that I can track reviewed vs. outstanding items.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | DD is initiated | Checklist loads | A standard IB DD checklist is shown: Financial Statements, Cap Table, Material Contracts, IP, Tax, Litigation, etc. |
| AC-2 | The agent finds a document matching an item | It auto-ticks the checklist | The item shows "Reviewed by AI" with confidence score and source document reference |
| AC-3 | An item is missing | Agent cannot find a matching doc | The item is flagged "Missing — Not Found in Data Room" in red |

---

## Epic 5: Market Research

---

### US-010 — Generate Industry Research Brief
**Priority:** P0

> As a **Financial Consultant**,
> I want to enter an industry sector and receive a structured research brief,
> so that I can quickly understand market context for a client meeting.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I enter "SaaS – HR Technology" | I click "Research Industry" | The agent produces a brief covering: market size, growth rate, key players, tailwinds/headwinds, recent M&A activity |
| AC-2 | Research completes | I download the brief | A .pdf is generated with the compliance disclaimer and semantic colour palette for data charts |
| AC-3 | I request a buyer universe | I click "Identify Strategic Buyers" | The agent returns 10–15 potential acquirers with rationale per buyer |

---

## Epic 6: Deal Documentation

---

### US-011 — Draft a CIM
**Priority:** P0

> As a **Boutique IB Associate**,
> I want the AI to draft the market overview and financial summary sections of a CIM,
> so that I have a strong first draft in under an hour.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I provide a deal brief + indexed financials | I click "Draft CIM" | The agent outputs: Executive Summary, Business Overview, Market Overview, Financial Summary — all sourced via RAG retrieval |
| AC-2 | I review the Financial Summary | Numbers are checked | All figures in the narrative match source documents; any unverified figure shows a yellow "⚠ unverified" badge |
| AC-3 | I want to edit a section | I click "Edit Section" | A text editor opens pre-populated with the AI-generated text for that section only |
| AC-4 | CIM is generated | Audit log is checked | A `cim_draft_generated` event is recorded with agent_run_id and output_id |

---

## Epic 7: Deal Coordination

---

### US-012 — Capture and Summarise Meeting Notes
**Priority:** P1

> As an **Independent Sponsor**,
> I want to paste raw meeting notes and receive a structured summary with action items,
> so that nothing falls through the cracks after a client call.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I paste unstructured notes | They are processed | Input is sanitised for prompt injection attempts before being sent to the LLM |
| AC-2 | Processing completes | I view output | Summary shows: Summary, Key Decisions, Action Items (owner + deadline if mentioned), Open Questions |
| AC-3 | An action item has a deadline | It is in the notes | The action item appears in the Deal Tracker automatically |
| AC-4 | I approve the summary | I click "Save to Deal" | The summary is saved to the deal's activity log with the approving user_id |

---

### US-013 — Deal Status Tracker
**Priority:** P1

> As a **Boutique IB Associate**,
> I want a live task board for my active deal,
> so that I always know what is outstanding and what is done.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I open a deal workspace | Tracker is visible | Tasks are grouped by: To Do / In Progress / Completed |
| AC-2 | An agent completes a run | Task auto-updates | The corresponding task moves to "Completed" with a link to the output file |
| AC-3 | I manually add a task | I type and press Enter | A new task card appears in "To Do" |
| AC-4 | A task's due_date has passed | I view the board | Overdue tasks display in red — the semantic danger colour |

---

## Epic 8: UI and UX

---

### US-014 — Professional Interface with Financial Semantic Colours
**Priority:** P0

> As any user,
> I want the application to use a professional interface that clearly communicates financial data,
> so that it is appropriate for a financial services context and easy to read.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I load the app | Page renders | UI chrome uses black/white/grey: bg `#FFFFFF`, text `#0A0A0A`, accents `#6B6B6B` |
| AC-2 | I view a financial chart or sensitivity table | Data renders | Financial data uses the semantic palette: positive/gains = `#1A7A4A`, negative/losses = `#C0392B`, neutral = `#2C5F8A` |
| AC-3 | I view a DD risk report | Risk badges render | High severity = red, Medium = amber, Low = green — matching the semantic palette |
| AC-4 | I hover over a button | I see feedback | Buttons use black fill with white text on hover; transitions are smooth |
| AC-5 | I use the app on a 13" laptop | No scroll or clipping | The layout is fully responsive at 1280px minimum width |

---

### US-015 — Agent Transparency (Reasoning Display)
**Priority:** P1

> As any user,
> I want to see the agent's reasoning steps before the final output is shown,
> so that I trust and understand what it produced.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | An agent task is running | I watch the UI | A "Thinking…" panel shows real-time SSE steps: "Retrieving context (8 chunks)…", "Applying DCF formula…" |
| AC-2 | Task completes | Reasoning is available | I can expand a "How was this created?" section under any output |
| AC-3 | Confidence score is below 0.6 | Output renders | A yellow warning badge states: "Low confidence — human review recommended" |
| AC-4 | MNPI document is used | Agent runs | A consent banner is shown before the run proceeds: "This analysis will use documents marked as MNPI. Confirm to proceed." |

---

## Epic 9: Compliance & Security *(NEW)*

---

### US-016 — Audit Trail Access
**Priority:** P1

> As an **organisation admin**,
> I want to view an immutable audit trail of all actions in my org,
> so that I can satisfy regulatory record-keeping requirements.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I am an org admin | I open the Audit Trail page | I see all events: logins, uploads, agent runs, output approvals, settings changes |
| AC-2 | I attempt to delete an audit log entry | Via any method | The server returns `405 Method Not Allowed` — audit logs are append-only |
| AC-3 | I export the audit trail | I click "Export" | A signed CSV is generated with all events and their integrity hashes |

---

### US-017 — Data Retention & Deletion
**Priority:** P1

> As an **organisation admin**,
> I want to set data retention policies and delete deal data when required,
> so that I comply with GDPR and internal data governance rules.

**Acceptance Criteria:**

| # | Given | When | Then |
|---|---|---|---|
| AC-1 | I archive a deal | I click "Archive Deal" | The deal is soft-deleted; documents and outputs are retained per the org's retention policy |
| AC-2 | A document's retention period expires | The nightly cleanup job runs | The document file is securely deleted; a tombstone record remains in the audit log |
| AC-3 | I submit a GDPR deletion request | Via the settings page | All personal data for the specified user is purged within 30 days; audit log entries are anonymised (user_id → "[DELETED]") |

---

*End of Document — 02-user-stories-and-acceptance-criteria.md*
