from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from sklearn.linear_model import LogisticRegression

from .data import make_synthetic_dataset
from .evaluate import choose_alert_threshold, summarize_metrics
from .features import build_feature_frame


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "artifacts"
ARTIFACT_PATH = ARTIFACT_DIR / "model_metadata.json"

FEATURE_LABELS = {
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
}


def train_and_export(check_only: bool = False) -> dict:
    dataset = make_synthetic_dataset()
    features = build_feature_frame(dataset)
    labels = dataset["is_fraud"]

    model = LogisticRegression(max_iter=1200, class_weight="balanced")
    model.fit(features, labels)
    probabilities = model.predict_proba(features)[:, 1]

    alert_threshold = choose_alert_threshold(labels, probabilities)
    artifact = {
        "model_version": f"logreg-{datetime.now(timezone.utc).strftime('%Y.%m.%d')}",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "intercept": round(float(model.intercept_[0]), 6),
        "thresholds": {"medium": 0.45, "high": 0.72, "alert": alert_threshold},
        "feature_weights": {
            name: round(float(weight), 6) for name, weight in zip(features.columns.tolist(), model.coef_[0])
        },
        "feature_labels": FEATURE_LABELS,
        "metrics": summarize_metrics(labels.to_numpy(), probabilities, alert_threshold),
        "baseline_stats": {
            "average_amount": round(float(dataset["amount"].mean()), 4),
            "international_rate": round(float(dataset["is_international"].mean()), 4),
        },
    }
    if not check_only:
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        ARTIFACT_PATH.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the FraudShield baseline model.")
    parser.add_argument("--check", action="store_true", help="Run training without writing an artifact.")
    args = parser.parse_args()
    artifact = train_and_export(check_only=args.check)
    print(json.dumps(artifact["metrics"], indent=2))


if __name__ == "__main__":
    main()
