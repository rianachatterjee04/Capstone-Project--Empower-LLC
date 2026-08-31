"use client";
/**
 * Automated AI Onboarding — enterprise provisioning-control plane for new hires.
 *
 * For every onboarding run we orchestrate account provisioning across a fixed
 * tool set (Slack / GitHub / Jira / Cursor / Claude / OpenAI / Google / AWS /
 * Databricks / Snowflake) and enforce four security gates (MFA, training,
 * policies signed, least-privilege) before a hire is marked productive.
 *
 * Renders entirely from deterministic mock data + helpers in
 * "@/lib/aiWorkforce2"; no backend, no Math.random. A small amount of view
 * state (the selected run + a time-to-productive what-if slider) lives in React
 * and recomputes live.
 */
import { useMemo, useState } from "react";
import {
  ONBOARDING_RUNS,
  ONBOARDING_TOOLS,
  onboardingProgress,
  onboardingNeedsAttention,
  computeOnboardingStatus,
  scoreColor,
  type OnboardingRun,
  type OnboardingTool,
  type ToolProvision,
  type ProvisionStatus,
  type OnboardingStatus,
  type OnboardingVerifications,
} from "@/lib/aiWorkforce2";
import { useLiveData } from "@/lib/useLiveData";
import { PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";

// ---------------------------------------------------------------------------
// Live-row normalization: the API returns onboarding runs whose field names
// differ from the mock `OnboardingRun` shape. We map them so ALL downstream
// rendering keeps working unchanged.
//
//   live row: { tools: {tool->status}, mfa, training_done, policies_signed,
//               least_privilege, status, time_to_productive_days, started_at, ... }
// ---------------------------------------------------------------------------

const PROVISION_STATUSES: ReadonlyArray<ProvisionStatus> = [
  "provisioned",
  "in_progress",
  "pending",
  "failed",
  "skipped",
];

const RUN_STATUSES: ReadonlyArray<OnboardingStatus> = [
  "complete",
  "in_progress",
  "blocked",
  "not_started",
];

function normalizeProvisionStatus(v: any): ProvisionStatus {
  return PROVISION_STATUSES.includes(v) ? (v as ProvisionStatus) : "pending";
}

// jsonb columns can arrive already-parsed (object/array) OR as a JSON string
// when the row is serialized by the raw `select *`. Parse strings defensively
// and never throw — any unparseable value collapses to a safe empty object.
function parseJsonish(raw: any): any {
  if (typeof raw === "string") {
    const s = raw.trim();
    if (s === "") return {};
    try {
      return JSON.parse(s);
    } catch {
      return {};
    }
  }
  return raw ?? {};
}

// Live `tools` is a jsonb map tool->status (or array of {tool,status}); mock
// expects an ordered array over the fixed ONBOARDING_TOOLS set. Always returns
// exactly one normalized cell per known tool, so downstream `.find`/`.map` is safe.
function normalizeTools(raw: any): ReadonlyArray<ToolProvision> {
  const parsed = parseJsonish(raw);
  if (Array.isArray(parsed)) {
    return ONBOARDING_TOOLS.map((tool) => {
      const cell = parsed.find(
        (t: any) =>
          t?.tool === tool ||
          (typeof t?.tool === "string" && t.tool.toLowerCase() === tool.toLowerCase())
      );
      return { tool, status: normalizeProvisionStatus(cell?.status ?? cell) };
    });
  }
  const map = (parsed ?? {}) as Record<string, any>;
  return ONBOARDING_TOOLS.map((tool) => ({
    tool: tool as OnboardingTool,
    status: normalizeProvisionStatus(
      map?.[tool] ?? map?.[tool.toLowerCase()] ?? map?.[tool.toUpperCase()]
    ),
  }));
}

function normalizeRun(row: any, idx: number): OnboardingRun {
  const r = row ?? {};
  const tools = normalizeTools(r?.tools);
  const verifications: OnboardingVerifications = {
    mfa: !!r?.mfa,
    training: !!(r?.training_done ?? r?.training),
    policiesSigned: !!(r?.policies_signed ?? r?.policiesSigned),
    leastPrivilege: !!(r?.least_privilege ?? r?.leastPrivilege),
  };
  // Live `status` defaults to 'pending' (not a valid OnboardingStatus); only
  // trust it when it's one of the known states, else derive it from the data.
  const status: OnboardingStatus = RUN_STATUSES.includes(r?.status as OnboardingStatus)
    ? (r.status as OnboardingStatus)
    : computeOnboardingStatus(tools, verifications);
  const startRaw = r?.started_at ?? r?.startDate ?? r?.start_date ?? "";
  // numeric(8,2) may arrive as a string or null; coerce and floor at 0.
  const ttp = Number(r?.time_to_productive_days ?? r?.timeToProductiveDays ?? 0);
  return {
    id: String(r?.id ?? r?.employee_id ?? `onb_live_${idx}`),
    newHire: String(
      r?.newHire ?? r?.new_hire ?? r?.name ?? r?.employee_name ?? "New hire"
    ),
    role: String(r?.role ?? r?.title ?? ""),
    department: String(r?.department ?? r?.dept ?? ""),
    startDate: String(startRaw ?? "").slice(0, 10),
    tools,
    verifications,
    status,
    timeToProductiveDays: Number.isFinite(ttp) ? Math.max(0, ttp) : 0,
  };
}

// ---------------------------------------------------------------------------
// Presentation helpers (color / copy decisions live here; data lives in lib)
// ---------------------------------------------------------------------------

type Tone = "neutral" | "success" | "warn" | "danger" | "info" | "accent";

// Provisioning status → pill tone + dot color + label.
const PROVISION_META: Record<
  ProvisionStatus,
  { tone: Tone; dot: string; label: string }
> = {
  provisioned: { tone: "success", dot: "#16A34A", label: "Provisioned" },
  in_progress: { tone: "info", dot: "#0EA5E9", label: "In progress" },
  pending: { tone: "neutral", dot: "#94A3B8", label: "Pending" },
  failed: { tone: "danger", dot: "#DC2626", label: "Failed" },
  skipped: { tone: "neutral", dot: "#CBD5E1", label: "Skipped" },
};

// Overall onboarding status → pill tone + label.
const RUN_STATUS_META: Record<OnboardingStatus, { tone: Tone; label: string }> = {
  complete: { tone: "success", label: "Complete" },
  in_progress: { tone: "info", label: "In progress" },
  blocked: { tone: "danger", label: "Blocked" },
  not_started: { tone: "neutral", label: "Not started" },
};

// Safe lookups: an unexpected status string never crashes on `.label`/`.dot`.
const FALLBACK_PROVISION_META = { tone: "neutral" as Tone, dot: "#94A3B8", label: "Pending" };
const FALLBACK_RUN_STATUS_META = { tone: "neutral" as Tone, label: "Unknown" };
const provisionMeta = (s: any) => PROVISION_META[s as ProvisionStatus] ?? FALLBACK_PROVISION_META;
const runStatusMeta = (s: any) => RUN_STATUS_META[s as OnboardingStatus] ?? FALLBACK_RUN_STATUS_META;

const VERIFICATION_META: { key: keyof OnboardingVerifications; label: string; blurb: string }[] = [
  { key: "mfa", label: "MFA enrolled", blurb: "Multi-factor auth active" },
  { key: "training", label: "Training complete", blurb: "Security & role training" },
  { key: "policiesSigned", label: "Policies signed", blurb: "Acceptable-use & data" },
  { key: "leastPrivilege", label: "Least privilege", blurb: "No broad admin grants" },
];

const usd = (n: number) =>
  (Number(n) || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function fmtDate(iso: string) {
  const d = new Date(String(iso ?? "") + "T00:00:00");
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function daysSince(iso: string) {
  // Anchored to the deterministic "today" of this dataset (2026-06-28).
  const now = new Date("2026-06-28T00:00:00").getTime();
  const then = new Date(String(iso ?? "") + "T00:00:00").getTime();
  if (Number.isNaN(then)) return 0;
  return Math.max(0, Math.round((now - then) / 86_400_000));
}

// ttp band → color (lower is better for time-to-productive).
function ttpColor(daysRaw: number): string {
  const days = Number(daysRaw) || 0;
  if (days <= 5) return "#16A34A";
  if (days <= 8) return "#0F766E";
  if (days <= 10) return "#D97706";
  return "#DC2626";
}

// ---------------------------------------------------------------------------
// Small UI atoms
// ---------------------------------------------------------------------------

function Kpi({
  label,
  value,
  delta,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  delta?: { dir: "up" | "down" | "flat"; text: string; good?: boolean };
  tone?: "neutral" | "success" | "warn" | "danger";
}) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
  };
  const deltaCls = delta
    ? delta.dir === "flat"
      ? "text-muted"
      : delta.good
      ? "text-[#16A34A]"
      : "text-[#DC2626]"
    : "";
  const glyph = delta ? (delta.dir === "up" ? "▲" : delta.dir === "down" ? "▼" : "▬") : "";
  return (
    <div className={`rounded-xl border border-line bg-surface p-4 shadow-soft ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-ink">{value}</div>
      {delta && (
        <div className={`mt-1 flex items-center gap-1 text-xs font-medium ${deltaCls}`}>
          <span aria-hidden>{glyph}</span>
          <span className="tabular-nums">{delta.text}</span>
        </div>
      )}
    </div>
  );
}

// 0-100 progress meter with status color.
function ProgressBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-sunken">
      <div
        className="h-full rounded-full transition-[width] duration-300 ease-calm"
        style={{ width: `${Math.max(3, value)}%`, backgroundColor: color }}
      />
    </div>
  );
}

// Compact provisioning dot grid for the runs table.
function ProvisionDots({ tools }: { tools: OnboardingRun["tools"] }) {
  return (
    <div className="flex items-center gap-1">
      {(tools ?? []).map((t) => (
        <span
          key={t?.tool}
          title={`${t?.tool}: ${provisionMeta(t?.status).label}`}
          className="inline-block h-2.5 w-2.5 rounded-[3px]"
          style={{ backgroundColor: provisionMeta(t?.status).dot }}
        />
      ))}
    </div>
  );
}

// Verification gate chips for one run.
function VerificationGates({ v }: { v: OnboardingVerifications }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {VERIFICATION_META.map((g) => {
        const ok = v?.[g.key];
        return (
          <span
            key={g.key}
            title={g.blurb}
            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] font-medium ${
              ok
                ? "border-success-line bg-success-bg text-success-fg"
                : "border-danger-line bg-danger-bg text-danger-fg"
            }`}
          >
            <span aria-hidden>{ok ? "✓" : "✕"}</span>
            {g.label.replace(" complete", "").replace(" enrolled", "").replace(" signed", "")}
          </span>
        );
      })}
    </div>
  );
}

