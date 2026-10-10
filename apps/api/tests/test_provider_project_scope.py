from types import SimpleNamespace

import httpx
import pytest

from agents.auditor import AuditorAgent
from agents.prompt_builder import PromptBuilder
from engine import llm
from engine.request_budget import RequestBudget


def test_auditor_cannot_approve_contradictory_net_debt():
    result = AuditorAgent._apply_arithmetic_checks(
        {"overall_status": "approved", "field_verdicts": [{"field": "net_debt", "status": "approved"}], "corrections": {}},
        {"net_debt": 1e6, "total_borrowings": 300e6, "lease_liabilities": 50e6, "cash_and_equivalents": 200e6})
    assert result["overall_status"] == "flagged"
    assert result["corrections"]["net_debt"] == 150e6
    assert result["field_verdicts"][0]["status"] == "flagged"


def test_auditor_checks_ccps_and_lease_components_without_inventing_missing_data():
    data = {"net_debt": 0, "total_borrowings": 100, "lease_liabilities": 10,
            "lease_liabilities_current": 4, "lease_liabilities_noncurrent": 8,
            "ccps_liability": 5, "cash_and_equivalents": 20}
    result = AuditorAgent._apply_arithmetic_checks({"overall_status": "approved"}, data)
    assert result["corrections"] == {"net_debt": 97, "lease_liabilities": 12}
    assert AuditorAgent._apply_arithmetic_checks({"overall_status": "flagged"}, {"net_debt": None}) == {"overall_status": "flagged"}


def test_auditor_rejects_an_inconsistent_llm_correction():
    result = AuditorAgent._apply_arithmetic_checks(
        {"overall_status": "approved", "corrections": {"net_debt": 999}},
        {"net_debt": 95, "total_borrowings": 100, "lease_liabilities": 10, "cash_and_equivalents": 15})
    assert result["overall_status"] == "flagged" and result["corrections"]["net_debt"] == 95


def test_lbo_reuses_unit_aware_preparer_and_derives_ebitda():
    from agents.lbo_modeling import LBOModelingAgent
    result = LBOModelingAgent._from_preparer({"extracted_data": {
        "historical_revenues": [1e9, 1.4641e9], "historical_ebitda_margins": [0.2, 0.2]}})
    assert result["revenue_ltm"] == 1.4641e9 and result["entry_ebitda"] == 292.82e6


@pytest.mark.parametrize("data", [
    {}, {"historical_revenues": [1e9], "historical_ebitda_margins": []},
    {"historical_revenues": [1e9], "historical_ebitda_margins": [20]},
    {"historical_revenues": [float("inf")], "historical_ebitda_margins": [0.2]},
    {"historical_revenues": [1e9], "historical_ebitda_margins": [None]},
])
def test_lbo_rejects_missing_misaligned_or_invalid_financials(data):
    from agents.lbo_modeling import LBOModelingAgent
    with pytest.raises(ValueError):
        LBOModelingAgent._from_preparer({"extracted_data": data})


@pytest.fixture
def nvidia_mock(monkeypatch, tmp_path):
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="answer"))])
    monkeypatch.setattr(llm, "nvidia_client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(llm, "_nvidia_budget", RequestBudget("NVIDIA", "fake-key", tmp_path / "usage.sqlite3", 40, 10))
    monkeypatch.setattr("engine.request_budget.time.sleep", lambda _: None)
    monkeypatch.setenv("NVIDIA_FINANCIAL_MODEL", "nvidia/nemotron-3-super-120b-a12b")
    return calls


def test_nvidia_financial_route_is_one_bounded_request(nvidia_mock):
    assert llm._call_nvidia("system", "user", task="financial") == "answer"
    assert len(nvidia_mock) == 1
    assert nvidia_mock[0]["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert nvidia_mock[0]["max_tokens"] == 4096
    assert nvidia_mock[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}


def test_nvidia_rate_limit_stops_and_persists_cooldown(nvidia_mock, monkeypatch):
    attempts = []
    def fail(**kwargs):
        attempts.append(kwargs)
        response = httpx.Response(429, headers={"Retry-After": "120"})
        error = RuntimeError("private provider error")
        error.status_code = 429
        error.response = response
        raise error
    monkeypatch.setattr(llm.nvidia_client.chat.completions, "create", fail)
    with pytest.raises(RuntimeError, match="120 seconds"):
        llm._call_nvidia("system", "user")
    with pytest.raises(RuntimeError, match="cooling down"):
        llm._call_nvidia("system", "user")
    assert len(attempts) == 1


def test_nvidia_truncation_is_not_accepted(nvidia_mock, monkeypatch):
    monkeypatch.setattr(llm.nvidia_client.chat.completions, "create", lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content='{"partial":'))]))
    with pytest.raises(RuntimeError, match="no complete answer"):
        llm._call_nvidia("system", "user")


def test_llm_dispatch_keeps_task_category(monkeypatch):
    seen = []
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setattr("engine.openrouter.ask_openrouter", lambda *args, **kwargs: seen.append(kwargs) or "ok")
    assert llm.ask_llm("system", "user", task="financial") == "ok"
    assert seen == [{"task": "financial"}]


def test_paid_role_override_is_rejected(monkeypatch, tmp_path):
    from engine.openrouter import OpenRouterChat, OpenRouterError
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "apodex/apodex-1.1-mini:free")
    with pytest.raises(OpenRouterError, match=":free"):
        OpenRouterChat(budget_path=tmp_path / "usage.sqlite3").ask("system", "user", model_id="openai/gpt-4")
