"use client";
/**
 * Human + AI Workforce Registry — a single, unified registry of the WHOLE
 * workforce: employees, contractors, AI agents, and bots in one governed
 * table with a kind badge, lifecycle, approval state, cost, permissions,
 * capabilities, and audit volume.
 *
 * Built as an enterprise AI-economy operating dashboard (Ramp / Vanta /
 * Datadog / Brex energy) — NOT a chatbot. Renders entirely from deterministic
 * mock data + helpers in "@/lib/aiWorkforce2"; no backend, no Math.random.
 */
import { useMemo, useState } from "react";
import {
  WORKFORCE_MEMBERS,
  WORKFORCE_SUMMARY,
  scoreColor,
  type WorkforceMember,
  type WorkforceKind,
  type LifecycleStatus,
  type ApprovalStatus,
} from "@/lib/aiWorkforce2";
import { useLiveData } from "@/lib/useLiveData";
import { PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";

// ---------------------------------------------------------------------------
// Live-data normalization (raw DB row -> WorkforceMember the UI renders)
// ---------------------------------------------------------------------------

const VALID_KINDS: ReadonlyArray<WorkforceKind> = ["human", "contractor", "agent", "bot"];
const VALID_LIFECYCLE: ReadonlyArray<LifecycleStatus> = ["active", "pending_approval", "retired"];
const VALID_APPROVAL: ReadonlyArray<ApprovalStatus> = ["approved", "pending", "rejected", "n/a"];

/** Coerce any value to a finite number (handles numeric strings from numeric cols). */
function toNum(v: unknown): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** Coerce any value to a trimmed string ('' for null/undefined/objects). */
function toStr(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  return "";
}

/**
 * Coerce a jsonb/array/string field into a string[]. The live column defaults
 * to `'{}'` (an object) and may arrive as a JSON string, a real array, a
 * Postgres `{a,b}` array literal, or an object of values — none of which the
 * UI's `.slice/.join/.length` calls can assume. We normalize all of them.
 */
function toStrArray(v: unknown): string[] {
  if (v == null) return [];
  if (Array.isArray(v)) return v.map(toStr).filter(Boolean);
  if (typeof v === "string") {
    const s = v.trim();
    if (s === "" || s === "{}" || s === "[]") return [];
    try {
      const parsed = JSON.parse(s);
      if (parsed !== s) return toStrArray(parsed);
    } catch {
      /* not JSON — fall through to literal/CSV handling */
    }
    // Postgres array literal like `{a,b,c}` or a plain comma list.
    const inner = s.startsWith("{") && s.endsWith("}") ? s.slice(1, -1) : s;
    return inner
      .split(",")
      .map((p) => toStr(p).replace(/^"|"$/g, "").trim())
      .filter(Boolean);
  }
  if (typeof v === "object") return Object.values(v as Record<string, unknown>).map(toStr).filter(Boolean);
  return [];
}

function asKind(v: unknown): WorkforceKind {
  const s = toStr(v).toLowerCase();
  return (VALID_KINDS as ReadonlyArray<string>).includes(s) ? (s as WorkforceKind) : "agent";
}

function asLifecycle(v: unknown): LifecycleStatus {
  const s = toStr(v).toLowerCase();
  return (VALID_LIFECYCLE as ReadonlyArray<string>).includes(s) ? (s as LifecycleStatus) : "active";
}

function asApproval(v: unknown): ApprovalStatus {
  const s = toStr(v).toLowerCase();
  return (VALID_APPROVAL as ReadonlyArray<string>).includes(s) ? (s as ApprovalStatus) : "n/a";
}

/**
 * Normalize one raw live row (snake_case DB columns) into the camelCase
 * `WorkforceMember` shape the page renders. Accepts the mock shape unchanged
 * (camelCase keys win when present) so this is safe on either input. Fills
 * every field the UI touches with a safe default — no access is ever on
 * undefined, and every metadata-lookup key is guaranteed valid.
 */
function normalizeMember(r: any, i = 0): WorkforceMember {
  const row = r ?? {};
  return {
    id: toStr(row.id) || `wf_live_${i}`,
    kind: asKind(row.kind),
    name: toStr(row.name) || "Unnamed worker",
    // mock: `role`; live: `title`
    role: toStr(row.role ?? row.title),
    department: toStr(row.department),
    owner: toStr(row.owner) || undefined,
    // mock: `modelProvider`; live: `model_provider`
    modelProvider: toStr(row.modelProvider ?? row.model_provider) || undefined,
    // mock: `monthlyCostUsd`; live: `monthly_cost_usd` (numeric col -> may be string)
    monthlyCostUsd: toNum(row.monthlyCostUsd ?? row.monthly_cost_usd),
    // jsonb defaulting to `{}` — coerce to string[]
    permissions: toStrArray(row.permissions),
    capabilities: toStrArray(row.capabilities),
    // mock: `lifecycleStatus`; live: `lifecycle_status`
    lifecycleStatus: asLifecycle(row.lifecycleStatus ?? row.lifecycle_status),
    // mock: `approvalStatus`; live: `approval_status`
    approvalStatus: asApproval(row.approvalStatus ?? row.approval_status),
    // mock: `auditCount`; live: NO such column -> default 0
    auditCount: toNum(row.auditCount ?? row.audit_count),
    // mock: `lastActive`; live: `last_active` (timestamptz)
    lastActive: toStr(row.lastActive ?? row.last_active),
  };
}

// ---------------------------------------------------------------------------
// Presentation helpers (color/label decisions live here; data lives in lib)
// ---------------------------------------------------------------------------

const usd = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

const num = (n: number) => n.toLocaleString("en-US");

function fmtWhen(iso: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// Kind metadata: badge tone + accent color used across rings and chips.
const KIND_META: Record<
  WorkforceKind,
  { label: string; glyph: string; tone: "info" | "neutral" | "accent" | "warn"; color: string }
> = {
  human: { label: "Employee", glyph: "◉", tone: "info", color: "#0EA5E9" },
  contractor: { label: "Contractor", glyph: "◑", tone: "neutral", color: "#475569" },
  agent: { label: "AI Agent", glyph: "✦", tone: "accent", color: "#0F766E" },
  bot: { label: "Bot", glyph: "⬡", tone: "warn", color: "#D97706" },
};

const LIFECYCLE_META: Record<
  LifecycleStatus,
  { label: string; tone: "success" | "warn" | "neutral"; dot: string }
> = {
  active: { label: "Active", tone: "success", dot: "#16A34A" },
  pending_approval: { label: "Pending approval", tone: "warn", dot: "#D97706" },
  retired: { label: "Retired", tone: "neutral", dot: "#94A3B8" },
};

const APPROVAL_META: Record<ApprovalStatus, { label: string; tone: "success" | "warn" | "danger" | "neutral" }> = {
  approved: { label: "Approved", tone: "success" },
  pending: { label: "Pending", tone: "warn" },
  rejected: { label: "Rejected", tone: "danger" },
  "n/a": { label: "N/A", tone: "neutral" },
};

const KIND_ORDER: ReadonlyArray<WorkforceKind> = ["human", "contractor", "agent", "bot"];
type KindFilter = "all" | WorkforceKind;

// Safe metadata accessors — fall back to a neutral entry if an unexpected key
// ever slips through (e.g. a live row with an out-of-enum status), so a lookup
// never resolves to undefined and crashes on `.tone`/`.label`/`.color`.
const kindMeta = (k: WorkforceKind) => KIND_META[k] ?? KIND_META.agent;
const lifecycleMeta = (s: LifecycleStatus) => LIFECYCLE_META[s] ?? LIFECYCLE_META.active;
const approvalMeta = (s: ApprovalStatus) => APPROVAL_META[s] ?? APPROVAL_META["n/a"];

function KindBadge({ kind }: { kind: WorkforceKind }) {
  const m = kindMeta(kind);
  return (
    <Pill tone={m.tone}>
      <span aria-hidden style={{ color: m.color }}>
        {m.glyph}
      </span>
      {m.label}
    </Pill>
  );
}

// Stacked horizontal bar of cost (or count) split by kind ---------------------
function StackedBar({
  segments,
  height = 10,
}: {
  segments: { key: WorkforceKind; value: number }[];
  height?: number;
}) {
  const total = (segments ?? []).reduce((s, x) => s + (Number(x.value) || 0), 0) || 1;
  return (
    <div className="flex w-full overflow-hidden rounded-full bg-sunken" style={{ height }}>
      {(segments ?? []).map((s) => (
        <div
          key={s.key}
          title={`${kindMeta(s.key).label}: ${Math.round(((Number(s.value) || 0) / total) * 100)}%`}
          style={{ width: `${((Number(s.value) || 0) / total) * 100}%`, backgroundColor: kindMeta(s.key).color }}
        />
      ))}
    </div>
  );
}

// Compute-cost composition donut (inline SVG, no chart lib) -------------------
function CostDonut({ segments, size = 132 }: { segments: { key: WorkforceKind; value: number }[]; size?: number }) {
  const stroke = 16;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const total = (segments ?? []).reduce((s, x) => s + (Number(x.value) || 0), 0) || 1;
  let offset = 0;
  return (
    <svg width={size} height={size} className="-rotate-90">
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E2E8F0" strokeWidth={stroke} />
      {(segments ?? []).map((s) => {
        const frac = (Number(s.value) || 0) / total;
        const dash = frac * c;
        const el = (
          <circle
            key={s.key}
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={kindMeta(s.key).color}
            strokeWidth={stroke}
            strokeDasharray={`${dash} ${c - dash}`}
            strokeDashoffset={-offset}
          />
        );
        offset += dash;
        return el;
      })}
    </svg>
  );
}

// Small 0-100 governance ring (audit / approval coverage) ---------------------
function MeterRing({ value, label, size = 92 }: { value: number; label: string; size?: number }) {
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value)) / 100;
  return (
    <div className="flex flex-col items-center gap-1">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#E2E8F0" strokeWidth={stroke} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={scoreColor(value)}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            strokeDashoffset={c * (1 - pct)}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-lg font-semibold tabular-nums text-ink">{value}%</span>
        </div>
      </div>
      <span className="text-2xs uppercase tracking-eyebrow text-muted">{label}</span>
    </div>
  );
}

