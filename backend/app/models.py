from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TransactionRecord(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    merchant_name: Mapped[str] = mapped_column(String(128))
    merchant_category: Mapped[str] = mapped_column(String(64))
    entry_mode: Mapped[str] = mapped_column(String(32))
    country: Mapped[str] = mapped_column(String(8))
    customer_tenure_days: Mapped[int] = mapped_column(Integer)
    account_age_days: Mapped[int] = mapped_column(Integer)
    email_age_days: Mapped[int] = mapped_column(Integer)
    card_present: Mapped[bool] = mapped_column(Boolean)
    is_international: Mapped[bool] = mapped_column(Boolean)
    ip_risk_score: Mapped[float] = mapped_column(Float)
    velocity_1h: Mapped[int] = mapped_column(Integer)
    velocity_24h: Mapped[int] = mapped_column(Integer)
    risk_score: Mapped[float] = mapped_column(Float, index=True)
    risk_band: Mapped[str] = mapped_column(String(16), index=True)
    flagged: Mapped[bool] = mapped_column(Boolean, index=True)
    top_factors: Mapped[str] = mapped_column(Text)
    model_version: Mapped[str] = mapped_column(String(32))
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    alert: Mapped["Alert | None"] = relationship(back_populates="transaction", uselist=False)


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id: Mapped[str] = mapped_column(String(36), ForeignKey("transactions.id"), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    reason_summary: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transaction: Mapped[TransactionRecord] = relationship(back_populates="alert")
    decisions: Mapped[list["AnalystDecision"]] = relationship(
        back_populates="alert",
        cascade="all, delete-orphan",
        order_by="AnalystDecision.created_at",
    )


class AnalystDecision(Base):
    __tablename__ = "analyst_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    alert_id: Mapped[str] = mapped_column(String(36), ForeignKey("alerts.id"), index=True)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    analyst_name: Mapped[str] = mapped_column(String(64))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    alert: Mapped[Alert] = relationship(back_populates="decisions")
