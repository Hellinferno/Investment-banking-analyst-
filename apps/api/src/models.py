import re
from datetime import datetime, timezone
from typing import Any, Dict, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

DealTypeStr = Literal[
    "ipo", "ma", "lbo", "debt_raise", "equity_raise",
    "restructuring", "merger", "acquisition", "secondary",
    "private_placement", "other",
]

DealStageStr = Literal[
    "preliminary", "in_progress", "due_diligence", "final", "closed",
]

ProcessStageStr = Literal[
    "origination", "teaser", "nda", "cim", "ioi", "management_meetings",
    "loi", "diligence", "close",
    # Legacy values accepted for backward compatibility with existing UI/data.
    "nda_negotiation", "nda_signed", "teaser_sent", "cim_sent",
    "io_received", "loi_signed", "exclusivity", "definitive_agreement",
]

PriorityStr = Literal["low", "medium", "high"]
ReviewStatusStr = Literal["draft", "in_review", "approved", "rejected", "needs_changes"]
UserRoleStr = Literal["analyst", "reviewer", "admin"]
RegistryStatusStr = Literal["staged", "active", "rollback"]
ValidationStatusStr = Literal["pending", "passed", "failed", "warning", "skipped"]

_HTML_TAG_RE = re.compile(r"<[^>]+>")
T = TypeVar("T")


