from __future__ import annotations

import base64
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from .schemas import AnalystAction, AnalystRole, AuthSessionRequest, AuthSessionResponse


DEMO_USERS = {
    "demo.analyst": {"pin": "1357", "role": AnalystRole.analyst},
    "lead.analyst": {"pin": "2468", "role": AnalystRole.lead_analyst},
    "fraud.manager": {"pin": "9999", "role": AnalystRole.manager},
}


@dataclass(frozen=True)
class AnalystIdentity:
    analyst_name: str
    role: AnalystRole

    @property
    def allowed_actions(self) -> list[AnalystAction]:
        actions = [AnalystAction.confirm_fraud, AnalystAction.mark_legit]
        if self.role in {AnalystRole.lead_analyst, AnalystRole.manager}:
            actions.append(AnalystAction.escalate)
        return actions


def create_demo_session(payload: AuthSessionRequest) -> AuthSessionResponse:
    user = DEMO_USERS.get(payload.analyst_name)
    if user is None or user["pin"] != payload.pin:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid analyst credentials")

    identity = AnalystIdentity(analyst_name=payload.analyst_name, role=user["role"])
    token = _encode_token(identity)
    return AuthSessionResponse(
        analyst_name=identity.analyst_name,
        role=identity.role,
        token=token,
        allowed_actions=identity.allowed_actions,
    )


def _encode_token(identity: AnalystIdentity) -> str:
    raw = f"{identity.analyst_name}:{identity.role.value}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def _decode_token(token: str) -> AnalystIdentity:
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        analyst_name, role_value = raw.split(":", 1)
        role = AnalystRole(role_value)
    except Exception as exc:  # pragma: no cover - defensive token parsing
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid analyst session") from exc

    if analyst_name not in DEMO_USERS or DEMO_USERS[analyst_name]["role"] != role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid analyst session")
    return AnalystIdentity(analyst_name=analyst_name, role=role)


def require_analyst_session(authorization: str | None = Header(default=None)) -> AnalystIdentity:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Analyst session required")
    return _decode_token(authorization.removeprefix("Bearer ").strip())


def enforce_action_permission(identity: AnalystIdentity, action: AnalystAction) -> None:
    if action not in identity.allowed_actions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{identity.role.value} cannot perform action {action.value}",
        )
