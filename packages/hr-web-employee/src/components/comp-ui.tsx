"use client";
/**
 * Compensation UI kit — calm, premium visual primitives for the employee
 * "My Compensation" total-comp surface.
 *
 * No external chart library: clean inline SVG / CSS only, themed via the
 * design-system CSS variables so it inherits light/dark automatically.
 *
 * WHY THIS FILE EXISTS SEPARATELY
 * These formatters and chart primitives used to live in `equity-ui.tsx`
 * alongside the cap-table vesting timeline. Nothing in this file is about
 * equity -- they format money and stack a bar -- but when the equity module
 * was removed from this build they went with it, and the compensation page
 * (their only remaining caller) failed to compile. Generic primitives now sit
 * in a generic module so removing a feature cannot take them along.
 */
import React from "react";
import clsx from "clsx";

// ---------------------------------------------------------------------------
// Formatters — every number on the surface goes through these.
// ---------------------------------------------------------------------------
export function fmtNum(n: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(n);
}
export function fmtMoney(n: number, opts: { cents?: boolean } = {}) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: opts.cents ? 2 : 0,
  }).format(n);
}
export function fmtMoneyCompact(n: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
}
export function fmtPct(n: number, digits = 1) {
  return `${n.toFixed(digits)}%`;
}
export function fmtDate(iso: string | null | undefined) {
  if (!iso) return "—";
  return new Date(iso + (iso.length <= 10 ? "T00:00:00" : "")).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

// A calm palette drawn from the DS accent + neutral tokens. Used for series
// (security classes, cash vs equity). CSS vars keep it theme-aware.
export const SERIES = [
  "#1F1F25",
  "#0ea5e9",
  "#14b8a6",
  "#f59e0b",
  "#8b5cf6",
  "#ec4899",
  "#64748b",
];

// ---------------------------------------------------------------------------
// Skeleton — calm shimmer for loading states.
// ---------------------------------------------------------------------------
export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-md bg-sunken/70", className)} />;
}

// ---------------------------------------------------------------------------
// ProgressRing — circular % (used for per-grant vested %).
// ---------------------------------------------------------------------------
export function ProgressRing({
  pct,
  size = 72,
  stroke = 7,
  label,
}: {
  pct: number;
  size?: number;
  stroke?: number;
  label?: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, pct));
  const dash = (clamped / 100) * c;
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E2E8F0" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#1F1F25"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${c - dash}`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-sm font-semibold tabular-nums text-ink">{Math.round(clamped)}%</span>
        {label && <span className="text-[9px] uppercase tracking-wide text-muted">{label}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StackedBar — horizontal, segmented (cash vs equity, vested vs unvested).
// ---------------------------------------------------------------------------
export type Segment = { label: string; value: number; color: string; sub?: string };

export function StackedBar({ segments, height = 18 }: { segments: Segment[]; height?: number }) {
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0) || 1;
  return (
    <div className="flex w-full overflow-hidden rounded-full" style={{ height }}>
      {segments.map((s, i) => {
        const w = (Math.max(0, s.value) / total) * 100;
        if (w <= 0) return null;
        return (
          <div
            key={i}
            title={`${s.label}: ${fmtMoney(s.value)}`}
            style={{ width: `${w}%`, background: s.color }}
            className="h-full transition-all duration-500 ease-out"
          />
        );
      })}
    </div>
  );
}

export function Legend({ segments }: { segments: Segment[] }) {
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2">
      {segments.map((s, i) => (
        <div key={i} className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ background: s.color }} />
          <span className="text-xs text-muted">{s.label}</span>
          <span className="text-xs font-medium tabular-nums text-ink">{fmtMoney(s.value)}</span>
          {s.sub && <span className="text-[11px] text-muted">{s.sub}</span>}
        </div>
      ))}
    </div>
  );
}
