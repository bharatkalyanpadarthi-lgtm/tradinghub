export type Status = {
  project: string;
  mode: string;
  kill_switch: boolean;
  backend_health: string;
  today_signals: number;
  today_blocked_signals: number;
  open_paper_positions: number;
  today_paper_pnl_eur: number;
  latest_run_status: string;
};

export type RiskStatus = {
  daily_loss_cap_eur: number;
  today_paper_pnl_eur: number;
  remaining_daily_risk_eur: number;
  max_open_positions: number;
  current_open_positions: number;
  allowed_symbols: string[];
  allowed_strategies: string[];
  cooldown_minutes: number;
  kill_switch: boolean;
  mode: string;
};

export type RunListItem = {
  id: number;
  status: string;
  reason: string | null;
  created_at: string;
  source: string | null;
  symbol: string | null;
  side: string | null;
  strategy: string | null;
  risk_decision: string | null;
  signal_grade: string | null;
  reason_codes: string[];
  paper_order_status: string | null;
};

export type RunDetail = {
  run: Record<string, unknown>;
  signal: Record<string, unknown>;
  risk_decision: Record<string, unknown>;
  paper_orders: Array<Record<string, unknown>>;
  stage_events: Array<Record<string, unknown>>;
};

export type JournalEntry = {
  time: string;
  source: string | null;
  symbol: string;
  side: string;
  strategy: string;
  final_decision: string | null;
  reason: string;
  paper_order_status: string;
  exit_reason: string | null;
  pnl_eur: string | null;
  pnl_percent: string | null;
  run_id: number | null;
};

export type Journal = {
  entries: JournalEntry[];
  paper_orders: Array<Record<string, unknown>>;
};

const API_BASE = process.env.NEXT_PUBLIC_TRADENEST_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {})
    },
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export async function getStatus() {
  return request<Status>("/api/status");
}

export async function getRiskStatus() {
  return request<RiskStatus>("/api/risk/status");
}

export async function getRuns() {
  return request<{ runs: RunListItem[] }>("/api/runs");
}

export async function getRun(runId: number) {
  return request<RunDetail>(`/api/runs/${runId}`);
}

export async function getJournal() {
  return request<Journal>("/api/journal");
}

export async function killSystem() {
  return request<{ kill_switch: boolean }>("/api/system/kill", { method: "POST" });
}

export async function unkillSystem() {
  return request<{ kill_switch: boolean }>("/api/system/unkill", { method: "POST" });
}
