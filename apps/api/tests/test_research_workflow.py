import json
from io import BytesIO
from pathlib import Path

import fitz
from openpyxl import load_workbook
import pytest
from fastapi.testclient import TestClient

from database import SessionLocal
from db_models import AgentRunModel, DocumentModel
from main import app
from persistence import hydrate_store_from_db
from routers import agents
from store import store
from tools.serpapi_client import SerpApiClient


class ImmediateExecutor:
    def submit(self, fn, *args):
        fn(*args)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(agents, "_agent_pool", ImmediateExecutor())
    return TestClient(app)


def auth(client, tenant=None, role="reviewer"):
    response = client.post("/api/v1/auth/dev-token", headers={"X-Dev-API-Token": "dev-local-token"},
                           json={"requested_role": role, "tenant_id": tenant})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}


def create(client, headers):
    response = client.post("/api/v1/deals", headers=headers, json={
        "name": "Research review", "company_name": "Example Systems", "industry": "Technology", "deal_type": "ma",
        "notes": "PRIVATE_NOTE_NEVER_SEARCH"})
    assert response.status_code == 201
    return response.json()["data"]["id"]


def test_live_research_persists_and_exports_with_tenant_boundaries(client, monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "live")
    monkeypatch.setenv("SERPAPI_API_KEY", "fake-key-used-only-by-mocked-search")
    queries = []
    def search(self, *, engine, q, gl, hl="en"):
        queries.append(q)
        results = {"title": "Public result", "link": "https://example.com/" + engine, "snippet": "Source excerpt for review."}
        return {"search_metadata": {"id": "mocked-search-id", "status": "Success"},
                "organic_results" if engine == "google" else "news_results": [results]}, False
    monkeypatch.setattr(SerpApiClient, "search", search)
    headers = auth(client)
    deal_id = create(client, headers)
    with SessionLocal() as db:
        db.add(DocumentModel(id="pending-document-" + deal_id, deal_id=deal_id, filename="private.txt", file_type="txt",
                             storage_path="not-read-by-search.txt", parse_status="pending", parsed_text="PRIVATE_DOCUMENT_NEVER_SEARCH"))
        db.commit()
    response = client.post(f"/api/v1/deals/{deal_id}/agents/run", headers=headers,
                           json={"agent_type": "research", "task_name": "industry_brief", "parameters": {}})
    assert response.status_code == 202, response.text
    run = response.json()["data"]
    assert run["status"] == "completed", run
    assert run["research_evidence"]["mode"] == "live"
    assert len(queries) == 4 and all("PRIVATE_" not in q for q in queries)
    with SessionLocal() as db:
        saved = db.get(AgentRunModel, run["run_id"])
        assert saved.status == "completed" and saved.input_payload["research_evidence"]["sources"]
    # A fresh facade, as after process startup, reads the persisted run. pop()
    # would DELETE the database row, not evict an in-memory cache.
    from store import AgentRun, DictFacade
    monkeypatch.setattr(store, "agent_runs", DictFacade(AgentRunModel, AgentRun))
    restored = client.get(f"/api/v1/deals/{deal_id}/agents/runs/{run['run_id']}", headers=headers)
    assert restored.status_code == 200
    assert restored.json()["data"]["research_evidence"]["sources"] == run["research_evidence"]["sources"]
    outputs = client.get(f"/api/v1/deals/{deal_id}/outputs", headers=headers).json()["data"]
    assert {o["output_type"] for o in outputs} == {"pdf", "json"}
    for output in outputs:
        assert client.get(f"/api/v1/outputs/{output['id']}/download", headers=headers).status_code == 409
        approved = client.patch(f"/api/v1/outputs/{output['id']}/review", headers=headers, json={"review_status": "approved"})
        assert approved.status_code == 200
        download = client.get(f"/api/v1/outputs/{output['id']}/download", headers=headers)
        assert download.status_code == 200 and download.content
        if output["output_type"] == "json":
            assert json.loads(download.content)["evidence"]["mode"] == "live"
    other_headers = auth(client, "other-tenant")
    assert client.get(f"/api/v1/deals/{deal_id}/agents/runs/{run['run_id']}", headers=other_headers).status_code == 404
    assert client.get(f"/api/v1/outputs/{outputs[0]['id']}/download", headers=other_headers).status_code == 404


