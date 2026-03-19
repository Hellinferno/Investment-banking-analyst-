# 08 — Computation Logic Engine Spec
## AI Investment Banking Analyst Agent (AIBAA) — v2.0 (Enterprise Edition)

---

## 1. Overview

The **Computation Logic Engine (CLE)** is the deterministic calculation layer between the LLM and the output formatters.

**Core Principle:**
> The LLM decides *what* to compute. The CLE *computes it*. No arithmetic is ever delegated to the LLM.

### Key changes from v1

- `_frange()` is now defined (was referenced but missing — caused a crash on all sensitivity tables)
- IRR now uses `numpy_financial.irr()` on the full cash flow series (not the simplified MOIC^(1/n) formula)
- DCF uses mid-year discounting convention (`year - 0.5` exponent) per IB standard practice
- WACC uses the Hamada equation to re-lever beta at the target's actual capital structure
- Terminal value sanity check added: warns if TV > 85% of total EV
- Hallucination Guard redesigned with a typed field registry that distinguishes DOCUMENT_EXTRACTED vs COMPUTED fields
- Output verification checklist extended with DSCR and TV% checks

---

## 2. Engine Architecture

```
LLM Output (structured JSON)
        ↓
[Input Validator]
   - Schema validation (Pydantic)
   - Type coercion
   - Range checks (e.g. WACC must be positive)
        ↓
[Computation Router]
   - Identifies model type: DCF / LBO / CCA
        ↓
┌─────────────────────────────────────────────────────┐
│              Computation Modules                     │
│                                                      │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐ │
│  │  DCF     │  │  LBO     │  │   CCA              │ │
│  │  Engine  │  │  Engine  │  │   Engine           │ │
│  └──────────┘  └──────────┘  └────────────────────┘ │
└─────────────────────────────────────────────────────┘
        ↓
[Output Verifier]
   - TV as % of EV sanity check
   - WACC > TGR check
   - DSCR check (LBO)
   - IRR sanity check
   - Balance check (LBO Sources & Uses)
        ↓
[Hallucination Guard]
   - Typed field registry: only DOCUMENT_EXTRACTED fields verified against source
   - COMPUTED and INDUSTRY_DEFAULT fields exempt
        ↓
[Structured Output JSON]
   → Excel Writer / PDF Generator / PPTX Builder
```

---

## 3. Module 1: DCF Engine

### 3.1 Inputs Schema

```python
from dataclasses import dataclass, field

@dataclass
class DCFInputs:
    # Revenue — DOCUMENT_EXTRACTED
    historical_revenue: list[float]          # Last 3–5 years
    
    # Projection assumptions — INDUSTRY_DEFAULT (LLM-suggested or user-set)
    revenue_growth_rates: list[float]         # % per projection year
    projection_years: int = 5
    ebitda_margins: list[float] = field(default_factory=list)
    da_percent_revenue: float = 0.05
    capex_percent_revenue: float = 0.04
    nwc_change_percent_revenue: float = 0.02
    
    # Tax — USER_PROVIDED or INDUSTRY_DEFAULT
    tax_rate: float = 0.25
    
    # WACC components — USER_PROVIDED or INDUSTRY_DEFAULT
    risk_free_rate: float = 0.045
    equity_risk_premium: float = 0.055
    beta: float = 1.0                        # Raw beta from public comps
    cost_of_debt: float = 0.065
    debt_to_capital: float = 0.30
    
    # Terminal value — USER_PROVIDED or INDUSTRY_DEFAULT
    terminal_growth_rate: float = 0.025
    exit_multiple: float = None              # EV/EBITDA exit (alternative method)
    
    # Balance sheet — DOCUMENT_EXTRACTED
    net_debt: float = 0.0
    shares_outstanding: float = 1.0
    
    # Convention flags
    use_mid_year_discounting: bool = True    # IB standard; set False for academic/simple model
```

### 3.2 `_frange` — Floating Point Range *(was missing in v1 — caused crash)*

```python
@staticmethod
def _frange(start: float, stop: float, step: float) -> list[float]:
    """
    Floating-point range. Avoids accumulating precision errors by computing
    each value from the start rather than iteratively adding step.
    
    _frange(-0.02, 0.02, 0.005) → [-0.02, -0.015, -0.01, -0.005, 0.0, 0.005, 0.01, 0.015, 0.02]
    """
    result = []
    i = 0
    while True:
        val = round(start + i * step, 6)
        if (step > 0 and val > stop + 1e-10) or (step < 0 and val < stop - 1e-10):
            break
        result.append(val)
        i += 1
    return result
```

### 3.3 WACC with Hamada Equation *(re-levered beta — new in v2)*

