"""Run historical financial regressions with explicit, offline test fixtures.

The legacy scripts assumed no-key LLM calls selected company profiles. Production
no longer does that. Inject those profiles here only, keeping real extraction
failures visible in the app and keeping tests independent of API credentials.
"""
from pathlib import Path
import runpy

import pytest

from engine.llm import _get_deterministic_fallback_response


@pytest.mark.parametrize("filename", [
    "test_preipo_boat_logic.py", "test_turnaround_dcf_logic.py",
    "test_infosys_largecap_logic.py", "test_reliance_largecap_logic.py",
    "test_hcl_largecap_logic.py", "test_private_company_logic.py", "test_dcf_fixes.py",
])
def test_historical_modeling_regression(filename, monkeypatch):
    monkeypatch.setattr("agents.modeling.ask_llm",
                        lambda system, prompt: _get_deterministic_fallback_response(prompt))
    runpy.run_path(str(Path(__file__).resolve().parents[1] / filename), run_name="__main__")


def test_repeated_dcf_runs_preserve_results_and_prior_exports(monkeypatch):
    from agents.modeling import FinancialModelingAgent
    from store import Deal, store
    monkeypatch.setattr("agents.modeling.ask_llm",
                        lambda system, prompt: _get_deterministic_fallback_response(prompt))
    deal = Deal(name="Repeated fixture", company_name="Synthetic Fixture Company")
    store.deals[deal.id] = deal
    runs, paths = [], []
    for _ in range(2):
        agent = FinancialModelingAgent(deal.id, {"parameters": {}})
        agent.run()
        saved = store.agent_runs[agent.run_id]
        assert saved.status == "completed"
        assert saved.input_payload["valuation_result"]["header"]["enterprise_value"]
        runs.append(saved)
        paths.append(next(Path(o.storage_path) for o in store.outputs.values() if o.agent_run_id == agent.run_id))
    assert paths[0] != paths[1]
    assert all(p.exists() and p.stat().st_size > 0 for p in paths)
    assert runs[0].input_payload["valuation_result"]["parallel_analysis"]["comps_worker"]["data_basis"] == "illustrative_sector_assumptions"
