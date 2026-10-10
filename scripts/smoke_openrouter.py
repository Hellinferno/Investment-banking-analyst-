"""Opt-in live integration check using previously saved public search evidence."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))

from engine.llm import llm_configured, llm_provider
from tools.research_evidence import build_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence_json", type=Path)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    artifact = json.loads(args.evidence_json.read_text(encoding="utf-8"))
    evidence = artifact["evidence"]
    if evidence["mode"] != "live" or llm_provider() != "openrouter" or not llm_configured():
        raise SystemExit("Requires live saved evidence and a configured OpenRouter provider.")
    report = build_report(evidence, synthesize=True)
    known = {source["id"] for source in evidence["sources"]}
    result = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "provider": llm_provider(),
        "evidence_run": artifact.get("research_run_id"),
        "new_serpapi_calls": 0,
        "source_count": len(known),
        "synthesis_mode": report["synthesis_mode"],
        "finding_count": len(report["findings"]),
        "citations_valid": all(set(f["source_ids"]).issubset(known) for f in report["findings"]),
        "analyst_warning_present": any("support for each statement" in w for w in report["warnings"]),
    }
    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    if result["synthesis_mode"] != "llm" or not result["citations_valid"]:
        raise SystemExit("Live synthesis check failed; source-excerpt fallback remained available.")


if __name__ == "__main__":
    main()