def test_demo_diligence_produces_review_checklist_without_risk_score(client, monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "demo")
    headers = auth(client)
    deal_id = create(client, headers)
    response = client.post(f"/api/v1/deals/{deal_id}/agents/run", headers=headers,
                           json={"agent_type": "due_diligence", "task_name": "dd_report", "parameters": {}})
    assert response.status_code == 202, response.text
    assert response.json()["data"]["status"] == "completed"
    outputs = client.get(f"/api/v1/deals/{deal_id}/outputs", headers=headers).json()["data"]
    assert {o["output_type"] for o in outputs} == {"pdf", "json", "xlsx"}
    assert "synthetic" in " ".join(response.json()["data"]["research_report"]["warnings"])
    workbook_output = next(output for output in outputs if output["output_type"] == "xlsx")
    assert client.patch(
        f"/api/v1/outputs/{workbook_output['id']}/review",
        headers=headers,
        json={"review_status": "approved"},
    ).status_code == 200
    workbook_bytes = client.get(f"/api/v1/outputs/{workbook_output['id']}/download", headers=headers).content
    workbook = load_workbook(BytesIO(workbook_bytes), read_only=False)
    assert workbook["Sources"]["C2"].hyperlink.target.startswith("https://")
    assert workbook["Review Checklist"].column_dimensions["B"].width == 90


def test_review_board_is_run_scoped_authorized_and_exports_immutable_snapshots(client, monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "demo")
    headers = auth(client)
    deal_id = create(client, headers)
    run_response = client.post(
        f"/api/v1/deals/{deal_id}/agents/run",
        headers=headers,
        json={"agent_type": "research", "task_name": "industry_brief", "parameters": {}},
    )
    assert run_response.status_code == 202, run_response.text
    run_id = run_response.json()["data"]["run_id"]
    review_url = f"/api/v1/research/deals/{deal_id}/runs/{run_id}/review-items"

    initial_outputs = client.get(f"/api/v1/deals/{deal_id}/outputs", headers=headers).json()["data"]
    initial_json = next(output for output in initial_outputs if output["output_type"] == "json")
    assert initial_json["version"] == 1
    assert client.patch(
        f"/api/v1/outputs/{initial_json['id']}/review",
        headers=headers,
        json={"review_status": "approved"},
    ).status_code == 200
    initial_bytes = client.get(f"/api/v1/outputs/{initial_json['id']}/download", headers=headers).content

    bad_source = client.post(review_url, headers=headers, json={
        "kind": "question", "title": "Unknown citation", "note": "", "next_action": "",
        "source_ids": ["S999"], "status": "unreviewed",
    })
    assert bad_source.status_code == 422 and "Unknown source IDs" in bad_source.text

    created = client.post(review_url, headers=headers, json={
        "kind": "question",
        "title": "<b>Confirm company identity</b>",
        "note": "Check the source against the official company site.",
        "next_action": "Open the cited page and record the legal entity name.",
        "source_ids": ["S1"],
        "status": "unreviewed",
    })
    assert created.status_code == 201, created.text
    item = created.json()["data"]
    assert item["title"] == "Confirm company identity"
    assert item["sources"][0]["url"] == "https://example.com/annual-report"

    analyst_headers = auth(client, role="analyst")
    assert client.patch(
        f"{review_url}/{item['id']}", headers=analyst_headers, json={"status": "reviewed"}
    ).status_code == 403
    other_headers = auth(client, tenant="other-tenant")
    assert client.get(review_url, headers=other_headers).status_code == 404

    updated = client.patch(
        f"{review_url}/{item['id']}",
        headers=headers,
        json={"status": "needs_follow_up", "note": "Identity still needs confirmation."},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["status"] == "needs_follow_up"
    assert client.get(review_url, headers=headers).json()["data"][0]["note"] == "Identity still needs confirmation."
    assert client.patch(f"{review_url}/{item['id']}", headers=headers, json={"title": None}).status_code == 422

    exported = client.post(
        f"/api/v1/research/deals/{deal_id}/runs/{run_id}/review-export",
        headers=headers,
    )
    assert exported.status_code == 201, exported.text
    export_data = exported.json()["data"]
    assert export_data["version"] == 2 and export_data["review_item_count"] == 1
    assert {output["output_type"] for output in export_data["outputs"]} == {"pdf", "json"}

    for output in export_data["outputs"]:
        assert client.patch(
            f"/api/v1/outputs/{output['id']}/review",
            headers=headers,
            json={"review_status": "approved"},
        ).status_code == 200
        artifact = client.get(f"/api/v1/outputs/{output['id']}/download", headers=headers)
        assert artifact.status_code == 200
        if output["output_type"] == "json":
            snapshot = json.loads(artifact.content)
            assert snapshot["research_run_id"] == run_id
            assert snapshot["review_items"][0]["source_ids"] == ["S1"]
            assert snapshot["review_items"][0]["sources"][0]["url"] == "https://example.com/annual-report"
        else:
            pdf = fitz.open(stream=artifact.content, filetype="pdf")
            pdf_text = "\n".join(page.get_text() for page in pdf)
            assert "Analyst Review Board" in pdf_text
            assert "Confirm company identity" in pdf_text

    assert client.get(f"/api/v1/outputs/{initial_json['id']}/download", headers=headers).content == initial_bytes

    second_run = client.post(
        f"/api/v1/deals/{deal_id}/agents/run",
        headers=headers,
        json={"agent_type": "research", "task_name": "industry_brief", "parameters": {}},
    ).json()["data"]["run_id"]
    second_items = client.get(
        f"/api/v1/research/deals/{deal_id}/runs/{second_run}/review-items",
        headers=headers,
    )
    assert second_items.status_code == 200 and second_items.json()["data"] == []

    assert client.delete(f"{review_url}/{item['id']}", headers=headers).status_code == 200
    assert client.get(review_url, headers=headers).json()["data"] == []


def test_missing_live_key_and_invalid_parameters_are_reported_before_dispatch(client, monkeypatch):
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "live")
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    headers = auth(client)
    deal_id = create(client, headers)
    response = client.post(f"/api/v1/deals/{deal_id}/agents/run", headers=headers,
                           json={"agent_type": "research", "task_name": "industry_brief", "parameters": {}})
    assert response.status_code == 503 and "SERPAPI_API_KEY" in response.text
    response = client.post(f"/api/v1/deals/{deal_id}/agents/run", headers=headers,
                           json={"agent_type": "research", "task_name": "industry_brief", "parameters": {"news_days": 999}})
    assert response.status_code == 422
    assert client.get(f"/api/v1/deals/{deal_id}/agents/runs", headers=headers).json()["data"]["runs"] == []


