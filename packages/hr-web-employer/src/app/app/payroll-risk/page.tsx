"use client";
/**
 * Payroll Risk Review — Foundry People (Fintra HR) employer portal.
 *
 * An AI observability / trust dashboard for the payroll automation agent:
 * anomaly + risk alert cards, employee classification risk, overtime /
 * compliance flags, missing-approval detection, sensitive-data-access
 * monitoring, and an evidence audit trail. All data + scoring is imported,
 * static, and deterministic from "@/lib/workforceAi" — no backend.
 */
import { useMemo, useState } from "react";
import { downloadCsv } from "@/lib/exportRows";
import {
  PAYROLL_ALERTS,
  PAYROLL_RUNS,
  PAYROLL_TRUST_SCORES,
  PAYROLL_TRUST_SUMMARY,
  PAYROLL_EVIDENCE,
  getRunTrust,
  getPayrollRun,
  scoreColor,
  scoreBand,
  type PayrollAlert,
  type Severity,
  type PayrollTrustDimensions,
} from "@/lib/workforceAi";
import {
  PageHeader,
  SectionTitle,
  Surface,
  Pill,
  Action,
  Divider,
} from "@/components/ds";
import { useLiveData } from "@/lib/useLiveData";

// ---------------------------------------------------------------------------
// Local presentation helpers (derived from the imported scoring lib)
// ---------------------------------------------------------------------------

type Tone = "neutral" | "success" | "warn" | "danger" | "info" | "accent";

const SEVERITY_TONE: Record<Severity, Tone> = {
  critical: "danger",
  high: "danger",
  medium: "warn",
  low: "neutral",
};

const SEVERITY_RANK: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

/** Coerce any incoming severity (snake_case, unknown, undefined) to a valid Severity. */
function normalizeSeverity(s: unknown): Severity {
  const v = String(s ?? "").toLowerCase().trim();
  return v === "critical" || v === "high" || v === "medium" || v === "low"
    ? (v as Severity)
    : "low";
}

/** Coerce a jsonb / string / object evidence value into the human-readable string the page renders. */
function normalizeEvidence(e: unknown): string {
  if (e == null) return "";
  if (typeof e === "string") return e;
  try {
    return JSON.stringify(e);
  } catch {
    return String(e);
  }
}

const RUN_STATUS_TONE: Record<string, Tone> = {
  blocked: "danger",
  in_review: "warn",
  draft: "neutral",
  approved: "info",
  paid: "success",
};

/** Map an alert title to its anomaly category (drives the category column). */
function alertCategory(a: PayrollAlert): string {
  const t = (a.title ?? "").toLowerCase();
  if (t.includes("deduction")) return "Deduction · no approval";
  if (t.includes("overtime")) return "Overtime review";
  if (t.includes("classification") || t.includes("contractor"))
    return "Classification risk";
  if (t.includes("variance")) return "Unusual variance";
  return "Anomaly";
}

const DIMENSION_LABELS: Record<keyof PayrollTrustDimensions, string> = {
  accuracy: "Accuracy",
  policyCompliance: "Policy compliance",
  approvalCoverage: "Approval coverage",
  sensitiveDataHandling: "Sensitive-data handling",
  anomalyRecovery: "Anomaly recovery",
};

