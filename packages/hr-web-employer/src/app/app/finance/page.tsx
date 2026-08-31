"use client";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Divider, LinkAction } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Overview = {
  as_of: string;
  headcount: number;
  annual_payroll_base: number;
  annual_payroll_loaded: number;
  benefits_loading_rate: number;
  comp_budget_annual: number;
  comp_budget_consumed: number;
  comp_budget_variance_pct: number;
  open_reqs: number;
  hiring_delta_base: number;
  hiring_delta_loaded: number;
  by_department: { department: string; headcount: number; annual_base: number; annual_loaded: number }[];
  cohort?: {
    is_sample: boolean;
    sample_headcount: number;
    your_active_employees: number;
    real_inputs: string[];
    sample_inputs: string[];
    note: string;
  };
};

type ForecastMonth = { month_index: number; label: string; annual_base: number; annual_loaded: number; monthly_loaded: number };
type Forecast = { starting_annual_base: number; starting_monthly: number; assumed_open_reqs_filled: number; assumed_raise_factor: number; months: ForecastMonth[] };

type HiringImpactItem = { id: string; title: string; status: string; estimated_base: number; estimated_loaded: number };
type HiringImpact = { open_reqs: number; total_loaded_delta: number; items: HiringImpactItem[] };

type CompBudget = {
  budget: number; consumed: number; variance_pct: number; tone: "danger" | "warn" | "success";
  by_department: { department: string; headcount: number; annual_base: number; annual_loaded: number }[];
};