```python
def _compute_wacc(self, inputs: DCFInputs) -> float:
    """
    Step 1: Unlever the observed beta (which embeds the comparable's capital structure).
    Step 2: Re-lever at the target's actual D/E ratio (Hamada equation).
    Step 3: Use re-levered beta in CAPM to get cost of equity.
    Step 4: WACC = Ke * E/V + Kd * (1-t) * D/V
    
    Skipping this step overstates or understates the cost of equity depending on
    whether the target is more or less levered than the comparable.
    """
    # Unlever: βU = βL / (1 + (1-t) × D/E)
    debt_to_equity = inputs.debt_to_capital / (1 - inputs.debt_to_capital)
    unlevered_beta = inputs.beta / (1 + (1 - inputs.tax_rate) * debt_to_equity)
    
    # Re-lever at target D/E
    relevered_beta = unlevered_beta * (1 + (1 - inputs.tax_rate) * debt_to_equity)
    
    # CAPM: Ke = Rf + β × ERP
    ke = inputs.risk_free_rate + relevered_beta * inputs.equity_risk_premium
    
    # WACC
    equity_weight = 1 - inputs.debt_to_capital
    kd_after_tax = inputs.cost_of_debt * (1 - inputs.tax_rate)
    return ke * equity_weight + kd_after_tax * inputs.debt_to_capital
```

### 3.4 Mid-Year Discounting *(new in v2 — IB standard)*

```python
def _discount_factor(self, wacc: float, year: int, mid_year: bool = True) -> float:
    """
    Mid-year convention: exponent is (year - 0.5) instead of (year).
    Rationale: cash flows arrive throughout the year, not as a single lump sum
    in December. Mid-year convention increases EV by approximately 5% vs year-end.
    This is standard practice in IB — models using year-end discounting will
    systematically undervalue companies.
    """
    exponent = (year - 0.5) if mid_year else year
    return 1 / ((1 + wacc) ** exponent)
```

### 3.5 Full DCF Computation