function fmtUsd(n: number): string {
  return (Number(n) || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function fmtTime(iso: string): string {
  const d = new Date(iso ?? "");
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ---------------------------------------------------------------------------
// Score ring (0-100 gauge)
// ---------------------------------------------------------------------------
function ScoreRing({ value, size = 96, label }: { value: number; size?: number; label?: string }) {
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  const dash = (pct / 100) * c;
  const color = scoreColor(value);
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--fp-sunken, #F1F5F9)" strokeWidth={stroke} />
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
        <span className="text-xl font-semibold tabular-nums text-ink">{pct}</span>
        {label && <span className="text-2xs uppercase tracking-eyebrow text-muted">{label}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Score bar (horizontal 0-100)
// ---------------------------------------------------------------------------
function ScoreBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 rounded-full bg-sunken overflow-hidden">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, backgroundColor: scoreColor(value) }} />
      </div>
      <span className="w-8 text-right text-xs tabular-nums text-body">{pct}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sparkline — tiny trend mini-bars
// ---------------------------------------------------------------------------
function MiniBars({ values, tone = "#0F766E" }: { values: number[]; tone?: string }) {
  const safeValues = (values ?? []).map((v) => Number(v) || 0);
  const max = Math.max(...safeValues, 1);
  return (
    <div className="flex items-end gap-0.5 h-8">
      {safeValues.map((v, i) => (
        <div
          key={i}
          className="w-1.5 rounded-sm"
          style={{ height: `${Math.max(8, (v / (max || 1)) * 100)}%`, backgroundColor: tone, opacity: 0.35 + (i / (safeValues.length || 1)) * 0.65 }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// KPI stat card
// ---------------------------------------------------------------------------
function Kpi({
  label,
  value,
  hint,
  trend,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  trend?: { dir: "up" | "down" | "flat"; text: string };
  tone?: Tone;
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
    trend?.dir === "up" ? "text-danger-fg" : trend?.dir === "down" ? "text-success-fg" : "text-muted";
  const arrow = trend?.dir === "up" ? "▲" : trend?.dir === "down" ? "▼" : "—";
  return (
    <div className={`rounded-xl border border-line bg-surface p-4 shadow-sm ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
      <div className="mt-1 flex items-center gap-1.5">
        {trend && <span className={`text-2xs font-medium ${trendColor}`}>{arrow} {trend.text}</span>}
        {hint && <span className="text-2xs text-muted">{hint}</span>}
      </div>
    </div>
  );
}

// ===========================================================================
// Page
// ===========================================================================
export default function PayrollRiskPage() {
  const [sevFilter, setSevFilter] = useState<"all" | Severity>("all");

  // --- Live alerts (mock-first, then live) ---------------------------------
  // Live rows arrive as { title, severity, detected_at, evidence (jsonb),
  // resolved }; map them onto the local PayrollAlert shape so all rendering
  // below is unchanged. Resolved alerts are filtered out (they aren't "open").
  const { data: alerts, live, refresh } = useLiveData<ReadonlyArray<PayrollAlert>>(
    "/ai-workforce/payroll/alerts",
    PAYROLL_ALERTS,
    (j) => {
      // Live rows arrive as raw DB rows (snake_case): { id, run_id, title,
      // severity, detected_at, evidence (jsonb — object/array OR JSON string),
      // resolved }. Normalize each into the page's camelCase PayrollAlert shape
      // with safe defaults so no property access below is ever on undefined.
      const rows = (j?.alerts ?? j?.rows ?? j) as unknown;
      if (!Array.isArray(rows)) return PAYROLL_ALERTS;
      return rows
        .filter((r: any) => !(r?.resolved ?? false))
        .map((r: any, i: number): PayrollAlert => ({
          id: String(r?.id ?? `alert_${i}`),
          title: r?.title ?? "Untitled alert",
          severity: normalizeSeverity(r?.severity),
          detectedAt:
            r?.detected_at ?? r?.detectedAt ?? new Date().toISOString(),
          runId: r?.run_id ?? r?.runId ?? "",
          evidence: normalizeEvidence(r?.evidence),
        }));
    },
  );

  // --- Derived KPI / summary numbers (from the imported lib) ---------------
  // Always work against a safe array regardless of mock / live / empty shape.
  const safeAlerts = useMemo(
    () => (Array.isArray(alerts) ? alerts : []),
    [alerts],
  );

  const alertsSorted = useMemo(
    () =>
      [...safeAlerts].sort(
        (a, b) =>
          (SEVERITY_RANK[normalizeSeverity(a.severity)] ?? 99) -
            (SEVERITY_RANK[normalizeSeverity(b.severity)] ?? 99) ||
          (b.detectedAt ?? "").localeCompare(a.detectedAt ?? ""),
      ),
    [safeAlerts],
  );

  const visibleAlerts = useMemo(
    () => alertsSorted.filter((a) => sevFilter === "all" || a.severity === sevFilter),
    [alertsSorted, sevFilter],
  );

  const openRisks = safeAlerts.length;
  const highSeverity = safeAlerts.filter(
    (a) => a.severity === "high" || a.severity === "critical",
  ).length;

  // Missing-approval detection: evidence actions performed but not approved.
  const missingApprovals = useMemo(
    () => (PAYROLL_EVIDENCE ?? []).filter((e) => !e?.approved),
    [],
  );

  const classificationRisks = safeAlerts.filter((a) =>
    (a.title ?? "").toLowerCase().includes("classification"),
  ).length;

  // Sensitive-data-access monitoring rows (derived from runs + dimensions).
  const sensitiveAccess = useMemo(
    () =>
      (PAYROLL_TRUST_SCORES ?? []).map((t) => {
        const run = getPayrollRun(t.runId);
        const sdh = Number(t.dimensions?.sensitiveDataHandling) || 0;
        return {
          runId: t.runId,
          period: run?.period ?? t.runId,
          score: sdh,
          piiFields: Number(run?.employees) || 0,
          status: sdh >= 90 ? "compliant" : sdh >= 80 ? "review" : "exposed",
        };
      }),
    [],
  );

  // Overtime / compliance flags (alerts that are OT or classification related).
  const complianceFlags = alertsSorted.filter((a) => {
    const t = (a.title ?? "").toLowerCase();
    return t.includes("overtime") || t.includes("classification") || t.includes("contractor");
  });

  // Per-run anomaly mini-bars for the trend sparkline.
  const anomalyTrend = (PAYROLL_RUNS ?? []).map((r) => Number(r?.anomalyCount) || 0);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Payroll · Trust & Risk"
        title="Payroll Risk Review"
        subtitle="Continuous observability over the payroll automation agent — anomaly detection, missing-approval tracking, worker-classification risk, overtime / compliance flags, and sensitive-data-access monitoring. Scores are deterministic 0-100 trust signals."
        actions={
          <>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                live
                  ? "bg-teal-50 text-teal-700 ring-1 ring-teal-600/20"
                  : "bg-slate-100 text-slate-600 ring-1 ring-slate-500/20"
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${live ? "bg-teal-500" : "bg-slate-400"}`}
                aria-hidden
              />
              {live ? "Live" : "Sample data"}
            </span>
            <Action
              variant="subtle"
              size="sm"
              onClick={() =>
                downloadCsv("payroll-risk-evidence.csv", alertsSorted as any, {
                  live,
                  note:
                    "Each row is an alert with the evidence string the scan " +
                    "produced. Nothing here is corroborated by a payroll " +
                    "provider or a bank.",
                })
              }
            >
              Export evidence
            </Action>
            <Action variant="primary" size="sm" onClick={refresh}>
              Re-run scan
            </Action>
          </>
        }
      />

      {/* --- Executive summary: KPI stat cards ------------------------------ */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Kpi
          label="Open risks"
          value={openRisks}
          tone="warn"
          trend={{ dir: "up", text: "+2 wk" }}
          hint="across 4 runs"
        />
        <Kpi
          label="High severity"
          value={highSeverity}
          tone="danger"
          trend={{ dir: "up", text: "+1 wk" }}
          hint={`${PAYROLL_TRUST_SUMMARY.openCriticalAlerts} critical`}
        />
        <Kpi
          label="Missing approvals"
          value={missingApprovals.length}
          tone="danger"
          trend={{ dir: "flat", text: "no change" }}
          hint="unapproved actions"
        />
        <Kpi
          label="Classification risks"
          value={classificationRisks}
          tone="warn"
          trend={{ dir: "up", text: "+1 wk" }}
          hint="1099 vs W-2"
        />
        <Kpi
          label="Agent trust"
          value={`${PAYROLL_TRUST_SUMMARY.overall}`}
          tone={PAYROLL_TRUST_SUMMARY.band === "at-risk" ? "danger" : "success"}
          trend={{ dir: "down", text: "-6 wk" }}
          hint={PAYROLL_TRUST_SUMMARY.band}
        />
      </div>

      {/* --- Trust posture: ring + dimension bars + anomaly sparkline ------- */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Surface className="lg:col-span-1">
          <SectionTitle eyebrow="Composite" title="Payroll agent trust" description="Weighted across 5 trust dimensions." />
          <div className="mt-4 flex items-center gap-5">
            <ScoreRing value={PAYROLL_TRUST_SUMMARY.overall} label="trust" />
            <div className="min-w-0">
              <Pill tone={PAYROLL_TRUST_SUMMARY.band === "at-risk" ? "danger" : "success"}>
                {PAYROLL_TRUST_SUMMARY.band}
              </Pill>
              <div className="mt-2 text-xs text-muted">
                Worst run{" "}
                <span className="font-medium text-ink">
                  {getPayrollRun(PAYROLL_TRUST_SUMMARY.lowestRunId ?? "")?.period ?? "—"}
                </span>
              </div>
              <div className="mt-3 text-2xs uppercase tracking-eyebrow text-muted">Anomalies / run</div>
              <MiniBars values={anomalyTrend} tone="#DC2626" />
            </div>
          </div>
        </Surface>

        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow="Dimensions"
            title="Trust breakdown · current period"
            description="Run 2026-06 (1st half) — the blocked run under review."
            trailing={<Pill tone="danger">blocked</Pill>}
          />
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
            {(() => {
              const t = getRunTrust("run_2026_06_a");
              if (!t) return null;
              return (Object.keys(DIMENSION_LABELS) as (keyof PayrollTrustDimensions)[]).map((k) => {
                const dim = Number(t.dimensions?.[k]) || 0;
                return (
                <div key={k}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-body">{DIMENSION_LABELS[k]}</span>
                    <span className="text-2xs uppercase tracking-eyebrow text-muted">
                      {scoreBand(dim)}
                    </span>
                  </div>
                  <div className="mt-1">
                    <ScoreBar value={dim} />
                  </div>
                </div>
                );
              });
            })()}
          </div>
        </Surface>
      </div>

      {/* --- Anomaly + risk alert cards ------------------------------------ */}
      <Surface>
        <SectionTitle
          eyebrow="Alerts"
          title="Payroll anomaly & risk alerts"
          description="Deduction-without-approval, overtime review, contractor classification, and unusual variance."
          trailing={
            <div className="flex items-center gap-1.5">
              {(["all", "critical", "high", "medium", "low"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSevFilter(s)}
                  className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors ${
                    sevFilter === s ? "border-ink/40 bg-sunken text-ink" : "border-line text-muted hover:bg-sunken"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          }
        />
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          {visibleAlerts.map((a) => {
            const run = getPayrollRun(a.runId);
            return (
              <div
                key={a.id}
                className="rounded-xl border border-line bg-canvas p-4 hover:bg-sunken transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">{alertCategory(a)}</div>
                    <div className="mt-0.5 text-sm font-semibold text-ink">{a.title}</div>
                  </div>
                  <Pill tone={SEVERITY_TONE[normalizeSeverity(a.severity)]}>{a.severity}</Pill>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-body">{a.evidence}</p>
                <div className="mt-3 flex items-center justify-between text-2xs text-muted">
                  <span>{run?.period ?? a.runId}</span>
                  <span className="tabular-nums">{fmtTime(a.detectedAt)}</span>
                </div>
              </div>
            );
          })}
          {visibleAlerts.length === 0 && (
            <div className="md:col-span-2 py-8 text-center text-sm text-muted">
              No alerts at this severity.
            </div>
          )}
        </div>
      </Surface>

      {/* --- Payroll runs: classification + variance risk table ------------ */}
      <Surface pad="none">
        <div className="p-5 pb-3">
          <SectionTitle
            eyebrow="Runs"
            title="Per-run risk register"
            description="Trust score, anomaly count, and status across recent payroll runs."
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-line text-left text-2xs uppercase tracking-eyebrow text-muted">
                <th className="px-5 py-2 font-medium">Pay period</th>
                <th className="px-5 py-2 font-medium text-right">Gross</th>
                <th className="px-5 py-2 font-medium text-right">Employees</th>
                <th className="px-5 py-2 font-medium text-right">Anomalies</th>
                <th className="px-5 py-2 font-medium">Trust</th>
                <th className="px-5 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {(PAYROLL_RUNS ?? []).map((r) => {
                const anomalyCount = Number(r?.anomalyCount) || 0;
                return (
                <tr key={r.id} className="hover:bg-sunken transition-colors">
                  <td className="px-5 py-3">
                    <div className="font-medium text-ink">{r.period}</div>
                    <div className="text-2xs text-muted">{r.aiAssisted ? "AI-assisted" : "manual"}</div>
                  </td>
                  <td className="px-5 py-3 text-right tabular-nums text-body">{fmtUsd(r.grossUsd)}</td>
                  <td className="px-5 py-3 text-right tabular-nums text-body">{Number(r?.employees) || 0}</td>
                  <td className="px-5 py-3 text-right">
                    <Pill tone={anomalyCount >= 3 ? "danger" : anomalyCount >= 1 ? "warn" : "success"}>
                      {anomalyCount}
                    </Pill>
                  </td>
                  <td className="px-5 py-3 w-44">
                    <ScoreBar value={r.trustScore} />
                  </td>
                  <td className="px-5 py-3">
                    <Pill tone={RUN_STATUS_TONE[r.status] ?? "neutral"}>{(r?.status ?? "").replace("_", " ")}</Pill>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Surface>

      {/* --- Overtime / compliance flags + Missing approvals --------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Surface>
          <SectionTitle
            eyebrow="Compliance"
            title="Overtime & classification flags"
            description="FLSA overtime and IRS common-law worker-test exposure."
          />
          <ul className="mt-3 divide-y divide-rule">
            {complianceFlags.map((a) => (
              <li key={a.id} className="py-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink">{a.title}</div>
                  <div className="mt-0.5 text-xs text-muted line-clamp-2">{a.evidence}</div>
                </div>
                <Pill tone={SEVERITY_TONE[normalizeSeverity(a.severity)]}>{a.severity}</Pill>
              </li>
            ))}
            {complianceFlags.length === 0 && (
              <li className="py-6 text-center text-sm text-muted">No open compliance flags.</li>
            )}
          </ul>
        </Surface>

        <Surface>
          <SectionTitle
            eyebrow="Approvals"
            title="Missing-approval detection"
            description="Agent actions that proceeded without a required human sign-off."
            trailing={<Pill tone="danger">{missingApprovals.length} open</Pill>}
          />
          <ul className="mt-3 divide-y divide-rule">
            {missingApprovals.map((e) => (
              <li key={e.id} className="py-3 flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium text-ink">{e.action}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-2xs text-muted">
                    <span>{e.actor}</span>
                    <span aria-hidden>·</span>
                    <span className="tabular-nums">{fmtTime(e.at)}</span>
                    {e.reference && (
                      <>
                        <span aria-hidden>·</span>
                        <span className="font-mono">{e.reference}</span>
                      </>
                    )}
                  </div>
                </div>
                <Pill tone="danger">unapproved</Pill>
              </li>
            ))}
            {missingApprovals.length === 0 && (
              <li className="py-6 text-center text-sm text-muted">All actions approved.</li>
            )}
          </ul>
        </Surface>
      </div>

      {/* --- Sensitive-data-access monitoring ------------------------------ */}
      <Surface pad="none">
        <div className="p-5 pb-3">
          <SectionTitle
            eyebrow="Data protection"
            title="Sensitive-data-access monitoring"
            description="PII / compensation-data handling score per payroll run."
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-line text-left text-2xs uppercase tracking-eyebrow text-muted">
                <th className="px-5 py-2 font-medium">Run</th>
                <th className="px-5 py-2 font-medium text-right">PII records touched</th>
                <th className="px-5 py-2 font-medium">Handling score</th>
                <th className="px-5 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-rule">
              {sensitiveAccess.map((s) => (
                <tr key={s.runId} className="hover:bg-sunken transition-colors">
                  <td className="px-5 py-3 font-medium text-ink">{s.period}</td>
                  <td className="px-5 py-3 text-right tabular-nums text-body">{s.piiFields.toLocaleString()}</td>
                  <td className="px-5 py-3 w-48">
                    <ScoreBar value={s.score} />
                  </td>
                  <td className="px-5 py-3">
                    <Pill tone={s.status === "compliant" ? "success" : s.status === "review" ? "warn" : "danger"}>
                      {s.status}
                    </Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Surface>

      {/* --- Audit-trail / evidence timeline ------------------------------- */}
      <Surface>
        <SectionTitle
          eyebrow="Audit trail"
          title="Evidence timeline"
          description="Chronological log of agent and human actions with approval state — exportable for compliance review."
        />
        <ol className="mt-4 relative border-l border-line ml-2">
          {[...(PAYROLL_EVIDENCE ?? [])]
            .sort((a, b) => (b.at ?? "").localeCompare(a.at ?? ""))
            .map((e) => {
              const run = getPayrollRun(e.runId);
              const actor = e.actor ?? "";
              const isAgent = actor.toLowerCase().includes("agent") || actor.toLowerCase().includes("monitor");
              return (
                <li key={e.id} className="ml-5 pb-5 last:pb-0">
                  <span
                    className="absolute -left-[7px] mt-1 h-3 w-3 rounded-full border-2 border-surface"
                    style={{ backgroundColor: e.approved ? "#16A34A" : "#DC2626" }}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-ink">{e.action}</span>
                    <Pill tone={e.approved ? "success" : "danger"}>{e.approved ? "approved" : "unapproved"}</Pill>
                    {isAgent && <Pill tone="info">agent</Pill>}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-2 text-2xs text-muted">
                    <span>{e.actor}</span>
                    <span aria-hidden>·</span>
                    <span className="tabular-nums">{fmtTime(e.at)}</span>
                    <span aria-hidden>·</span>
                    <span>{run?.period ?? e.runId}</span>
                    {e.reference && (
                      <>
                        <span aria-hidden>·</span>
                        <span className="font-mono">{e.reference}</span>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
        </ol>
        <Divider className="my-4" />
        <div className="flex items-center justify-between text-2xs text-muted">
          <span>{(PAYROLL_EVIDENCE ?? []).length} logged actions · {missingApprovals.length} require approval</span>
          <span>Retention: 7 years · SOC 2 evidence</span>
        </div>
      </Surface>
    </div>
  );
}
