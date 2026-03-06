from __future__ import annotations

import pandas as pd


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
ENTRY_MODE_RISK = {"chip": 0.05, "tap": 0.15, "online": 0.75, "manual": 0.92, "keyed": 1.0}


def build_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "amount_scaled": (frame["amount"] / 250.0).clip(upper=8.0),
            "velocity_1h": frame["velocity_1h"].astype(float),
            "velocity_24h": frame["velocity_24h"].astype(float),
            "ip_risk_score": frame["ip_risk_score"].astype(float),
            "is_international": frame["is_international"].astype(int),
            "card_not_present": (~frame["card_present"].astype(bool)).astype(int),
            "entry_mode_risk": frame["entry_mode"].str.lower().map(ENTRY_MODE_RISK).fillna(0.45),
            "merchant_category_risk": frame["merchant_category"].str.lower().map(HIGH_RISK_CATEGORIES).fillna(0.35),
            "country_risk": frame["country"].str.upper().isin(HIGH_RISK_COUNTRIES).astype(int),
            "account_email_gap": (frame["account_age_days"] - frame["email_age_days"]).clip(lower=0) / 365.0,
            "young_account": (frame["account_age_days"] < 60).astype(int),
        }
    )
