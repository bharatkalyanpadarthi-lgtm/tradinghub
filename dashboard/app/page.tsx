"use client";

import { useEffect, useMemo, useState } from "react";
import { Power, RefreshCw, ShieldCheck } from "lucide-react";
import {
  getJournal,
  getRiskStatus,
  getRun,
  getRuns,
  getStatus,
  killSystem,
  unkillSystem,
  Journal,
  RiskStatus,
  RunDetail,
  RunListItem,
  Status
} from "@/lib/api";
import { Badge, Card, Field, IconButton, Metric, Shell } from "@/components/ui";

type Screen = "mission" | "signals" | "risk" | "journal";

const screens: Array<{ id: Screen; label: string }> = [
  { id: "mission", label: "Mission Control" },
  { id: "signals", label: "Signal Review" },
  { id: "risk", label: "Risk Control" },
  { id: "journal", label: "Trade Journal" }
];

function toneFor(value?: string | null) {
  if (!value) return "neutral" as const;
  if (["passed", "accepted", "open", "ok"].includes(value)) return "green" as const;
  if (["blocked", "closed", "duplicate"].includes(value)) return "amber" as const;
  if (["rejected", "error", "true"].includes(value)) return "red" as const;
  return "blue" as const;
}

function money(value?: number | string | null) {
  const numberValue = Number(value ?? 0);
  return `EUR ${numberValue.toFixed(2)}`;
}

function display(value: unknown, fallback = "none") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

