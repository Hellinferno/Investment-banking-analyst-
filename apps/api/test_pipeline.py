import os

import pytest
import requests


BASE_URL = os.getenv("AIBAA_PIPELINE_TEST_BASE_URL", "http://127.0.0.1:8000/api/v1")


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_PIPELINE_TEST") != "1",
    reason="Live pipeline smoke test requires RUN_LIVE_PIPELINE_TEST=1 and a running API server.",
)


def _auth_headers(role: str = "reviewer") -> dict[str, str]:
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"username": role, "password": os.getenv("AIBAA_DEMO_PASSWORD", "AIBAA-demo-2026!")},
        timeout=30,
    )
    response.raise_for_status()
    cookie = response.cookies.get("aibaa_session")
    return {"Cookie": f"aibaa_session={cookie}"} if cookie else {}


def test_live_autopilot_pipeline_smoke():
    headers = _auth_headers()
    deal_response = requests.post(
        f"{BASE_URL}/deals",
        json={
            "name": "Pipeline Test",
            "company_name": "Titan Corp",
            "deal_type": "ma",
            "industry": "Technology",
        },
        headers=headers,
        timeout=30,
    )
    deal_response.raise_for_status()
    deal_id = deal_response.json()["data"]["id"]

    agent_response = requests.post(
        f"{BASE_URL}/deals/{deal_id}/agents/run",
        json={
            "agent_type": "autopilot",
            "task_name": "full_deal_package",
            "parameters": {"steps": ["dcf_bootstrap", "three_statement_model"]},
            "mnpi_consent": True,
        },
        headers=headers,
        timeout=600,
    )
    agent_response.raise_for_status()
    payload = agent_response.json()["data"]
    assert payload["run_id"]
    assert payload["status"] in {"running", "completed", "awaiting_review"}
