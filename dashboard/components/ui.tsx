import { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type Tone = "green" | "amber" | "red" | "blue" | "neutral";

const toneClass: Record<Tone, string> = {
  green: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  amber: "border-amber-300/40 bg-amber-300/10 text-amber-100",
  red: "border-red-400/40 bg-red-400/10 text-red-100",
  blue: "border-sky-400/40 bg-sky-400/10 text-sky-100",
  neutral: "border-slate-500/40 bg-slate-500/10 text-slate-200"
};

export function Shell({ children }: { children: ReactNode }) {
  return <main className="mx-auto min-h-screen w-full max-w-7xl px-4 py-5 sm:px-6 lg:px-8">{children}</main>;
}

export function Card({
  title,
  children,
  className = ""
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-cockpit-line bg-cockpit-panel/92 p-4 shadow-panel ${className}`}>
      {title ? <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-cockpit-muted">{title}</h2> : null}
      {children}
    </section>
  );
}

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={`inline-flex items-center rounded-md border px-2 py-1 text-xs font-semibold ${toneClass[tone]}`}>
      {children}
    </span>
  );
}

export function Metric({
  label,
  value,
  tone = "neutral"
}: {
  label: string;
  value: ReactNode;
  tone?: Tone;
}) {
  return (
    <div className="min-h-24 rounded-lg border border-cockpit-line bg-cockpit-panel2 p-3">
      <div className="text-xs uppercase tracking-wide text-cockpit-muted">{label}</div>
      <div className="mt-3 break-words text-2xl font-semibold text-cockpit-text">{value}</div>
      <div className={`mt-3 h-1 rounded-full ${tone === "green" ? "bg-emerald-400" : tone === "red" ? "bg-red-400" : tone === "amber" ? "bg-amber-300" : "bg-sky-400"}`} />
    </div>
  );
}

export function IconButton({
  icon: Icon,
  label,
  onClick,
  tone = "neutral"
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
  tone?: Tone;
}) {
  return (
    <button
      aria-label={label}
      title={label}
      onClick={onClick}
      className={`inline-flex h-10 items-center gap-2 rounded-md border px-3 text-sm font-semibold transition hover:brightness-125 ${toneClass[tone]}`}
    >
      <Icon size={17} />
      <span>{label}</span>
    </button>
  );
}

export function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-cockpit-line bg-cockpit-panel2 px-3 py-2">
      <div className="text-xs uppercase tracking-wide text-cockpit-muted">{label}</div>
      <div className="mt-1 break-words text-sm font-medium text-cockpit-text">{value ?? "none"}</div>
    </div>
  );
}