export default function Dashboard() {
  const [screen, setScreen] = useState<Screen>("mission");
  const [status, setStatus] = useState<Status | null>(null);
  const [risk, setRisk] = useState<RiskStatus | null>(null);
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [journal, setJournal] = useState<Journal | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState({ source: "", symbol: "", status: "", date: "all" });

  async function refresh() {
    setError(null);
    try {
      const [statusData, riskData, runsData, journalData] = await Promise.all([
        getStatus(),
        getRiskStatus(),
        getRuns(),
        getJournal()
      ]);
      setStatus(statusData);
      setRisk(riskData);
      setRuns(runsData.runs);
      setJournal(journalData);
      if (runsData.runs[0]?.id) {
        setRunDetail(await getRun(runsData.runs[0].id));
      } else {
        setRunDetail(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to reach backend");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function setKill(next: boolean) {
    if (next) await killSystem();
    else await unkillSystem();
    await refresh();
  }

  const filteredEntries = useMemo(() => {
    const entries = journal?.entries ?? [];
    const today = new Date().toISOString().slice(0, 10);
    return entries.filter((entry) => {
      if (filters.source && entry.source !== filters.source) return false;
      if (filters.symbol && entry.symbol !== filters.symbol) return false;
      if (filters.status && entry.paper_order_status !== filters.status && entry.final_decision !== filters.status) return false;
      if (filters.date === "today" && !entry.time?.startsWith(today)) return false;
      return true;
    });
  }, [filters, journal]);

  return (
    <Shell>
      <header className="mb-5 flex flex-col gap-4 border-b border-cockpit-line pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-sm font-semibold uppercase tracking-wide text-emerald-300">TradeNest</div>
          <h1 className="mt-1 text-3xl font-bold text-cockpit-text">Paper Signal Cockpit</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <IconButton icon={RefreshCw} label="Refresh" onClick={() => void refresh()} tone="blue" />
          <IconButton icon={Power} label="Kill" onClick={() => void setKill(true)} tone="red" />
          <IconButton icon={ShieldCheck} label="Unkill" onClick={() => void setKill(false)} tone="green" />
        </div>
      </header>

      <nav className="mb-5 grid grid-cols-2 gap-2 lg:grid-cols-4">
        {screens.map((item) => (
          <button
            key={item.id}
            onClick={() => setScreen(item.id)}
            className={`h-11 rounded-md border px-3 text-sm font-semibold transition ${
              screen === item.id
                ? "border-emerald-300 bg-emerald-300/12 text-emerald-100"
                : "border-cockpit-line bg-cockpit-panel text-cockpit-muted hover:text-cockpit-text"
            }`}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {error ? (
        <Card>
          <Badge tone="red">Backend unavailable</Badge>
          <p className="mt-3 text-sm text-cockpit-muted">{error}</p>
        </Card>
      ) : null}

      {screen === "mission" ? <MissionControl status={status} /> : null}
      {screen === "signals" ? <SignalReview runs={runs} detail={runDetail} /> : null}
      {screen === "risk" ? <RiskControl risk={risk} /> : null}
      {screen === "journal" ? (
        <TradeJournal entries={filteredEntries} filters={filters} setFilters={setFilters} />
      ) : null}
    </Shell>
  );
}

function MissionControl({ status }: { status: Status | null }) {
  return (
    <section className="grid gap-4 lg:grid-cols-4">
      <Metric label="Mode" value={status?.mode ?? "unknown"} tone="blue" />
      <Metric label="Kill Switch" value={status?.kill_switch ? "Enabled" : "Clear"} tone={status?.kill_switch ? "red" : "green"} />
      <Metric label="Backend" value={status?.backend_health ?? "unknown"} tone={toneFor(status?.backend_health)} />
      <Metric label="Latest Run" value={status?.latest_run_status ?? "none"} tone={toneFor(status?.latest_run_status)} />
      <Metric label="Today Signals" value={status?.today_signals ?? 0} tone="blue" />
      <Metric label="Today Blocked" value={status?.today_blocked_signals ?? 0} tone={(status?.today_blocked_signals ?? 0) > 0 ? "amber" : "green"} />
      <Metric label="Open Positions" value={status?.open_paper_positions ?? 0} tone={(status?.open_paper_positions ?? 0) > 0 ? "amber" : "green"} />
      <Metric label="Today P&L" value={money(status?.today_paper_pnl_eur)} tone={(status?.today_paper_pnl_eur ?? 0) < 0 ? "red" : "green"} />
    </section>
  );
}

function SignalReview({ runs, detail }: { runs: RunListItem[]; detail: RunDetail | null }) {
  const latest = runs[0];
  const risk = detail?.risk_decision ?? {};
  const signal = detail?.signal ?? {};
  const order = detail?.paper_orders?.[0] ?? {};
  return (
    <section className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
      <Card title="Latest Run">
        <div className="grid gap-2 sm:grid-cols-2">
          <Field label="Run ID" value={latest?.id ?? "none"} />
          <Field label="Source" value={display(latest?.source ?? signal.source)} />
          <Field label="Symbol" value={display(latest?.symbol ?? signal.symbol)} />
          <Field label="Side" value={display(latest?.side ?? signal.side)} />
          <Field label="Signal Type" value={display(signal.timeframe, "signal")} />
          <Field label="Strategy ID" value={display(latest?.strategy ?? signal.strategy)} />
          <Field label="Signal Engine" value={String(risk.signal_grade ?? latest?.signal_grade ?? "none")} />
          <Field label="Market Features" value={stageValue(detail, "MarketFeaturesStage")} />
          <Field label="Risk Decision" value={<Badge tone={toneFor(String(risk.decision ?? latest?.risk_decision))}>{String(risk.decision ?? latest?.risk_decision ?? "none")}</Badge>} />
          <Field label="Paper Order" value={String(order.status ?? latest?.paper_order_status ?? "none")} />
        </div>
      </Card>
      <Card title="Stage Timeline">
        <div className="space-y-2">
          {(detail?.stage_events ?? []).map((event, index) => (
            <div key={index} className="flex items-center justify-between rounded-lg border border-cockpit-line bg-cockpit-panel2 px-3 py-2">
              <span className="text-sm text-cockpit-text">{String(event.stage_name)}</span>
              <Badge tone={toneFor(String(event.status))}>{String(event.status)}</Badge>
            </div>
          ))}
          {!detail?.stage_events?.length ? <p className="text-sm text-cockpit-muted">No stage events yet.</p> : null}
        </div>
      </Card>
    </section>
  );
}

function stageValue(detail: RunDetail | null, stageName: string) {
  const event = detail?.stage_events?.find((item) => item.stage_name === stageName);
  const payload = event?.payload as Record<string, unknown> | undefined;
  return String(payload?.feature_status ?? event?.status ?? "none");
}

function RiskControl({ risk }: { risk: RiskStatus | null }) {
  const pnl = risk?.today_paper_pnl_eur ?? 0;
  return (
    <section className="grid gap-4 lg:grid-cols-3">
      <Metric label="Daily Loss Cap" value={money(risk?.daily_loss_cap_eur)} tone="amber" />
      <Metric label="Today P&L" value={money(pnl)} tone={pnl < 0 ? "red" : "green"} />
      <Metric label="Remaining Risk" value={money(risk?.remaining_daily_risk_eur)} tone={(risk?.remaining_daily_risk_eur ?? 0) <= 0 ? "red" : "green"} />
      <Metric label="Max Open" value={risk?.max_open_positions ?? 0} tone="blue" />
      <Metric label="Current Open" value={risk?.current_open_positions ?? 0} tone={(risk?.current_open_positions ?? 0) > 0 ? "amber" : "green"} />
      <Metric label="Kill Switch" value={risk?.kill_switch ? "Enabled" : "Clear"} tone={risk?.kill_switch ? "red" : "green"} />
      <Card title="Allowed Symbols" className="lg:col-span-1">
        <div className="flex flex-wrap gap-2">{(risk?.allowed_symbols ?? []).map((symbol) => <Badge key={symbol} tone="blue">{symbol}</Badge>)}</div>
      </Card>
      <Card title="Allowed Strategies" className="lg:col-span-1">
        <div className="flex flex-wrap gap-2">{(risk?.allowed_strategies ?? []).map((strategy) => <Badge key={strategy} tone="green">{strategy}</Badge>)}</div>
      </Card>
      <Card title="Configuration" className="lg:col-span-1">
        <div className="grid gap-2">
          <Field label="Cooldown" value={`${risk?.cooldown_minutes ?? 0} min`} />
          <Field label="Mode" value={risk?.mode ?? "unknown"} />
        </div>
      </Card>
    </section>
  );
}

function TradeJournal({
  entries,
  filters,
  setFilters
}: {
  entries: Journal["entries"];
  filters: { source: string; symbol: string; status: string; date: string };
  setFilters: (next: { source: string; symbol: string; status: string; date: string }) => void;
}) {
  return (
    <Card title="Trade Journal">
      <div className="mb-4 grid gap-2 md:grid-cols-4">
        <Filter label="Source" value={filters.source} options={["", "TradingView", "Replay", "Manual"]} onChange={(source) => setFilters({ ...filters, source })} />
        <Filter label="Symbol" value={filters.symbol} options={["", ...Array.from(new Set(entries.map((entry) => entry.symbol)))]} onChange={(symbol) => setFilters({ ...filters, symbol })} />
        <Filter label="Decision" value={filters.status} options={["", "accepted", "blocked", "open", "closed"]} onChange={(status) => setFilters({ ...filters, status })} />
        <Filter label="Date" value={filters.date} options={["all", "today"]} onChange={(date) => setFilters({ ...filters, date })} />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] border-collapse text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-cockpit-muted">
            <tr className="border-b border-cockpit-line">
              {["Time", "Source", "Symbol", "Side", "Strategy", "Final", "Reason", "Order", "Exit", "P&L EUR", "P&L %", "Run"].map((heading) => (
                <th key={heading} className="px-3 py-2">{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              <tr key={`${entry.run_id}-${index}`} className="border-b border-cockpit-line/70">
                <td className="px-3 py-3 text-cockpit-muted">{entry.time}</td>
                <td className="px-3 py-3">{entry.source}</td>
                <td className="px-3 py-3 font-semibold">{entry.symbol}</td>
                <td className="px-3 py-3">{entry.side}</td>
                <td className="px-3 py-3">{entry.strategy}</td>
                <td className="px-3 py-3"><Badge tone={toneFor(entry.final_decision)}>{entry.final_decision ?? "none"}</Badge></td>
                <td className="px-3 py-3 text-cockpit-muted">{entry.reason || "none"}</td>
                <td className="px-3 py-3"><Badge tone={toneFor(entry.paper_order_status)}>{entry.paper_order_status}</Badge></td>
                <td className="px-3 py-3">{entry.exit_reason ?? "none"}</td>
                <td className="px-3 py-3">{entry.pnl_eur ?? "0"}</td>
                <td className="px-3 py-3">{entry.pnl_percent ?? "0"}</td>
                <td className="px-3 py-3">{entry.run_id ?? "none"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!entries.length ? <p className="py-6 text-sm text-cockpit-muted">No journal entries match the filters.</p> : null}
      </div>
    </Card>
  );
}

function Filter({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs uppercase tracking-wide text-cockpit-muted">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-10 w-full rounded-md border border-cockpit-line bg-cockpit-panel2 px-3 text-sm text-cockpit-text outline-none"
      >
        {options.map((option) => (
          <option key={option || "all"} value={option}>
            {option || "all"}
          </option>
        ))}
      </select>
    </label>
  );
}
