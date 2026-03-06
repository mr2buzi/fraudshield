from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT = ROOT_DIR / "ml" / "artifacts" / "model_metadata.json"


@dataclass(frozen=True)
class Settings:
    database_url: str
    model_artifact_path: Path
    seed_on_startup: bool
    cors_origins: list[str]
    rate_limit_per_minute: int
    demo_analyst_name: str


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> Settings:
    cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./fraudshield.db"),
        model_artifact_path=Path(os.getenv("MODEL_ARTIFACT_PATH", str(DEFAULT_ARTIFACT))),
        seed_on_startup=_as_bool(os.getenv("SEED_ON_STARTUP"), True),
        cors_origins=[origin.strip() for origin in cors_origins.split(",") if origin.strip()],
        rate_limit_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")),
        demo_analyst_name=os.getenv("DEMO_ANALYST_NAME", "demo.analyst"),
    )
