import json


class PromptBuilder:
    @staticmethod
    def get_system_prompt(agent_type: str) -> str:
        prompts = {
            "orchestrator": "You are the AIBAA Orchestrator. Route user requests to the correct specialized analyst agent.",
            "modeling": (
                "You are a senior Investment Banking Analyst specializing in building complex Financial Models "
                "(DCF, LBO, CCA). You are precise, methodical, and trust factual data over assumptions. "
                "You have deep expertise in Indian market valuations across sectors and you understand "
                "Indian GAAP / Ind AS financial statements. All monetary values must be in INR absolute "
                "numbers. You can handle both profitable and loss-making companies."
            ),
            "auditor": (
                "You are a senior Statutory Auditor with 15+ years of experience in Indian GAAP / Ind AS. "
                "Your job is to verify financial data extracted by a junior analyst. You are skeptical, "
                "precise, and follow double-entry accounting principles rigorously. You check citations, "
                "verify calculations, and flag any inconsistencies. You never accept a number without proof."
            ),
            "pitchbook": "You are an IB analyst creating client pitch presentations. You excel at summarizing complex data into high-impact insights.",
            "due_diligence": "You are a legal and financial due diligence reviewer. Your job is to read complex contracts and financial statements and flag potential risks categorized by severity.",
            "research": "You are an equity research analyst. Summarize market landscapes, identify key industry players, and compile buyer universes.",
            "doc_drafter": "You are drafting a Confidential Information Memorandum (CIM). You write with a professional, institutional tone suitable for enterprise buyers.",
            "coordination": "You are a deal coordination specialist. Summarize meetings, extract tasks, and track status.",
        }
        return prompts.get(agent_type, "You are an expert AI Analyst.")

    @staticmethod
    def build_modeling_dcf_prompt(parameters: dict, active_documents_context: str) -> str:
        """Legacy prompt kept for backward compatibility."""
        return f"""
Please execute a Discounted Cash Flow (DCF) model analysis based on the following context.

--- Parameters ---
Years to Project: {parameters.get('projection_years', 5)}
Terminal Growth Rate: {parameters.get('terminal_growth_rate', 0.030)}
Override WACC: {parameters.get('wacc_override', 'None')}
Currency: {parameters.get('currency', 'INR')}

--- Extracted Document Context ---
{active_documents_context}
---

INSTRUCTIONS:
You are a financial data extraction engine. Your only job is to extract historical financial data from the provided document context.

EXTRACTION RULES:
1. All monetary values must be in INR absolute numbers, not in lakhs or crores.
2. Revenue = "Revenue from Operations" from the Consolidated Statement of Profit and Loss.
3. EBITDA = PBT + Finance Costs + Depreciation and Amortisation.
4. Net Debt = Total Borrowings - Cash and Equivalents.
5. Shares Outstanding = exact number of equity shares from the Share Capital note.
6. Extract CapEx, D&A, Debt-to-Equity, Beta, and Base Fiscal Year if available.

If you cannot find a specific number, return null for that field. Do not make up numbers.

Return only a raw JSON object:
{{
  "historical_revenues": [year1_inr, year2_inr, year3_inr, year4_inr, year5_inr],
  "historical_ebitda_margins": [year1_margin, year2_margin, year3_margin, year4_margin, year5_margin],
  "net_debt": <number_or_null>,
  "total_borrowings": <number_or_null>,
  "cash_and_equivalents": <number_or_null>,
  "shares_outstanding": <exact_number_or_null>,
  "cap_ex_percent_rev": <decimal_or_null>,
  "da_percent_rev": <decimal_or_null>,
  "debt_to_equity": <decimal_or_null>,
  "beta": <decimal_or_null>,
  "base_fy": <integer_or_null>,
  "currency": "INR"
}}
""".strip()

    @staticmethod
    def build_preparer_prompt(parameters: dict, document_context: str, company_name: str = "") -> str:
        company_label = company_name or "the target company"

        return f"""
You are extracting financial data for {company_label} from annual report documents.

--- Document Context ---
{document_context}
---

You must follow this workflow and reconcile the numbers before you answer.

STEP 0: DETECT REPORTING UNITS
- Look for headers like "(₹ in Crores)", "(₹ in Lakhs)", "(in Millions)", "(in Thousands)" etc.
- This determines the multiplier: Crores = 10,000,000, Lakhs = 100,000, Millions = 1,000,000.
- All monetary values in your JSON output must be converted to absolute INR (i.e. multiply by the unit).
- For example, if the document says revenue is 117,055 in Crores, return 1170550000000 (117055 × 10000000).
- If the document says revenue is 1,17,055 in Lakhs, return 11705500000 (117055 × 100000).
- Report the detected unit in the "reporting_unit" field.

STEP 1: IDENTIFY BASE FIGURES
- Identify the company legal form and listing status first.
- Determine whether this is a large-cap, mid-cap, or small-cap company from the revenue scale.
- Extract the CIN if shown.
- Explicitly detect pre-IPO indicators such as DRHP/P-DRHP filing, proposed listing, and unlisted status.
- Find "Revenue from Operations" from the Consolidated Statement of Profit and Loss.
- Extract up to 5 years of historical revenue.
- State the page or section where you found each number.
- All monetary values must be returned in INR absolute numbers (after unit conversion).
- SANITY CHECK: For a large-cap Indian listed company, revenue should be ₹10,000 Crores+ (₹100B+). For mega-cap IT companies like TCS, Infosys, HCL, revenue is ₹50,000-2,00,000 Crores. For mega-cap diversified conglomerates (Reliance Industries, Adani Group, Tata Group), revenue can exceed ₹5,00,000 Crore (₹5 Lakh Crore). Always use CONSOLIDATED financials.

STEP 1B: PARTIAL-YEAR RUN-RATE DETECTION
- Scan ALL column headers for quarterly labels (e.g. "1Q26", "2Q26", "3Q26", "Q1FY26", "Q2FY26").
- If you find quarterly columns for a fiscal year that has NO corresponding full-year FY column yet:
  * Count n_quarters = number of quarters reported (e.g. 3 for 1Q26+2Q26+3Q26).
  * Sum revenue for those quarters → ytd_revenue.
  * Compute implied_annual_run_rate = (ytd_revenue / n_quarters) × 4.
  * Compute run_rate_growth_vs_last_fy = (implied_run_rate / last_completed_FY_revenue) − 1.
  * CRITICAL: If this run-rate differs from historical CAGR by more than 3 percentage points,
    the run-rate takes priority as the Year 1 baseline in your projections.
  * Report this in the partial_year_run_rate field.
- If NO partial quarterly data exists, set partial_year_run_rate to null.

STEP 2: EBITDA RECONCILIATION
- For each year, compute EBITDA as:
  a) Profit Before Tax
  b) plus Finance Costs
  c) plus Depreciation and Amortisation
  d) equals EBITDA
  e) EBITDA Margin = EBITDA / Revenue
- Negative margins are valid for loss-making companies.
- For IT services companies, EBITDA margins typically range from 18-28%.

STEP 3: BALANCE SHEET EXTRACTION
- Total Borrowings = Current Borrowings + Non-Current Borrowings (including term loans, debentures, commercial paper).
- CCPS Liability (or preference share liability measured as financial liability) must be extracted separately when disclosed.
- Lease Liabilities (IFRS 16 / Ind AS 116) — extract SEPARATELY as two distinct line items:
  * lease_liabilities_current: current portion (due within 12 months).
  * lease_liabilities_noncurrent: non-current portion (due after 12 months).
  * lease_liabilities: TOTAL = current + non-current (this feeds the equity bridge).
  * THESE ARE NOT FINANCIAL DEBT — do not merge with total_borrowings.
  * If zero, explicitly confirm "confirmed zero — company has no IFRS 16 lease obligations".
- Cash and Equivalents = Cash + Bank Balances + Current Investments + Other Liquid Investments.
- Include term deposits/bank balances with maturity > 12 months if they are unrestricted cash-like balances.
- IT services and technology companies typically hold enormous cash positions (30-60% of revenue in cash + investments).
  Look carefully in BOTH current and non-current sections for:
  * Cash and cash equivalents
  * Other bank balances / term deposits
  * Current investments / treasury investments / mutual fund units
  * Non-current investments (liquid mutual funds, bonds, government securities)
  * Earmarked/restricted balances (include only if unrestricted)
  Sum ALL of these to get the complete cash position. Missing even one category will significantly understate the value.
- Net Debt = Total Borrowings + Lease Liabilities + CCPS Liability - Cash and Equivalents.
- If the company is net-cash positive (cash > debt), Net Debt will be negative. This is valid and common for IT companies.
- Shares Outstanding:
  - Find "Issued, Subscribed and Fully Paid-Up" in the Share Capital note.
  - Extract the exact number of equity shares if shown.
  - If only amount and face value are shown, compute shares = share capital amount / face value per share.
  - CRITICAL CROSS-CHECK: Verify shares using EPS calculation:
    shares = Profit After Tax / Basic EPS
    This should match the Share Capital note. If it doesn't, explain the discrepancy.
  - Also extract diluted shares if available.
  - Return shares as an absolute number, not in crores or lakhs.
  - Large-cap Indian companies typically have 50 Crore to 700 Crore shares (500M to 7B).
  - Never infer shares from market cap, stock price, or external knowledge.
- Debt-to-Equity = (Total Borrowings + Lease Liabilities) / Shareholders' Equity.

STEP 4: CASH FLOW STATEMENT
- CapEx = Purchase of Property, Plant and Equipment or Additions to Fixed Assets.
- For asset-light IT services companies, CapEx is typically 3-5% of revenue.
- For capital-intensive sectors (energy, refinery, O2C chemicals, telecom, manufacturing, power,
  infrastructure, mining), CapEx is typically 8-12% of revenue. A figure below 5% for these
  sectors is a red flag — re-check the Cash Flow Statement carefully.
- cap_ex_percent_rev = CapEx / Latest Revenue.
- D&A from P&L and da_percent_rev = D&A / Latest Revenue.
- Operating Cash Flow (OCF) = "Cash generated from operations" or "Net cash from operating activities".
  Extract this as an absolute INR number. OCF is a critical cross-check:
  * For profitable IT companies, OCF is typically 80-120% of PAT.
  * FCF ≈ OCF - CapEx. If FCF seems unreasonably low, check whether OCF was missed.

STEP 5: MARKET PARAMETERS
- Beta from the document if available. If not available in the document, return null.
- For listed companies, if beta is not in the document, note the sector for estimation.
- WACC GUIDANCE BY SECTOR (for reference; the DCF engine will compute the actual WACC):
  * Large-cap diversified conglomerate (RIL, Adani, Tata): Beta ~1.0, NO size premium, WACC 10-13%
  * Large-cap energy/O2C/refinery: Beta ~1.0-1.1, WACC 10-12%
  * Large-cap telecom: Beta ~0.9-1.0, WACC 10-12%
  * Large-cap IT services: Beta ~0.85-1.0, WACC 9-13%
  * Mid/small-cap digital/fintech: Beta ~1.2-1.5, size premium 2-3%, WACC 14-20%
- Base Fiscal Year = the most recent completed fiscal year.
- If annual report contains fair-value valuation assumptions, extract:
  - discount_rate_reference
  - forecast_revenue_growth_range
  - terminal_growth_reference (default 3.0% for India GDP-aligned growth)
- Identify the company's primary industry/sector for appropriate WACC estimation.

STEP 6: SEGMENT REPORTING (for diversified companies)
- If the company has multiple business segments, extract the latest fiscal year segment data:
  * Segment name, segment revenue (₹ Crore), segment EBITDA/EBIT (₹ Crore), segment EBITDA margin.
  * Common segments for Indian conglomerates: O2C (Oil-to-Chemicals), Retail, Digital/Telecom,
    Oil & Gas E&P, Financial Services, Media & Entertainment, New Energy.
- Typical EBITDA margin ranges by segment:
  * O2C / Refining: 8-12%  |  Retail: 7-9%  |  Telecom/Digital: 35-50%
  * E&P / Upstream: 70-85%  |  IT services: 18-28%  |  FMCG: 15-22%
- Return segment data in the segment_revenues and segment_ebitda_margins fields.
- This is optional but highly important for accurate blended EBITDA margin computation.

STEP 6: CONFIDENCE SELF-ASSESSMENT
- 1.0 = exact number with citation
- 0.7 = calculated from cited figures
- 0.4 = estimated from partial data
- 0.0 = not found

Return only one JSON object with this structure:
{{
  "reconciliation_log": "<step-by-step notes as a text string>",
  "company_legal_form": {{"value": "<string_or_null>", "confidence": 0.95, "source": "Cover page / corporate information"}},
  "listing_status": {{"value": "<private|public|listed|unlisted|unknown>", "confidence": 0.8, "source": "Company name / CIN / annual report"}},
  "cin": {{"value": "<string_or_null>", "confidence": 0.95, "source": "Corporate information / annual report cover"}},
  "historical_revenues": {{"value": [...], "confidence": 0.9, "source": "P&L Statement, Page X"}},
  "historical_ebitda_margins": {{"value": [...], "confidence": 0.85, "source": "Calculated from PBT, finance cost, and D&A"}},
  "net_debt": {{"value": <number_or_null>, "confidence": 0.8, "source": "Balance Sheet / Notes"}},
  "total_borrowings": {{"value": <number_or_null>, "confidence": 0.8, "source": "Balance Sheet / Notes"}},
  "ccps_liability": {{"value": <number_or_null>, "confidence": 0.8, "source": "Financial liabilities note / fair value note"}},
  "lease_liabilities": {{"value": <number_or_null>, "confidence": 0.7, "source": "Lease note / Balance Sheet — TOTAL current + non-current"}},
  "lease_liabilities_current": {{"value": <number_or_null>, "confidence": 0.7, "source": "Balance Sheet current liabilities section"}},
  "lease_liabilities_noncurrent": {{"value": <number_or_null>, "confidence": 0.7, "source": "Balance Sheet non-current liabilities section"}},
  "cash_and_equivalents": {{"value": <number_or_null>, "confidence": 0.8, "source": "Balance Sheet / Notes"}},
  "partial_year_run_rate": {{"value": {{"partial_quarters_reported": <int_or_null>, "fiscal_year_partial": <int_or_null>, "ytd_revenue_inr": <number_or_null>, "implied_annual_run_rate": <number_or_null>, "run_rate_growth_vs_last_fy": <decimal_or_null>}} or null, "confidence": 0.85, "source": "Quarterly columns in data sheet"}},
  "shares_outstanding": {{"value": <number_or_null>, "confidence": 0.9, "source": "Share Capital note or computed from paid-up capital / face value"}},
  "diluted_shares_outstanding": {{"value": <number_or_null>, "confidence": 0.8, "source": "EPS note"}},
  "cap_ex_percent_rev": {{"value": <decimal_or_null>, "confidence": 0.7, "source": "Cash Flow Statement"}},
  "da_percent_rev": {{"value": <decimal_or_null>, "confidence": 0.7, "source": "P&L Statement"}},
  "debt_to_equity": {{"value": <decimal_or_null>, "confidence": 0.8, "source": "Balance Sheet"}},
  "beta": {{"value": <decimal_or_null>, "confidence": 0.5, "source": "Document or sector estimate"}},
  "discount_rate_reference": {{"value": <decimal_or_null>, "confidence": 0.7, "source": "Fair value measurement / valuation note"}},
  "forecast_revenue_growth_low": {{"value": <decimal_or_null>, "confidence": 0.7, "source": "Fair value sensitivity / valuation note"}},
  "forecast_revenue_growth_high": {{"value": <decimal_or_null>, "confidence": 0.7, "source": "Fair value sensitivity / valuation note"}},
  "terminal_growth_reference": {{"value": <decimal_or_null>, "confidence": 0.7, "source": "Fair value sensitivity / valuation note"}},
  "base_fy": {{"value": <integer_or_null>, "confidence": 0.95, "source": "Annual report cover or statements header"}},
  "reporting_unit": {{"value": "<crores|lakhs|millions|absolute>", "confidence": 0.95, "source": "Statement header / notes to accounts"}},
  "industry_sector": {{"value": "<string>", "confidence": 0.8, "source": "Company description / segment reporting"}},
  "profit_after_tax": {{"value": <number_or_null>, "confidence": 0.9, "source": "P&L Statement"}},
  "basic_eps": {{"value": <number_or_null>, "confidence": 0.9, "source": "P&L Statement / EPS note"}},
  "operating_cash_flow": {{"value": <number_or_null>, "confidence": 0.8, "source": "Cash Flow Statement"}},
  "segment_revenues": {{"value": {{"<segment_name>": <crore_value>, ...}} or null, "confidence": 0.75, "source": "Segment reporting note"}},
  "segment_ebitda_margins": {{"value": {{"<segment_name>": <decimal_ebitda_margin>, ...}} or null, "confidence": 0.70, "source": "Segment reporting note"}},
  "currency": "INR"
}}
""".strip()

    @staticmethod
    def build_auditor_prompt(extracted_data: dict, audit_trail: list, reconciliation_log: str, company_name: str = "") -> str:
        company_label = company_name or "the target company"
        audit_summary = json.dumps(audit_trail, indent=2, default=str)
        data_summary = json.dumps(extracted_data, indent=2, default=str)

        return f"""
You are auditing the financial data extraction for {company_label}.
A junior analyst extracted the following data. Your job is to verify it.

=== PREPARER RECONCILIATION WORK ===
{reconciliation_log}

=== EXTRACTED DATA ===
{data_summary}

=== AUDIT TRAIL ===
{audit_summary}

Audit checklist:
1. Citation verification
- Company type should be supported by legal name, CIN, or annual-report disclosures.
- Revenue should come from the Statement of Profit and Loss.
- Shares should come from the Share Capital note or an explicit paid-up-capital divided by face-value calculation.
- Net debt should come from balance sheet items.

2. Mathematical verification
- EBITDA = PBT + Finance Costs + D&A.
- Net Debt = Borrowings + Lease Liabilities - Cash.
- EBITDA Margin = EBITDA / Revenue.

3. Reasonableness checks
- Are the growth trends internally consistent?
- Are shares outstanding within a plausible Indian listed-company range?
- Do the assumptions look like extracted facts or unsupported estimates?

4. Lease liability completeness (IFRS 16 / Ind AS 116)
- Are lease_liabilities_current and lease_liabilities_noncurrent both extracted or explicitly confirmed zero?
- Is lease_liabilities = lease_liabilities_current + lease_liabilities_noncurrent?
- Flag if lease_liabilities is null but the company is known to operate physical offices or use equipment.

5. Run-rate revenue anchoring
- If partial_year_run_rate is present: verify implied_annual_run_rate = (ytd_revenue_inr / partial_quarters_reported) × 4.
- Flag if run_rate_growth_vs_last_fy differs from historical CAGR by more than 5 percentage points without explanation.

Return only a JSON object:
{{
  "overall_status": "approved" | "flagged" | "rejected",
  "field_verdicts": [
    {{
      "field": "<field_name>",
      "status": "approved" | "flagged" | "rejected",
      "auditor_confidence": <0.0-1.0>,
      "reason": "<explanation>"
    }}
  ],
  "auditor_notes": "<overall summary>",
  "corrections": {{
    "<field_name>": <corrected_value_or_null>
  }}
}}
""".strip()

    @staticmethod
    def build_dcf_validator_prompt(
        dcf_output: dict,
        extracted_data: dict,
        wacc: float,
        run_rate_data: dict | None,
    ) -> str:
        """Phase 3 post-DCF validation prompt.

        Validates the completed DCF model output against source data and
        known financial logic bounds. Returns a structured JSON verdict
        with PASS/FAIL for each check so modeling.py can auto-correct.
        """
        import json as _json

        run_rate_block = _json.dumps(run_rate_data, indent=2) if run_rate_data else "null"

        total_borrowings = extracted_data.get("total_borrowings") or 0
        lease_total = extracted_data.get("lease_liabilities") or 0
        cash = extracted_data.get("cash_and_equivalents") or 0
        bs_net_cash = cash - total_borrowings - lease_total

        return f"""
You are a DCF model quality checker. Given the model output and the source extraction data,
run the five checks below. Return ONLY a JSON object — no prose outside the JSON.

=== DCF MODEL OUTPUT ===
{_json.dumps(dcf_output, indent=2, default=str)}

=== SOURCE EXTRACTION DATA ===
enterprise_value: {dcf_output.get('implied_enterprise_value')}
equity_value: {dcf_output.get('implied_equity_value')}
wacc_used: {wacc}
total_borrowings (BS): {total_borrowings}
lease_liabilities (BS): {lease_total}
cash_and_equivalents (BS): {cash}
bs_net_cash (cash - debt - leases): {bs_net_cash}
net_debt_in_model: {dcf_output.get('net_debt')}
year1_revenue_projection: {(dcf_output.get('projections') or {{}}).get('revenue', [None])[0] if dcf_output.get('projections') else None}
historical_revenues: {extracted_data.get('historical_revenues')}
historical_ebitda_margins: {extracted_data.get('historical_ebitda_margins')}
year1_ebitda_margin_pct: {(dcf_output.get('projections') or {{}}).get('ebitda_margin_pct', [None])[0] if dcf_output.get('projections') else None}
partial_year_run_rate: {run_rate_block}

=== CHECKS ===
Run each check and return PASS or FAIL with specific numbers:

CHECK 1 — Revenue Year 1 vs Run-Rate Anchor:
  If partial_year_run_rate is not null:
    model_year1_revenue = year1_revenue_projection
    source_run_rate = partial_year_run_rate.implied_annual_run_rate
    delta_pct = abs(model_year1_revenue - source_run_rate) / source_run_rate
    PASS if delta_pct <= 0.07 (within 7% of run-rate), else FAIL.
  If partial_year_run_rate is null: status = "SKIPPED".

CHECK 2 — EBITDA Margin Year 1 vs Trailing Average:
  trailing_avg_margin = mean(historical_ebitda_margins[-4:]) if >=4 values else mean(all)
  model_year1_margin = year1_ebitda_margin_pct / 100
  delta_abs = abs(model_year1_margin - trailing_avg_margin)
  PASS if delta_abs <= 0.02 (within 2 percentage points), else FAIL.

CHECK 3 — Net Cash / Net Debt Reconciliation:
  model_net_debt = net_debt_in_model
  bs_derived_net_debt = total_borrowings + lease_liabilities - cash_and_equivalents
  delta = abs(model_net_debt - bs_derived_net_debt)
  tolerance = max(abs(bs_derived_net_debt) * 0.05, 1000000000)
  PASS if delta <= tolerance, else FAIL.

CHECK 4 — Lease Liabilities Captured in Equity Bridge:
  PASS if lease_liabilities > 0 AND net_debt_in_model includes lease_liabilities
       (i.e. net_debt_in_model >= total_borrowings + lease_liabilities - cash_and_equivalents - tolerance).
  PASS if lease_liabilities == 0 (confirmed zero).
  FAIL if lease_liabilities > 0 but appears excluded from net_debt.

CHECK 5 — WACC Plausibility for Indian Large-Cap:
  PASS if 0.10 <= wacc_used <= 0.17.
  FAIL otherwise with note on expected range.

Return this exact JSON structure:
{{
  "checks": {{
    "revenue_year1_vs_runrate": {{
      "model_value": <number_or_null>,
      "source_runrate": <number_or_null>,
      "delta_pct": <decimal_or_null>,
      "status": "PASS" | "FAIL" | "SKIPPED"
    }},
    "ebitda_margin_year1_vs_trailing": {{
      "model_margin": <decimal_or_null>,
      "trailing_avg_margin": <decimal_or_null>,
      "delta_abs": <decimal_or_null>,
      "status": "PASS" | "FAIL"
    }},
    "net_cash_reconciliation": {{
      "model_net_debt": <number_or_null>,
      "bs_derived_net_debt": <number_or_null>,
      "delta": <number_or_null>,
      "status": "PASS" | "FAIL"
    }},
    "lease_liabilities_in_bridge": {{
      "bs_lease_total": <number_or_null>,
      "captured_in_model": <boolean>,
      "status": "PASS" | "FAIL"
    }},
    "wacc_range_check": {{
      "wacc": <decimal>,
      "status": "PASS" | "FAIL",
      "note": "<acceptable range 10-17% for India large-cap>"
    }}
  }},
  "overall": "PASS" | "FAIL",
  "corrections_needed": ["<list FAIL items with specific fix instructions, or empty list>"]
}}
""".strip()

    # ------------------------------------------------------------------
    # NEW AGENT PROMPTS — Phase 4 agents
    # ------------------------------------------------------------------

    @staticmethod
    def build_pitchbook_prompt(deal_info: dict, dcf_result: dict, doc_context: str) -> str:
        company = deal_info.get("company_name", "the target company")
        deal_type = deal_info.get("deal_type", "M&A")
        industry = deal_info.get("industry", "")
        bear_val = dcf_result.get("bear", {}).get("valuation", {}).get("equity_value", "N/A") if dcf_result else "N/A"
        base_val = dcf_result.get("base", {}).get("valuation", {}).get("equity_value", "N/A") if dcf_result else "N/A"
        bull_val = dcf_result.get("bull", {}).get("valuation", {}).get("equity_value", "N/A") if dcf_result else "N/A"

        return f"""
You are creating a pitchbook for {company} ({deal_type} deal, {industry} sector).

--- Document Context ---
{doc_context[:60000]}
---

DCF Valuation Summary (if available):
Bear Case Equity Value: {bear_val}
Base Case Equity Value: {base_val}
Bull Case Equity Value: {bull_val}

Create a professional investment banking pitchbook with 4 sections.
Return ONLY valid JSON:

{{
  "company_overview": {{
    "headline": "<one-sentence investment thesis>",
    "description": "<2-3 paragraph business description>",
    "key_highlights": ["<highlight 1>", "<highlight 2>", "<highlight 3>", "<highlight 4>"],
    "business_model": "<how the company makes money>",
    "competitive_position": "<market position and moat>"
  }},
  "industry_analysis": {{
    "market_size": "<TAM in appropriate units>",
    "growth_rate": "<market CAGR>",
    "key_trends": ["<trend 1>", "<trend 2>", "<trend 3>"],
    "competitive_landscape": "<description of competitive dynamics>",
    "tailwinds": ["<tailwind 1>", "<tailwind 2>"],
    "headwinds": ["<headwind 1>", "<headwind 2>"]
  }},
  "financial_highlights": {{
    "revenue_trend": "<description of revenue trajectory>",
    "ebitda_trend": "<description of margin trajectory>",
    "balance_sheet": "<leverage / cash position>",
    "key_metrics": ["<metric 1>", "<metric 2>", "<metric 3>"]
  }},
  "valuation_summary": {{
    "methodology": "DCF + Comparable Companies Analysis",
    "bear_case": "{bear_val}",
    "base_case": "{base_val}",
    "bull_case": "{bull_val}",
    "key_value_drivers": ["<driver 1>", "<driver 2>", "<driver 3>"],
    "transaction_rationale": "<why this deal makes strategic sense>"
  }}
}}
""".strip()

    @staticmethod
    def build_dd_prompt(doc_context: str) -> str:
        return f"""
You are a senior due diligence reviewer analyzing deal documents for potential risks.

--- Document Context ---
{doc_context[:80000]}
---

Conduct a comprehensive due diligence risk assessment. Analyze the documents for:
1. Financial risks (accounting quality, revenue sustainability, debt covenants, liquidity)
2. Operational risks (key person dependency, supply chain, customer concentration)
3. Legal risks (litigation, regulatory issues, IP ownership, contract terms)
4. Market risks (competitive threats, market saturation, macro sensitivity)

Return ONLY valid JSON:
{{
  "overall_risk_score": <number 0-10, where 10 = highest risk>,
  "risk_rating": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
  "financial_risks": [
    {{"risk": "<description>", "severity": "high|medium|low", "evidence": "<document citation>", "mitigation": "<suggested mitigation>"}}
  ],
  "operational_risks": [
    {{"risk": "<description>", "severity": "high|medium|low", "evidence": "<document citation>", "mitigation": "<suggested mitigation>"}}
  ],
  "legal_risks": [
    {{"risk": "<description>", "severity": "high|medium|low", "evidence": "<document citation>", "mitigation": "<suggested mitigation>"}}
  ],
  "market_risks": [
    {{"risk": "<description>", "severity": "high|medium|low", "evidence": "<document citation>", "mitigation": "<suggested mitigation>"}}
  ],
  "red_flags": [
    {{"flag": "<critical issue>", "impact": "<potential deal impact>", "recommendation": "BLOCK_DEAL|PRICE_ADJUSTMENT|RENEGOTIATE|MONITOR"}}
  ],
  "positive_factors": ["<strength 1>", "<strength 2>", "<strength 3>"],
  "summary": "<2-3 sentence overall DD conclusion>"
}}
""".strip()

    @staticmethod
    def build_research_prompt(deal_info: dict, doc_context: str, mode: str) -> str:
        company = deal_info.get("company_name", "the target company")
        industry = deal_info.get("industry", "Technology")
        deal_type = deal_info.get("deal_type", "M&A")

        if mode == "industry_brief":
            return f"""
You are an equity research analyst writing an industry brief for {company} in the {industry} sector.

--- Document Context ---
{doc_context[:60000]}
---

Write a comprehensive industry brief. Return ONLY valid JSON:
{{
  "sector": "{industry}",
  "market_size": "<estimated TAM with source>",
  "market_growth_cagr": "<historical and forecast CAGR>",
  "growth_drivers": ["<driver 1>", "<driver 2>", "<driver 3>", "<driver 4>"],
  "competitive_landscape": "<paragraph describing competitive dynamics>",
  "key_players": [
    {{"name": "<company>", "market_position": "<#1/#2/niche>", "key_strength": "<differentiator>"}}
  ],
  "regulatory_environment": "<key regulations affecting sector>",
  "technology_disruption": "<digital/AI/tech trends>",
  "risks": ["<macro risk>", "<sector risk>", "<regulatory risk>"],
  "investment_thesis": "<1-2 paragraph thesis for investing in this sector>"
}}
""".strip()
        else:  # buyer_universe
            return f"""
You are an M&A analyst compiling a buyer universe for {company} ({industry}, {deal_type}).

--- Document Context ---
{doc_context[:60000]}
---

Identify potential acquirers/investors. Return ONLY valid JSON:
{{
  "strategic_buyers": [
    {{
      "name": "<company name>",
      "rationale": "<why they would acquire>",
      "fit_score": <1-10>,
      "synergies": "<expected synergies>",
      "deal_type": "acquisition|merger|partnership"
    }}
  ],
  "financial_buyers": [
    {{
      "name": "<PE/VC firm name>",
      "rationale": "<investment thesis>",
      "typical_check_size": "<range>",
      "portfolio_fit": "<existing portfolio companies>"
    }}
  ],
  "summary": "<paragraph on most likely buyer profile>"
}}
""".strip()

    @staticmethod
    def build_cim_section_prompt(
        deal_info: dict,
        doc_context: str,
        dcf_result: dict,
        section: str,
    ) -> str:
        company = deal_info.get("company_name", "the target company")
        industry = deal_info.get("industry", "Technology")

        section_instructions = {
            "executive_summary": (
                f"Write a compelling 3-4 paragraph executive summary for {company}. "
                "Cover: investment highlights, business overview, financial performance, and the opportunity."
            ),
            "business_description": (
                f"Write a detailed 4-5 paragraph business description for {company}. "
                "Cover: history, products/services, business model, revenue streams, go-to-market strategy."
            ),
            "management": (
                f"Write a 2-3 paragraph management team section for {company}. "
                "Cover: key executives, their backgrounds, track record, and organizational strengths."
            ),
            "financials": (
                f"Write a 3-4 paragraph financial overview for {company}. "
                "Cover: revenue growth, EBITDA margins, balance sheet strength, capex, and financial trajectory."
            ),
            "market": (
                f"Write a 3-4 paragraph market opportunity section for {company} in the {industry} sector. "
                "Cover: market size, growth drivers, competitive position, and addressable opportunity."
            ),
        }

        instruction = section_instructions.get(section, f"Write a professional CIM section for {section}.")

        return f"""
You are drafting a Confidential Information Memorandum (CIM) for {company}.
Write with an institutional tone suitable for sophisticated buyers and investors.

--- Document Context ---
{doc_context[:50000]}
---

SECTION TO DRAFT: {section.upper().replace("_", " ")}

Instructions: {instruction}

Return ONLY the prose text (no JSON). Write 3-5 substantial paragraphs.
Use professional investment banking language. Be specific with data points from the documents.
Do not include section headers. Do not use bullet points — write in flowing paragraphs.
""".strip()

    @staticmethod
    def build_coordination_prompt(doc_context: str) -> str:
        return f"""
You are a deal coordination specialist extracting structured information from meeting notes and deal documents.

--- Document Context ---
{doc_context[:80000]}
---

Extract all action items, decisions, and follow-ups. Return ONLY valid JSON:
{{
  "meeting_summary": "<2-3 paragraph summary of key discussion points>",
  "tasks": [
    {{
      "title": "<clear actionable task title>",
      "description": "<detail of what needs to be done>",
      "priority": "high|medium|low",
      "owner": "<person or role responsible>",
      "due_date": "<YYYY-MM-DD or 'TBD'>",
      "category": "financial|legal|operational|due_diligence|documentation|other"
    }}
  ],
  "decisions": [
    {{
      "decision": "<what was decided>",
      "rationale": "<why>",
      "decided_by": "<who>"
    }}
  ],
  "open_questions": [
    {{
      "question": "<unresolved question>",
      "owner": "<who needs to answer>",
      "urgency": "high|medium|low"
    }}
  ],
  "next_steps": ["<next step 1>", "<next step 2>", "<next step 3>"]
}}
""".strip()

    @staticmethod
    def build_lbo_extraction_prompt(doc_context: str, parameters: dict) -> str:
        return f"""
You are extracting financial data for an LBO (Leveraged Buyout) analysis.

--- Document Context ---
{doc_context[:80000]}
---

LBO Parameters provided by the user:
- Entry EV/EBITDA: {parameters.get('entry_ev_ebitda', 'not specified')}
- Equity Contribution: {parameters.get('equity_contribution_pct', 'not specified')}
- Senior Debt (x EBITDA): {parameters.get('senior_debt_ebitda', 'not specified')}
- Exit EV/EBITDA: {parameters.get('exit_ev_ebitda', 'not specified')}
- Hold Period (years): {parameters.get('projection_years', 5)}

Extract the following from the documents. All monetary values must be in absolute INR.
Return ONLY valid JSON:
{{
  "entry_ebitda": <LTM EBITDA in absolute INR>,
  "revenue_ltm": <LTM Revenue in absolute INR>,
  "total_borrowings": <total debt in absolute INR>,
  "cash_and_equivalents": <cash in absolute INR>,
  "net_debt": <total_borrowings - cash, can be negative>,
  "shares_outstanding": <exact number or null>,
  "ebitda_margin_ltm": <decimal e.g. 0.25>,
  "revenue_growth_historical": <3-year CAGR as decimal>,
  "reporting_unit": "<Crores|Lakhs|Millions|absolute>",
  "base_fy": <fiscal year integer e.g. 2024>,
  "extraction_confidence": <0.0-1.0>,
  "notes": "<any important caveats or assumptions>"
}}
""".strip()

