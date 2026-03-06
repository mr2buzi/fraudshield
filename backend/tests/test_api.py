from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "ml" / "artifacts" / "model_metadata.json"


class FraudShieldApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(self.temp_dir.name) / 'test.db'}"
        os.environ["SEED_ON_STARTUP"] = "false"
        os.environ["MODEL_ARTIFACT_PATH"] = str(MODEL_PATH)
        os.environ["RATE_LIMIT_PER_MINUTE"] = "2"
        from app.main import create_app

        self.app = create_app()
        await self.app.router.startup()
        transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(transport=transport, base_url="http://testserver")

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        await self.app.router.shutdown()
        self.app.state.engine.dispose()
        self.temp_dir.cleanup()

    async def test_health_endpoint(self) -> None:
        response = await self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("model_version", body)

    async def create_session(self, analyst_name: str = "demo.analyst", pin: str = "1357") -> str:
        response = await self.client.post("/api/v1/auth/session", json={"analyst_name": analyst_name, "pin": pin})
        self.assertEqual(response.status_code, 200)
        return response.json()["token"]

    async def get_auth_headers(self, analyst_name: str = "demo.analyst", pin: str = "1357") -> dict[str, str]:
        token = await self.create_session(analyst_name, pin)
        return {"Authorization": f"Bearer {token}"}

    def high_risk_payload(self, external_id: str = "test-001") -> dict:
        return {
            "external_id": external_id,
            "amount": 999.0,
            "currency": "GBP",
            "merchant_name": "Risky Travel",
            "merchant_category": "travel",
            "entry_mode": "manual",
            "country": "NG",
            "customer_tenure_days": 10,
            "account_age_days": 10,
            "email_age_days": 1,
            "card_present": False,
            "is_international": True,
            "ip_risk_score": 0.91,
            "velocity_1h": 6,
            "velocity_24h": 18,
        }

    async def test_score_creates_alert_for_high_risk_transaction(self) -> None:
        headers = await self.get_auth_headers()
        response = await self.client.post("/api/v1/transactions/score", json=self.high_risk_payload(), headers=headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["risk_band"], "high")
        self.assertIsNotNone(body["alert_id"])
        alerts = (await self.client.get("/api/v1/alerts", headers=headers)).json()["alerts"]
        self.assertEqual(len(alerts), 1)

    async def test_decision_updates_alert(self) -> None:
        await self.test_score_creates_alert_for_high_risk_transaction()
        headers = await self.get_auth_headers()
        alert_id = (await self.client.get("/api/v1/alerts", headers=headers)).json()["alerts"][0]["id"]
        response = await self.client.post(
            f"/api/v1/alerts/{alert_id}/decision",
            json={"decision": "confirm_fraud", "notes": "Velocity burst plus risky IP."},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "resolved")
        self.assertEqual(body["decisions"][0]["decision"], "confirm_fraud")
        self.assertEqual(body["decisions"][0]["analyst_name"], "demo.analyst")

    async def test_metrics_reflect_reviews(self) -> None:
        await self.test_decision_updates_alert()
        response = await self.client.get("/api/v1/metrics/overview", headers=await self.get_auth_headers())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_alerts"], 1)
        self.assertEqual(body["reviewed_alerts"], 1)
        self.assertEqual(body["precision_proxy"], 1.0)

    async def test_protected_endpoints_require_session(self) -> None:
        response = await self.client.get("/api/v1/alerts")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Analyst session required")

    async def test_auth_rejects_invalid_credentials(self) -> None:
        response = await self.client.post("/api/v1/auth/session", json={"analyst_name": "demo.analyst", "pin": "0000"})
        self.assertEqual(response.status_code, 401)

    async def test_duplicate_transaction_returns_existing_result(self) -> None:
        headers = await self.get_auth_headers()
        first = await self.client.post("/api/v1/transactions/score", json=self.high_risk_payload("duplicate-1"), headers=headers)
        second = await self.client.post("/api/v1/transactions/score", json=self.high_risk_payload("duplicate-1"), headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["transaction_id"], second.json()["transaction_id"])
        alerts = (await self.client.get("/api/v1/alerts", headers=headers)).json()["alerts"]
        self.assertEqual(len(alerts), 1)

    async def test_rate_limit_applies_to_scoring(self) -> None:
        headers = await self.get_auth_headers()
        await self.client.post("/api/v1/transactions/score", json=self.high_risk_payload("rate-1"), headers=headers)
        await self.client.post("/api/v1/transactions/score", json=self.high_risk_payload("rate-2"), headers=headers)
        response = await self.client.post("/api/v1/transactions/score", json=self.high_risk_payload("rate-3"), headers=headers)
        self.assertEqual(response.status_code, 429)

    async def test_invalid_payload_returns_422(self) -> None:
        headers = await self.get_auth_headers()
        payload = self.high_risk_payload("invalid-1")
        payload["amount"] = -1
        response = await self.client.post("/api/v1/transactions/score", json=payload, headers=headers)
        self.assertEqual(response.status_code, 422)

    async def test_escalation_requires_privileged_role(self) -> None:
        headers = await self.get_auth_headers()
        await self.client.post("/api/v1/transactions/score", json=self.high_risk_payload("escalate-1"), headers=headers)
        alert_id = (await self.client.get("/api/v1/alerts", headers=headers)).json()["alerts"][0]["id"]
        response = await self.client.post(
            f"/api/v1/alerts/{alert_id}/decision",
            json={"decision": "escalate", "notes": "Needs specialist review."},
            headers=headers,
        )
        self.assertEqual(response.status_code, 403)

    async def test_lead_analyst_can_escalate(self) -> None:
        lead_headers = await self.get_auth_headers("lead.analyst", "2468")
        await self.client.post("/api/v1/transactions/score", json=self.high_risk_payload("lead-escalate-1"), headers=lead_headers)
        alert_id = (await self.client.get("/api/v1/alerts", headers=lead_headers)).json()["alerts"][0]["id"]
        response = await self.client.post(
            f"/api/v1/alerts/{alert_id}/decision",
            json={"decision": "escalate", "notes": "Needs specialist review."},
            headers=lead_headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "escalated")


if __name__ == "__main__":
    unittest.main()
