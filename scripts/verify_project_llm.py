"""Opt-in live contract checks across the project with synthetic source data.

Uses the real preparer/auditor helpers, prompt builders, and DCF/LBO engines.
Eight LLM calls cover extraction, auditing, LBO, pitchbook, two CIM sections,
coordination, and post-DCF validation. It does not read private deal documents.
"""
import argparse
import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import time

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]

FINANCIALS = """SYNTHETIC TEST DATA; no real company.
Synthetic Systems Limited, unlisted public limited company, INR in crores.
Company provides software subscriptions. No executive names or market-size data are supplied.
Consolidated Profit and Loss, page 10:
Fiscal year           FY2021 FY2022 FY2023 FY2024 FY2025
Revenue from operations 100 110 121 133.1 146.41
Profit before tax        12 13.2 14.52 15.972 17.5692
Finance costs            2 2.2 2.42 2.662 2.9282
Depreciation/amortization 6 6.6 7.26 7.986 8.7846
Profit after tax FY2025: 13.1769 crores. Basic EPS FY2025: INR 13.1769 per share.
Balance Sheet, page 20: current borrowings 10 crores, non-current borrowings 20 crores.
Lease liabilities current 2 crores and non-current 3 crores; no CCPS liabilities.
Cash 5 crores; unrestricted bank balances 3 crores; liquid current investments 12 crores.
Shareholders equity 100 crores. Share capital note, page 25: exactly 10,000,000 equity shares,
paid-up capital 10 crores, face value INR 10 per share; no dilution.
Cash Flow, page 30: FY2025 CapEx 5.8564 crores; operating cash flow 17 crores.
No quarterly financials, beta, forecast growth or discount rate are provided.
"""
DEAL = {"company_name": "Synthetic Systems Limited", "deal_name": "Synthetic validation", "deal_type": "ma", "industry": "Software"}
EXPECTED = {"historical_revenues": [1e9, 1.1e9, 1.21e9, 1.331e9, 1.4641e9],
            "historical_ebitda_margins": [0.2] * 5, "net_debt": 150e6,
            "total_borrowings": 300e6, "lease_liabilities": 50e6,
            "lease_liabilities_current": 20e6, "lease_liabilities_noncurrent": 30e6,
            "cash_and_equivalents": 200e6, "shares_outstanding": 10e6,
            "cap_ex_percent_rev": 0.04, "da_percent_rev": 0.06, "base_fy": 2025}


def parsed(raw):
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text[text.find("{"):text.rfind("}") + 1])


