"use client";
/**
 * Payroll Agent Trust — observability + trust dashboard for the payroll
 * automation agent. Mirrors the calm enterprise layout of the Skills Graph
 * page: KPI header row, score rings, a dense run-review table with risk
 * badges, alert cards, and an evidence (audit) trail.
 *
 * All data + scoring is imported from "@/lib/workforceAi" (deterministic
 * mock data, no backend).
 */
import { useMemo, useState } from "react";
import { PageHeader, SectionTitle, Surface, Pill } from "@/components/ds";
import { useLiveData } from "@/lib/useLiveData";
import {
  PAYROLL_RUNS,
  PAYROLL_ALERTS,
  PAYROLL_EVIDENCE,
  PAYROLL_TRUST_SCORES,
  PAYROLL_TRUST_SUMMARY,
  PAYROLL_TRUST_WEIGHTS,
  getRunTrust,
  scoreColor,
  scoreBand,
  clamp100,
  type PayrollRun,
  type PayrollRunStatus,
  type PayrollTrustDimensions,
  type Severity,
} from "@/lib/workforceAi";

// ---------------------------------------------------------------------------
// Local presentation helpers
// ---------------------------------------------------------------------------

type Tone = "neutral" | "success" | "warn" | "danger" | "info" | "accent";

const STATUS_TONE: Record<PayrollRunStatus, Tone> = {
  draft: "neutral",
  in_review: "info",
  approved: "success",
  paid: "success",
  blocked: "danger",
};

const STATUS_LABEL: Record<PayrollRunStatus, string> = {
  draft: "Draft",
  in_review: "In review",
  approved: "Approved",
  paid: "Paid",
  blocked: "Blocked",
};

// Defensive status lookups — live rows can carry an unknown/empty status, so
// fall back to a neutral pill instead of indexing into `undefined`.
const statusTone = (s: PayrollRunStatus | string | undefined): Tone =>
  STATUS_TONE[s as PayrollRunStatus] ?? "neutral";
const statusLabel = (s: PayrollRunStatus | string | undefined): string =>
  STATUS_LABEL[s as PayrollRunStatus] ?? (s ? String(s) : "Unknown");

const SEVERITY_TONE: Record<Severity, Tone> = {
  low: "neutral",
  medium: "warn",
  high: "warn",
  critical: "danger",
};

const severityTone = (s: Severity | string | undefined): Tone =>
  SEVERITY_TONE[s as Severity] ?? "neutral";

const DIMENSION_LABEL: Record<keyof PayrollTrustDimensions, string> = {
  accuracy: "Accuracy",
  policyCompliance: "Policy compliance",
  approvalCoverage: "Approval coverage",
  sensitiveDataHandling: "Sensitive-data handling",
  anomalyRecovery: "Anomaly recovery",
};

const DIMENSION_HINT: Record<keyof PayrollTrustDimensions, string> = {
  accuracy: "Computed amounts vs. ground truth",
  policyCompliance: "Respects comp / benefits / tax policy",
  approvalCoverage: "Required human sign-off obtained",
  sensitiveDataHandling: "PII & comp data handled correctly",
  anomalyRecovery: "Roll-back / recovery when things break",
};

const usd0 = (n: number) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(n);

const fmtNum = (n: number) => new Intl.NumberFormat("en-US").format(n);

const fmtDateTime = (iso: string | undefined | null) => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
};

