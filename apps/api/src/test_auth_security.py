import sys
import uuid

from fastapi.testclient import TestClient

sys.path.insert(0, ".")

from database import SessionLocal, ensure_database_ready
from db_models import DealModel, OutputModel
from dependencies import get_auth_settings
from main import app


client = TestClient(app)
DEV_BOOTSTRAP_TOKEN = "dev-local-token"


def _issue_token(role: str) -> str:
    response = client.post(
        "/api/v1/auth/dev-token",
        json={"requested_role": role},
        headers={"X-Dev-API-Token": DEV_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_output() -> tuple[str, str]:
    ensure_database_ready()
    settings = get_auth_settings()
    deal_id = str(uuid.uuid4())
    output_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(
            DealModel(
                id=deal_id,
                tenant_id=settings.default_tenant_id,
                owner_id=settings.default_user_id,
                name=f"Auth Test {deal_id[:8]}",
                company_name="Role Gating Co",
                deal_type="other",
                industry="Tech",
                deal_stage="preliminary",
                notes="auth test fixture",
                is_archived=False,
            )
        )
        db.add(
            OutputModel(
                id=output_id,
                deal_id=deal_id,
                filename="fixture.xlsx",
                output_type="xlsx",
                output_category="financial_model",
                storage_path="data/outputs/fixture.xlsx",
                review_status="draft",
                version=1,
            )
        )
        db.commit()
    return deal_id, output_id


def test_auth_me_returns_claims_from_jwt():
    token = _issue_token("analyst")
    response = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["user_id"] == get_auth_settings().default_user_id
    assert payload["tenant_id"] == get_auth_settings().default_tenant_id
    assert payload["role"] == "analyst"


def test_output_review_requires_reviewer_or_admin():
    _, output_id = _seed_output()
    analyst_token = _issue_token("analyst")
    reviewer_token = _issue_token("reviewer")

    analyst_attempt = client.patch(
        f"/api/v1/outputs/{output_id}/review",
        json={"review_status": "approved", "reviewer_notes": "not allowed"},
        headers=_auth_headers(analyst_token),
    )
    assert analyst_attempt.status_code == 403

    reviewer_attempt = client.patch(
        f"/api/v1/outputs/{output_id}/review",
        json={"review_status": "approved", "reviewer_notes": "approved by reviewer"},
        headers=_auth_headers(reviewer_token),
    )
    assert reviewer_attempt.status_code == 200
    assert reviewer_attempt.json()["data"]["review_status"] == "approved"