def matches(actual, expected):
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(matches(a, b) for a, b in zip(actual, expected))
    return isinstance(actual, (int, float)) and math.isclose(actual, expected, rel_tol=1e-5, abs_tol=1e-5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["openrouter", "nvidia"], required=True)
    parser.add_argument("--tasks", nargs="+", help="Run only named workflow checks; preserve other saved results.")
    parser.add_argument("--results", type=Path, default=ROOT / "docs" / "llm-project-validation.json")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    os.environ["LLM_PROVIDER"] = args.provider
    sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
    from agents.extractor import PreparerAgent
    from agents.auditor import AuditorAgent
    from agents.prompt_builder import PromptBuilder
    from engine.llm import ask_llm
    from engine.dcf import DCFEngine
    from engine.lbo import LBOEngine
    from agents.lbo_modeling import LBOModelingAgent

    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "providers": {}}
    if args.results.exists():
        report["providers"] = json.loads(args.results.read_text(encoding="utf-8")).get("providers", {})
    previous_rows = report["providers"].get(args.provider, {}).get("checks", [])
    rows = [row for row in previous_rows if args.tasks and row["workflow"] not in args.tasks]
    report["providers"][args.provider] = {"model": os.getenv("OPENROUTER_MODEL" if args.provider == "openrouter" else "NVIDIA_MODEL"),
                                            "financial_model": os.getenv("OPENROUTER_FINANCIAL_MODEL" if args.provider == "openrouter" else "NVIDIA_FINANCIAL_MODEL"),
                                            "synthetic_inputs_only": True, "checks": rows}
    def check(name, fn):
        if args.tasks and name not in args.tasks:
            return
        started = time.monotonic()
        try:
            details = fn()
            row = {"workflow": name, "passed": bool(details.pop("passed")), **details}
        except Exception as exc:
            row = {"workflow": name, "passed": False, "error_type": type(exc).__name__}
        row["latency_seconds"] = round(time.monotonic() - started, 2)
        if args.provider == "openrouter":
            from engine import openrouter
            row["observed_model"] = openrouter._client.last_model if openrouter._client else None
        else:
            row["observed_model"] = os.getenv("NVIDIA_FINANCIAL_MODEL") if name in {"financial_extraction", "financial_auditor", "lbo_extraction_and_engine", "dcf_engine_and_validator"} else os.getenv("NVIDIA_MODEL")
        rows.append(row)
        args.results.parent.mkdir(parents=True, exist_ok=True)
        args.results.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"provider": args.provider, **row}), flush=True)

    extraction = {}
    def extract():
        extraction.update(PreparerAgent.extract(PromptBuilder.get_system_prompt("modeling"), FINANCIALS, {}, DEAL["company_name"]))
        data = extraction.get("extracted_data", {})
        checks = {key: matches(data.get(key), value) for key, value in EXPECTED.items()}
        checks["unknown_beta_not_invented"] = data.get("beta") is None
        return {"passed": all(checks.values()), "numeric_checks": checks,
                "mismatches": {key: {"actual": data.get(key), "expected": EXPECTED.get(key)} for key, ok in checks.items() if not ok},
                "audit_citations": len(extraction.get("audit_trail", []))}
    check("financial_extraction", extract)

    def audit():
        fixture = copy.deepcopy(extraction)
        fixture["extracted_data"] = dict(EXPECTED) | {"net_debt": 1e6}
        fixture["extraction_mode"] = "llm"
        result = AuditorAgent.audit(PromptBuilder.get_system_prompt("auditor"), fixture, DEAL["company_name"])
        caught = result.get("overall_status") in {"flagged", "rejected"} and (
            "net_debt" in result.get("corrections", {}) or any(v.get("field") == "net_debt" and v.get("status") != "approved" for v in result.get("field_verdicts", [])))
        return {"passed": caught, "overall_status": result.get("overall_status"), "deliberate_net_debt_error_caught": caught}
    check("financial_auditor", audit)

    def lbo():
        prepared = PreparerAgent.extract(PromptBuilder.get_system_prompt("modeling"), FINANCIALS, {}, DEAL["company_name"])
        result = LBOModelingAgent._from_preparer(prepared)
        correct = matches(result.get("entry_ebitda"), 292.82e6) and matches(result.get("revenue_ltm"), 1.4641e9)
        output = LBOEngine(entry_ebitda=result["entry_ebitda"], revenue_ltm=result["revenue_ltm"], entry_ev_ebitda=8.0).run()
        return {"passed": correct and math.isfinite(output["irr_pct"]), "ebitda_and_revenue_exact": correct,
                "extracted_ebitda": result.get("entry_ebitda"), "extracted_revenue": result.get("revenue_ltm"), "deterministic_irr_pct": output["irr_pct"]}
    check("lbo_extraction_and_engine", lbo)

    # Compute DCF from exact source values, rather than trusting LLM arithmetic.
    engine = DCFEngine(EXPECTED["historical_revenues"], EXPECTED["historical_ebitda_margins"], cap_ex_percent_rev=0.04, da_percent_rev=0.06, base_fy=2025)
    projections = engine.build_projections(projection_years=5)
    dcf = engine.calculate_valuation(projections["projections"]["ufcf"], 0.12, 0.03, net_debt=150e6, shares_outstanding=10e6)
    dcf["projections"] = projections["projections"]
    dcf["net_debt"] = 150e6
    scenarios = {name: {"valuation": {"equity_value": dcf["implied_equity_value"] * factor}} for name, factor in (("bear", 0.8), ("base", 1), ("bull", 1.2))}

    def validate_dcf():
        result = parsed(ask_llm(PromptBuilder.get_system_prompt("auditor"), PromptBuilder.build_dcf_validator_prompt(dcf, EXPECTED, 0.12, None), task="financial"))
        required = {"revenue_year1_vs_runrate", "ebitda_margin_year1_vs_trailing", "net_cash_reconciliation", "lease_liabilities_in_bridge", "wacc_range_check"}
        checks = result.get("checks", {})
        valid = required.issubset(checks) and checks["revenue_year1_vs_runrate"]["status"] == "SKIPPED" and all(checks[key]["status"] == "PASS" for key in required - {"revenue_year1_vs_runrate"})
        return {"passed": valid, "overall": result.get("overall"), "deterministic_enterprise_value": dcf["implied_enterprise_value"]}
    check("dcf_engine_and_validator", validate_dcf)

    def pitchbook():
        result = parsed(ask_llm(PromptBuilder.get_system_prompt("pitchbook"), PromptBuilder.build_pitchbook_prompt(DEAL, scenarios, FINANCIALS), task="draft"))
        required = {"company_overview", "industry_analysis", "financial_highlights", "valuation_summary"}
        valid = required.issubset(result) and all(isinstance(result[key], dict) for key in required)
        market_size = str(result.get("industry_analysis", {}).get("market_size", ""))
        missing_acknowledged = bool(re.search(r"not (?:provided|disclosed|available)|unknown|not specified|n/a|unavailable", market_size, re.I))
        return {"passed": valid and missing_acknowledged, "four_section_contract": valid,
                "missing_market_size_not_invented": missing_acknowledged, "market_size_text": market_size[:150]}
    check("pitchbook", pitchbook)

    for section in ("financials", "management"):
        def cim(section=section):
            text = ask_llm(PromptBuilder.get_system_prompt("doc_drafter"), PromptBuilder.build_cim_section_prompt(DEAL, FINANCIALS, scenarios, section), task="draft")
            acknowledged = bool(re.search(r"not (?:provided|disclosed|available)|no (?:specific|details|information)|unspecified|unavailable", text, re.I))
            return {"passed": len(text.strip()) > 150 and not text.lstrip().startswith("{") and (section != "management" or acknowledged), "section": section, "characters": len(text),
                    "unknown_details_acknowledged": acknowledged}
        check("cim_" + section, cim)

    def coordination():
        notes = "Synthetic meeting 2026-10-10: Alice will send the financial statements by 2026-10-15 (high priority). Bob will review the lease note by 2026-10-16 (medium priority). Decision: defer valuation until both tasks finish. No other attendees or actions."
        result = parsed(ask_llm(PromptBuilder.get_system_prompt("coordination"), PromptBuilder.build_coordination_prompt(notes), task="coordination"))
        tasks = result.get("tasks", [])
        owners = {task.get("owner") for task in tasks}
        dates = {task.get("due_date") for task in tasks}
        correct = len(tasks) == 2 and owners == {"Alice", "Bob"} and dates == {"2026-10-15", "2026-10-16"}
        return {"passed": correct, "task_count": len(tasks), "owners_and_dates_exact": correct}
    check("meeting_coordination", coordination)
    if not all(row["passed"] for row in rows):
        raise SystemExit("One or more live project contract checks failed; inspect the report before selecting models.")


if __name__ == "__main__":
    main()
