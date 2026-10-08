import json
from pathlib import Path

import httpx
import pytest
from openpyxl import load_workbook

from tools.research_evidence import ResearchParameters, build_report, build_search_plan, collect_evidence, safe_source_url
from tools.research_export import export_research
from tools.serpapi_client import SearchError, SerpApiClient


@pytest.fixture(autouse=True)
def clear_search_cache():
    SerpApiClient._cache.clear()


def response_payload(engine):
    if engine == "google_news":
        return {"search_metadata": {"id": "news-123", "status": "Success"}, "news_results": [
            {"stories": [{"title": "Reported company development", "link": "https://news.example.com/story",
                          "source": {"name": "Example News"}, "iso_date": "2026-10-07T00:00:00Z"}]}]}
    return {"search_metadata": {"id": "web-123", "status": "Success"}, "organic_results": [
        {"title": "Annual report <2026>", "link": "https://company.example.com/report?utm_source=google", "snippet": "A public filing was found."},
        {"title": "Bad URL", "link": "javascript:alert(1)"}]}


def make_client(handler=None):
    return SerpApiClient(api_key="test-key-not-real", transport=httpx.MockTransport(
        handler or (lambda req: httpx.Response(200, json=response_payload(req.url.params["engine"])))))


def test_normalizes_nested_news_deduplicates_urls_and_records_provenance(monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "live")
    bundle = collect_evidence("Company", "Technology", ResearchParameters(official_domain="company.example.com"), client=make_client())
    assert bundle["mode"] == "live"
    assert bundle["status"] == "complete"
    assert len(bundle["sources"]) == 2
    assert bundle["sources"][0]["id"] == "S1"
    assert bundle["sources"][0]["official_domain_match"]
    assert "utm_" not in bundle["sources"][0]["url"]
    assert bundle["sources"][1]["publisher"] == "Example News"
    assert bundle["sources"][1]["published_at"] == "2026-10-07T00:00:00Z"
    assert len(bundle["searches"]) == 4
    assert "test-key" not in json.dumps(bundle)


def test_cache_avoids_repeat_http_calls_and_returns_independent_data():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json=response_payload("google"))
    client = make_client(handler)
    first, hit = client.search(engine="google", q="same")
    assert not hit
    first["organic_results"].clear()
    second, hit = client.search(engine="google", q="same")
    assert hit and second["organic_results"]
    assert len(calls) == 1


def test_normalizes_news_highlight(monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "live")
    payload = {"search_metadata": {"id": "highlight-id"}, "news_results": [
        {"highlight": {"title": "Highlighted story", "link": "https://example.com/highlight"}}]}
    bundle = collect_evidence("Company", "", ResearchParameters(),
                              client=make_client(lambda req: httpx.Response(200, json=payload)))
    assert bundle["sources"][0]["title"] == "Highlighted story"
    assert bundle["sources"][0]["engine"] == "google_news"


def test_malformed_provider_metadata_is_a_safe_error():
    with pytest.raises(SearchError) as error:
        make_client(lambda req: httpx.Response(200, json={"search_metadata": None})).search(engine="google", q="test")
    assert error.value.code == "invalid_response"


@pytest.mark.parametrize("status,code", [(401, "authentication"), (403, "authentication"), (429, "quota")])
def test_auth_and_quota_failures_are_not_retried_or_leaked(status, code):
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(status, json={"error": "secret-test-key-not-real"})
    with pytest.raises(SearchError) as error:
        make_client(handler).search(engine="google", q="test")
    assert error.value.code == code
    assert "secret" not in str(error.value)
    assert len(calls) == 1


def test_transient_failure_retries_once_then_succeeds():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(503 if len(calls) == 1 else 200, json=response_payload("google"))
    make_client(handler).search(engine="google", q="test")
    assert len(calls) == 2


