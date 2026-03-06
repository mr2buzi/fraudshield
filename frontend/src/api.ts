import type {
  AlertListResponse,
  AlertRecord,
  AnalystSession,
  MetricsOverview,
  ScoreRequest,
  ScoreResponse,
  SessionRequest,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";

async function request<T>(path: string, init?: RequestInit, token?: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(body.detail ?? "Request failed");
  }

  return response.json() as Promise<T>;
}

export function createSession(payload: SessionRequest): Promise<AnalystSession> {
  return request<AnalystSession>("/api/v1/auth/session", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAlerts(token: string): Promise<AlertListResponse> {
  return request<AlertListResponse>("/api/v1/alerts", undefined, token);
}

export function getAlert(alertId: string, token: string): Promise<AlertRecord> {
  return request<AlertRecord>(`/api/v1/alerts/${alertId}`, undefined, token);
}

export function getMetrics(token: string): Promise<MetricsOverview> {
  return request<MetricsOverview>("/api/v1/metrics/overview", undefined, token);
}

export function scoreTransaction(payload: ScoreRequest, token: string): Promise<ScoreResponse> {
  return request<ScoreResponse>("/api/v1/transactions/score", {
    method: "POST",
    body: JSON.stringify(payload),
  }, token);
}

export function submitDecision(
  alertId: string,
  decision: "confirm_fraud" | "mark_legit" | "escalate",
  notes: string,
  token: string,
): Promise<AlertRecord> {
  return request<AlertRecord>(`/api/v1/alerts/${alertId}/decision`, {
    method: "POST",
    body: JSON.stringify({
      decision,
      notes,
    }),
  }, token);
}
