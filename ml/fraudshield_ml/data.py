from __future__ import annotations

import numpy as np
import pandas as pd


MERCHANT_CATEGORIES = ["groceries", "fuel", "electronics", "travel", "gaming", "utilities", "digital_goods", "luxury"]
ENTRY_MODES = ["chip", "tap", "online", "manual", "keyed"]
COUNTRIES = ["GB", "GB", "GB", "US", "FR", "DE", "NG", "BR", "MX"]


def make_synthetic_dataset(size: int = 4000, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    merchant_category = rng.choice(MERCHANT_CATEGORIES, size=size)
    entry_mode = rng.choice(ENTRY_MODES, size=size, p=[0.24, 0.29, 0.28, 0.1, 0.09])
    country = rng.choice(COUNTRIES, size=size)
    amount = np.round(rng.gamma(shape=2.2, scale=68.0, size=size), 2)
    customer_tenure_days = rng.integers(5, 1200, size=size)
    account_age_days = np.clip(customer_tenure_days - rng.integers(0, 40, size=size), 1, None)
    email_age_days = np.clip(account_age_days - rng.integers(0, 180, size=size), 1, None)
    card_present = rng.choice([0, 1], size=size, p=[0.42, 0.58]).astype(bool)
    is_international = rng.choice([0, 1], size=size, p=[0.82, 0.18]).astype(bool)
    ip_risk_score = np.round(rng.beta(1.7, 5.0, size=size), 4)
    velocity_1h = rng.poisson(lam=1.6, size=size)
    velocity_24h = velocity_1h + rng.poisson(lam=3.2, size=size)

    category_risk = pd.Series(merchant_category).map(
        {
            "groceries": 0.05,
            "fuel": 0.12,
            "electronics": 0.65,
            "travel": 0.55,
            "gaming": 0.72,
            "utilities": 0.04,
            "digital_goods": 0.9,
            "luxury": 0.48,
        }
    ).to_numpy()
    entry_mode_risk = pd.Series(entry_mode).map(
        {"chip": 0.05, "tap": 0.15, "online": 0.55, "manual": 0.78, "keyed": 0.9}
    ).to_numpy()
    country_risk = np.isin(country, ["NG", "BR", "MX"]).astype(float)
    young_account = (account_age_days < 60).astype(float)
    card_not_present = (~card_present).astype(float)
    account_email_gap = np.maximum(account_age_days - email_age_days, 0) / 365.0
    amount_scaled = np.minimum(amount / 250.0, 8.0)

    logit = (
        -3.3
        + 0.9 * amount_scaled
        + 0.15 * velocity_1h
        + 0.05 * velocity_24h
        + 2.3 * ip_risk_score
        + 0.8 * is_international.astype(float)
        + 0.95 * card_not_present
        + 0.75 * entry_mode_risk
        + 1.2 * category_risk
        + 0.9 * country_risk
        + 0.5 * account_email_gap
        + 0.6 * young_account
    )
    probability = 1.0 / (1.0 + np.exp(-logit))
    fraud = rng.binomial(1, probability)

    return pd.DataFrame(
        {
            "amount": amount,
            "customer_tenure_days": customer_tenure_days,
            "account_age_days": account_age_days,
            "email_age_days": email_age_days,
            "card_present": card_present,
            "is_international": is_international,
            "ip_risk_score": ip_risk_score,
            "velocity_1h": velocity_1h,
            "velocity_24h": velocity_24h,
            "merchant_category": merchant_category,
            "entry_mode": entry_mode,
            "country": country,
            "is_fraud": fraud,
        }
    )
