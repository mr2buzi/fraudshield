import { FormEvent, useEffect, useState } from "react";
import { createSession, getAlerts, getMetrics, scoreTransaction, submitDecision } from "./api";
import type { AlertRecord, AnalystSession, MetricsOverview, ScoreRequest, SessionRequest } from "./types";

const SESSION_STORAGE_KEY = "fraudshield.session";
type AppView = "overview" | "alerts" | "scoring" | "ops";

const defaultTransaction = (): ScoreRequest => ({
  external_id: `manual-${Date.now()}`,
  amount: 540,
  currency: "GBP",
  merchant_name: "Velocity Electronics",
  merchant_category: "electronics",
  entry_mode: "online",
  country: "GB",
  customer_tenure_days: 24,
  account_age_days: 24,
  email_age_days: 2,
  card_present: false,
  is_international: false,
  ip_risk_score: 0.82,
  velocity_1h: 4,
  velocity_24h: 9,
});

const demoCredentials: Array<SessionRequest & { roleLabel: string; accessSummary: string }> = [
  { analyst_name: "demo.analyst", pin: "1357", roleLabel: "Analyst", accessSummary: "Fraud confirm and legit decisions" },
  { analyst_name: "lead.analyst", pin: "2468", roleLabel: "Lead Analyst", accessSummary: "Escalation and queue ownership" },
  { analyst_name: "fraud.manager", pin: "9999", roleLabel: "Manager", accessSummary: "Full review and escalation access" },
];

const scenarioPresets: Array<{ label: string; caption: string; payload: Partial<ScoreRequest> }> = [
  {
    label: "Card Not Present Burst",
    caption: "High IP risk, new email, strong short-term velocity",
    payload: {
      amount: 540,
      merchant_name: "Velocity Electronics",
      merchant_category: "electronics",
      entry_mode: "online",
      ip_risk_score: 0.82,
      velocity_1h: 4,
      velocity_24h: 9,
      is_international: false,
      card_present: false,
      email_age_days: 2,
      account_age_days: 24,
      customer_tenure_days: 24,
      country: "GB",
    },
  },
  {
    label: "Cross-Border Gaming",
    caption: "International spend with manual entry and sharp amount shift",
    payload: {
      amount: 1180,
      merchant_name: "Nightline Gaming",
      merchant_category: "gaming",
      entry_mode: "manual",
      ip_risk_score: 0.94,
      velocity_1h: 7,
      velocity_24h: 13,
      is_international: true,
      card_present: false,
      email_age_days: 1,
      account_age_days: 10,
      customer_tenure_days: 11,
      country: "NL",
    },
  },
  {
    label: "Low-Risk Grocery",
    caption: "Established customer profile with low device and velocity risk",
    payload: {
      amount: 42,
      merchant_name: "Market Square",
      merchant_category: "groceries",
      entry_mode: "chip",
      ip_risk_score: 0.08,
      velocity_1h: 1,
      velocity_24h: 2,
      is_international: false,
      card_present: true,
      email_age_days: 620,
      account_age_days: 1820,
      customer_tenure_days: 1820,
      country: "GB",
    },
  },
];

const viewMeta: Record<AppView, { label: string; eyebrow: string; description: string }> = {
  overview: { label: "Overview", eyebrow: "Operations Snapshot", description: "Risk posture, queue pressure, and current spotlight." },
  alerts: { label: "Alerts", eyebrow: "Case Review", description: "Focused triage with queue, decisions, and audit trail." },
  scoring: { label: "Scoring", eyebrow: "Decisioning Lab", description: "Simulate transactions and push suspicious cases into the queue." },
  ops: { label: "Ops", eyebrow: "Model Signals", description: "Metrics and review throughput without the rest of the clutter." },
};

function riskTone(riskBand: string): string {
  if (riskBand === "high") return "risk-high";
  if (riskBand === "medium") return "risk-medium";
  return "risk-low";
}

function statusTone(status: AlertRecord["status"] | "escalate" | "confirm_fraud" | "mark_legit"): string {
  if (status === "escalated" || status === "escalate") return "status-escalated";
  if (status === "resolved" || status === "confirm_fraud" || status === "mark_legit") return "status-resolved";
  if (status === "under_review") return "status-review";
  return "status-open";
}

function isUnauthorized(message: string): boolean {
  return message.toLowerCase().includes("session") || message.toLowerCase().includes("credential");
}

function formatCurrency(currency: string, amount: number): string {
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency, maximumFractionDigits: 2 }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

