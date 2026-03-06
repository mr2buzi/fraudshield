from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from .schemas import RiskBand, TopFactor, TransactionScoreRequest


DEFAULT_MODEL_METADATA = {
    "model_version": "baseline-2026.03",
    "intercept": -2.75,
    "thresholds": {"medium": 0.45, "high": 0.72, "alert": 0.66},
    "feature_weights": {
        "amount_scaled": 0.85,
        "velocity_1h": 0.12,
        "velocity_24h": 0.04,
        "ip_risk_score": 2.2,
        "is_international": 0.75,
        "card_not_present": 0.92,
        "entry_mode_risk": 0.68,
        "merchant_category_risk": 1.15,
        "country_risk": 0.88,
        "account_email_gap": 0.5,
        "young_account": 0.6,
    },
    "feature_labels": {
        "amount_scaled": "High transaction amount",
        "velocity_1h": "Rapid transaction burst",
        "velocity_24h": "High daily transaction volume",
        "ip_risk_score": "Risky IP or device fingerprint",
        "is_international": "International usage pattern",
        "card_not_present": "Card-not-present transaction",
        "entry_mode_risk": "Risky entry mode",
        "merchant_category_risk": "Merchant category risk",
        "country_risk": "Elevated country risk",
        "account_email_gap": "Large account and email age mismatch",
        "young_account": "Young customer account",
    },
    "baseline_stats": {"average_amount": 124.5, "international_rate": 0.19},
}

HIGH_RISK_COUNTRIES = {"NG", "BR", "MX", "ID"}
HIGH_RISK_CATEGORIES = {
    "electronics": 0.95,
    "travel": 0.72,
    "digital_goods": 1.0,
    "gaming": 0.88,
    "luxury": 0.64,
    "groceries": 0.1,
    "fuel": 0.18,
    "utilities": 0.05,
}
ENTRY_MODE_RISK = {
    "chip": 0.05,
    "tap": 0.15,
    "online": 0.75,
    "manual": 0.92,
    "keyed": 1.0,
}


@dataclass
class ScoreResult:
    score: float
    band: RiskBand
    should_alert: bool
    top_factors: list[TopFactor]
    model_version: str


class WeightedFraudScorer:
    def __init__(self, artifact_path: Path):
        self._artifact_path = artifact_path
        self._metadata = self._load_metadata()

    def _load_metadata(self) -> dict:
        if self._artifact_path.exists():
            return json.loads(self._artifact_path.read_text(encoding="utf-8"))
        return DEFAULT_MODEL_METADATA

    @property
    def metadata(self) -> dict:
        return self._metadata

    def _feature_values(self, payload: TransactionScoreRequest) -> dict[str, float]:
        amount_scaled = min(payload.amount / 250.0, 8.0)
        account_gap = max(payload.account_age_days - payload.email_age_days, 0) / 365.0
        return {
            "amount_scaled": amount_scaled,
            "velocity_1h": float(payload.velocity_1h),
            "velocity_24h": float(payload.velocity_24h),
            "ip_risk_score": payload.ip_risk_score,
            "is_international": 1.0 if payload.is_international else 0.0,
            "card_not_present": 0.0 if payload.card_present else 1.0,
            "entry_mode_risk": ENTRY_MODE_RISK.get(payload.entry_mode.lower(), 0.45),
            "merchant_category_risk": HIGH_RISK_CATEGORIES.get(payload.merchant_category.lower(), 0.35),
            "country_risk": 1.0 if payload.country.upper() in HIGH_RISK_COUNTRIES else 0.15,
            "account_email_gap": account_gap,
            "young_account": 1.0 if payload.account_age_days < 60 else 0.0,
        }

    def score(self, payload: TransactionScoreRequest) -> ScoreResult:
        weights = self._metadata["feature_weights"]
        labels = self._metadata["feature_labels"]
        thresholds = self._metadata["thresholds"]
        features = self._feature_values(payload)
        logit = self._metadata["intercept"]
        contributions: list[tuple[str, float]] = []
        for name, value in features.items():
            contribution = value * weights.get(name, 0.0)
            contributions.append((name, contribution))
            logit += contribution

        score = 1.0 / (1.0 + math.exp(-logit))
        if score >= thresholds["high"]:
            band = RiskBand.high
        elif score >= thresholds["medium"]:
            band = RiskBand.medium
        else:
            band = RiskBand.low

        top_factors = [
            TopFactor(
                feature=name,
                label=labels.get(name, name.replace("_", " ").title()),
                contribution=round(abs(contribution), 4),
                direction="increase" if contribution >= 0 else "decrease",
            )
            for name, contribution in sorted(contributions, key=lambda item: abs(item[1]), reverse=True)[:3]
        ]
        return ScoreResult(
            score=round(score, 4),
            band=band,
            should_alert=score >= thresholds["alert"],
            top_factors=top_factors,
            model_version=self._metadata["model_version"],
        )