function TrendChip({ dir, text }: { dir: "up" | "down" | "flat"; text: string }) {
  const map = {
    up: { glyph: "▲", cls: "text-[#16A34A]" },
    down: { glyph: "▼", cls: "text-[#DC2626]" },
    flat: { glyph: "▬", cls: "text-muted" },
  } as const;
  const t = map[dir];
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${t.cls}`}>
      <span aria-hidden>{t.glyph}</span>
      {text}
    </span>
  );
}

// Executive KPI stat card -----------------------------------------------------
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
  tone?: "neutral" | "success" | "warn" | "danger" | "accent";
}) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
    accent: "ring-1 ring-line",
  };
  return (
    <div className={`rounded-xl border border-line bg-surface p-4 shadow-soft ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-ink">{value}</div>
      <div className="mt-1 flex items-center gap-2">
        {trend && <TrendChip dir={trend.dir} text={trend.text} />}
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function WorkforceRegistryPage() {
  const [filter, setFilter] = useState<KindFilter>("all");

  // Workforce rows: LIVE data with deterministic mock fallback. The hook
  // returns the mock until live data resolves, then swaps in live rows.
  //
  // The live endpoint (/ai-workforce/registry) returns RAW DB ROWS from
  // `workforce_registry` (snake_case columns; jsonb permissions/capabilities
  // that may arrive as a JSON string, an object default `{}`, or an array; no
  // auditCount column at all). The mock, by contrast, is the camelCase
  // `WorkforceMember` shape the UI renders. The `pick` mapper below NORMALIZES
  // each live row into that exact shape so no property access is ever on
  // undefined and every metadata lookup key is valid.
  const { data: members, live: isLive } = useLiveData<WorkforceMember[]>(
    "/ai-workforce/registry",
    // Spread: the constant is `readonly` and the hook holds it in state, which
    // is a mutable slot.
    [...WORKFORCE_MEMBERS],
    (j) => {
      const raw = Array.isArray(j) ? j : j?.registry ?? j?.rows ?? j?.data ?? [];
      const list: any[] = Array.isArray(raw) ? raw : [];
      return list.map(normalizeMember);
    }
  );

  // Org-wide rollups from the imported summary + raw rows.
  const stats = useMemo(() => {
    const list = members ?? [];
    const agents = list.filter((m) => m?.kind === "agent");
    const aiMembers = list.filter((m) => m?.kind === "agent" || m?.kind === "bot");
    const humanCost = list.filter((m) => m?.kind === "human" || m?.kind === "contractor").reduce(
      (s, m) => s + (Number(m?.monthlyCostUsd) || 0),
      0
    );
    const agentMonthlyCost = agents.reduce((s, m) => s + (Number(m?.monthlyCostUsd) || 0), 0);
    const pendingAgents = agents.filter(
      (m) => m?.lifecycleStatus === "pending_approval" || m?.approvalStatus === "pending"
    );
    const totalAudits = list.reduce((s, m) => s + (Number(m?.auditCount) || 0), 0);
    const aiAudits = aiMembers.reduce((s, m) => s + (Number(m?.auditCount) || 0), 0);
    // Governance coverage: share of AI workforce that is approved & active-or-retired (not awaiting sign-off).
    const govApproved = aiMembers.filter((m) => m?.approvalStatus === "approved").length;
    const govCoverage = Math.round((govApproved / (aiMembers.length || 1)) * 100);
    const auditCoverage = Math.round((aiAudits / (totalAudits || 1)) * 100);
    // Human work fully automatable cost-equivalent: AI cost as % of total spend.
    const aiCostShare = Math.round(
      ((Number(WORKFORCE_SUMMARY.aiMonthlyCostUsd) || 0) / (Number(WORKFORCE_SUMMARY.monthlyCostUsd) || 1)) * 100
    );
    return {
      agents,
      aiMembers,
      humanCost,
      agentMonthlyCost,
      pendingAgents,
      totalAudits,
      aiAudits,
      govCoverage,
      auditCoverage,
      aiCostShare,
    };
  }, [members]);

  // Cost composition per kind (for donut + stacked bar + legend).
  const costByKind = useMemo(
    () =>
      KIND_ORDER.map((kind) => ({
        key: kind,
        value: WORKFORCE_SUMMARY.byKind.find((b) => b.kind === kind)?.monthlyCostUsd ?? 0,
        count: WORKFORCE_SUMMARY.byKind.find((b) => b.kind === kind)?.count ?? 0,
      })),
    []
  );

  // Filtered + ordered roster: humans, contractors, agents, bots; within kind,
  // pending approvals float to the top, then by monthly cost desc.
  const rows = useMemo(() => {
    const kindRank: Record<WorkforceKind, number> = { human: 0, contractor: 1, agent: 2, bot: 3 };
    return [...(members ?? [])]
      .filter((m) => (filter === "all" ? true : m?.kind === filter))
      .sort((a, b) => {
        if (a.kind !== b.kind) return (kindRank[a.kind] ?? 99) - (kindRank[b.kind] ?? 99);
        const ap = a.approvalStatus === "pending" ? 0 : 1;
        const bp = b.approvalStatus === "pending" ? 0 : 1;
        if (ap !== bp) return ap - bp;
        return (Number(b.monthlyCostUsd) || 0) - (Number(a.monthlyCostUsd) || 0);
      });
  }, [filter, members]);

  // Pending-approval queue (agents + bots awaiting sign-off) — action panel.
  const approvalQueue = useMemo(
    () =>
      (members ?? []).filter(
        (m) =>
          (m?.kind === "agent" || m?.kind === "bot") &&
          (m?.lifecycleStatus === "pending_approval" || m?.approvalStatus === "pending")
      ),
    [members]
  );

  const totalMonthly = WORKFORCE_SUMMARY.monthlyCostUsd;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="People · AI Workforce Operations"
        title="Human + AI Workforce Registry"
        subtitle="One governed registry for the entire workforce — employees, contractors, AI agents, and bots — with ownership, cost, permissions, capabilities, approval workflow, and audit trail in a single source of truth."
        actions={
          <div className="flex items-center gap-2">
            <Pill tone={isLive ? "success" : "neutral"}>{isLive ? "Live" : "Sample"}</Pill>
            <Pill tone="info">{WORKFORCE_SUMMARY.activeCount} active</Pill>
            <Pill tone="accent">{stats.aiMembers.length} AI workers</Pill>
            {stats.pendingAgents.length > 0 && (
              <Pill tone="warn">{stats.pendingAgents.length} pending</Pill>
            )}
          </div>
        }
      />

      {/* Executive KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-5">
        <Kpi
          label="Total workforce"
          value={num(WORKFORCE_SUMMARY.headcount)}
          trend={{ dir: "up", text: `${WORKFORCE_SUMMARY.activeCount} active` }}
          hint={`${stats.aiMembers.length} non-human`}
        />
        <Kpi
          label="AI agents"
          value={num(stats.agents.length)}
          tone="accent"
          trend={{ dir: "up", text: "+1 / 30d" }}
          hint={`${WORKFORCE_SUMMARY.byKind.find((b) => b.kind === "bot")?.count ?? 0} bots`}
        />
        <Kpi
          label="Monthly AI agent cost"
          value={usd(stats.agentMonthlyCost)}
          hint={`${stats.aiCostShare}% of total spend`}
          trend={{ dir: "down", text: "-6% vs human/hr" }}
        />
        <Kpi
          label="Agents pending approval"
          value={num(stats.pendingAgents.length)}
          tone={stats.pendingAgents.length > 0 ? "warn" : "success"}
          hint={stats.pendingAgents.length > 0 ? "needs sign-off" : "all cleared"}
        />
        <Kpi
          label="AI audit events"
          value={num(stats.aiAudits)}
          hint={`${stats.auditCoverage}% of all audit volume`}
          trend={{ dir: "up", text: "logged" }}
        />
      </div>

      {/* Composition: donut + stacked bars + governance rings */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.3fr_1fr]">
        <Surface>
          <SectionTitle
            eyebrow="Cost composition"
            title="Monthly workforce spend by kind"
            description="Fully-loaded monthly cost split across humans, contractors, AI agents, and bots. AI labor is now a managed line item alongside payroll."
            trailing={<span className="text-xs text-muted">{usd(totalMonthly)} / mo</span>}
          />
          <div className="mt-4 grid grid-cols-1 gap-6 sm:grid-cols-[auto_1fr] sm:items-center">
            <div className="relative mx-auto flex items-center justify-center">
              <CostDonut segments={costByKind.map((c) => ({ key: c.key, value: c.value }))} />
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <span className="text-lg font-semibold tabular-nums text-ink">{usd(totalMonthly)}</span>
                <span className="text-2xs uppercase tracking-eyebrow text-muted">total / mo</span>
              </div>
            </div>
            <div className="space-y-3">
              {costByKind.map((c) => {
                const share = Math.round((c.value / (totalMonthly || 1)) * 100);
                return (
                  <div key={c.key}>
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="flex items-center gap-2 text-xs font-medium text-body">
                        <span
                          aria-hidden
                          className="inline-block h-2.5 w-2.5 rounded-sm"
                          style={{ backgroundColor: kindMeta(c.key).color }}
                        />
                        {kindMeta(c.key).label}
                        <span className="text-muted">· {c.count}</span>
                      </span>
                      <span className="text-xs font-semibold tabular-nums text-ink">
                        {usd(c.value)} <span className="text-muted">· {share}%</span>
                      </span>
                    </div>
                    <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-sunken">
                      <div
                        className="h-full rounded-full"
                        style={{ width: `${Math.max(2, share)}%`, backgroundColor: kindMeta(c.key).color }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </Surface>

        <Surface>
          <SectionTitle
            eyebrow="Governance posture"
            title="AI workforce control coverage"
            description="Approval, audit, and headcount-mix coverage across the non-human workforce."
            trailing={<Pill tone="success">monitored</Pill>}
          />
          <div className="mt-5 flex items-center justify-around">
            <MeterRing value={stats.govCoverage} label="Approved" />
            <MeterRing value={stats.auditCoverage} label="AI audit share" />
            <MeterRing value={stats.aiCostShare} label="AI cost share" />
          </div>
          <div className="mt-5">
            <div className="mb-1 flex items-center justify-between text-2xs uppercase tracking-eyebrow text-muted">
              <span>Headcount mix</span>
              <span>{WORKFORCE_SUMMARY.headcount} total</span>
            </div>
            <StackedBar segments={costByKind.map((c) => ({ key: c.key, value: c.count }))} />
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
              {costByKind.map((c) => (
                <span key={c.key} className="flex items-center gap-1.5 text-2xs text-muted">
                  <span
                    aria-hidden
                    className="inline-block h-2 w-2 rounded-sm"
                    style={{ backgroundColor: kindMeta(c.key).color }}
                  />
                  {kindMeta(c.key).label} {c.count}
                </span>
              ))}
            </div>
          </div>
        </Surface>
      </div>

      {/* Approval queue (action panel) */}
      {approvalQueue.length > 0 && (
        <Surface className="border-warn-line bg-warn-bg/40">
          <SectionTitle
            eyebrow="Action queue"
            title="AI workers awaiting approval"
            description="New agents and bots are blocked from production scopes until an owner-accountable approval clears governance review."
            trailing={<Pill tone="warn">{approvalQueue.length} pending</Pill>}
          />
          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
            {approvalQueue.map((m) => (
              <div key={m.id} className="rounded-xl border border-line bg-surface p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <KindBadge kind={m.kind} />
                      <span className="truncate text-sm font-semibold text-ink">{m.name}</span>
                    </div>
                    <div className="mt-1 text-xs text-muted">
                      {m.role} · {m.department}
                      {m.owner ? ` · owner ${m.owner}` : ""}
                    </div>
                  </div>
                  <Pill tone={approvalMeta(m.approvalStatus).tone}>{approvalMeta(m.approvalStatus).label}</Pill>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted">
                  <span className="tabular-nums">{usd(Number(m.monthlyCostUsd) || 0)}/mo</span>
                  {m.modelProvider && <span className="font-mono text-2xs text-body">{m.modelProvider}</span>}
                  <span className="tabular-nums">{num(Number(m.auditCount) || 0)} audits</span>
                </div>
              </div>
            ))}
          </div>
        </Surface>
      )}

      {/* Unified registry table */}
      <Surface pad="none">
        <div className="flex flex-wrap items-end justify-between gap-3 p-5">
          <SectionTitle
            eyebrow="Unified registry"
            title="The whole workforce, one table"
            description="Every employee, contractor, AI agent, and bot — with owner, department, model provider, cost, permissions, capabilities, approval state, audit count, and lifecycle."
          />
          {/* Interactive filter control — live React-state recompute */}
          <div className="flex flex-wrap items-center gap-1.5">
            {(["all", ...KIND_ORDER] as KindFilter[]).map((k) => {
              const active = filter === k;
              const label =
                k === "all"
                  ? `All · ${members?.length ?? 0}`
                  : `${kindMeta(k).label} · ${WORKFORCE_SUMMARY.byKind.find((b) => b.kind === k)?.count ?? 0}`;
              return (
                <button
                  key={k}
                  onClick={() => setFilter(k)}
                  className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150 ease-calm ${
                    active
                      ? "border-ink/30 bg-ink text-white"
                      : "border-line bg-surface text-body hover:bg-sunken"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1180px] border-t border-line text-sm">
            <thead>
              <tr className="bg-sunken text-left text-2xs uppercase tracking-eyebrow text-muted">
                <th className="px-5 py-2 font-medium">Worker</th>
                <th className="px-3 py-2 font-medium">Kind</th>
                <th className="px-3 py-2 font-medium">Owner · Dept</th>
                <th className="px-3 py-2 font-medium">Model provider</th>
                <th className="px-3 py-2 text-right font-medium">Monthly cost</th>
                <th className="px-3 py-2 font-medium">Permissions</th>
                <th className="px-3 py-2 font-medium">Capabilities</th>
                <th className="px-3 py-2 font-medium">Approval</th>
                <th className="px-3 py-2 text-right font-medium">Audits</th>
                <th className="px-5 py-2 font-medium">Lifecycle</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.map((m) => (
                <RegistryRow key={m.id} m={m} />
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-5 py-10 text-center text-sm text-muted">
                    No workers match this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line px-5 py-3 text-xs text-muted">
          <span>
            {rows.length} of {members?.length ?? 0} workers
            {filter !== "all" ? ` · filtered to ${kindMeta(filter).label}s` : ""}
          </span>
          <span className="tabular-nums">
            {usd(rows.reduce((s, m) => s + (Number(m?.monthlyCostUsd) || 0), 0))}/mo combined ·{" "}
            {num(rows.reduce((s, m) => s + (Number(m?.auditCount) || 0), 0))} audit events
          </span>
        </div>
      </Surface>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Registry row
// ---------------------------------------------------------------------------

function RegistryRow({ m }: { m: WorkforceMember }) {
  const isAi = m.kind === "agent" || m.kind === "bot";
  const life = lifecycleMeta(m.lifecycleStatus);
  const approval = approvalMeta(m.approvalStatus);
  const kindM = kindMeta(m.kind);
  const permissions = (m.permissions ?? []) as ReadonlyArray<string>;
  const capabilities = (m.capabilities ?? []) as ReadonlyArray<string>;
  return (
    <tr className="align-top hover:bg-sunken/60">
      {/* Worker */}
      <td className="px-5 py-3">
        <div className="flex items-start gap-2.5">
          <span
            aria-hidden
            className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-sm"
            style={{ backgroundColor: `${kindM.color}1A`, color: kindM.color }}
          >
            {kindM.glyph}
          </span>
          <div className="min-w-0">
            <div className="font-medium text-ink">{m.name}</div>
            <div className="text-xs text-muted">{m.role}</div>
            <div className="mt-0.5 text-2xs text-muted">active {fmtWhen(m.lastActive)}</div>
          </div>
        </div>
      </td>

      {/* Kind */}
      <td className="px-3 py-3">
        <KindBadge kind={m.kind} />
      </td>

      {/* Owner · Dept */}
      <td className="px-3 py-3">
        <div className="text-ink">{m.owner ?? <span className="text-muted">—</span>}</div>
        <div className="text-xs text-muted">{m.department}</div>
      </td>

      {/* Model provider */}
      <td className="px-3 py-3">
        {m.modelProvider ? (
          <span className="rounded-md border border-line bg-surface px-1.5 py-0.5 font-mono text-2xs text-body">
            {m.modelProvider}
          </span>
        ) : (
          <span className="text-xs text-muted">{isAi ? "internal" : "—"}</span>
        )}
      </td>

      {/* Monthly cost */}
      <td className="px-3 py-3 text-right tabular-nums text-body">{usd(Number(m.monthlyCostUsd) || 0)}</td>

      {/* Permissions */}
      <td className="px-3 py-3">
        <div className="flex max-w-[180px] flex-wrap gap-1">
          {permissions.slice(0, 3).map((p) => (
            <span
              key={p}
              className="rounded-md border border-line bg-sunken px-1.5 py-0.5 font-mono text-2xs text-body"
            >
              {p}
            </span>
          ))}
          {permissions.length > 3 && (
            <span className="rounded-md px-1 py-0.5 text-2xs text-muted">+{permissions.length - 3}</span>
          )}
        </div>
      </td>

      {/* Capabilities */}
      <td className="px-3 py-3">
        <div className="max-w-[220px] text-xs text-body">
          {capabilities.slice(0, 3).join(" · ")}
          {capabilities.length > 3 && <span className="text-muted"> · +{capabilities.length - 3}</span>}
        </div>
      </td>

      {/* Approval */}
      <td className="px-3 py-3">
        <Pill tone={approval.tone}>{approval.label}</Pill>
      </td>

      {/* Audits */}
      <td className="px-3 py-3 text-right tabular-nums text-body">{num(Number(m.auditCount) || 0)}</td>

      {/* Lifecycle */}
      <td className="px-5 py-3">
        <span className="inline-flex items-center gap-1.5">
          <span aria-hidden className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: life.dot }} />
          <Pill tone={life.tone}>{life.label}</Pill>
        </span>
      </td>
    </tr>
  );
}