function bandTone(score: number): Tone {
  const b = scoreBand(score);
  return b === "strong"
    ? "success"
    : b === "solid"
    ? "info"
    : b === "developing"
    ? "warn"
    : "danger";
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

/**
 * Normalize one payroll-run record into the page's expected `PayrollRun`
 * shape. Live API rows arrive as raw DB rows (snake_case columns, numbers as
 * strings, etc.); the mock is already camelCase. This maps every field the
 * page renders, coerces types, and fills safe defaults so no property access
 * downstream is ever on `undefined`.
 */
function normalizeRun(r: any): PayrollRun {
  const row = r ?? {};
  const pick = <T,>(...candidates: T[]): T | undefined =>
    candidates.find((v) => v !== undefined && v !== null);
  const num = (v: unknown): number => {
    const n = typeof v === "string" ? Number(v) : (v as number);
    return Number.isFinite(n) ? n : 0;
  };
  const id = String(pick(row.id, row.run_id, row.runId, "") ?? "");
  return {
    id,
    period: String(
      pick(row.period, row.pay_period, row.payPeriod, row.name, id) ?? ""
    ),
    grossUsd: num(pick(row.grossUsd, row.gross_usd, row.gross, row.amount_usd)),
    employees: num(
      pick(row.employees, row.employee_count, row.employeeCount, row.headcount)
    ),
    status: String(
      pick(row.status, row.run_status, row.runStatus, "draft") ?? "draft"
    ) as PayrollRunStatus,
    aiAssisted: Boolean(
      pick(row.aiAssisted, row.ai_assisted, row.is_ai_assisted) ?? false
    ),
    anomalyCount: num(
      pick(row.anomalyCount, row.anomaly_count, row.anomalies, row.anomaliesCount)
    ),
    trustScore: num(
      pick(row.trustScore, row.trust_score, row.score, row.trust)
    ),
  };
}

export default function PayrollTrustPage() {
  // LIVE payroll runs with deterministic mock fallback (mock renders until live loads).
  // `pick` normalizes each raw DB row into the page's camelCase PayrollRun shape.
  const { data: runs, live } = useLiveData<PayrollRun[]>(
    "/ai-workforce/payroll/runs",
    PAYROLL_RUNS as PayrollRun[],
    (j) => {
      const rows = j?.runs ?? j?.rows ?? j?.data ?? j;
      return (Array.isArray(rows) ? rows : []).map(normalizeRun);
    }
  );

  // Default the deep-dive ring panel to the org's lowest-trust (riskiest) run.
  const [activeRunId, setActiveRunId] = useState<string>(
    PAYROLL_TRUST_SUMMARY.lowestRunId ?? PAYROLL_RUNS[0]?.id ?? ""
  );

  const kpis = useMemo(() => {
    const safeRuns = runs ?? [];
    const runsReviewed = safeRuns.length;
    const anomaliesCaught = safeRuns.reduce(
      (s, r) => s + (Number(r?.anomalyCount) || 0),
      0
    );
    // Approval coverage = mean of the per-run approvalCoverage dimension.
    const coverage = clamp100(
      (PAYROLL_TRUST_SCORES ?? []).reduce(
        (s, t) => s + (Number(t?.dimensions?.approvalCoverage) || 0),
        0
      ) / Math.max(1, (PAYROLL_TRUST_SCORES ?? []).length)
    );
    return {
      trust: PAYROLL_TRUST_SUMMARY.overall,
      runsReviewed,
      anomaliesCaught,
      coverage,
      openCritical: PAYROLL_TRUST_SUMMARY.openCriticalAlerts,
    };
  }, [runs]);

  const activeTrust = getRunTrust(activeRunId);
  const activeRun = (runs ?? []).find((r) => r.id === activeRunId);
  const activeEvidence = useMemo(
    () =>
      [...PAYROLL_EVIDENCE]
        .filter((e) => e.runId === activeRunId)
        .sort((a, b) => a.at.localeCompare(b.at)),
    [activeRunId]
  );

  const sortedAlerts = useMemo(
    () =>
      [...PAYROLL_ALERTS].sort(
        (a, b) =>
          severityRank(b.severity) - severityRank(a.severity) ||
          b.detectedAt.localeCompare(a.detectedAt)
      ),
    []
  );

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Payroll · Agent trust"
        title="Payroll Agent Trust"
        subtitle="How much we can rely on the payroll automation agent — accuracy, policy compliance, approval coverage, sensitive-data handling, and anomaly recovery, scored per run with a full evidence trail for every money-moving action."
        actions={
          <div className="flex items-center gap-2">
            <Pill tone={live ? "success" : "neutral"}>
              <span className="size-1.5 rounded-full bg-current opacity-70" />
              {live ? "Live" : "Sample"}
            </Pill>
            <Pill tone={bandTone(kpis.trust)}>
              <span className="size-1.5 rounded-full bg-current opacity-70" />
              Trust {kpis.trust} · {scoreBand(kpis.trust)}
            </Pill>
          </div>
        }
      />

      {/* Executive KPI row -------------------------------------------------- */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Kpi
          label="Payroll trust score"
          value={kpis.trust}
          suffix="/100"
          tone={bandTone(kpis.trust)}
          hint={`Org-wide · band ${scoreBand(kpis.trust)}`}
          trend="up"
          trendLabel="+4 vs. last period"
        />
        <Kpi
          label="Runs reviewed"
          value={kpis.runsReviewed}
          hint="Trailing 60 days"
          trend="flat"
          trendLabel="All AI-assisted"
        />
        <Kpi
          label="Anomalies caught"
          value={kpis.anomaliesCaught}
          tone={kpis.openCritical > 0 ? "danger" : "warn"}
          hint={`${kpis.openCritical} critical open`}
          trend="up"
          trendLabel="Monitor active"
        />
        <Kpi
          label="Approval coverage"
          value={kpis.coverage}
          suffix="%"
          tone={bandTone(kpis.coverage)}
          hint="Actions with human sign-off"
          trend={kpis.coverage >= 85 ? "up" : "down"}
          trendLabel={kpis.coverage >= 85 ? "Within target" : "Below 85% target"}
        />
      </div>

      {/* Trust dimensions (rings) + worst-run callout ---------------------- */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <Surface className="xl:col-span-2">
          <SectionTitle
            eyebrow="Trust dimensions"
            title={
              activeRun
                ? `${activeRun.period} · trust breakdown`
                : "Trust breakdown"
            }
            description="Weighted sub-dimensions for the selected run. Accuracy and policy compliance dominate the rollup."
            trailing={
              activeTrust ? (
                <Pill tone={bandTone(activeTrust.overall)}>
                  overall {activeTrust.overall}
                </Pill>
              ) : null
            }
          />
          {activeTrust ? (
            <div className="mt-5 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
              {(
                Object.keys(activeTrust.dimensions ?? {}) as Array<
                  keyof PayrollTrustDimensions
                >
              ).map((dim) => (
                <Ring
                  key={dim}
                  value={activeTrust.dimensions[dim]}
                  label={DIMENSION_LABEL[dim]}
                  hint={DIMENSION_HINT[dim]}
                  weight={PAYROLL_TRUST_WEIGHTS[dim]}
                />
              ))}
            </div>
          ) : (
            <div className="mt-4 text-sm text-muted">Select a run below.</div>
          )}
        </Surface>

        {/* Composite trust gauge */}
        <Surface>
          <SectionTitle
            eyebrow="Composite"
            title="Org payroll trust"
            description="Mean across all scored runs."
          />
          <div className="mt-4 flex flex-col items-center">
            <Ring value={kpis.trust} size={132} stroke={12} showBand />
            <div className="mt-4 w-full space-y-2">
              <GaugeRow
                label="Highest run"
                runId={PAYROLL_TRUST_SUMMARY.highestRunId}
              />
              <GaugeRow
                label="Lowest run"
                runId={PAYROLL_TRUST_SUMMARY.lowestRunId}
              />
            </div>
          </div>
        </Surface>
      </div>

      {/* Run review table -------------------------------------------------- */}
      <Surface pad="none">
        <div className="p-5 pb-0">
          <SectionTitle
            eyebrow="Run review"
            title="Payroll runs · trust & anomalies"
            description="Each run scored by the trust model. Click a row to load its dimensions and evidence trail."
            trailing={
              <span className="text-2xs uppercase tracking-eyebrow text-muted">
                {(runs ?? []).length} runs
              </span>
            }
          />
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-line bg-canvas text-left">
                <Th>Period</Th>
                <Th className="text-right">Gross</Th>
                <Th className="text-right">Employees</Th>
                <Th>Status</Th>
                <Th className="text-right">Anomalies</Th>
                <Th>Trust score</Th>
                <Th className="text-right" />
              </tr>
            </thead>
            <tbody>
              {(runs ?? []).map((run) => {
                const isActive = run.id === activeRunId;
                const anomalyCount = Number(run.anomalyCount) || 0;
                return (
                  <tr
                    key={run.id}
                    onClick={() => setActiveRunId(run.id)}
                    className={`cursor-pointer border-b border-rule transition-colors ${
                      isActive ? "bg-sunken" : "hover:bg-canvas"
                    }`}
                  >
                    <Td>
                      <div className="font-medium text-ink">{run.period}</div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted">
                        {run.aiAssisted ? "AI-assisted" : "Manual"} · {run.id}
                      </div>
                    </Td>
                    <Td className="text-right tabular-nums text-ink">
                      {usd0(Number(run.grossUsd) || 0)}
                    </Td>
                    <Td className="text-right tabular-nums text-body">
                      {fmtNum(Number(run.employees) || 0)}
                    </Td>
                    <Td>
                      <Pill tone={statusTone(run.status)}>
                        {statusLabel(run.status)}
                      </Pill>
                    </Td>
                    <Td className="text-right">
                      <span
                        className={`tabular-nums font-medium ${
                          anomalyCount === 0
                            ? "text-muted"
                            : anomalyCount >= 3
                            ? "text-danger-fg"
                            : "text-warn-fg"
                        }`}
                      >
                        {anomalyCount}
                      </span>
                    </Td>
                    <Td>
                      <ScoreBar value={Number(run.trustScore) || 0} />
                    </Td>
                    <Td className="text-right">
                      <span className="text-xs text-muted">
                        {isActive ? "Viewing" : "View →"}
                      </span>
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Surface>

      {/* Alerts + Evidence trail ------------------------------------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Alert cards */}
        <Surface>
          <SectionTitle
            eyebrow="Anomaly monitor"
            title="Open & recent alerts"
            description="Every alert links to the run and the evidence that fired it."
            trailing={
              <Pill tone={kpis.openCritical > 0 ? "danger" : "success"}>
                {kpis.openCritical} critical
              </Pill>
            }
          />
          <div className="mt-4 space-y-3">
            {sortedAlerts.map((a) => {
              const run = (runs ?? []).find((r) => r.id === a.runId);
              return (
                <button
                  key={a.id}
                  onClick={() => setActiveRunId(a.runId)}
                  className={`w-full text-left rounded-md border p-3 transition-colors ${
                    a.severity === "critical"
                      ? "border-danger-line bg-danger-bg/40"
                      : "border-line bg-canvas hover:bg-sunken"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-ink">
                        {a.title}
                      </div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                        {run?.period ?? a.runId} · {fmtDateTime(a.detectedAt)}
                      </div>
                    </div>
                    <Pill tone={severityTone(a.severity)}>{a.severity}</Pill>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-body">
                    {a.evidence}
                  </p>
                </button>
              );
            })}
          </div>
        </Surface>

        {/* Evidence trail (audit timeline) */}
        <Surface>
          <SectionTitle
            eyebrow="Evidence trail"
            title={
              activeRun ? `Audit trail · ${activeRun.period}` : "Audit trail"
            }
            description="Chronological record of every payroll action on this run, with approval state and references."
            trailing={
              <span className="text-2xs uppercase tracking-eyebrow text-muted">
                {activeEvidence.length} events
              </span>
            }
          />
          {activeEvidence.length === 0 ? (
            <div className="mt-4 text-sm text-muted">
              No recorded actions for this run.
            </div>
          ) : (
            <ol className="mt-4 relative pl-6">
              <span className="absolute left-[7px] top-1 bottom-1 w-px bg-line" />
              {activeEvidence.map((e) => (
                <li key={e.id} className="relative pb-4 last:pb-0">
                  <span
                    className={`absolute -left-6 top-1 size-3.5 rounded-full border-2 border-surface ${
                      e.approved ? "bg-success-fg" : "bg-danger-fg"
                    }`}
                    style={{ marginLeft: 1 }}
                  />
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-ink">
                        {e.action}
                      </div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                        {e.actor} · {fmtDateTime(e.at)}
                      </div>
                    </div>
                    <Pill tone={e.approved ? "success" : "danger"}>
                      {e.approved ? "approved" : "unapproved"}
                    </Pill>
                  </div>
                  {e.reference && (
                    <div className="mt-1 inline-flex items-center rounded-md bg-canvas border border-line px-1.5 py-0.5 font-mono text-[10px] text-muted">
                      {e.reference}
                    </div>
                  )}
                </li>
              ))}
            </ol>
          )}
        </Surface>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Local sub-components
// ---------------------------------------------------------------------------

function severityRank(s: Severity): number {
  return s === "critical" ? 3 : s === "high" ? 2 : s === "medium" ? 1 : 0;
}

function Kpi({
  label,
  value,
  suffix,
  hint,
  tone = "neutral",
  trend = "flat",
  trendLabel,
}: {
  label: string;
  value: number | string;
  suffix?: string;
  hint?: string;
  tone?: Tone;
  trend?: "up" | "down" | "flat";
  trendLabel?: string;
}) {
  const ring: Record<Tone, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
    info: "ring-1 ring-info-line",
    accent: "ring-1 ring-line",
  };
  const trendColor =
    trend === "up"
      ? "text-success-fg"
      : trend === "down"
      ? "text-danger-fg"
      : "text-muted";
  const trendGlyph = trend === "up" ? "▲" : trend === "down" ? "▼" : "—";
  return (
    <div
      className={`bg-surface border border-line rounded-xl p-4 shadow-sm ${ring[tone]}`}
    >
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className="text-3xl font-semibold tracking-tight text-ink tabular-nums">
          {value}
        </span>
        {suffix && (
          <span className="text-sm font-medium text-muted">{suffix}</span>
        )}
      </div>
      {(hint || trendLabel) && (
        <div className="mt-1.5 flex items-center gap-1.5 text-xs">
          {trendLabel && (
            <span className={`inline-flex items-center gap-1 ${trendColor}`}>
              <span className="text-[9px] leading-none">{trendGlyph}</span>
              {trendLabel}
            </span>
          )}
          {hint && trendLabel && <span className="text-line">·</span>}
          {hint && <span className="text-muted">{hint}</span>}
        </div>
      )}
    </div>
  );
}

/** A 0-100 score ring drawn with two stacked SVG circles. */
function Ring({
  value,
  label,
  hint,
  weight,
  size = 84,
  stroke = 8,
  showBand = false,
}: {
  value: number;
  label?: string;
  hint?: string;
  weight?: number;
  size?: number;
  stroke?: number;
  showBand?: boolean;
}) {
  const v = clamp100(value);
  const color = scoreColor(v);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (v / 100) * c;
  return (
    <div className="flex flex-col items-center text-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="#E2E8F0"
            strokeWidth={stroke}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${c - dash}`}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="font-semibold tabular-nums text-ink"
            style={{ fontSize: size >= 120 ? 30 : 18 }}
          >
            {v}
          </span>
          {showBand && (
            <span className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
              {scoreBand(v)}
            </span>
          )}
        </div>
      </div>
      {label && (
        <div className="mt-2 text-xs font-medium text-ink leading-tight">
          {label}
        </div>
      )}
      {typeof weight === "number" && (
        <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
          weight {Math.round(weight * 100)}%
        </div>
      )}
      {hint && (
        <div className="mt-0.5 text-[10px] text-muted leading-tight max-w-[12ch]">
          {hint}
        </div>
      )}
    </div>
  );
}

/** Compact horizontal score bar used inside the runs table. */
function ScoreBar({ value }: { value: number }) {
  const v = clamp100(value);
  const color = scoreColor(v);
  return (
    <div className="flex items-center gap-2 min-w-[140px]">
      <div className="h-1.5 flex-1 rounded-full bg-sunken overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ width: `${v}%`, backgroundColor: color }}
        />
      </div>
      <span
        className="w-7 text-right text-xs font-semibold tabular-nums"
        style={{ color }}
      >
        {v}
      </span>
    </div>
  );
}

function GaugeRow({ label, runId }: { label: string; runId?: string }) {
  const run = runId ? PAYROLL_RUNS.find((r) => r.id === runId) : undefined;
  const trust = runId ? getRunTrust(runId) : undefined;
  if (!run || !trust) return null;
  return (
    <div className="flex items-center justify-between rounded-md border border-line bg-canvas px-3 py-2">
      <div className="min-w-0">
        <div className="text-2xs uppercase tracking-eyebrow text-muted">
          {label}
        </div>
        <div className="text-xs font-medium text-ink truncate">
          {run.period}
        </div>
      </div>
      <Pill tone={bandTone(trust.overall)}>{trust.overall}</Pill>
    </div>
  );
}

function Th({
  children,
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <th
      className={`px-5 py-2.5 text-2xs font-medium uppercase tracking-eyebrow text-muted ${className}`}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  className = "",
}: {
  children?: React.ReactNode;
  className?: string;
}) {
  return <td className={`px-5 py-3 align-middle ${className}`}>{children}</td>;
}
