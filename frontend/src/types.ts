export type AnalystDecision = {
  id: string;
  decision: "confirm_fraud" | "mark_legit" | "escalate";
  analyst_name: string;
  notes: string;
  created_at: string;
};

export type TopFactor = {
  feature: string;
  label: string;
  contribution: number;
  direction: "increase" | "decrease";
};

export type TransactionSummary = {
  id: string;
  external_id: string;
  amount: number;
  currency: string;
  merchant_name: string;
  merchant_category: string;
  country: string;
  created_at: string;
  risk_score: number;
  risk_band: "low" | "medium" | "high";
  flagged: boolean;
  model_version: string;
  latency_ms: number;
  top_factors: TopFactor[];
};

export type AlertRecord = {
  id: string;
  status: "open" | "resolved" | "escalated" | "under_review";
  reason_summary: string;
  created_at: string;
  updated_at: string;
  transaction: TransactionSummary;
  decisions: AnalystDecision[];
};

export type AlertListResponse = {
  alerts: AlertRecord[];
};

export type MetricsOverview = {
  total_transactions: number;
  total_alerts: number;
  open_alerts: number;
  escalated_alerts: number;
  reviewed_alerts: number;
  precision_proxy: number;
  average_risk_score: number;
  p95_latency_ms: number;
  recent_amount_shift_pct: number;
  recent_international_rate: number;
  baseline_international_rate: number;
  model_version: string;
};

export type AnalystRole = "analyst" | "lead_analyst" | "manager";

export type AnalystSession = {
  analyst_name: string;
  role: AnalystRole;
  token: string;
  allowed_actions: Array<"confirm_fraud" | "mark_legit" | "escalate">;
};

export type ScoreRequest = {
  external_id: string;
  amount: number;
  currency: string;
  merchant_name: string;
  merchant_category: string;
  entry_mode: string;
  country: string;
  customer_tenure_days: number;
  account_age_days: number;
  email_age_days: number;
  card_present: boolean;
  is_international: boolean;
  ip_risk_score: number;
  velocity_1h: number;
  velocity_24h: number;
};

export type ScoreResponse = {
  transaction_id: string;
  alert_id: string | null;
  risk_score: number;
  risk_band: "low" | "medium" | "high";
  top_factors: TopFactor[];
  model_version: string;
  latency_ms: number;
};

export type SessionRequest = {
  analyst_name: string;
  pin: string;
};
