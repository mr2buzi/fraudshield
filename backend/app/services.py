from __future__ import annotations

import json
import time
from statistics import quantiles

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from .auth import AnalystIdentity
from .models import Alert, AnalystDecision, TransactionRecord
from .sample_data import demo_transactions
from .schemas import (
    AlertListResponse,
    AlertResponse,
    AlertStatus,
    AnalystAction,
    DecisionRequest,
    MetricsOverview,
    TopFactor,
    TransactionScoreRequest,
    TransactionScoreResponse,
    TransactionSummary,
)
from .scoring import WeightedFraudScorer


def _serialize_top_factors(top_factors: list[TopFactor]) -> str:
    return json.dumps([factor.model_dump() for factor in top_factors])


def _deserialize_top_factors(raw: str) -> list[TopFactor]:
    return [TopFactor(**item) for item in json.loads(raw)]


def _reason_summary(top_factors: list[TopFactor]) -> str:
    return ", ".join(factor.label for factor in top_factors)


def score_transaction(session: Session, scorer: WeightedFraudScorer, payload: TransactionScoreRequest) -> TransactionScoreResponse:
    started = time.perf_counter()
    existing = session.scalar(select(TransactionRecord).where(TransactionRecord.external_id == payload.external_id))
    if existing:
        return TransactionScoreResponse(
            transaction_id=existing.id,
            alert_id=existing.alert.id if existing.alert else None,
            risk_score=existing.risk_score,
            risk_band=existing.risk_band,
            top_factors=_deserialize_top_factors(existing.top_factors),
            model_version=existing.model_version,
            latency_ms=existing.latency_ms,
        )

    score_result = scorer.score(payload)
    latency_ms = round((time.perf_counter() - started) * 1000.0, 2)
    transaction = TransactionRecord(
        external_id=payload.external_id,
        amount=payload.amount,
        currency=payload.currency,
        merchant_name=payload.merchant_name,
        merchant_category=payload.merchant_category,
        entry_mode=payload.entry_mode,
        country=payload.country,
        customer_tenure_days=payload.customer_tenure_days,
        account_age_days=payload.account_age_days,
        email_age_days=payload.email_age_days,
        card_present=payload.card_present,
        is_international=payload.is_international,
        ip_risk_score=payload.ip_risk_score,
        velocity_1h=payload.velocity_1h,
        velocity_24h=payload.velocity_24h,
        risk_score=score_result.score,
        risk_band=score_result.band.value,
        flagged=score_result.should_alert,
        top_factors=_serialize_top_factors(score_result.top_factors),
        model_version=score_result.model_version,
        latency_ms=latency_ms,
    )
    session.add(transaction)
    session.flush()

    alert = None
    if score_result.should_alert:
        alert = Alert(
            transaction_id=transaction.id,
            status=AlertStatus.open.value,
            reason_summary=_reason_summary(score_result.top_factors),
        )
        session.add(alert)

    session.commit()
    if alert is not None:
        session.refresh(alert)

    return TransactionScoreResponse(
        transaction_id=transaction.id,
        alert_id=alert.id if alert else None,
        risk_score=score_result.score,
        risk_band=score_result.band,
        top_factors=score_result.top_factors,
        model_version=score_result.model_version,
        latency_ms=latency_ms,
    )


def _transaction_summary(row: TransactionRecord) -> TransactionSummary:
    return TransactionSummary(
        id=row.id,
        external_id=row.external_id,
        amount=row.amount,
        currency=row.currency,
        merchant_name=row.merchant_name,
        merchant_category=row.merchant_category,
        country=row.country,
        created_at=row.created_at,
        risk_score=row.risk_score,
        risk_band=row.risk_band,
        flagged=row.flagged,
        model_version=row.model_version,
        latency_ms=row.latency_ms,
        top_factors=_deserialize_top_factors(row.top_factors),
    )


def _alert_response(alert: Alert) -> AlertResponse:
    return AlertResponse(
        id=alert.id,
        status=alert.status,
        reason_summary=alert.reason_summary,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        transaction=_transaction_summary(alert.transaction),
        decisions=alert.decisions,
    )


def list_alerts(session: Session) -> AlertListResponse:
    alerts = session.scalars(
        select(Alert).options(joinedload(Alert.transaction), joinedload(Alert.decisions)).order_by(Alert.created_at.desc())
    ).unique()
    return AlertListResponse(alerts=[_alert_response(alert) for alert in alerts])


