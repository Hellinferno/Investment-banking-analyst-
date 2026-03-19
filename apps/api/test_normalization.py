"""
Test the normalization layer that fixes LLM unit mismatches.
Tests revenues in crores, margins as percentages, shares in crores, etc.
"""
import sys
sys.path.insert(0, "src")

from agents.modeling import FinancialModelingAgent
from engine.dcf import DCFEngine

print("=" * 60)
print("NORMALIZATION LAYER TESTS")
print("=" * 60)

# ─── Test 1: Revenue normalization ──────────────
print("\n1. Revenue Normalization:")

# Case A: LLM returns in Crores (e.g. 2789.61)
revs_crores = [2588, 2910, 2960, 2914.06, 2789.61]
normalized = FinancialModelingAgent._normalize_revenues(revs_crores)
print(f"   Input (Crores):  {revs_crores}")
print(f"   Output (Absolute): {[round(r, 2) for r in normalized]}")
assert normalized[4] > 27_000_000_000, f"FAIL: Revenue should be ~27.9B, got {normalized[4]}"
print("   ✓ PASS")

# Case B: LLM returns in absolute INR (already correct)
revs_abs = [25_880_000_000, 29_100_000_000, 27_896_100_000]
normalized2 = FinancialModelingAgent._normalize_revenues(revs_abs)
assert normalized2 == revs_abs, "Should not modify already-absolute values"
print("   ✓ Absolute INR passes through unchanged")

# ─── Test 2: EBITDA Margin normalization ────────
print("\n2. EBITDA Margin Normalization:")

# Case A: LLM returns as percentages (e.g. 13.69)
margins_pct = [16, 14, 13, 13.3, 13.69]
normalized = FinancialModelingAgent._normalize_margins(margins_pct)
print(f"   Input (%):    {margins_pct}")
print(f"   Output (dec): {[round(m, 4) for m in normalized]}")
assert 0.13 < normalized[4] < 0.14, f"FAIL: Margin should be ~0.1369, got {normalized[4]}"
print("   ✓ PASS")

# Case B: LLM returns as decimals (correct)
margins_dec = [0.16, 0.14, 0.13, 0.133, 0.1369]
normalized2 = FinancialModelingAgent._normalize_margins(margins_dec)
assert normalized2 == margins_dec, "Should not modify already-decimal values"
print("   ✓ Decimal values pass through unchanged")

# Case C: Negative margins (loss-making company)
margins_neg = [-22, -15, -8, -3, 2]
normalized3 = FinancialModelingAgent._normalize_margins(margins_neg)
assert abs(normalized3[0] - (-0.22)) < 0.001, f"FAIL: Expected -0.22, got {normalized3[0]}"
print("   ✓ Negative margins (loss-making) normalized correctly")

# ─── Test 3: Shares normalization ────────────────
print("\n3. Shares Outstanding Normalization:")

# Case A: LLM returns in Crores (e.g. 24.89)
shares_cr = 24.89
normalized = FinancialModelingAgent._normalize_shares(shares_cr)
print(f"   Input (Crores): {shares_cr}")
print(f"   Output (Absolute): {normalized}")
assert abs(normalized - 248_900_000) < 100_000, f"FAIL: Expected ~248.9M, got {normalized}"
print("   ✓ PASS")

# Case B: LLM returns absolute (e.g. 248938586)
shares_abs = 248_938_586
normalized2 = FinancialModelingAgent._normalize_shares(shares_abs)
assert normalized2 == shares_abs, f"Should pass through, got {normalized2}"
print("   ✓ Absolute shares pass through unchanged")

# Case C: LLM returns in millions (e.g. 248.9)
shares_mil = 248.9
normalized3 = FinancialModelingAgent._normalize_shares(shares_mil)
print(f"   248.9 (ambiguous) → {normalized3}")
assert normalized3 > 1_000_000, "Should auto-detect as crores"
print("   ✓ Small number auto-detected as crores")

# ─── Test 4: Percentage field normalization ──────
print("\n4. CapEx/D&A Percentage Normalization:")

# 4.0 should become 0.04
assert abs(FinancialModelingAgent._normalize_pct_field(4.0) - 0.04) < 0.001
print("   ✓ 4.0 → 0.04")

# 0.04 should stay 0.04
assert abs(FinancialModelingAgent._normalize_pct_field(0.04) - 0.04) < 0.001
print("   ✓ 0.04 unchanged")

# 8.0 should become 0.08
assert abs(FinancialModelingAgent._normalize_pct_field(8.0) - 0.08) < 0.001
print("   ✓ 8.0 → 0.08")

# ─── Test 5: JSON Parsing ────────────────────────
print("\n5. Robust JSON Parsing:")

# DeepSeek think block
resp1 = '<think>Let me analyze...</think>\n{"historical_revenues": [2789], "shares_outstanding": 24.89}'
parsed = FinancialModelingAgent._parse_llm_response(resp1)
assert parsed["shares_outstanding"] == 24.89
print("   ✓ DeepSeek <think> block stripped")

# Markdown fences
resp2 = '```json\n{"shares_outstanding": 248900000}\n```'
parsed2 = FinancialModelingAgent._parse_llm_response(resp2)
assert parsed2["shares_outstanding"] == 248900000
print("   ✓ Markdown fences stripped")

# Extra text around JSON
resp3 = 'Here is the data:\n{"net_debt": 0}\nLet me know if you need more.'
parsed3 = FinancialModelingAgent._parse_llm_response(resp3)
assert parsed3["net_debt"] == 0
print("   ✓ Extra text stripped, JSON extracted")

# ─── Test 6: Full DCF with Relaxo data ───────────
print("\n6. Full DCF — Relaxo Footwears (Normalized):")

norm_revs = FinancialModelingAgent._normalize_revenues([2588, 2910, 2960, 2914.06, 2789.61])
norm_margins = FinancialModelingAgent._normalize_margins([16, 14, 13, 13.3, 13.69])
norm_shares = FinancialModelingAgent._normalize_shares(24.89)

engine = DCFEngine(
    historical_revenues=norm_revs,
    historical_ebitda_margins=norm_margins,
    tax_rate=0.25,
    cap_ex_percent_rev=FinancialModelingAgent._normalize_pct_field(2.21),
    da_percent_rev=FinancialModelingAgent._normalize_pct_field(5.68),
    nwc_percent_rev=0.10,
    base_fy=2025,
)

cagr = engine.calculate_cagr(norm_revs)
print(f"   Revenue CAGR: {cagr*100:.2f}%")

wacc_b = engine.calculate_wacc_breakdown(
    risk_free_rate=0.07, equity_risk_premium=0.055,
    beta=0.95, cost_of_debt=0.09, debt_to_equity=0.0
)
wacc = wacc_b["wacc"]
print(f"   WACC: {wacc*100:.2f}%")

proj = engine.build_projections(7, 0.025)
val = engine.calculate_valuation(proj["projections"]["ufcf"], wacc, 0.025, 0, norm_shares)

print(f"   Shares: {norm_shares/1e7:.2f} Cr")
print(f"   EV: Rs {val['implied_enterprise_value']/1e7:,.2f} Cr")
print(f"   Equity: Rs {val['implied_equity_value']/1e7:,.2f} Cr")
print(f"   Share Price: Rs {val['implied_share_price']:.2f}")

# ─── Summary ─────────────────────────────────────
print(f"\n{'=' * 60}")
print("ALL NORMALIZATION TESTS PASSED ✓")
print(f"{'=' * 60}")
