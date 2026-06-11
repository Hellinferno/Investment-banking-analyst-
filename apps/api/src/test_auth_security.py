import os
import sys
import uuid

# Set required env vars before importing the app so AuthSettings initialises
os.environ.setdefault("AIBAA_JWT_SECRET", "test-jwt-secret-for-ci-only")
os.environ.setdefault("AIBAA_DEMO_PASSWORD", "testpass-ci")
os.environ.setdefault("AIBAA_ENVIRONMENT", "development")

from fastapi.testclient import TestClient

sys.path.insert(0, ".")

# The dev-token endpoint is fail-closed: it requires AIBAA_ENV in
# {development, test} AND a strong (>= 32 char) non-default bootstrap token.
# Configure both before importing the app so the test exercises the real path.
DEV_BOOTSTRAP_TOKEN = "test-bootstrap-" + ("x" * 32)
os.environ["AIBAA_ENV"] = "test"
os.environ["AIBAA_DEV_BOOTSTRAP_TOKEN"] = DEV_BOOTSTRAP_TOKEN

from database import SessionLocal, ensure_database_ready
from db_models import DealModel, OutputModel
from dependencies import create_access_token, get_auth_settings, get_demo_users
from main import app


client = TestClient(app)


def _issue_token(role: str) -> str:
    """Issue a JWT for the given demo role directly via create_access_token."""
    settings = get_auth_settings()
    users = get_demo_users(settings)
    user = users[role]
    token, _ = create_access_token(
        user_id=user["user_id"],
        tenant_id=user["tenant_id"],
        role=user["role"],
        email=user["email"],
        settings=settings,
    )
    return token


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_output() -> tuple[str, str]:
    ensure_database_ready()
    settings = get_auth_settings()
    users = get_demo_users(settings)
    analyst = users["analyst"]
    deal_id = str(uuid.uuid4())
    output_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(
            DealModel(
                id=deal_id,
                tenant_id=analyst["tenant_id"],
                owner_id=analyst["user_id"],
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


def test_dev_token_rejects_well_known_token():
    """The old default token must be rejected even with a valid env."""
    response = client.post(
        "/api/v1/auth/dev-token",
        json={"requested_role": "analyst"},
        headers={"X-Dev-API-Token": "dev-local-token"},
    )
    assert response.status_code == 403, response.text


def test_dev_token_cannot_mint_admin():
    """Privilege escalation to admin via the bootstrap path must be blocked."""
    response = client.post(
        "/api/v1/auth/dev-token",
        json={"requested_role": "admin"},
        headers={"X-Dev-API-Token": DEV_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 403, response.text


def test_dev_token_404_when_env_is_production(monkeypatch):
    """Endpoint must be invisible (404) outside development/test."""
    monkeypatch.setenv("AIBAA_ENV", "production")
    response = client.post(
        "/api/v1/auth/dev-token",
        json={"requested_role": "analyst"},
        headers={"X-Dev-API-Token": DEV_BOOTSTRAP_TOKEN},
    )
    assert response.status_code == 404, response.text


def test_auth_me_returns_claims_from_jwt():
    settings = get_auth_settings()
    users = get_demo_users(settings)
    analyst = users["analyst"]

    token = _issue_token("analyst")
    response = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["user_id"] == analyst["user_id"]
    assert payload["tenant_id"] == analyst["tenant_id"]
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