def get_alert(session: Session, alert_id: str) -> AlertResponse | None:
    alert = session.scalar(
        select(Alert)
        .options(joinedload(Alert.transaction), joinedload(Alert.decisions))
        .where(Alert.id == alert_id)
    )
    if alert is None:
        return None
    return _alert_response(alert)


def record_decision(
    session: Session,
    alert_id: str,
    payload: DecisionRequest,
    identity: AnalystIdentity,
) -> AlertResponse | None:
    alert = session.scalar(
        select(Alert)
        .options(joinedload(Alert.transaction), joinedload(Alert.decisions))
        .where(Alert.id == alert_id)
    )
    if alert is None:
        return None

    decision = AnalystDecision(
        alert_id=alert.id,
        decision=payload.decision.value,
        analyst_name=identity.analyst_name,
        notes=payload.notes,
    )
    session.add(decision)
    if payload.decision == AnalystAction.escalate:
        alert.status = AlertStatus.escalated.value
    else:
        alert.status = AlertStatus.resolved.value
    session.commit()
    session.refresh(alert)
    return get_alert(session, alert_id)


def metrics_overview(session: Session, scorer: WeightedFraudScorer) -> MetricsOverview:
    total_transactions = session.scalar(select(func.count(TransactionRecord.id))) or 0
    total_alerts = session.scalar(select(func.count(Alert.id))) or 0
    open_alerts = session.scalar(select(func.count(Alert.id)).where(Alert.status == AlertStatus.open.value)) or 0
    escalated_alerts = session.scalar(select(func.count(Alert.id)).where(Alert.status == AlertStatus.escalated.value)) or 0
    reviewed_alerts = session.scalar(select(func.count(Alert.id)).where(Alert.status == AlertStatus.resolved.value)) or 0
    average_risk_score = session.scalar(select(func.avg(TransactionRecord.risk_score))) or 0.0
    latencies = list(session.scalars(select(TransactionRecord.latency_ms)))
    p95_latency = quantiles(latencies, n=20)[-1] if len(latencies) >= 2 else (latencies[0] if latencies else 0.0)

    reviewed_total = session.scalar(
        select(func.count(AnalystDecision.id)).where(
            AnalystDecision.decision.in_([AnalystAction.confirm_fraud.value, AnalystAction.mark_legit.value])
        )
    ) or 0
    confirmed_fraud = session.scalar(
        select(func.count(AnalystDecision.id)).where(AnalystDecision.decision == AnalystAction.confirm_fraud.value)
    ) or 0
    precision_proxy = round(confirmed_fraud / reviewed_total, 4) if reviewed_total else 0.0

    recent_rows = list(
        session.scalars(select(TransactionRecord).order_by(TransactionRecord.created_at.desc()).limit(20))
    )
    recent_amount_avg = sum(row.amount for row in recent_rows) / len(recent_rows) if recent_rows else 0.0
    recent_international_rate = (
        sum(1 for row in recent_rows if row.is_international) / len(recent_rows) if recent_rows else 0.0
    )
    baseline = scorer.metadata.get("baseline_stats", {})
    baseline_amount = baseline.get("average_amount", 0.0) or 1.0
    recent_amount_shift_pct = round(((recent_amount_avg - baseline_amount) / baseline_amount) * 100.0, 2)

    return MetricsOverview(
        total_transactions=total_transactions,
        total_alerts=total_alerts,
        open_alerts=open_alerts,
        escalated_alerts=escalated_alerts,
        reviewed_alerts=reviewed_alerts,
        precision_proxy=precision_proxy,
        average_risk_score=round(float(average_risk_score), 4),
        p95_latency_ms=round(float(p95_latency), 2),
        recent_amount_shift_pct=recent_amount_shift_pct,
        recent_international_rate=round(recent_international_rate, 4),
        baseline_international_rate=round(float(baseline.get("international_rate", 0.0)), 4),
        model_version=scorer.metadata["model_version"],
    )


def seed_demo_data(session: Session, scorer: WeightedFraudScorer) -> None:
    has_rows = session.scalar(select(func.count(TransactionRecord.id))) or 0
    if has_rows:
        return
    for payload in demo_transactions():
        score_transaction(session, scorer, payload)