def test_network_timeout_is_bounded():
    calls = []
    def handler(req):
        calls.append(req)
        raise httpx.ReadTimeout("secret-in-request-url", request=req)
    with pytest.raises(SearchError) as error:
        make_client(handler).search(engine="google", q="test")
    assert len(calls) == 2 and error.value.code == "network"
    assert "secret" not in str(error.value)


def test_partial_failure_does_not_become_complete(monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "live")
    def handler(req):
        return httpx.Response(429) if req.url.params["engine"] == "google_news" else httpx.Response(200, json=response_payload("google"))
    bundle = collect_evidence("Company", "Tech", ResearchParameters(), client=make_client(handler))
    assert bundle["status"] == "partial"
    assert bundle["searches"][-1]["status"] == "error"
    assert "incomplete" in " ".join(bundle["warnings"])


def test_empty_response_does_not_create_facts(monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "live")
    bundle = collect_evidence("Company", "Tech", ResearchParameters(), client=make_client(lambda req: httpx.Response(200, json={})))
    assert bundle["status"] == "empty"
    assert not build_report(bundle)["findings"]


def test_missing_key_cannot_silently_fall_back_to_demo(monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "live")
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    with pytest.raises(SearchError, match="SERPAPI_API_KEY"):
        collect_evidence("Company", "Tech", ResearchParameters())


def test_demo_is_explicit_and_never_calls_search(monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "demo")
    client = make_client(lambda req: pytest.fail("Demo must not search"))
    bundle = collect_evidence("Demo Company", "Tech", ResearchParameters(), client=client)
    assert bundle["mode"] == "demo"
    assert bundle["sources"][0]["verification"] == "synthetic_fixture"
    assert "synthetic" in " ".join(bundle["warnings"])


def test_unknown_citations_are_removed_and_llm_failure_preserves_sources(monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "live")
    bundle = collect_evidence("Company", "Tech", ResearchParameters(), client=make_client())
    report = build_report(bundle, synthesize=True, llm=lambda *args: json.dumps({"findings": [
        {"statement": "Supported interpretation", "source_ids": ["S1"], "category": "Company"},
        {"statement": "Invented claim", "source_ids": ["S999"], "category": "Company"}]}))
    assert report["synthesis_mode"] == "llm"
    assert [f["statement"] for f in report["findings"]] == ["Supported interpretation"]
    report = build_report(bundle, synthesize=True, llm=lambda *args: "invalid JSON")
    assert report["synthesis_mode"] == "evidence_only" and report["findings"]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///etc/passwd", "http://127.0.0.1/private", "http://localhost/", "https://user:pass@example.com"])
def test_unsafe_source_links_are_dropped(url):
    assert safe_source_url(url) is None


def test_invalid_parameters_and_query_operator_injection():
    with pytest.raises(ValueError):
        ResearchParameters(official_domain="https://example.com/path")
    with pytest.raises(ValueError):
        ResearchParameters(news_days=1000)
    plan = build_search_plan('Company" site:evil.com', "Tech", ResearchParameters())
    assert "site:evil.com" not in plan[0]["query"]


def test_exports_escape_markup_preserve_citations_and_prevent_spreadsheet_formulas(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "demo")
    bundle = collect_evidence("Company & Co", "Tech", ResearchParameters())
    bundle["sources"][0]["title"] = '=HYPERLINK("https://example.com")'
    bundle["sources"][0]["snippet"] = "<b>Text & markup</b>"
    report = build_report(bundle)
    outputs = export_research("Company & Co", "unique-run", bundle, report, diligence=True, output_dir=tmp_path)
    assert len(outputs) == 3
    assert all(Path(path).exists() for path, _ in outputs)
    workbook = load_workbook(next(path for path, kind in outputs if kind == "xlsx"))
    assert workbook["Sources"]["B2"].data_type == "s"
    assert workbook["Summary"]["B4"].value == "Not assessed - discovery only"
    import fitz
    pdf = fitz.open(next(path for path, kind in outputs if kind == "pdf"))
    text = "".join(page.get_text() for page in pdf)
    assert "DEMO" in text and "S1" in text and "Sources and provenance" in text
