import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, ".")

from database import SessionLocal, ensure_database_ready
from db_models import DealModel, OutputModel
from dependencies import get_auth_settings
from engine.three_statement import ThreeStatementEngine
from agents.orchestrator import OrchestratorAgent
from main import app
from tools.market_data import MarketDataClient


client = TestClient(app)


def _issue_token(role: str) -> str:
    response = client.post(
        "/api/v1/auth/dev-token",
        json={"requested_role": role},
        headers={"X-Dev-API-Token": "dev-local-token"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def _auth_headers(role: str = "reviewer") -> dict[str, str]:
    return {"Authorization": f"Bearer {_issue_token(role)}"}


def test_orchestrator_routes_new_autonomous_tasks():
    for raw_task, expected_agent, expected_task in [
        ("three_statement", "three_statement", "three_statement_model"),
        ("teaser", "doc_drafter", "teaser_draft"),
        ("process_status", "coordination", "process_status"),
        ("run_everything", "autopilot", "full_deal_package"),
    ]:
        decision, error = OrchestratorAgent._build_route_decision("", raw_task)
        assert error is None
        assert decision["target_agent"] == expected_agent
        assert decision["target_task"] == expected_task


def test_three_statement_balances_and_draws_revolver_in_stress_case():
    engine = ThreeStatementEngine(
        historical_revenues=[100.0, 90.0, 70.0],
        historical_ebitda_margins=[0.10, -0.05, -0.20],
        opening_cash=1.0,
        term_loan_balance=100.0,
        min_cash_balance=5.0,
    )
    result = engine.build_projections(projection_years=3)
    assert all(check["balanced"] for check in result["balance_checks"])
    assert any(draw > 0 for draw in result["debt_schedule"]["revolver_draw"])
    assert len(result["cash_flow_statement"]["ufcf"]) == 3


def test_market_data_band_uses_peer_quartiles():
    peers = {
        "A": {"ev_ebitda": 8.0},
        "B": {"ev_ebitda": 10.0},
        "C": {"ev_ebitda": 12.0},
        "D": {"ev_ebitda": 14.0},
    }
    band = MarketDataClient.band_from_peers(peers)
    assert band == {"bear": 9.5, "base": 11.0, "bull": 12.5, "sample_size": 4}


def test_review_endpoint_accepts_decision_comment_and_populates_audit_fields():
    ensure_database_ready()
    settings = get_auth_settings()
    deal_id = str(uuid.uuid4())
    output_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(
            DealModel(
                id=deal_id,
                tenant_id=settings.demo_tenant_id,
                owner_id=settings.default_user_id,
                name="Review Compatibility",
                company_name="Compatibility Co",
                deal_type="ma",
                industry="Technology",
                deal_stage="preliminary",
                process_stage="origination",
                is_archived=False,
            )
        )
        db.add(
            OutputModel(
                id=output_id,
                deal_id=deal_id,
                filename="fixture.pdf",
                output_type="pdf",
                output_category="memo",
                storage_path="data/outputs/fixture.pdf",
                review_status="draft",
                version=1,
            )
        )
        db.commit()

    response = client.patch(
        f"/api/v1/outputs/{output_id}/review",
        json={"decision": "needs_changes", "comment": "Please reconcile valuation range."},
        headers=_auth_headers("reviewer"),
    )
    assert response.status_code == 200, response.text
    payload = response.json()["data"]
    assert payload["review_status"] == "needs_changes"
    assert payload["reviewed_by"] == "usr_demo_reviewer"
    assert payload["review_comment"] == "Please reconcile valuation range."
    assert payload["reviewed_at"]