// Score ring used for the org provisioning-coverage gauge.
function CoverageRing({ value, size = 104 }: { value: number; size?: number }) {
  const stroke = 9;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value)) / 100;
  const color = scoreColor(value);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E2E8F0" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - pct)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-semibold tabular-nums text-ink">{value}%</span>
        <span className="text-2xs uppercase tracking-eyebrow text-muted">coverage</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AiOnboardingPage() {
  // Live-first with mock fallback: the hook returns the mock immediately, then
  // swaps in API rows when present. We normalize live rows to OnboardingRun.
  const { data: rawRuns, live } = useLiveData(
    "/ai-workforce/onboarding",
    ONBOARDING_RUNS,
    (j) => {
      // The endpoint returns a bare array of raw DB rows, but tolerate a wrapped
      // shape too. Drop any non-object rows before normalizing, and fall back to
      // the mock when nothing usable comes back so the page never renders empty.
      const rows = j?.onboarding ?? j?.rows ?? j?.data ?? j;
      if (!Array.isArray(rows)) return ONBOARDING_RUNS;
      const normalized = rows
        .filter((row: any) => row != null && typeof row === "object")
        .map((row: any, i: number) => normalizeRun(row, i)) as ReadonlyArray<OnboardingRun>;
      return normalized.length > 0 ? normalized : ONBOARDING_RUNS;
    }
  );

  const runs = useMemo(
    () =>
      [...(rawRuns ?? [])].sort(
        (a, b) =>
          onboardingProgress(b) - onboardingProgress(a) ||
          (a?.newHire ?? "").localeCompare(b?.newHire ?? "")
      ),
    [rawRuns]
  );

  const [selectedId, setSelectedId] = useState<string>(runs[0]?.id ?? "");
  // What-if control: an automation-coverage lever that shaves estimated TTP.
  const [autoBoost, setAutoBoost] = useState(0); // 0–60 % extra automation

  const selected = useMemo(
    () => runs.find((r) => r.id === selectedId) ?? runs[0],
    [runs, selectedId]
  );

  // Org-level executive rollups, derived purely from the runs.
  const org = useMemo(() => {
    const inProgress = runs.filter((r) => r?.status === "in_progress" || r?.status === "not_started").length;
    const blocked = (onboardingNeedsAttention() ?? []).length;
    const complete = runs.filter((r) => r?.status === "complete").length;

    // Provisioning coverage = provisioned/skipped cells / all cells, across the matrix.
    const totalCells = runs.length * ONBOARDING_TOOLS.length;
    const doneCells = runs.reduce(
      (s, r) => s + (r?.tools ?? []).filter((t) => t?.status === "provisioned" || t?.status === "skipped").length,
      0
    );
    const failedCells = runs.reduce((s, r) => s + (r?.tools ?? []).filter((t) => t?.status === "failed").length, 0);
    const coverage = Math.round((doneCells / (totalCells || 1)) * 100);

    // Policy compliance = satisfied verification gates / all gates.
    const totalGates = runs.length * VERIFICATION_META.length;
    const passedGates = runs.reduce(
      (s, r) => s + VERIFICATION_META.filter((g) => r?.verifications?.[g.key]).length,
      0
    );
    const compliance = Math.round((passedGates / (totalGates || 1)) * 100);

    // Avg time-to-productive over active (non-complete) runs.
    const activeRuns = runs.filter((r) => r?.status !== "complete");
    const avgTtp =
      activeRuns.length > 0
        ? Math.round((activeRuns.reduce((s, r) => s + (Number(r?.timeToProductiveDays) || 0), 0) / activeRuns.length) * 10) / 10
        : 0;

    return {
      inProgress,
      blocked,
      complete,
      coverage,
      compliance,
      avgTtp,
      failedCells,
      passedGates,
      totalGates,
      doneCells,
      totalCells,
    };
  }, [runs]);

  // Per-tool provisioning breakdown across all runs (stacked bar source).
  const toolBreakdown = useMemo(() => {
    return ONBOARDING_TOOLS.map((tool) => {
      const counts: Record<ProvisionStatus, number> = {
        provisioned: 0,
        in_progress: 0,
        pending: 0,
        failed: 0,
        skipped: 0,
      };
      runs.forEach((r) => {
        const cell = (r?.tools ?? []).find((t) => t?.tool === tool);
        if (cell && counts[cell.status] !== undefined) counts[cell.status] += 1;
      });
      const ready = counts.provisioned + counts.skipped;
      return { tool, counts, ready, total: runs.length };
    }).sort((a, b) => a.ready - b.ready || a.tool.localeCompare(b.tool));
  }, [runs]);

  // What-if recompute: applying extra automation coverage to the selected run's TTP.
  const projectedTtp = useMemo(() => {
    if (!selected) return 0;
    const factor = 1 - autoBoost / 100;
    // Floor at 2 days — onboarding can never be instant.
    return Math.max(2, Math.round((Number(selected.timeToProductiveDays) || 0) * factor));
  }, [selected, autoBoost]);

  const stackOrder: ProvisionStatus[] = ["provisioned", "skipped", "in_progress", "pending", "failed"];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="People · IT Provisioning"
        title="Automated AI Onboarding"
        subtitle="One control plane for new-hire provisioning across the AI tool stack — Slack, GitHub, Jira, Cursor, Claude, OpenAI, Google, AWS, Databricks, Snowflake — gated by MFA, training, signed policies, and least-privilege access before a hire is marked productive."
        actions={
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${
                live
                  ? "border-[#0F766E] bg-[#0F766E]/10 text-[#0F766E]"
                  : "border-slate-300 bg-slate-100 text-slate-600"
              }`}
              title={live ? "Showing live API data" : "Showing sample data — the API returned nothing usable"}
            >
              <span
                aria-hidden
                className="inline-block h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: live ? "#0F766E" : "#64748B" }}
              />
              {live ? "Live" : "Sample data"}
            </span>
            <Pill tone="info">{runs.length} active runs</Pill>
            {org.blocked > 0 ? (
              <Pill tone="danger">{org.blocked} need attention</Pill>
            ) : (
              <Pill tone="success">all clear</Pill>
            )}
          </div>
        }
      />

      {/* Executive KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-5">
        <Kpi
          label="Onboardings in progress"
          value={org.inProgress}
          delta={{ dir: "up", text: `${org.complete} completed · 30d`, good: true }}
        />
        <Kpi
          label="Avg time-to-productive"
          value={`${org.avgTtp}d`}
          tone="warn"
          delta={{ dir: "down", text: "-1.4d vs prior cohort", good: true }}
        />
        <Kpi
          label="Provisioning coverage"
          value={`${org.coverage}%`}
          tone={org.coverage >= 85 ? "success" : org.coverage >= 70 ? "neutral" : "warn"}
          delta={{ dir: "up", text: `${org.doneCells}/${org.totalCells} cells`, good: true }}
        />
        <Kpi
          label="Policy compliance"
          value={`${org.compliance}%`}
          tone={org.compliance >= 85 ? "success" : org.compliance >= 70 ? "warn" : "danger"}
          delta={{ dir: "flat", text: `${org.passedGates}/${org.totalGates} gates`, good: org.compliance >= 85 }}
        />
        <Kpi
          label="Failed provisions"
          value={org.failedCells}
          tone={org.failedCells > 0 ? "danger" : "success"}
          delta={
            org.failedCells > 0
              ? { dir: "up", text: "remediation needed", good: false }
              : { dir: "flat", text: "no failures", good: true }
          }
        />
      </div>

      {/* Coverage gauge + per-tool provisioning breakdown */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[320px_1fr]">
        <Surface>
          <SectionTitle
            eyebrow="Org rollup"
            title="Provisioning coverage"
            description="Provisioned or skipped cells across the full onboarding matrix."
          />
          <div className="mt-4 flex items-center gap-5">
            <CoverageRing value={org.coverage} />
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between gap-6">
                <span className="text-muted">Policy compliance</span>
                <span className="font-semibold tabular-nums text-ink">{org.compliance}%</span>
              </div>
              <ProgressBar value={org.compliance} color={scoreColor(org.compliance)} />
              <div className="flex items-center justify-between gap-6 pt-1">
                <span className="text-muted">Runs complete</span>
                <span className="font-semibold tabular-nums text-ink">
                  {org.complete}/{runs.length}
                </span>
              </div>
              <ProgressBar value={(org.complete / (runs.length || 1)) * 100} color="#0EA5E9" />
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 border-t border-line pt-3 text-2xs text-muted">
            {(["provisioned", "in_progress", "pending", "failed", "skipped"] as ProvisionStatus[]).map((s) => (
              <span key={s} className="inline-flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-[2px]" style={{ backgroundColor: PROVISION_META[s].dot }} />
                {PROVISION_META[s].label}
              </span>
            ))}
          </div>
        </Surface>

        <Surface>
          <SectionTitle
            eyebrow="By tool"
            title="Provisioning status across the AI stack"
            description="Stacked share of run states per tool. Tools with the least readiness float to the top."
            trailing={<span className="text-xs text-muted">{ONBOARDING_TOOLS.length} integrations</span>}
          />
          <div className="mt-4 space-y-2.5">
            {toolBreakdown.map((row) => (
              <div key={row.tool} className="flex items-center gap-3">
                <div className="w-24 shrink-0 text-xs font-medium text-body">{row.tool}</div>
                <div className="flex h-5 flex-1 overflow-hidden rounded-md bg-sunken">
                  {stackOrder.map((s) => {
                    const n = row.counts?.[s] ?? 0;
                    if (n === 0) return null;
                    return (
                      <div
                        key={s}
                        title={`${provisionMeta(s).label}: ${n}`}
                        className="h-full"
                        style={{ width: `${(n / (row.total || 1)) * 100}%`, backgroundColor: provisionMeta(s).dot }}
                      />
                    );
                  })}
                </div>
                <div className="w-14 shrink-0 text-right text-xs font-semibold tabular-nums text-ink">
                  {row.ready}/{row.total}
                </div>
              </div>
            ))}
          </div>
        </Surface>
      </div>

      {/* Onboarding runs table */}
      <Surface pad="none">
        <div className="p-5">
          <SectionTitle
            eyebrow="Active runs"
            title="New-hire onboarding runs"
            description="Provisioning progress, verification gates, and estimated time-to-productive per hire. Select a row to inspect its checklist."
            trailing={<span className="text-xs text-muted">{runs.length} runs</span>}
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[940px] border-t border-line text-sm">
            <thead>
              <tr className="bg-sunken text-left text-2xs uppercase tracking-eyebrow text-muted">
                <th className="px-5 py-2 font-medium">New hire</th>
                <th className="px-3 py-2 font-medium">Start</th>
                <th className="px-3 py-2 font-medium">Provisioning</th>
                <th className="px-3 py-2 font-medium">Verification gates</th>
                <th className="px-3 py-2 text-right font-medium">TTP</th>
                <th className="px-5 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {runs.map((r) => {
                const pct = onboardingProgress(r);
                const isSel = selected?.id === r.id;
                return (
                  <tr
                    key={r.id}
                    onClick={() => setSelectedId(r.id)}
                    className={`cursor-pointer transition-colors duration-150 ease-calm hover:bg-sunken/60 ${
                      isSel ? "bg-sunken" : ""
                    }`}
                  >
                    <td className="px-5 py-3">
                      <div className="font-medium text-ink">{r.newHire}</div>
                      <div className="text-xs text-muted">{r.role} · {r.department}</div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-xs text-muted">
                      {fmtDate(r.startDate)}
                      <span className="ml-1 text-2xs">· {daysSince(r.startDate)}d ago</span>
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2">
                        <span className="w-9 text-xs font-semibold tabular-nums text-ink">{pct}%</span>
                        <div className="w-28">
                          <ProgressBar value={pct} color={scoreColor(pct)} />
                        </div>
                      </div>
                      <div className="mt-1.5">
                        <ProvisionDots tools={r.tools} />
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <VerificationGates v={r.verifications} />
                    </td>
                    <td className="px-3 py-3 text-right">
                      <span
                        className="inline-flex h-6 min-w-[2.5rem] items-center justify-center rounded-md px-2 text-xs font-semibold tabular-nums text-white"
                        style={{ backgroundColor: ttpColor(r.timeToProductiveDays) }}
                      >
                        {r.timeToProductiveDays}d
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <Pill tone={runStatusMeta(r.status).tone}>{runStatusMeta(r.status).label}</Pill>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Surface>

      {/* Selected run detail: provisioning checklist + gates + what-if */}
      {selected && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.5fr_1fr]">
          <Surface>
            <SectionTitle
              eyebrow="Provisioning checklist"
              title={`${selected.newHire} · ${selected.role}`}
              description={`${selected.department} · started ${fmtDate(selected.startDate)} · ${onboardingProgress(
                selected
              )}% of the stack provisioned`}
              trailing={<Pill tone={runStatusMeta(selected.status).tone}>{runStatusMeta(selected.status).label}</Pill>}
            />
            <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {(selected.tools ?? []).map((t) => {
                const meta = provisionMeta(t?.status);
                return (
                  <div
                    key={t?.tool}
                    className="flex items-center justify-between gap-3 rounded-lg border border-line bg-canvas px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: meta.dot }} />
                      <span className="text-sm font-medium text-ink">{t?.tool}</span>
                    </div>
                    <Pill tone={meta.tone}>{meta.label}</Pill>
                  </div>
                );
              })}
            </div>
          </Surface>

          <div className="space-y-4">
            <Surface>
              <SectionTitle
                eyebrow="Security gates"
                title="Verification status"
                description="All four gates must pass before the hire is cleared as productive."
              />
              <ul className="mt-4 space-y-2">
                {VERIFICATION_META.map((g) => {
                  const ok = selected.verifications?.[g.key];
                  return (
                    <li
                      key={g.key}
                      className="flex items-center justify-between gap-3 rounded-lg border border-line bg-canvas px-3 py-2"
                    >
                      <div>
                        <div className="text-sm font-medium text-ink">{g.label}</div>
                        <div className="text-2xs text-muted">{g.blurb}</div>
                      </div>
                      <span
                        className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-semibold ${
                          ok
                            ? "border-success-line bg-success-bg text-success-fg"
                            : "border-danger-line bg-danger-bg text-danger-fg"
                        }`}
                      >
                        {ok ? "✓ Passed" : "✕ Blocked"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </Surface>

            <Surface>
              <SectionTitle
                eyebrow="What-if"
                title="Automation lever"
                description="Project time-to-productive as provisioning automation coverage increases."
              />
              <div className="mt-4">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs font-medium text-body">Extra automation</span>
                  <span className="text-xs font-semibold tabular-nums text-ink">+{autoBoost}%</span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={60}
                  step={5}
                  value={autoBoost}
                  onChange={(e) => setAutoBoost(Number(e.target.value))}
                  className="mt-2 w-full accent-[#0F766E]"
                  aria-label="Extra automation coverage"
                />
                <div className="mt-4 flex items-end justify-between rounded-lg border border-line bg-canvas px-4 py-3">
                  <div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">Baseline TTP</div>
                    <div className="text-lg font-semibold tabular-nums text-muted line-through">
                      {Number(selected.timeToProductiveDays) || 0}d
                    </div>
                  </div>
                  <span className="pb-1 text-muted" aria-hidden>→</span>
                  <div className="text-right">
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">Projected</div>
                    <div
                      className="text-2xl font-semibold tabular-nums"
                      style={{ color: ttpColor(projectedTtp) }}
                    >
                      {projectedTtp}d
                    </div>
                  </div>
                </div>
                {(() => {
                  const saved = Math.max(0, (Number(selected.timeToProductiveDays) || 0) - projectedTtp);
                  return (
                    <p className="mt-2 text-2xs text-muted">
                      Estimated savings of {saved} day{saved === 1 ? "" : "s"} ≈{" "}
                      {usd(saved * 850)} in ramp cost per hire.
                    </p>
                  );
                })()}
              </div>
            </Surface>
          </div>
        </div>
      )}
    </div>
  );
}