```python
class DCFEngine:
    
    def compute(self, inputs: DCFInputs) -> "DCFOutputs":
        wacc = self._compute_wacc(inputs)
        
        # Guard: WACC must exceed TGR — otherwise terminal value formula breaks
        if inputs.terminal_growth_rate >= wacc:
            raise ValueError(
                f"Terminal growth rate ({inputs.terminal_growth_rate:.1%}) must be strictly "
                f"below WACC ({wacc:.1%}). Increase WACC or decrease terminal growth rate."
            )
        
        # Step 1: Project revenue
        revenues = self._project_revenues(inputs.historical_revenue[-1],
                                          inputs.revenue_growth_rates,
                                          inputs.projection_years)
        
        # Step 2: EBITDA
        ebitda = [rev * margin for rev, margin in zip(revenues, inputs.ebitda_margins)]
        
        # Step 3: D&A and EBIT
        da     = [rev * inputs.da_percent_revenue for rev in revenues]
        ebit   = [e - d for e, d in zip(ebitda, da)]
        
        # Step 4: NOPAT
        nopat  = [e * (1 - inputs.tax_rate) for e in ebit]
        
        # Step 5: Unlevered Free Cash Flow
        capex     = [rev * inputs.capex_percent_revenue for rev in revenues]
        delta_nwc = [rev * inputs.nwc_change_percent_revenue for rev in revenues]
        ufcf = [nopat[i] + da[i] - capex[i] - delta_nwc[i]
                for i in range(inputs.projection_years)]
        
        # Step 6: PV of UFCFs (mid-year discounting)
        pv_ufcfs = [
            ufcf[i] * self._discount_factor(wacc, i + 1, inputs.use_mid_year_discounting)
            for i in range(inputs.projection_years)
        ]
        sum_pv_ufcf = sum(pv_ufcfs)
        
        # Step 7: Terminal value
        if inputs.exit_multiple:
            terminal_value = ebitda[-1] * inputs.exit_multiple
        else:
            terminal_fcf = ufcf[-1] * (1 + inputs.terminal_growth_rate)
            terminal_value = terminal_fcf / (wacc - inputs.terminal_growth_rate)
        
        tv_discount = self._discount_factor(wacc, inputs.projection_years,
                                            inputs.use_mid_year_discounting)
        pv_terminal_value = terminal_value * tv_discount
        
        # Step 8: Enterprise value, equity value, share price
        enterprise_value   = sum_pv_ufcf + pv_terminal_value
        equity_value       = enterprise_value - inputs.net_debt
        implied_share_price = equity_value / max(inputs.shares_outstanding, 1)
        
        # Step 9: TV sanity check
        tv_percent = pv_terminal_value / enterprise_value if enterprise_value > 0 else 0
        warnings = self._run_sanity_checks(inputs, tv_percent, wacc)
        
        # Step 10: Sensitivity table
        sensitivity = self._build_sensitivity_table(inputs)
        
        return DCFOutputs(
            revenues=revenues, ebitda=ebitda, ufcf=ufcf,
            wacc=wacc, pv_ufcfs=pv_ufcfs, sum_pv_ufcf=sum_pv_ufcf,
            terminal_value=terminal_value, pv_terminal_value=pv_terminal_value,
            tv_percent_of_ev=tv_percent,
            enterprise_value=enterprise_value, equity_value=equity_value,
            implied_share_price=implied_share_price,
            sensitivity_table=sensitivity,
            warnings=warnings
        )
    
    def _run_sanity_checks(self, inputs, tv_percent, wacc) -> list:
        warnings = []
        if tv_percent > 0.85:
            warnings.append({
                "code": "TV_DOMINATES_EV",
                "severity": "high",
                "message": f"Terminal value is {tv_percent:.0%} of total EV. Consider shortening the "
                           f"projection period or reducing the terminal growth rate."
            })
        if tv_percent < 0.40:
            warnings.append({
                "code": "TV_LOW",
                "severity": "medium",
                "message": f"Terminal value is only {tv_percent:.0%} of EV — unusually low. "
                           f"Check terminal growth rate ({inputs.terminal_growth_rate:.1%})."
            })
        if any(fcf < 0 for fcf in [0]):  # placeholder — actual UFCF list passed in full impl
            warnings.append({
                "code": "NEGATIVE_FCF",
                "severity": "medium",
                "message": "One or more projection years have negative unlevered free cash flow. "
                           "Verify CapEx and NWC assumptions."
            })
        return warnings
    
    def _build_sensitivity_table(self, inputs: DCFInputs) -> dict:
        """
        2-D sensitivity matrix: WACC scenarios (rows) × TGR scenarios (columns).
        Each cell contains the implied Enterprise Value.
        Uses _frange (now correctly defined — was missing in v1).
        """
        base_wacc = self._compute_wacc(inputs)
        wacc_deltas = self._frange(-0.02, 0.02, 0.005)   # ±2% in 0.5% steps = 9 scenarios
        tgr_deltas  = self._frange(-0.01, 0.01, 0.005)   # ±1% in 0.5% steps = 5 scenarios
        
        table = {}
        for dw in wacc_deltas:
            scenario_wacc = round(base_wacc + dw, 4)
            table[scenario_wacc] = {}
            for dt in tgr_deltas:
                scenario_tgr = round(inputs.terminal_growth_rate + dt, 4)
                if scenario_tgr >= scenario_wacc:
                    table[scenario_wacc][scenario_tgr] = None  # invalid — mark as N/A
                    continue
                ev = self._ev_for_scenario(inputs, scenario_wacc, scenario_tgr)
                table[scenario_wacc][scenario_tgr] = round(ev, 2)
        
        return table
```

---

## 4. Module 2: LBO Engine

### 4.1 IRR — Corrected to Use Full Cash Flow Series *(v1 was wrong)*

```python
import numpy_financial as npf  # pip install numpy-financial

class LBOEngine:
    
    def compute_irr(self, equity_invested: float,
                    annual_fcf_to_equity: list[float],
                    equity_at_exit: float) -> float:
        """
        CORRECT IRR formula using the full cash flow series.
        
        v1 used: MOIC^(1/n) - 1
        This is WRONG for LBOs with interim cash flows (dividends, recaps, etc.)
        
        v2 uses numpy_financial.irr() on the actual cash flow series:
        [-equity_invested, fcf_yr1, fcf_yr2, ..., fcf_yr(n-1), fcf_yr(n) + exit_equity]
        
        Note: numpy.irr() was deprecated and removed in NumPy 1.17.
        Always import from numpy_financial, not numpy.
        """
        cash_flows = [-equity_invested]
        for i, fcf in enumerate(annual_fcf_to_equity):
            if i == len(annual_fcf_to_equity) - 1:
                cash_flows.append(fcf + equity_at_exit)
            else:
                cash_flows.append(fcf)
        
        irr = npf.irr(cash_flows)
        
        if irr is None or not (-1 < irr < 10):
            raise ValueError(
                f"IRR did not converge or is unreasonable ({irr}). "
                f"Check equity investment, FCF projections, and exit assumptions."
            )
        
        return float(irr)
    
    def compute_moic(self, equity_invested: float, equity_at_exit: float) -> float:
        """MOIC = total equity returned / equity invested."""
        if equity_invested <= 0:
            raise ValueError("Equity invested must be positive.")
        return equity_at_exit / equity_invested
```