function currency(n?: number | null) {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function shortCurrency(n?: number | null) {
  if (n == null) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n}`;
}

export default function FinancePage() {
  const ovQ = useQuery({ queryKey: ["finance-overview"], queryFn: () => apiFetch<Overview>("/workforce-finance/overview") });
  const fcQ = useQuery({ queryKey: ["finance-forecast"], queryFn: () => apiFetch<Forecast>("/workforce-finance/forecast?months=12") });
  const hrQ = useQuery({ queryKey: ["finance-hiring"], queryFn: () => apiFetch<HiringImpact>("/workforce-finance/hiring-impact") });
  const cbQ = useQuery({ queryKey: ["finance-comp-budget"], queryFn: () => apiFetch<CompBudget>("/workforce-finance/comp-budget") });

  const ov = ovQ.data;
  const fc = fcQ.data;
  const hr = hrQ.data;
  const cb = cbQ.data;

  // Build forecast chart bars
  const forecastChart = useMemo(() => {
    if (!fc) return null;
    const max = Math.max(...fc.months.map((m) => m.annual_loaded));
    return fc.months.map((m) => ({ ...m, pct: max ? (m.annual_loaded / max) : 0 }));
  }, [fc]);

  const consumedPct = cb ? Math.min(100, Math.round((cb.consumed / Math.max(cb.budget, 1)) * 100)) : 0;
  const utilizationTone = cb?.tone ?? "success";

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Finance"
        title="Workforce finance"
        subtitle="Payroll · comp budget · hiring impact — joined to live HR data. One surface for the people-money picture."
        actions={
          <>
            <LinkAction href="/app/cfo" variant="subtle">Open CFO modeling</LinkAction>
            <LinkAction href="/app/comp" variant="primary"><IconSparkle /> Comp review</LinkAction>
          </>
        }
      />

      {/* "$1.98M annual loaded payroll · 10 employees · comp budget $2.40M ·
          budget variance -17.3%" for an organisation with one employee. The
          salaries are a module constant; the open requisitions beside them are
          real, which is what made the whole row look credible. */}
      {ov?.cohort?.is_sample && (
        <Surface pad="md">
          <div className="fp-eyebrow">Which of these numbers are yours</div>
          <p className="mt-1 text-sm text-body">{ov.cohort.note}</p>
          <p className="mt-2 text-xs text-muted">
            From your records: {ov.cohort.real_inputs.join(", ")}. From the sample cohort:{" "}
            {ov.cohort.sample_inputs.join(", ")}.
          </p>
        </Surface>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat
          label="Annual loaded payroll"
          value={shortCurrency(ov?.annual_payroll_loaded)}
          hint={ov?.cohort?.is_sample
            ? `${ov.headcount} sample employees`
            : `${ov?.headcount ?? "—"} employees`}
        />
        <Stat label="Comp budget" value={shortCurrency(ov?.comp_budget_annual)} hint={`Loading ${Math.round((ov?.benefits_loading_rate ?? 0) * 100)}%`} />
        <Stat
          label="Budget variance"
          value={ov ? `${ov.comp_budget_variance_pct > 0 ? "+" : ""}${ov.comp_budget_variance_pct}%` : "—"}
          tone={ov ? (ov.comp_budget_variance_pct > 5 ? "danger" : ov.comp_budget_variance_pct > 0 ? "warn" : "success") : "neutral"}
        />
        <Stat label="Hiring delta (loaded)" value={shortCurrency(ov?.hiring_delta_loaded)} hint={`${ov?.open_reqs ?? "—"} open reqs`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Forecast */}
        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow="Forecast"
            title="12-month payroll trajectory"
            description="Assumes open reqs fill over 2 months and a 3% comp cycle at month 6."
          />
          <div className="mt-4">
            {!forecastChart ? (
              <div className="text-sm text-muted py-6 text-center">Loading…</div>
            ) : (
              <>
                <div className="flex items-end gap-1.5 h-48">
                  {forecastChart.map((m) => (
                    <div key={m.month_index} className="flex-1 flex flex-col items-center">
                      <div
                        className="w-full bg-accent rounded-sm transition-all duration-200"
                        style={{ height: `${Math.max(8, m.pct * 100)}%` }}
                        title={`${m.label}: ${currency(m.annual_loaded)}`}
                      />
                      <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">{m.label}</div>
                    </div>
                  ))}
                </div>
                <Divider className="my-4" />
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <div className="fp-eyebrow">Starting monthly</div>
                    <div className="mt-1 text-base font-semibold text-ink tabular-nums">{shortCurrency(fc?.starting_monthly)}</div>
                  </div>
                  <div>
                    <div className="fp-eyebrow">After {fc?.months.length ?? 12}m</div>
                    <div className="mt-1 text-base font-semibold text-ink tabular-nums">{shortCurrency(fc?.months.at(-1)?.monthly_loaded)}</div>
                  </div>
                  <div>
                    <div className="fp-eyebrow">Assumed raise</div>
                    <div className="mt-1 text-base font-semibold text-ink tabular-nums">{fc ? `${(fc.assumed_raise_factor * 100).toFixed(0)}%` : "—"}</div>
                  </div>
                </div>
              </>
            )}
          </div>
        </Surface>

        {/* Comp budget gauge */}
        <Surface>
          <SectionTitle eyebrow="Budget" title="Comp utilization" />
          <div className="mt-3">
            <div className="flex items-end justify-between">
              <div className="text-3xl font-bold tracking-tight tabular-nums">{consumedPct}%</div>
              <Pill tone={utilizationTone}>{cb ? `${cb.variance_pct > 0 ? "+" : ""}${cb.variance_pct}%` : "—"}</Pill>
            </div>
            <div className="mt-2 h-2 rounded-full bg-sunken overflow-hidden">
              <div className={`h-full ${utilizationTone === "danger" ? "bg-danger-fg" : utilizationTone === "warn" ? "bg-warn-fg" : "bg-success-fg"}`}
                   style={{ width: `${consumedPct}%` }} />
            </div>
            <div className="mt-3 text-xs text-muted">
              {currency(cb?.consumed)} of {currency(cb?.budget)} annual
            </div>
          </div>
          <Divider className="my-4" />
          <div className="fp-eyebrow mb-2">By department</div>
          <div className="space-y-2">
            {(cb?.by_department ?? []).map((d) => (
              <div key={d.department}>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-ink">{d.department}</span>
                  <span className="text-muted tabular-nums">{shortCurrency(d.annual_loaded)}</span>
                </div>
                <div className="mt-1 h-1 rounded-full bg-sunken overflow-hidden">
                  <div className="h-full bg-accent" style={{ width: `${Math.min(100, (d.annual_loaded / Math.max(ov?.annual_payroll_loaded || 1, 1)) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
        </Surface>
      </div>

      {/* Hiring impact */}
      <Surface>
        <SectionTitle
          eyebrow="Hiring impact"
          title="Open requisitions"
          description="Each row is the loaded annual cost if filled at target band."
          trailing={<Link href="/app/talent" className="text-xs underline text-muted hover:text-ink">Talent pipeline →</Link>}
        />
        {!hr ? (
          <div className="text-sm text-muted py-4">Loading…</div>
        ) : hr.items.length === 0 ? (
          <EmptyState title="No open requisitions" description="When recruiting opens reqs they'll surface here with cost impact." />
        ) : (
          <>
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {hr.items.map((r) => (
                <div key={r.id} className="rounded-lg border border-line bg-canvas p-3">
                  <div className="text-sm font-semibold text-ink">{r.title}</div>
                  <div className="text-2xs uppercase tracking-eyebrow text-muted">{r.status}</div>
                  <div className="mt-2 flex items-center justify-between">
                    <div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted">Base / loaded</div>
                      <div className="text-sm text-ink tabular-nums">{shortCurrency(r.estimated_base)} → {shortCurrency(r.estimated_loaded)}</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <Divider className="my-3" />
            <div className="flex items-center justify-between">
              <div>
                <div className="fp-eyebrow">Total loaded delta if all filled</div>
                <div className="mt-1 text-xl font-semibold text-ink tabular-nums">{currency(hr.total_loaded_delta)}</div>
              </div>
              <LinkAction href="/app/cfo" variant="subtle">Open CFO modeling <IconArrowUpRight /></LinkAction>
            </div>
          </>
        )}
      </Surface>

      {ov?.as_of && <p className="text-xs text-muted">Snapshot as of {new Date(ov.as_of).toLocaleString()}.</p>}
    </div>
  );
}

function Stat({ label, value, hint, tone = "neutral" }: { label: string; value: React.ReactNode; hint?: string; tone?: "neutral" | "warn" | "danger" | "success" }) {
  const ring: Record<string, string> = {
    neutral: "",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
    success: "ring-1 ring-success-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
      {hint && <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">{hint}</div>}
    </div>
  );
}
