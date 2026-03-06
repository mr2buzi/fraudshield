import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const fetchMock = vi.fn();

vi.stubGlobal("fetch", fetchMock);

const sessionResponse = {
  analyst_name: "demo.analyst",
  role: "analyst",
  token: "demo-token",
  allowed_actions: ["confirm_fraud", "mark_legit"],
};

const metricsResponse = {
  total_transactions: 5,
  total_alerts: 2,
  open_alerts: 1,
  escalated_alerts: 0,
  reviewed_alerts: 1,
  precision_proxy: 0.5,
  average_risk_score: 0.73,
  p95_latency_ms: 22,
  recent_amount_shift_pct: 12,
  recent_international_rate: 0.2,
  baseline_international_rate: 0.18,
  model_version: "test-model",
};

const alertsResponse = {
  alerts: [
    {
      id: "alert-1",
      status: "open",
      reason_summary: "Risky IP or device fingerprint, Merchant category risk",
      created_at: "2026-03-06T12:00:00Z",
      updated_at: "2026-03-06T12:00:00Z",
      transaction: {
        id: "txn-1",
        external_id: "demo-1",
        amount: 540,
        currency: "GBP",
        merchant_name: "Velocity Electronics",
        merchant_category: "electronics",
        country: "GB",
        created_at: "2026-03-06T12:00:00Z",
        risk_score: 0.91,
        risk_band: "high",
        flagged: true,
        model_version: "test-model",
        latency_ms: 18,
        top_factors: [
          {
            feature: "ip_risk_score",
            label: "Risky IP or device fingerprint",
            contribution: 1.7,
            direction: "increase",
          },
        ],
      },
      decisions: [],
    },
  ],
};

function jsonResponse(body: unknown, ok = true, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("App", () => {
  beforeEach(() => {
    fetchMock.mockReset();
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the analyst login screen before a session exists", async () => {
    render(<App />);
    expect(await screen.findByText("FraudShield Analyst Access")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Unlock Console" })).toBeInTheDocument();
  });

  it("signs in and loads the dashboard", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/auth/session")) {
        return jsonResponse(sessionResponse);
      }
      if (url.includes("/api/v1/alerts")) {
        return jsonResponse(alertsResponse);
      }
      return jsonResponse(metricsResponse);
    });

    render(<App />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Unlock Console" }))[0]);

    expect(await screen.findByRole("heading", { name: "Analyst Console" })).toBeInTheDocument();
    expect(await screen.findByText("Signed in as demo.analyst")).toBeInTheDocument();
    expect(window.localStorage.getItem("fraudshield.session")).toContain("demo.analyst");
  });

  it("disables escalation for a plain analyst session", async () => {
    window.localStorage.setItem("fraudshield.session", JSON.stringify(sessionResponse));
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/alerts")) {
        return jsonResponse(alertsResponse);
      }
      return jsonResponse(metricsResponse);
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Alert Detail" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Escalate" })).toBeDisabled();
  });

  it("submits a decision and refreshes the workspace", async () => {
    window.localStorage.setItem(
      "fraudshield.session",
      JSON.stringify({ ...sessionResponse, role: "lead_analyst", allowed_actions: ["confirm_fraud", "mark_legit", "escalate"] }),
    );

    let decisionCalled = false;
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/v1/alerts/alert-1/decision")) {
        decisionCalled = true;
        return jsonResponse({
          ...alertsResponse.alerts[0],
          status: "escalated",
          decisions: [
            {
              id: "decision-1",
              decision: "escalate",
              analyst_name: "demo.analyst",
              notes: "Needs specialist review.",
              created_at: "2026-03-06T12:05:00Z",
            },
          ],
        });
      }
      if (url.includes("/api/v1/alerts")) {
        return jsonResponse(
          decisionCalled
            ? {
                alerts: [
                  {
                    ...alertsResponse.alerts[0],
                    status: "escalated",
                    decisions: [
                      {
                        id: "decision-1",
                        decision: "escalate",
                        analyst_name: "demo.analyst",
                        notes: "Needs specialist review.",
                        created_at: "2026-03-06T12:05:00Z",
                      },
                    ],
                  },
                ],
              }
            : alertsResponse,
        );
      }
      if (url.includes("/api/v1/metrics")) {
        return jsonResponse(metricsResponse);
      }

      throw new Error(`Unexpected request: ${url} ${init?.method ?? "GET"}`);
    });

    render(<App />);
    fireEvent.change(await screen.findByLabelText("Notes"), { target: { value: "Needs specialist review." } });
    fireEvent.click((await screen.findAllByRole("button", { name: "Escalate" }))[0]);

    await waitFor(() => expect(decisionCalled).toBe(true));
    await waitFor(() => expect(screen.getAllByText("escalated").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getAllByText("demo.analyst").length).toBeGreaterThan(0));
  });
});