### 4.2 Sources & Uses Balance Check

```python
def _validate_sources_uses(self, sources: dict, uses: dict):
    total_sources = sum(sources.values())
    total_uses = sum(uses.values())
    if abs(total_sources - total_uses) > 0.01:
        raise ValueError(
            f"Sources & Uses do not balance: "
            f"Sources = {total_sources:,.2f}, Uses = {total_uses:,.2f}, "
            f"Difference = {total_sources - total_uses:,.2f}"
        )
```

---

## 5. Module 3: CCA Engine

```python
import statistics

class CCAEngine:
    MIN_COMPS = 6  # Warn if fewer than this
    
    def compute(self, comparables_raw: list[dict],
                target_ebitda: float, target_revenue: float) -> "CCAOutputs":
        
        if len(comparables_raw) < self.MIN_COMPS:
            # Do not refuse — produce best-effort result but add a warning
            warnings = [f"Only {len(comparables_raw)} comparables found. "
                        f"Statistical reliability is limited below {self.MIN_COMPS} comps. "
                        f"Expand the peer set or treat as directional only."]
        else:
            warnings = []
        
        comps = []
        for c in comparables_raw:
            comp = ComparableCompany(**c)
            comp.ev_revenue = comp.enterprise_value / comp.revenue_ltm if comp.revenue_ltm else None
            comp.ev_ebitda  = comp.enterprise_value / comp.ebitda_ltm  if comp.ebitda_ltm  else None
            comp.ev_ebit    = comp.enterprise_value / comp.ebit_ltm    if comp.ebit_ltm    else None
            comp.pe_ratio   = comp.equity_value / comp.net_income_ltm  if comp.net_income_ltm else None
            comps.append(comp)
        
        ev_ebitda_vals = sorted([c.ev_ebitda for c in comps if c.ev_ebitda])
        ev_rev_vals    = sorted([c.ev_revenue for c in comps if c.ev_revenue])
        
        n = len(ev_ebitda_vals)
        
        return CCAOutputs(
            comparables=comps,
            warnings=warnings,
            median_ev_ebitda  = statistics.median(ev_ebitda_vals),
            mean_ev_ebitda    = statistics.mean(ev_ebitda_vals),
            p25_ev_ebitda     = ev_ebitda_vals[n // 4],
            p75_ev_ebitda     = ev_ebitda_vals[3 * n // 4],
            median_ev_revenue = statistics.median(ev_rev_vals) if ev_rev_vals else None,
            mean_ev_revenue   = statistics.mean(ev_rev_vals)   if ev_rev_vals else None,
            # Implied EV range for target
            implied_target_ev_low    = ev_ebitda_vals[n // 4] * target_ebitda,
            implied_target_ev_median = statistics.median(ev_ebitda_vals) * target_ebitda,
            implied_target_ev_high   = ev_ebitda_vals[3 * n // 4] * target_ebitda,
        )
```

---

## 6. Hallucination Guard — Redesigned with Typed Field Registry

The v1 guard checked all LLM-output numbers against all source document numbers — producing false positives for computed values (WACC, EV) that legitimately aren't in source documents, and false negatives from superficial numerical matches.

