import json
from pathlib import Path

import httpx
import pytest

from engine import llm
from engine.openrouter import DEFAULT_FALLBACK, DEFAULT_MODEL, OpenRouterChat, OpenRouterError


def model(model_id=DEFAULT_MODEL, *, price="0", output="text", context=262144):
    return {"id": model_id, "pricing": {"prompt": price, "completion": "0", "request": "0"},
            "architecture": {"input_modalities": ["text"], "output_modalities": [output]},
            "context_length": context, "supported_parameters": ["max_tokens", "temperature", "reasoning"],
            "top_provider": {"max_completion_tokens": 8192}}


def completion(content='{"findings":[]}', finish="stop"):
    return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}]})


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("OPENROUTER_MODEL", DEFAULT_MODEL)
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", DEFAULT_FALLBACK)
    monkeypatch.setenv("OPENROUTER_DAILY_REQUEST_LIMIT", "40")
    monkeypatch.setenv("OPENROUTER_MAX_TOKENS", "4096")
    monkeypatch.setenv("OPENROUTER_MAX_PROMPT_CHARS", "120000")
    monkeypatch.setenv("OPENROUTER_MAX_ATTEMPTS", "2")
    monkeypatch.setenv("OPENROUTER_REQUESTS_PER_MINUTE", "10")
    monkeypatch.setattr("engine.openrouter.time.sleep", lambda _: None)


