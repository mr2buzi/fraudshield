from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class OrmModel(BaseModel):
    model_config = {"from_attributes": True, "protected_namespaces": ()}


class RiskBand(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class AlertStatus(str, Enum):
    open = "open"
    under_review = "under_review"
    resolved = "resolved"
    escalated = "escalated"


class AnalystAction(str, Enum):
    confirm_fraud = "confirm_fraud"
    mark_legit = "mark_legit"
    escalate = "escalate"


class AnalystRole(str, Enum):
    analyst = "analyst"
    lead_analyst = "lead_analyst"
    manager = "manager"


class TopFactor(OrmModel):
    feature: str
    label: str
    contribution: float
    direction: str


class TransactionScoreRequest(OrmModel):
    external_id: str = Field(..., min_length=3, max_length=64)
    amount: float = Field(..., gt=0)
    currency: str = Field(default="GBP", min_length=3, max_length=8)
    merchant_name: str = Field(..., min_length=2, max_length=128)
    merchant_category: str = Field(..., min_length=2, max_length=64)
    entry_mode: str = Field(..., min_length=2, max_length=32)
    country: str = Field(..., min_length=2, max_length=8)
    customer_tenure_days: int = Field(..., ge=0)
    account_age_days: int = Field(..., ge=0)
    email_age_days: int = Field(..., ge=0)
    card_present: bool
    is_international: bool
    ip_risk_score: float = Field(..., ge=0, le=1)
    velocity_1h: int = Field(..., ge=0)
    velocity_24h: int = Field(..., ge=0)

    @field_validator("currency", "country", mode="before")
    @classmethod
    def upper_code(cls, value: str) -> str:
        return value.upper()


class TransactionScoreResponse(OrmModel):
    transaction_id: str
    alert_id: str | None
    risk_score: float
    risk_band: RiskBand
    top_factors: list[TopFactor]
    model_version: str
    latency_ms: float


class DecisionRequest(OrmModel):
    decision: AnalystAction
    notes: str = Field(default="", max_length=1000)


class AuthSessionRequest(OrmModel):
    analyst_name: str = Field(..., min_length=2, max_length=64)
    pin: str = Field(..., min_length=4, max_length=16)


class AuthSessionResponse(OrmModel):
    analyst_name: str
    role: AnalystRole
    token: str
    allowed_actions: list[AnalystAction]


class AnalystDecisionResponse(OrmModel):
    id: str
    decision: AnalystAction
    analyst_name: str
    notes: str
    created_at: datetime


class TransactionSummary(OrmModel):
    id: str
    external_id: str
    amount: float
    currency: str
    merchant_name: str
    merchant_category: str
    country: str
    created_at: datetime
    risk_score: float
    risk_band: RiskBand
    flagged: bool
    model_version: str
    latency_ms: float
    top_factors: list[TopFactor]


class AlertResponse(OrmModel):
    id: str
    status: AlertStatus
    reason_summary: str
    created_at: datetime
    updated_at: datetime
    transaction: TransactionSummary
    decisions: list[AnalystDecisionResponse]


class AlertListResponse(OrmModel):
    alerts: list[AlertResponse]


class MetricsOverview(OrmModel):
    total_transactions: int
    total_alerts: int
    open_alerts: int
    escalated_alerts: int
    reviewed_alerts: int
    precision_proxy: float
    average_risk_score: float
    p95_latency_ms: float
    recent_amount_shift_pct: float
    recent_international_rate: float
    baseline_international_rate: float
    model_version: str


class HealthResponse(OrmModel):
    status: str
    model_version: str