def _strip_html(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _HTML_TAG_RE.sub("", value).strip()


class DealCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    company_name: str = Field(..., min_length=1, max_length=80)
    deal_type: DealTypeStr
    industry: str = Field(..., min_length=1, max_length=60)
    deal_stage: DealStageStr = "preliminary"
    process_stage: ProcessStageStr = "origination"
    notes: Optional[str] = Field(None, max_length=2000)

    @field_validator("name", "company_name", "industry", mode="before")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("notes", mode="before")
    @classmethod
    def sanitize_notes(cls, value):
        return _strip_html(value)


class DealUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    company_name: Optional[str] = Field(None, min_length=1, max_length=80)
    deal_type: Optional[DealTypeStr] = None
    industry: Optional[str] = Field(None, min_length=1, max_length=60)
    deal_stage: Optional[DealStageStr] = None
    process_stage: Optional[ProcessStageStr] = None
    notes: Optional[str] = Field(None, max_length=2000)
    force: bool = False

    @field_validator("name", "company_name", "industry", mode="before")
    @classmethod
    def strip_optional_whitespace(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("notes", mode="before")
    @classmethod
    def sanitize_notes(cls, value):
        return _strip_html(value)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=120)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class CurrentUserResponse(BaseModel):
    user_id: str
    tenant_id: str
    role: UserRoleStr | str
    email: Optional[str] = None
    token_id: Optional[str] = None


class LoginResponse(BaseModel):
    user: CurrentUserResponse
    session_expires_at: str


class DevAuthTokenRequest(BaseModel):
    requested_role: UserRoleStr = "analyst"
    tenant_id: Optional[str] = Field(None, min_length=1, max_length=80)
    user_id: Optional[str] = Field(None, min_length=1, max_length=80)
    email: Optional[str] = Field(None, max_length=120)

    @field_validator("tenant_id", "user_id", "email", mode="before")
    @classmethod
    def strip_optional_whitespace(cls, value):
        return value.strip() if isinstance(value, str) else value


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: str
    user: CurrentUserResponse


class OutputReviewUpdate(BaseModel):
    review_status: Optional[ReviewStatusStr] = None
    reviewer_notes: Optional[str] = Field(None, max_length=2000)
    decision: Optional[ReviewStatusStr] = None
    comment: Optional[str] = Field(None, max_length=2000)

    @field_validator("reviewer_notes", "comment", mode="before")
    @classmethod
    def sanitize_reviewer_notes(cls, value):
        return _strip_html(value)

    @model_validator(mode="after")
    def require_status(self):
        if not (self.review_status or self.decision):
            raise ValueError("review_status or decision is required")
        return self

    @property
    def resolved_status(self) -> ReviewStatusStr:
        status_value = self.review_status or self.decision
        if not status_value:
            raise ValueError("review_status or decision is required")
        return status_value

    @property
    def resolved_notes(self) -> Optional[str]:
        return self.reviewer_notes if self.reviewer_notes is not None else self.comment


class ExtractionField(BaseModel, Generic[T]):
    value: Optional[T] = None
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = Field(min_length=1)
    reasoning: Optional[str] = None


class PartialYearRunRateValue(BaseModel):
    partial_quarters_reported: Optional[int] = Field(default=None, ge=1, le=4)
    fiscal_year_partial: Optional[int] = None
    ytd_revenue_inr: Optional[float] = None
    implied_annual_run_rate: Optional[float] = None
    run_rate_growth_vs_last_fy: Optional[float] = None


class GeminiExtractionResponse(BaseModel):
    reconciliation_log: str = ""
    company_legal_form: ExtractionField[str | None]
    listing_status: ExtractionField[str | None]
    cin: ExtractionField[str | None]
    historical_revenues: ExtractionField[list[float]]
    historical_ebitda_margins: ExtractionField[list[float]]
    net_debt: ExtractionField[float | None]
    total_borrowings: ExtractionField[float | None]
    ccps_liability: ExtractionField[float | None]
    lease_liabilities: ExtractionField[float | None]
    lease_liabilities_current: ExtractionField[float | None]
    lease_liabilities_noncurrent: ExtractionField[float | None]
    cash_and_equivalents: ExtractionField[float | None]
    partial_year_run_rate: ExtractionField[PartialYearRunRateValue | None]
    shares_outstanding: ExtractionField[float | None]
    diluted_shares_outstanding: ExtractionField[float | None]
    cap_ex_percent_rev: ExtractionField[float | None]
    da_percent_rev: ExtractionField[float | None]
    debt_to_equity: ExtractionField[float | None]
    beta: ExtractionField[float | None]
    discount_rate_reference: ExtractionField[float | None]
    forecast_revenue_growth_low: ExtractionField[float | None]
    forecast_revenue_growth_high: ExtractionField[float | None]
    terminal_growth_reference: ExtractionField[float | None]
    base_fy: ExtractionField[int | None]
    reporting_unit: ExtractionField[str | None]
    industry_sector: ExtractionField[str | None]
    profit_after_tax: ExtractionField[float | None]
    basic_eps: ExtractionField[float | None]
    operating_cash_flow: ExtractionField[float | None]
    segment_revenues: ExtractionField[dict[str, float] | None]
    segment_ebitda_margins: ExtractionField[dict[str, float] | None]
    currency: str = "INR"


class ExtractionValidationCheck(BaseModel):
    name: str
    passed: bool
    blocking: bool = False
    details: str
    observed_value: Optional[Any] = None


class ExtractionValidatorReport(BaseModel):
    status: Literal["passed", "failed", "skipped"]
    summary: str
    blocking_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checks: list[ExtractionValidationCheck] = Field(default_factory=list)
    source_summary: dict[str, Any] = Field(default_factory=dict)


class ModelRegistryStageRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model_name: str = Field(min_length=1, max_length=120)
    prompt_version: str = Field(min_length=1, max_length=80)
    config: Dict[str, Any] = Field(default_factory=dict)


class ModelRegistryPromoteRequest(BaseModel):
    entry_id: str = Field(min_length=1, max_length=80)


class ModelRegistryRollbackRequest(BaseModel):
    entry_id: Optional[str] = Field(default=None, min_length=1, max_length=80)


class ModelRegistryEntryResponse(BaseModel):
    id: str
    tenant_id: Optional[str] = None
    purpose: str
    provider: str
    model_name: str
    prompt_version: str
    status: RegistryStatusStr
    config: Dict[str, Any] = Field(default_factory=dict)
    validation_status: ValidationStatusStr = "pending"
    validation_report: Dict[str, Any] = Field(default_factory=dict)
    eval_summary: Dict[str, Any] = Field(default_factory=dict)
    canary_status: str = "pending"
    rollout_notes: str = ""
    rollback_from_id: Optional[str] = None
    created_by: Optional[str] = None
    promoted_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class Meta(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    request_id: str


class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    meta: Meta


class APIResponseList(BaseModel):
    success: bool
    data: Dict[str, Any]
    error: Optional[Dict[str, Any]] = None
    meta: Meta