def test_search_status_is_authenticated_and_never_returns_credentials(client, monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "secret-not-to-return")
    assert client.get("/api/v1/research/status").status_code == 401
    response = client.get("/api/v1/research/status", headers=auth(client))
    assert response.status_code == 200 and response.json()["search_configured"]
    assert "secret-not-to-return" not in response.text


def test_restart_marks_interrupted_run_failed():
    with SessionLocal() as db:
        record = AgentRunModel(id="interrupted-research", deal_id="test-restart", agent_type="research",
                               task_name="industry_brief", status="running", input_payload={})
        db.add(record)
        db.commit()
        hydrate_store_from_db(db)
        assert store.agent_runs[record.id].status == "failed"
        assert "restarted" in store.agent_runs[record.id].error_message


def test_failed_queue_submission_does_not_leave_a_running_deal(client, monkeypatch):
    class BrokenExecutor:
        def submit(self, *args):
            raise RuntimeError("Executor closed")
    monkeypatch.setenv("AIBAA_RESEARCH_MODE", "demo")
    monkeypatch.setattr(agents, "_agent_pool", BrokenExecutor())
    headers = auth(client)
    deal_id = create(client, headers)
    payload = {"agent_type": "research", "task_name": "industry_brief", "parameters": {}}
    assert client.post(f"/api/v1/deals/{deal_id}/agents/run", headers=headers, json=payload).status_code == 500
    with SessionLocal() as db:
        assert not db.query(AgentRunModel).filter_by(deal_id=deal_id, status="running").first()
    monkeypatch.setattr(agents, "_agent_pool", ImmediateExecutor())
    assert client.post(f"/api/v1/deals/{deal_id}/agents/run", headers=headers, json=payload).status_code == 202