def client(tmp_path: Path, requests, reply=None, *, models=None, used=0, remaining=50):
    def handler(request):
        requests.append(request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": models if models is not None else [model(), model(DEFAULT_FALLBACK)]})
        if request.url.path.endswith("/key"):
            return httpx.Response(200, json={"data": {"free_model_daily_requests": {"used": used, "limit": 50, "remaining": remaining}}})
        return reply(request) if reply else completion()
    return OpenRouterChat(transport=httpx.MockTransport(handler), budget_path=tmp_path / "usage.sqlite3")


def posts(requests):
    return [request for request in requests if request.method == "POST"]


def test_free_chat_payload_and_persistent_budget(settings, tmp_path):
    requests = []
    chat = client(tmp_path, requests, used=12, remaining=38)
    assert chat.ask("System", "User") == '{"findings":[]}'
    payload = json.loads(posts(requests)[0].content)
    assert payload["model"] == DEFAULT_MODEL
    assert payload["provider"]["max_price"] == {"prompt": 0, "completion": 0, "request": 0}
    assert payload["max_tokens"] == 4096 and payload["reasoning"] == {"enabled": False}
    assert payload["messages"] == [{"role": "system", "content": "System"}, {"role": "user", "content": "User"}]
    assert b"test-openrouter-key" not in chat.budget_path.read_bytes()
    chat.close()


@pytest.mark.parametrize("model_id", ["openrouter/auto", "openai/gpt-4", "openrouter/free"])
def test_paid_and_dynamic_routers_rejected_before_network(settings, tmp_path, monkeypatch, model_id):
    monkeypatch.setenv("OPENROUTER_MODEL", model_id)
    with pytest.raises(OpenRouterError, match=":free"):
        client(tmp_path, [])


@pytest.mark.parametrize("catalog", [
    [model(price="0.001"), model(DEFAULT_FALLBACK, price="0.002")],
    [model(output="embeddings"), model(DEFAULT_FALLBACK, output="rerank")],
    [],
])
def test_catalog_price_modality_or_absence_blocks_inference(settings, tmp_path, catalog):
    requests = []
    chat = client(tmp_path, requests, models=catalog)
    with pytest.raises(OpenRouterError, match="free text-generation"):
        chat.ask("System", "User")
    assert not posts(requests)


def test_content_safety_cannot_be_used_for_analyst_generation(settings, tmp_path, monkeypatch):
    model_id = "nvidia/nemotron-3.5-content-safety:free"
    monkeypatch.setenv("OPENROUTER_MODEL", model_id)
    monkeypatch.setenv("OPENROUTER_FALLBACK_MODELS", "")
    requests = []
    with pytest.raises(OpenRouterError, match="free text-generation"):
        client(tmp_path, requests, models=[model(model_id)]).ask("System", "User")
    assert not posts(requests)


def test_transient_failure_has_only_one_free_fallback(settings, tmp_path):
    requests = []
    def reply(request):
        return httpx.Response(503) if len(posts(requests)) == 1 else completion("Fallback response")
    assert client(tmp_path, requests, reply).ask("System", "User") == "Fallback response"
    assert [json.loads(req.content)["model"] for req in posts(requests)] == [DEFAULT_MODEL, DEFAULT_FALLBACK]


def test_repeated_timeouts_are_bounded_and_sanitized(settings, tmp_path):
    requests = []
    def reply(request):
        raise httpx.ReadTimeout("test-openrouter-key PROMPT_PRIVATE", request=request)
    with pytest.raises(OpenRouterError, match="timed out") as error:
        client(tmp_path, requests, reply).ask("System", "User")
    assert len(posts(requests)) == 2
    assert "test-openrouter" not in str(error.value) and "PRIVATE" not in str(error.value)


@pytest.mark.parametrize("status", [400, 401, 402, 403])
def test_access_and_bad_request_errors_do_not_rotate_or_leak(settings, tmp_path, status):
    requests = []
    with pytest.raises(OpenRouterError) as error:
        client(tmp_path, requests, lambda _: httpx.Response(status, json={"error": {"message": "test-openrouter-key PRIVATE_DATA", "code": status}})).ask("System", "User")
    assert len(posts(requests)) == 1
    assert "PRIVATE" not in str(error.value) and "test-openrouter" not in str(error.value)


def test_rate_limit_persists_cooldown_across_clients(settings, tmp_path):
    requests = []
    chat = client(tmp_path, requests, lambda _: httpx.Response(429, headers={"Retry-After": "120"}))
    with pytest.raises(OpenRouterError, match="120 seconds"):
        chat.ask("System", "User")
    chat.close()
    with pytest.raises(OpenRouterError, match="cooling down"):
        client(tmp_path, requests).ask("System", "User")
    assert len(posts(requests)) == 1


def test_remote_daily_quota_stops_before_inference(settings, tmp_path):
    requests = []
    with pytest.raises(OpenRouterError, match="quota is exhausted"):
        client(tmp_path, requests, remaining=0).ask("System", "User")
    assert not posts(requests)


def test_local_budget_survives_restart_and_paces_requests(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_DAILY_REQUEST_LIMIT", "2")
    sleeps = []
    monkeypatch.setattr("engine.openrouter.time.sleep", sleeps.append)
    requests = []
    chat = client(tmp_path, requests)
    chat.ask("System", "User")
    chat.close()
    new_chat = client(tmp_path, requests)
    new_chat.ask("System", "User")
    with pytest.raises(OpenRouterError, match="local daily"):
        new_chat.ask("System", "User")
    assert len(posts(requests)) == 2 and sleeps[0] >= 5


def test_prompt_and_context_limits_reject_without_silent_truncation(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_MAX_PROMPT_CHARS", "1000")
    requests = []
    with pytest.raises(OpenRouterError, match="character limit"):
        client(tmp_path, requests).ask("System", "X" * 1001)
    assert not requests
    with pytest.raises(OpenRouterError, match="context"):
        client(tmp_path, requests, models=[model(context=100)]).ask("System", "User")
    assert not posts(requests)


def test_truncated_output_is_never_accepted(settings, tmp_path):
    requests = []
    with pytest.raises(OpenRouterError, match="truncated"):
        client(tmp_path, requests, lambda _: completion('{"findings":[', "length")).ask("System", "User")
    assert len(posts(requests)) == 1


def test_openrouter_selection_never_calls_other_providers(settings, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setattr("engine.openrouter.ask_openrouter", lambda *args, **kwargs: "OpenRouter answer")
    monkeypatch.setattr(llm, "_call_gemini", lambda *args: pytest.fail("Unexpected Gemini request"))
    monkeypatch.setattr(llm, "_call_nvidia", lambda *args: pytest.fail("Unexpected NVIDIA request"))
    assert llm.llm_configured()
    assert llm.ask_llm("System", "User") == "OpenRouter answer"


def test_research_status_supports_openrouter_only(settings, monkeypatch):
    from routers.research import research_status
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setattr(llm, "gemini_client", None)
    monkeypatch.setattr(llm, "nvidia_client", None)
    assert research_status({})["synthesis_configured"]
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    assert not research_status({})["synthesis_configured"]


def test_openrouter_failure_preserves_research_source_excerpts(settings, monkeypatch):
    from tools.research_evidence import build_report
    def fail(*args, **kwargs):
        raise OpenRouterError("Quota exhausted")
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setattr("engine.openrouter.ask_openrouter", fail)
    bundle = {"mode": "live", "status": "complete", "warnings": [], "sources": [
        {"id": "S1", "title": "Public filing", "snippet": "Source excerpt", "published_at": None,
         "purpose": "Company filings", "verification": "search_excerpt"}]}
    report = build_report(bundle, synthesize=True)
    assert report["synthesis_mode"] == "evidence_only"
    assert report["findings"][0]["statement"] == "Source excerpt"


def test_explicit_gemini_does_not_fall_through(settings, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setattr(llm, "gemini_client", object())
    monkeypatch.setattr(llm, "nvidia_client", object())
    def fail(*args):
        raise RuntimeError("test-openrouter-key provider failure")
    monkeypatch.setattr(llm, "_call_gemini", fail)
    monkeypatch.setattr(llm, "_call_nvidia", lambda *args, **kwargs: pytest.fail("Unexpected fallback"))
    with pytest.raises(RuntimeError) as error:
        llm.ask_llm("System", "User")
    assert "test-openrouter-key" not in str(error.value)