function formatRole(role: AnalystSession["role"]): string {
  return role.replace("_", " ");
}

function formatTimestamp(timestamp: string): string {
  return new Date(timestamp).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function minutesSince(timestamp: string): number {
  return Math.max(1, Math.round((Date.now() - new Date(timestamp).getTime()) / 60000));
}

export default function App() {
  const [session, setSession] = useState<AnalystSession | null>(() => {
    const saved = window.localStorage.getItem(SESSION_STORAGE_KEY);
    return saved ? (JSON.parse(saved) as AnalystSession) : null;
  });
  const [activeView, setActiveView] = useState<AppView>("alerts");
  const [alerts, setAlerts] = useState<AlertRecord[]>([]);
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<MetricsOverview | null>(null);
  const [transaction, setTransaction] = useState<ScoreRequest>(defaultTransaction);
  const [decisionNotes, setDecisionNotes] = useState("");
  const [statusMessage, setStatusMessage] = useState("Authenticate a demo analyst session to unlock the console.");
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [loginForm, setLoginForm] = useState<SessionRequest>({ analyst_name: "demo.analyst", pin: "1357" });

  function persistSession(nextSession: AnalystSession | null) {
    setSession(nextSession);
    if (nextSession) window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(nextSession));
    else window.localStorage.removeItem(SESSION_STORAGE_KEY);
  }

  function logout(message = "Analyst session cleared.") {
    persistSession(null);
    setAlerts([]);
    setMetrics(null);
    setSelectedAlertId(null);
    setDecisionNotes("");
    setStatusMessage(message);
    setActiveView("alerts");
  }

  async function refreshData(activeSession: AnalystSession = session as AnalystSession) {
    if (!activeSession) return;
    try {
      setError(null);
      const [alertsResponse, metricsResponse] = await Promise.all([getAlerts(activeSession.token), getMetrics(activeSession.token)]);
      setAlerts(alertsResponse.alerts);
      setMetrics(metricsResponse);
      setSelectedAlertId((current) => {
        if (current && alertsResponse.alerts.some((alert) => alert.id === current)) return current;
        return alertsResponse.alerts[0]?.id ?? null;
      });
      setStatusMessage(`Live workspace synced for ${activeSession.analyst_name}.`);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Unable to load FraudShield.";
      setError(message);
      if (isUnauthorized(message)) logout("Session expired. Sign back in to continue.");
    }
  }

  useEffect(() => {
    if (session) void refreshData(session);
  }, [session]);

  const selectedAlert = alerts.find((alert) => alert.id === selectedAlertId) ?? alerts[0] ?? null;
  const canEscalate = session?.allowed_actions.includes("escalate") ?? false;
  const openAlerts = alerts.filter((alert) => alert.status === "open").length;
  const escalatedAlerts = alerts.filter((alert) => alert.status === "escalated").length;
  const reviewedAlerts = alerts.filter((alert) => alert.decisions.length > 0).length;
  const recentDecisions = alerts
    .flatMap((alert) => alert.decisions.map((decision) => ({ ...decision, merchant_name: alert.transaction.merchant_name })))
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
    .slice(0, 6);

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setIsBusy(true);
      setError(null);
      const nextSession = await createSession(loginForm);
      persistSession(nextSession);
      setActiveView("alerts");
      setStatusMessage(`Signed in as ${nextSession.analyst_name}.`);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to authenticate analyst session.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleScore(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session) return;
    try {
      setIsBusy(true);
      setError(null);
      const response = await scoreTransaction(transaction, session.token);
      setStatusMessage(`Scored ${transaction.external_id}: ${response.risk_band.toUpperCase()} risk at ${Math.round(response.risk_score * 100)}%.`);
      setTransaction(defaultTransaction());
      await refreshData(session);
      setActiveView("alerts");
      if (response.alert_id) setSelectedAlertId(response.alert_id);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Unable to score transaction.";
      setError(message);
      if (isUnauthorized(message)) logout("Session expired. Sign back in to continue.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleDecision(decision: "confirm_fraud" | "mark_legit" | "escalate") {
    if (!selectedAlert || !session) return;
    try {
      setIsBusy(true);
      setError(null);
      const updated = await submitDecision(selectedAlert.id, decision, decisionNotes, session.token);
      setStatusMessage(`Alert ${updated.id.slice(0, 8)} updated with decision ${decision}.`);
      setDecisionNotes("");
      await refreshData(session);
      setActiveView("alerts");
      setSelectedAlertId(updated.id);
    } catch (requestError) {
      const message = requestError instanceof Error ? requestError.message : "Unable to submit decision.";
      setError(message);
      if (isUnauthorized(message)) logout("Session expired. Sign back in to continue.");
    } finally {
      setIsBusy(false);
    }
  }

  function loadPreset(preset: Partial<ScoreRequest>) {
    setTransaction({ ...defaultTransaction(), ...preset, external_id: `manual-${Date.now()}` });
    setStatusMessage("Scenario preset loaded into the scoring form.");
    setActiveView("scoring");
  }

  if (!session) {
    return (
      <div className="app-shell login-shell">
        <section className="login-hero">
          <div className="hero-copy-block">
            <p className="eyebrow">Internal Fraud Operations Demo</p>
            <h1>FraudShield Analyst Access</h1>
            <p className="hero-copy">I rebuilt the entry flow so it feels closer to a guarded internal console than a plain demo page.</p>
          </div>
          <div className="signal-board">
            <article className="signal-card signal-card-accent"><span>Live Signal</span><strong>Real-time scoring, alert creation, and audit updates</strong></article>
            <article className="signal-card"><span>Role Split</span><strong>Analyst, lead analyst, and manager sessions with different actions</strong></article>
            <article className="signal-card"><span>Ops Focus</span><strong>Latency, review precision, amount shift, and international rate tracking</strong></article>
          </div>
          <div className="credential-rack">
            {demoCredentials.map((credential) => (
              <button key={credential.analyst_name} type="button" className="credential-card" onClick={() => setLoginForm({ analyst_name: credential.analyst_name, pin: credential.pin })}>
                <span>{credential.roleLabel}</span>
                <strong>{credential.analyst_name}</strong>
                <small>{credential.accessSummary}</small>
                <em>PIN {credential.pin}</em>
              </button>
            ))}
          </div>
        </section>
        <section className="login-panel panel">
          <div className="panel-header"><h2>Sign In</h2><span>Seeded demo analysts</span></div>
          <form className="login-form" onSubmit={handleLogin}>
            <label>Analyst Name<input value={loginForm.analyst_name} onChange={(event) => setLoginForm({ ...loginForm, analyst_name: event.target.value })} /></label>
            <label>PIN<input type="password" value={loginForm.pin} onChange={(event) => setLoginForm({ ...loginForm, pin: event.target.value })} /></label>
            <button type="submit" disabled={isBusy}>{isBusy ? "Signing In..." : "Unlock Console"}</button>
          </form>
          {error ? <p className="error-text">{error}</p> : null}
        </section>
      </div>
    );
  }

  const page = viewMeta[activeView];

  return (
    <div className="app-shell dashboard-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <p className="eyebrow">FraudShield</p>
          <h1>Analyst Console</h1>
          <p>Split into focused workspaces so scoring, triage, and ops signals stop colliding.</p>
        </div>
        <nav className="sidebar-nav" aria-label="Workspace Views">
          {(Object.keys(viewMeta) as AppView[]).map((view) => (
            <button key={view} type="button" className={`nav-button ${activeView === view ? "active" : ""}`} onClick={() => setActiveView(view)}>
              <span>{viewMeta[view].eyebrow}</span>
              <strong>{viewMeta[view].label}</strong>
            </button>
          ))}
        </nav>
        <section className="sidebar-session">
          <span className="status-pill dark">Model {metrics?.model_version ?? "loading"}</span>
          <span className="status-pill dark">{formatRole(session.role)}</span>
          <p>Signed in as {session.analyst_name}</p>
          <button type="button" className="ghost-button dark" onClick={() => logout()}>Sign out</button>
        </section>
      </aside>

      <div className="content-shell">
        <header className="page-header">
          <div>
            <p className="eyebrow">{page.eyebrow}</p>
            <h2>{page.label}</h2>
            <p>{page.description}</p>
          </div>
          <div className="page-status">
            <div className="status-banner">
              <span className="status-pill">{canEscalate ? "Lead rights" : "Standard rights"}</span>
              <strong>{statusMessage}</strong>
            </div>
            {error ? <p className="error-text">{error}</p> : null}
          </div>
        </header>

        {activeView === "overview" ? (
          <section className="page-grid overview-grid">
            <div className="stack">
              <section className="panel hero-panel">
                <div className="hero-band hero-band-compact">
                  <div><span>Queue Load</span><strong>{alerts.length}</strong></div>
                  <div><span>Open Cases</span><strong>{openAlerts}</strong></div>
                  <div><span>Reviewed</span><strong>{reviewedAlerts}</strong></div>
                  <div><span>Escalated</span><strong>{escalatedAlerts}</strong></div>
                </div>
              </section>
              <section className="metrics-grid compact">
                <MetricCard label="Transactions" value={metrics?.total_transactions ?? 0} tone="teal" />
                <MetricCard label="Alerts" value={metrics?.total_alerts ?? 0} tone="amber" />
                <MetricCard label="Precision Proxy" value={`${Math.round((metrics?.precision_proxy ?? 0) * 100)}%`} tone="slate" />
                <MetricCard label="P95 Latency" value={`${metrics?.p95_latency_ms ?? 0} ms`} tone="blue" />
              </section>
            </div>
            <section className="panel spotlight-panel">
              <div className="panel-header"><h2>Current Spotlight</h2><span>{selectedAlert ? `${minutesSince(selectedAlert.created_at)} min old` : "No live case"}</span></div>
              {selectedAlert ? (
                <div className="detail-stack">
                  {renderAlertHero(selectedAlert)}
                  <button type="button" className="link-button" onClick={() => setActiveView("alerts")}>Open full alert review</button>
                </div>
              ) : <p className="empty-state">No alert selected yet.</p>}
            </section>
          </section>
        ) : null}

        {activeView === "alerts" ? (
          <main className="page-grid alerts-grid">
            <section className="panel panel-alerts">
              <div className="panel-header"><h2>Alert Queue</h2><span>Analyst triage workflow</span></div>
              <div className="queue-summary">
                <div><span>Open</span><strong>{openAlerts}</strong></div>
                <div><span>Escalated</span><strong>{escalatedAlerts}</strong></div>
                <div><span>Reviewed</span><strong>{reviewedAlerts}</strong></div>
              </div>
              <div className="alert-list">
                {alerts.map((alert) => (
                  <button key={alert.id} type="button" className={`alert-card ${selectedAlert?.id === alert.id ? "selected" : ""}`} onClick={() => setSelectedAlertId(alert.id)}>
                    <div className="alert-card-header">
                      <div><span className="alert-merchant">{alert.transaction.merchant_name}</span><small>{formatCurrency(alert.transaction.currency, alert.transaction.amount)}</small></div>
                      <span className={`risk-pill ${riskTone(alert.transaction.risk_band)}`}>{alert.transaction.risk_band}</span>
                    </div>
                    <p>{alert.reason_summary}</p>
                    <div className="alert-card-meta">
                      <span className={`status-tag ${statusTone(alert.status)}`}>{alert.status}</span>
                      <span>{minutesSince(alert.created_at)} min ago</span>
                    </div>
                  </button>
                ))}
                {alerts.length === 0 ? <p className="empty-state">No alerts yet. Score a risky transaction to create one.</p> : null}
              </div>
            </section>

            <section className="panel panel-detail">
              <div className="panel-header"><h2>Alert Detail</h2><span>Explanation and audit trail</span></div>
              {selectedAlert ? (
                <div className="detail-stack">
                  {renderAlertHero(selectedAlert)}
                  <div className="detail-grid">
                    <div className="detail-card">
                      <div className="detail-topline"><h3>Analyst Actions</h3><span className="analyst-chip">{session.analyst_name}</span></div>
                      <label>Notes<textarea value={decisionNotes} onChange={(event) => setDecisionNotes(event.target.value)} rows={4} /></label>
                      <div className="action-row">
                        <button type="button" className="confirm" disabled={isBusy} onClick={() => void handleDecision("confirm_fraud")}>Confirm Fraud</button>
                        <button type="button" className="legit" disabled={isBusy} onClick={() => void handleDecision("mark_legit")}>Mark Legit</button>
                        <button type="button" className="escalate" disabled={!canEscalate || isBusy} onClick={() => void handleDecision("escalate")} title={canEscalate ? "Escalate alert" : "Escalation requires a lead analyst or manager session"}>Escalate</button>
                      </div>
                    </div>
                    <div className="detail-card">
                      <h3>Case Snapshot</h3>
                      <div className="snapshot-grid">
                        <div><span>External ID</span><strong>{selectedAlert.transaction.external_id}</strong></div>
                        <div><span>Category</span><strong>{selectedAlert.transaction.merchant_category}</strong></div>
                        <div><span>Model</span><strong>{selectedAlert.transaction.model_version}</strong></div>
                        <div><span>Status</span><strong>{selectedAlert.status}</strong></div>
                      </div>
                    </div>
                  </div>
                  <div className="detail-card">
                    <h3>Audit Trail</h3>
                    {selectedAlert.decisions.length > 0 ? (
                      <div className="timeline">
                        {selectedAlert.decisions.map((decision) => (
                          <div key={decision.id} className="decision-row">
                            <div className="decision-line" />
                            <div className="decision-body">
                              <div className="decision-heading">
                                <span className={`status-tag ${statusTone(decision.decision)}`}>{decision.decision}</span>
                                <span>{decision.analyst_name}</span>
                                <span>{formatTimestamp(decision.created_at)}</span>
                              </div>
                              <p>{decision.notes || "No notes added."}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : <p className="empty-state">No analyst decisions recorded yet.</p>}
                  </div>
                </div>
              ) : <p className="empty-state">Select an alert to inspect model explanations and decisions.</p>}
            </section>
          </main>
        ) : null}

        {activeView === "scoring" ? (
          <main className="page-grid scoring-grid">
            <section className="panel">
              <div className="panel-header"><h2>Scenario Presets</h2><span>Fast ways to simulate behavior</span></div>
              <div className="preset-rack stacked">
                {scenarioPresets.map((preset) => (
                  <button key={preset.label} type="button" className="preset-card" onClick={() => loadPreset(preset.payload)}>
                    <strong>{preset.label}</strong>
                    <span>{preset.caption}</span>
                  </button>
                ))}
              </div>
            </section>
            <section className="panel panel-form">
              <div className="panel-header"><h2>Score a Transaction</h2><span>Authenticated real-time decisioning</span></div>
              <form className="score-form" onSubmit={handleScore}>
                <label>External ID<input value={transaction.external_id} onChange={(event) => setTransaction({ ...transaction, external_id: event.target.value })} /></label>
                <label>Amount<input type="number" step="0.01" value={transaction.amount} onChange={(event) => setTransaction({ ...transaction, amount: Number(event.target.value) })} /></label>
                <label>Merchant<input value={transaction.merchant_name} onChange={(event) => setTransaction({ ...transaction, merchant_name: event.target.value })} /></label>
                <label>Category<select value={transaction.merchant_category} onChange={(event) => setTransaction({ ...transaction, merchant_category: event.target.value })}><option value="electronics">electronics</option><option value="travel">travel</option><option value="gaming">gaming</option><option value="digital_goods">digital_goods</option><option value="groceries">groceries</option><option value="fuel">fuel</option></select></label>
                <label>Entry Mode<select value={transaction.entry_mode} onChange={(event) => setTransaction({ ...transaction, entry_mode: event.target.value })}><option value="chip">chip</option><option value="tap">tap</option><option value="online">online</option><option value="manual">manual</option><option value="keyed">keyed</option></select></label>
                <label>Country<input value={transaction.country} onChange={(event) => setTransaction({ ...transaction, country: event.target.value.toUpperCase() })} /></label>
                <label>IP Risk Score<input type="number" min="0" max="1" step="0.01" value={transaction.ip_risk_score} onChange={(event) => setTransaction({ ...transaction, ip_risk_score: Number(event.target.value) })} /></label>
                <label>Velocity 1h<input type="number" value={transaction.velocity_1h} onChange={(event) => setTransaction({ ...transaction, velocity_1h: Number(event.target.value) })} /></label>
                <label>Velocity 24h<input type="number" value={transaction.velocity_24h} onChange={(event) => setTransaction({ ...transaction, velocity_24h: Number(event.target.value) })} /></label>
                <label>Account Age<input type="number" value={transaction.account_age_days} onChange={(event) => setTransaction({ ...transaction, account_age_days: Number(event.target.value) })} /></label>
                <label>Email Age<input type="number" value={transaction.email_age_days} onChange={(event) => setTransaction({ ...transaction, email_age_days: Number(event.target.value) })} /></label>
                <label>Customer Tenure<input type="number" value={transaction.customer_tenure_days} onChange={(event) => setTransaction({ ...transaction, customer_tenure_days: Number(event.target.value) })} /></label>
                <label className="checkbox-row"><input type="checkbox" checked={transaction.card_present} onChange={(event) => setTransaction({ ...transaction, card_present: event.target.checked })} />Card present</label>
                <label className="checkbox-row"><input type="checkbox" checked={transaction.is_international} onChange={(event) => setTransaction({ ...transaction, is_international: event.target.checked })} />International</label>
                <button type="submit" disabled={isBusy}>{isBusy ? "Scoring..." : "Score Transaction"}</button>
              </form>
            </section>
          </main>
        ) : null}

        {activeView === "ops" ? (
          <section className="page-grid ops-grid">
            <section className="metrics-grid ops-metrics">
              <MetricCard label="Transactions" value={metrics?.total_transactions ?? 0} tone="teal" />
              <MetricCard label="Alerts" value={metrics?.total_alerts ?? 0} tone="amber" />
              <MetricCard label="Precision Proxy" value={`${Math.round((metrics?.precision_proxy ?? 0) * 100)}%`} tone="slate" />
              <MetricCard label="P95 Latency" value={`${metrics?.p95_latency_ms ?? 0} ms`} tone="blue" />
              <MetricCard label="Amount Shift" value={`${metrics?.recent_amount_shift_pct ?? 0}%`} tone="rose" />
              <MetricCard label="Intl. Rate" value={`${Math.round((metrics?.recent_international_rate ?? 0) * 100)}% / ${Math.round((metrics?.baseline_international_rate ?? 0) * 100)}% base`} tone="emerald" />
            </section>
            <section className="ops-layout">
              <section className="panel">
                <div className="panel-header"><h2>System Signals</h2><span>Current operating posture</span></div>
                <div className="ops-strip stacked">
                  <article className="ops-card ops-card-strong"><span>Decision Rights</span><strong>{canEscalate ? "Escalation enabled for this session." : "Escalation restricted to lead roles."}</strong></article>
                  <article className="ops-card"><span>Review Velocity</span><strong>{metrics?.reviewed_alerts ?? reviewedAlerts} cases reviewed in this run state</strong></article>
                  <article className="ops-card"><span>Risk Posture</span><strong>{Math.round((metrics?.average_risk_score ?? 0) * 100)}% average risk score across stored transactions</strong></article>
                </div>
              </section>
              <section className="panel">
                <div className="panel-header"><h2>Recent Decisions</h2><span>Latest analyst actions</span></div>
                {recentDecisions.length > 0 ? (
                  <div className="timeline">
                    {recentDecisions.map((decision) => (
                      <div key={decision.id} className="decision-row">
                        <div className="decision-line" />
                        <div className="decision-body">
                          <div className="decision-heading">
                            <span className={`status-tag ${statusTone(decision.decision)}`}>{decision.decision}</span>
                            <span>{decision.analyst_name}</span>
                            <span>{formatTimestamp(decision.created_at)}</span>
                          </div>
                          <p>{decision.merchant_name}{decision.notes ? `: ${decision.notes}` : "."}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <p className="empty-state">No analyst decisions recorded yet.</p>}
              </section>
            </section>
          </section>
        ) : null}
      </div>
    </div>
  );
}

function renderAlertHero(alert: AlertRecord) {
  return (
    <div className="detail-card hero-detail">
      <div className="detail-topline">
        <div>
          <h3>{alert.transaction.merchant_name}</h3>
          <small>{alert.reason_summary}</small>
        </div>
        <span className={`risk-pill ${riskTone(alert.transaction.risk_band)}`}>{Math.round(alert.transaction.risk_score * 100)}% {alert.transaction.risk_band}</span>
      </div>
      <div className="detail-snapshot detail-snapshot-compact">
        <div><span>Amount</span><strong>{formatCurrency(alert.transaction.currency, alert.transaction.amount)}</strong></div>
        <div><span>Country</span><strong>{alert.transaction.country}</strong></div>
        <div><span>Latency</span><strong>{alert.transaction.latency_ms} ms</strong></div>
        <div><span>Created</span><strong>{formatTimestamp(alert.created_at)}</strong></div>
      </div>
      <div className="factor-list factor-list-bars">
        {alert.transaction.top_factors.map((factor) => {
          const width = Math.max(24, Math.min(100, Math.round(Math.abs(factor.contribution) * 32)));
          return (
            <div key={factor.feature} className="factor-chip factor-bar">
              <div className="factor-copy">
                <strong>{factor.label}</strong>
                <span>{factor.contribution.toFixed(2)} contribution</span>
              </div>
              <div className="factor-meter"><span style={{ width: `${width}%` }} /></div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MetricCard({ label, value, tone }: { label: string; value: string | number; tone: string }) {
  return <article className={`metric-card metric-${tone}`}><span>{label}</span><strong>{value}</strong></article>;
}
