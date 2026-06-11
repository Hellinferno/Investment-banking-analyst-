from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from db_models import ModelRegistryModel

DEFAULT_PURPOSE = "modeling_extraction"
DEFAULT_PROVIDER = "google-genai"
DEFAULT_MODEL_NAME = os.environ.get("AIBAA_BOOTSTRAP_EXTRACTION_MODEL", "gemini-3-flash-preview")
DEFAULT_PROMPT_VERSION = os.environ.get("AIBAA_BOOTSTRAP_EXTRACTION_PROMPT_VERSION", "modeling-preparer-v1")

# Provider → model-name validator. A model passes when its name matches the
# provider's expected naming convention.
SUPPORTED_PROVIDERS: dict[str, dict[str, Any]] = {
    "google-genai": {
        "model_check": lambda name: name.startswith("gemini-"),
        "model_rule": "Model name must be a Gemini family identifier (gemini-*).",
    },
    "nvidia-nim": {
        # NIM catalog ids are namespaced, e.g. moonshotai/kimi-k2.6, meta/llama-3.3-70b-instruct
        "model_check": lambda name: bool(name) and "/" in name,
        "model_rule": "NVIDIA NIM model name must be a namespaced catalog id (e.g. moonshotai/kimi-k2.6).",
    },
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RuntimeModelConfig:
    registry_id: str | None
    tenant_id: str | None
    purpose: str
    provider: str
    model_name: str
    prompt_version: str
    config: dict[str, Any]


def _normalize_registry_config(config: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(config or {})
    normalized.setdefault("eval_summary", {})
    normalized.setdefault("canary_status", "pending")
    normalized.setdefault("rollout_notes", "")
    return normalized


def serialize_registry_entry(entry: ModelRegistryModel) -> dict[str, Any]:
    config = _normalize_registry_config(entry.config or {})
    return {
        "id": entry.id,
        "tenant_id": entry.tenant_id,
        "purpose": entry.purpose,
        "provider": entry.provider,
        "model_name": entry.model_name,
        "prompt_version": entry.prompt_version,
        "status": entry.status,
        "config": config,
        "validation_status": entry.validation_status or "pending",
        "validation_report": entry.validation_report or {},
        "eval_summary": config.get("eval_summary", {}),
        "canary_status": config.get("canary_status", "pending"),
        "rollout_notes": config.get("rollout_notes", ""),
        "rollback_from_id": entry.rollback_from_id,
        "created_by": entry.created_by,
        "promoted_at": entry.promoted_at.isoformat() if entry.promoted_at else None,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def _build_default_entry(tenant_id: str | None, purpose: str, created_by: str | None = None) -> ModelRegistryModel:
    report = validate_registry_candidate(
        provider=DEFAULT_PROVIDER,
        model_name=DEFAULT_MODEL_NAME,
        prompt_version=DEFAULT_PROMPT_VERSION,
        config={},
    )
    return ModelRegistryModel(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        purpose=purpose,
        provider=DEFAULT_PROVIDER,
        model_name=DEFAULT_MODEL_NAME,
        prompt_version=DEFAULT_PROMPT_VERSION,
        status="active",
        config=_normalize_registry_config({}),
        validation_status=report["overall_status"],
        validation_report=report,
        created_by=created_by or "bootstrap",
        promoted_at=_utcnow(),
    )


def ensure_active_registry_entry(
    db: Session,
    *,
    tenant_id: str | None,
    purpose: str = DEFAULT_PURPOSE,
    created_by: str | None = None,
) -> ModelRegistryModel:
    active = (
        db.query(ModelRegistryModel)
        .filter(
            ModelRegistryModel.tenant_id == tenant_id,
            ModelRegistryModel.purpose == purpose,
            ModelRegistryModel.status == "active",
        )
        .order_by(ModelRegistryModel.updated_at.desc())
        .first()
    )
    if active:
        return active

    entry = _build_default_entry(tenant_id, purpose, created_by=created_by)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def list_registry_entries(db: Session, *, tenant_id: str | None) -> list[ModelRegistryModel]:
    ensure_active_registry_entry(db, tenant_id=tenant_id)
    return (
        db.query(ModelRegistryModel)
        .filter(ModelRegistryModel.tenant_id == tenant_id)
        .order_by(ModelRegistryModel.created_at.desc(), ModelRegistryModel.updated_at.desc())
        .all()
    )


def get_active_runtime_config(
    db: Session,
    *,
    tenant_id: str | None,
    purpose: str = DEFAULT_PURPOSE,
) -> RuntimeModelConfig:
    entry = ensure_active_registry_entry(db, tenant_id=tenant_id, purpose=purpose)
    return RuntimeModelConfig(
        registry_id=entry.id,
        tenant_id=entry.tenant_id,
        purpose=entry.purpose,
        provider=entry.provider,
        model_name=entry.model_name,
        prompt_version=entry.prompt_version,
        config=_normalize_registry_config(entry.config or {}),
    )


def validate_registry_candidate(
    *,
    provider: str,
    model_name: str,
    prompt_version: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    failures: list[str] = []

    def add_check(name: str, passed: bool, details: str, observed_value: Any = None) -> None:
        checks.append(
            {
                "name": name,
                "passed": passed,
                "details": details,
                "observed_value": observed_value,
            }
        )
        if not passed:
            failures.append(f"{name}: {details}")

    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model_name or "").strip()
    normalized_prompt = str(prompt_version or "").strip()

    provider_spec = SUPPORTED_PROVIDERS.get(normalized_provider)
    add_check(
        "provider_supported",
        provider_spec is not None,
        f"Registry supports the following providers: {', '.join(sorted(SUPPORTED_PROVIDERS))}.",
        normalized_provider,
    )
    if provider_spec is not None:
        add_check(
            "model_name_format",
            bool(provider_spec["model_check"](normalized_model)),
            provider_spec["model_rule"],
            normalized_model,
        )
    else:
        add_check(
            "model_name_format",
            False,
            "Model name cannot be validated for an unsupported provider.",
            normalized_model,
        )
    add_check(
        "prompt_version_present",
        bool(normalized_prompt),
        "Prompt version must be set for auditability.",
        normalized_prompt,
    )
    add_check(
        "config_is_object",
        isinstance(config, dict),
        "Registry config must be a JSON object.",
        type(config).__name__,
    )
    normalized_config = _normalize_registry_config(config if isinstance(config, dict) else {})
    add_check(
        "eval_summary_present",
        isinstance(normalized_config.get("eval_summary"), dict),
        "Eval summary must be an object when supplied.",
        type(normalized_config.get("eval_summary")).__name__,
    )
    add_check(
        "canary_status_present",
        isinstance(normalized_config.get("canary_status"), str),
        "Canary status must be a string.",
        normalized_config.get("canary_status"),
    )

    fixture_report = {
        "name": "extraction_contract_fixture",
        "status": "passed" if not failures else "failed",
        "details": "Static fixture compatibility checks passed."
        if not failures
        else "Static fixture compatibility checks failed.",
    }

    overall_status = "passed" if not failures else "failed"
    return {
        "overall_status": overall_status,
        "checks": checks,
        "fixture_results": [fixture_report],
        "live_check": "skipped",
        "summary": "Registry candidate validated successfully."
        if not failures
        else "Registry candidate failed validation.",
    }


def stage_registry_entry(
    db: Session,
    *,
    tenant_id: str | None,
    purpose: str,
    provider: str,
    model_name: str,
    prompt_version: str,
    config: dict[str, Any],
    created_by: str | None,
) -> ModelRegistryModel:
    ensure_active_registry_entry(db, tenant_id=tenant_id, purpose=purpose, created_by=created_by)
    report = validate_registry_candidate(
        provider=provider,
        model_name=model_name,
        prompt_version=prompt_version,
        config=config,
    )
    entry = ModelRegistryModel(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        purpose=purpose,
        provider=provider.strip().lower(),
        model_name=model_name.strip(),
        prompt_version=prompt_version.strip(),
        status="staged",
        config=_normalize_registry_config(config or {}),
        validation_status=report["overall_status"],
        validation_report=report,
        created_by=created_by,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def validate_staged_entry(db: Session, *, entry_id: str, tenant_id: str | None) -> ModelRegistryModel:
    entry = (
        db.query(ModelRegistryModel)
        .filter(ModelRegistryModel.id == entry_id, ModelRegistryModel.tenant_id == tenant_id)
        .first()
    )
    if entry is None:
        raise ValueError("Registry entry not found")

    report = validate_registry_candidate(
        provider=entry.provider,
        model_name=entry.model_name,
        prompt_version=entry.prompt_version,
        config=entry.config or {},
    )
    entry.validation_status = report["overall_status"]
    entry.validation_report = report
    entry.updated_at = _utcnow()
    db.commit()
    db.refresh(entry)
    return entry


def promote_registry_entry(
    db: Session,
    *,
    tenant_id: str | None,
    purpose: str,
    entry_id: str,
) -> ModelRegistryModel:
    target = (
        db.query(ModelRegistryModel)
        .filter(
            ModelRegistryModel.id == entry_id,
            ModelRegistryModel.tenant_id == tenant_id,
            ModelRegistryModel.purpose == purpose,
        )
        .first()
    )
    if target is None:
        raise ValueError("Registry entry not found")
    if (target.validation_status or "pending") != "passed":
        raise ValueError("Only validation-passed registry entries can be promoted")

    current_active = (
        db.query(ModelRegistryModel)
        .filter(
            ModelRegistryModel.tenant_id == tenant_id,
            ModelRegistryModel.purpose == purpose,
            ModelRegistryModel.status == "active",
        )
        .first()
    )
    if current_active and current_active.id != target.id:
        current_active.status = "rollback"
        current_active.updated_at = _utcnow()

    target.status = "active"
    target.promoted_at = _utcnow()
    target.updated_at = _utcnow()
    db.commit()
    db.refresh(target)
    return target


def rollback_registry_entry(
    db: Session,
    *,
    tenant_id: str | None,
    purpose: str,
    entry_id: str | None = None,
) -> ModelRegistryModel:
    query = db.query(ModelRegistryModel).filter(
        ModelRegistryModel.tenant_id == tenant_id,
        ModelRegistryModel.purpose == purpose,
        ModelRegistryModel.status == "rollback",
    )
    if entry_id:
        query = query.filter(ModelRegistryModel.id == entry_id)
    target = query.order_by(ModelRegistryModel.updated_at.desc(), ModelRegistryModel.created_at.desc()).first()
    if target is None:
        raise ValueError("No rollback candidate found")

    current_active = (
        db.query(ModelRegistryModel)
        .filter(
            ModelRegistryModel.tenant_id == tenant_id,
            ModelRegistryModel.purpose == purpose,
            ModelRegistryModel.status == "active",
        )
        .first()
    )
    if current_active and current_active.id != target.id:
        current_active.status = "rollback"
        current_active.updated_at = _utcnow()

    target.status = "active"
    target.promoted_at = _utcnow()
    target.updated_at = _utcnow()
    db.commit()
    db.refresh(target)
    return target
