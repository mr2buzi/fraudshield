from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Generator
from threading import Lock

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .auth import AnalystIdentity, create_demo_session, enforce_action_permission, require_analyst_session
from .config import Settings, load_settings
from .database import Base, build_session_factory
from .schemas import (
    AlertListResponse,
    AlertResponse,
    AuthSessionRequest,
    AuthSessionResponse,
    DecisionRequest,
    HealthResponse,
    MetricsOverview,
    TransactionScoreRequest,
    TransactionScoreResponse,
)
from .scoring import WeightedFraudScorer
from .services import get_alert, list_alerts, metrics_overview, record_decision, score_transaction, seed_demo_data


logging.basicConfig(level=logging.INFO, format='{"time":"%(asctime)s","level":"%(levelname)s","message":"%(message)s"}')
logger = logging.getLogger("fraudshield")


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        with self._lock:
            bucket = self._requests[key]
            now = time.time()
            while bucket and now - bucket[0] > 60:
                bucket.popleft()
            if len(bucket) >= self.per_minute:
                return False
            bucket.append(now)
            return True


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    engine, session_factory = build_session_factory(settings.database_url)
    scorer = WeightedFraudScorer(settings.model_artifact_path)
    app = FastAPI(title="FraudShield API", version="1.0.0")
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.scorer = scorer
    app.state.rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        elapsed = round((time.perf_counter() - started) * 1000.0, 2)
        logger.info("path=%s method=%s status=%s latency_ms=%s", request.url.path, request.method, response.status_code, elapsed)
        return response

    @app.on_event("startup")
    def startup() -> None:
        Base.metadata.create_all(bind=engine)
        if settings.seed_on_startup:
            with session_factory() as session:
                seed_demo_data(session, scorer)

    def get_db() -> Generator[Session, None, None]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    def enforce_rate_limit(request: Request) -> None:
        client_host = request.client.host if request.client else "unknown"
        if not app.state.rate_limiter.allow(client_host):
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", model_version=scorer.metadata["model_version"])

    @app.post("/api/v1/auth/session", response_model=AuthSessionResponse)
    def create_session(payload: AuthSessionRequest) -> AuthSessionResponse:
        return create_demo_session(payload)

    @app.post("/api/v1/transactions/score", response_model=TransactionScoreResponse)
    def score(
        payload: TransactionScoreRequest,
        request: Request,
        db: Session = Depends(get_db),
        _: AnalystIdentity = Depends(require_analyst_session),
    ) -> TransactionScoreResponse:
        enforce_rate_limit(request)
        return score_transaction(db, scorer, payload)

    @app.get("/api/v1/alerts", response_model=AlertListResponse)
    def alerts(db: Session = Depends(get_db), _: AnalystIdentity = Depends(require_analyst_session)) -> AlertListResponse:
        return list_alerts(db)

    @app.get("/api/v1/alerts/{alert_id}", response_model=AlertResponse)
    def alert_detail(
        alert_id: str,
        db: Session = Depends(get_db),
        _: AnalystIdentity = Depends(require_analyst_session),
    ) -> AlertResponse:
        alert = get_alert(db, alert_id)
        if alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return alert

    @app.post("/api/v1/alerts/{alert_id}/decision", response_model=AlertResponse)
    def decision(
        alert_id: str,
        payload: DecisionRequest,
        db: Session = Depends(get_db),
        identity: AnalystIdentity = Depends(require_analyst_session),
    ) -> AlertResponse:
        enforce_action_permission(identity, payload.decision)
        alert = record_decision(db, alert_id, payload, identity)
        if alert is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
        return alert

    @app.get("/api/v1/metrics/overview", response_model=MetricsOverview)
    def metrics(db: Session = Depends(get_db), _: AnalystIdentity = Depends(require_analyst_session)) -> MetricsOverview:
        return metrics_overview(db, scorer)

    @app.get("/", include_in_schema=False)
    def root() -> Response:
        return JSONResponse({"name": "FraudShield API", "status": "ok"})

    return app


app = create_app()