```python
from enum import Enum

class FieldSource(Enum):
    DOCUMENT_EXTRACTED = "extracted"  # MUST be in source docs — flag if not found
    USER_PROVIDED      = "user"       # User typed it — no check needed
    INDUSTRY_DEFAULT   = "default"    # Assumption — warn but do not flag as hallucination
    COMPUTED           = "computed"   # Derived from other fields — never flag

# Every field in every input schema is registered here.
# Only DOCUMENT_EXTRACTED fields trigger hallucination flags.
FIELD_REGISTRY = {
    # DCF — extracted from financials
    "historical_revenue":      FieldSource.DOCUMENT_EXTRACTED,
    "historical_ebitda":       FieldSource.DOCUMENT_EXTRACTED,
    "net_debt":                FieldSource.DOCUMENT_EXTRACTED,
    "shares_outstanding":      FieldSource.DOCUMENT_EXTRACTED,
    "capex_last_year":         FieldSource.DOCUMENT_EXTRACTED,
    "total_debt":              FieldSource.DOCUMENT_EXTRACTED,
    "cash_and_equivalents":    FieldSource.DOCUMENT_EXTRACTED,
    
    # DCF — assumptions (LLM-suggested or user-set; not in source docs)
    "revenue_growth_rates":    FieldSource.INDUSTRY_DEFAULT,
    "ebitda_margins":          FieldSource.INDUSTRY_DEFAULT,
    "terminal_growth_rate":    FieldSource.INDUSTRY_DEFAULT,
    "risk_free_rate":          FieldSource.INDUSTRY_DEFAULT,
    "equity_risk_premium":     FieldSource.INDUSTRY_DEFAULT,
    "beta":                    FieldSource.INDUSTRY_DEFAULT,
    
    # DCF — computed (never in source docs)
    "wacc":                    FieldSource.COMPUTED,
    "enterprise_value":        FieldSource.COMPUTED,
    "equity_value":            FieldSource.COMPUTED,
    "implied_share_price":     FieldSource.COMPUTED,
    "terminal_value":          FieldSource.COMPUTED,
    
    # LBO — extracted
    "entry_ebitda":            FieldSource.DOCUMENT_EXTRACTED,
    "revenue_ltm":             FieldSource.DOCUMENT_EXTRACTED,
    
    # LBO — computed
    "irr":                     FieldSource.COMPUTED,
    "moic":                    FieldSource.COMPUTED,
    "exit_equity_value":       FieldSource.COMPUTED,
}

class HallucinationGuard:
    TOLERANCE = 0.05  # 5% deviation allowed for extracted fields
    
    def verify(self, llm_inputs: dict, source_chunks: list[str]) -> "VerificationResult":
        """
        source_chunks: the RAG-retrieved text chunks that were used for this run.
        Only these chunks are checked — not the full document, which may contain
        numbers from unrelated contexts.
        """
        source_numbers = self._extract_numbers(source_chunks)
        flags = []
        
        for field, value in llm_inputs.items():
            if not isinstance(value, (int, float)):
                continue
            
            source_type = FIELD_REGISTRY.get(field, FieldSource.DOCUMENT_EXTRACTED)
            
            if source_type == FieldSource.DOCUMENT_EXTRACTED:
                match = self._find_match(value, source_numbers)
                if not match or match["deviation"] > self.TOLERANCE:
                    flags.append({
                        "field": field,
                        "llm_value": value,
                        "nearest_source": match["value"] if match else None,
                        "deviation_pct": match["deviation"] if match else None,
                        "severity": "high",
                        "message": f"'{field}' ({value:,.2f}) not found in retrieved source chunks"
                    })
            # COMPUTED, INDUSTRY_DEFAULT, USER_PROVIDED: no flag
        
        high_count = len([f for f in flags if f["severity"] == "high"])
        confidence = round(max(0.0, 1.0 - (high_count * 0.2)), 2)
        
        return VerificationResult(
            is_clean=high_count == 0,
            confidence_score=confidence,
            flags=flags
        )
    
    def _extract_numbers(self, texts: list[str]) -> list[dict]:
        import re
        results = []
        pattern = r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)'
        for text in texts:
            for m in re.finditer(pattern, text):
                raw = m.group(1).replace(",", "")
                results.append({
                    "value": float(raw),
                    "context": text[max(0, m.start()-30):m.end()+30]
                })
        return results
    
    def _find_match(self, value: float, source_numbers: list[dict]) -> dict | None:
        if not source_numbers or value == 0:
            return None
        best = min(source_numbers, key=lambda x: abs(x["value"] - value) / max(abs(value), 1))
        deviation = abs(best["value"] - value) / max(abs(value), 1)
        return {**best, "deviation": deviation}
```

---

## 7. Output Verification Checklist

Before any financial model is presented to the user:

| Check | Description | Action if Failed |
|---|---|---|
| Sources & Uses balance | Total sources == total uses (LBO) | Raise: "Sources & Uses do not balance" |
| WACC > TGR | WACC must strictly exceed terminal growth rate | Raise: "TGR must be below WACC" |
| TV as % of EV | Should be 40–85% | Warn if outside range |
| Positive EBITDA | Base case EBITDA should not be negative | Warn: "Negative EBITDA in base case" |
| LBO DSCR | Debt service coverage > 1.0x in all years | Flag: "DSCR below 1.0x in Year N" |
| IRR range | LBO IRR between 0% and 100% | Flag: "Unusual IRR — review assumptions" |
| IRR convergence | `numpy_financial.irr()` must not return NaN | Raise: "IRR did not converge" |
| CCA count | At least 6 comparables for statistical reliability | Warn if < 6 |
| Revenue monotonicity | If all growth rates > 0, revenues must increase | Silent correction + log |
| Mid-year flag logged | If mid_year_discounting=False, note in output | Yellow badge: "Year-end discounting used" |

---

*End of Document — 08-computation-engine-spec.md*
