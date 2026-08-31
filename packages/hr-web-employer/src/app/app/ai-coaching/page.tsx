"use client";
/**
 * Employee AI Coaching — per-employee Workforce AI Proficiency coaching view.
 *
 * Mirrors the CubeBench "4 D's" proficiency model: score breakdown, AI session
 * history, targeted coaching suggestions, manager notes, and an org leaderboard
 * of top performers vs. employees who need support. Fully client-side; all data
 * and scoring come from "@/lib/workforceAi".
 */
import { useMemo, useState } from "react";
import { downloadCsv } from "@/lib/exportRows";
import {
  Action,
  EmptyState,
  MetricStat,
  PageHeader,
  Pill,
  SectionTitle,
  StatusPill,
  Surface,
} from "@/components/ds";
import {
  AI_SESSIONS,
  COACHING_SUGGESTIONS,
  EMPLOYEES,
  EMPLOYEE_PROFICIENCY,
  FOUR_D_WEIGHTS,
  NEEDS_SUPPORT,
  TOP_PERFORMERS,
  clamp100,
  coachingForEmployee,
  getEmployee,
  getProficiency,
  notesForEmployee,
  scoreBand,
  scoreColor,
  sessionsForEmployee,
  type AiSession,
  type CoachingSuggestion,
  type Employee,
  type EmployeeAiProficiency,
  type FourDs,
  type ManagerNote,
  type ScoreBand,
  type Severity,
  type Trend,
} from "@/lib/workforceAi";
import { useLiveData } from "@/lib/useLiveData";

// ---------------------------------------------------------------------------
// Live data adapter
// ---------------------------------------------------------------------------

// Coerce any incoming value (number | numeric-string | null | undefined) to a
// finite number, defaulting to `fallback` (0) on NaN/missing.
function num(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

const VALID_TRENDS: ReadonlyArray<Trend> = ["up", "down", "flat"];
function asTrend(v: unknown): Trend {
  return VALID_TRENDS.includes(v as Trend) ? (v as Trend) : "flat";
}

// Map a flat live proficiency row ({ employee_id, delegation, ..., ai_cost_usd })
// into the nested EmployeeAiProficiency shape this page renders from. The live
// API returns RAW DB ROWS (snake_case columns, numeric fields as strings, no
// nested `scores`, no `trend`), so every field is normalized + defaulted here
// so no downstream property access is ever on undefined / a wrong type.
function adaptProficiency(rows: any): EmployeeAiProficiency[] {
  const list = Array.isArray(rows) ? rows : [];
  return list.map((r): EmployeeAiProficiency => {
    const src = r ?? {};
    const nested = src.scores ?? {};
    const scores: FourDs = {
      delegation: num(src.delegation ?? nested.delegation),
      description: num(src.description ?? nested.description),
      discernment: num(src.discernment ?? nested.discernment),
      diligence: num(src.diligence ?? nested.diligence),
    };
    const overall =
      src.overall != null
        ? num(src.overall)
        : Math.round(
            (scores.delegation + scores.description + scores.discernment + scores.diligence) / 4,
          );
    return {
      employeeId: String(src.employee_id ?? src.employeeId ?? ""),
      scores,
      overall,
      aiCostUsd: num(src.ai_cost_usd ?? src.aiCostUsd),
      sessions: num(src.sessions),
      trend: asTrend(src.trend),
    };
  });
}

// Resolve an employee for a proficiency row. Live rows carry DB UUIDs that may
// not exist in the mock EMPLOYEES roster, so synthesize a safe placeholder
// (using any name/team/role the live row happens to include) instead of
// returning undefined and crashing on `.name`.
function resolveEmployee(p: { employeeId: string } & Record<string, any>): Employee {
  const found = getEmployee(p.employeeId);
  if (found) return found;
  return {
    id: p.employeeId || "unknown",
    name: p.employee_name ?? p.name ?? p.employeeId ?? "Unknown employee",
    team: p.department ?? p.team ?? "—",
    role: p.role ?? "—",
  };
}

// ---------------------------------------------------------------------------
// Tone + label maps
// ---------------------------------------------------------------------------

type Tone = "neutral" | "success" | "warn" | "danger" | "info" | "accent";

const BAND_TONE: Record<ScoreBand, Tone> = {
  strong: "success",
  solid: "info",
  developing: "warn",
  "at-risk": "danger",
};

const BAND_LABEL: Record<ScoreBand, string> = {
  strong: "Strong",
  solid: "Solid",
  developing: "Developing",
  "at-risk": "At risk",
};

const PRIORITY_TONE: Record<Severity, Tone> = {
  low: "neutral",
  medium: "info",
  high: "warn",
  critical: "danger",
};

const DIMENSIONS: ReadonlyArray<{ key: keyof FourDs; label: string; blurb: string }> = [
  { key: "delegation", label: "Delegation", blurb: "Routes the right work to AI" },
  { key: "description", label: "Description", blurb: "Clear, well-scoped prompts" },
  { key: "discernment", label: "Discernment", blurb: "Judges & corrects output" },
  { key: "diligence", label: "Diligence", blurb: "Verifies, sources, owns result" },
];

const DIM_LABEL: Record<keyof FourDs, string> = {
  delegation: "Delegation",
  description: "Description",
  discernment: "Discernment",
  diligence: "Diligence",
};

const TREND_GLYPH: Record<Trend, string> = { up: "▲", down: "▼", flat: "—" };
const TREND_TONE: Record<Trend, Tone> = { up: "success", down: "danger", flat: "neutral" };

function fmtUsd(n: number): string {
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function qualityTone(q: number): Tone {
  if (q >= 85) return "success";
  if (q >= 70) return "info";
  if (q >= 55) return "warn";
  return "danger";
}

// ===========================================================================
// Page
// ===========================================================================

export default function AiCoachingPage() {
  // Live per-employee 4-D proficiency rows, mock-first then live. The live
  // payload uses flat snake_case fields, so adapt it to EmployeeAiProficiency.
  const { data: proficiency, live } = useLiveData(
    "/ai-workforce/proficiency",
    EMPLOYEE_PROFICIENCY,
    (j) => adaptProficiency(j.proficiency || j.rows || j),
  );

  const ranked = useMemo(
    () =>
      [...(proficiency ?? [])].sort(
        (a, b) =>
          (b?.overall ?? 0) - (a?.overall ?? 0) ||
          (a?.employeeId ?? "").localeCompare(b?.employeeId ?? ""),
      ),
    [proficiency],
  );

  const [selectedId, setSelectedId] = useState<string>(
    ranked[0]?.employeeId ?? EMPLOYEES[0]?.id ?? "",
  );

  const employee = getEmployee(selectedId);
  const prof = getProficiency(selectedId);
  const sessions = useMemo(() => sessionsForEmployee(selectedId), [selectedId]);
  const coaching = useMemo(() => coachingForEmployee(selectedId), [selectedId]);
  const notes = useMemo(() => notesForEmployee(selectedId), [selectedId]);

  // Org-level executive summary KPIs.
  const orgAvg = useMemo(() => {
    const list = proficiency ?? [];
    return clamp100(list.reduce((s, p) => s + num(p?.overall), 0) / (list.length || 1));
  }, [proficiency]);
  const openCoaching = (COACHING_SUGGESTIONS ?? []).length;
  const highPriority = (COACHING_SUGGESTIONS ?? []).filter(
    (c) => c.priority === "high" || c.priority === "critical",
  ).length;
  const totalSessions = (AI_SESSIONS ?? []).length;
  const atRiskCount = (proficiency ?? []).filter((p) => num(p?.overall) < 70).length;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="People · Workforce AI"
        title="Employee AI Coaching"
        subtitle="Per-employee proficiency in working with AI — scored across the 4 D's (delegation, description, discernment, diligence). Surfaces session evidence, targeted coaching, and where to invest mentoring."
        actions={
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-2xs font-medium ${
                live
                  ? "bg-[#0F766E]/10 text-[#0F766E]"
                  : "bg-slate-100 text-slate-500"
              }`}
            >
              <span
                className={`inline-block h-1.5 w-1.5 rounded-full ${live ? "bg-[#0F766E]" : "bg-slate-400"}`}
              />
              {live ? "Live" : "Sample data"}
            </span>
            <Action
              variant="subtle"
              size="sm"
              onClick={() =>
                downloadCsv(
                  "ai-coaching-plan.csv",
                  ranked.map((r: any) => ({
                    employee: r.name ?? r.employee_id,
                    team: r.team ?? "",
                    role: r.role ?? "",
                    overall: r.overall,
                    delegation: r.delegation,
                    discernment: r.discernment,
                    diligence: r.diligence,
                    description: r.description,
                  })),
                  {
                    live,
                    note:
                      "Proficiency across the four D's. These are coaching " +
                      "inputs, not a performance rating.",
                  },
                )
              }
            >
              Export coaching plan
            </Action>
          </div>
        }
      />

      {/* Executive summary */}
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
        <MetricStat label="Org proficiency" value={orgAvg} hint="Mean overall · 4 D's" tone="info" />
        <MetricStat label="Employees tracked" value={(proficiency ?? []).length} hint="Across all teams" />
        <MetricStat label="Open coaching items" value={openCoaching} hint={`${highPriority} high priority`} tone={highPriority > 0 ? "warn" : "neutral"} />
        <MetricStat label="Needs support" value={atRiskCount} hint="Below 70 overall" tone={atRiskCount > 0 ? "danger" : "success"} />
        <MetricStat label="AI sessions (30d)" value={totalSessions} hint="Reviewed for quality" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] gap-4">
        {/* Employee roster / selector */}
        <Surface pad="none" className="overflow-hidden self-start">
          <div className="p-4 border-b border-line">
            <SectionTitle eyebrow="Roster" title="Select employee" description="Sorted by overall proficiency." />
          </div>
          <ul className="divide-y divide-line">
            {(ranked ?? []).map((p) => {
              const emp = resolveEmployee(p);
              const active = p.employeeId === selectedId;
              const trend = asTrend(p.trend);
              return (
                <li key={p.employeeId}>
                  <button
                    onClick={() => setSelectedId(p.employeeId)}
                    className={`w-full text-left px-4 py-3 transition-colors ${
                      active ? "bg-sunken" : "hover:bg-sunken/60"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className={`text-sm font-medium truncate ${active ? "text-ink" : "text-body"}`}>
                          {emp.name}
                        </div>
                        <div className="text-xs text-muted truncate">{emp.team}</div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span
                          className="text-sm font-semibold tabular-nums"
                          style={{ color: scoreColor(num(p.overall)) }}
                        >
                          {num(p.overall)}
                        </span>
                        <span className={`text-[11px] tabular-nums text-${TREND_TONE[trend]}-fg`}>
                          {TREND_GLYPH[trend]}
                        </span>
                      </div>
                    </div>
                    <div className="mt-2">
                      <ScoreBar value={num(p.overall)} />
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </Surface>

        {/* Selected-employee detail */}
        <div className="space-y-4 min-w-0">
          {!employee || !prof ? (
            <Surface>
              <EmptyState title="No employee selected" description="Pick someone from the roster to view their coaching profile." />
            </Surface>
          ) : (
            <>
              <EmployeeHeader employee={employee} prof={prof} />
              <ScoreBreakdown prof={prof} />
              <SessionHistory sessions={sessions} />
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <CoachingList coaching={coaching} />
                <ManagerNotes notes={notes} />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Leaderboard */}
      <Leaderboard onSelect={setSelectedId} selectedId={selectedId} />
    </div>
  );
}

// ===========================================================================
// Sections
// ===========================================================================

function EmployeeHeader({ employee, prof }: { employee: Employee; prof: EmployeeAiProficiency }) {
  const overall = num(prof?.overall);
  const band = scoreBand(overall);
  return (
    <Surface>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <ScoreRing value={overall} />
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-semibold text-ink">{employee?.name ?? "Unknown employee"}</h2>
              <Pill tone={BAND_TONE[band]}>{BAND_LABEL[band]}</Pill>
            </div>
            <div className="text-sm text-muted">
              {employee?.role ?? "—"} · {employee?.team ?? "—"}
            </div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-6 text-right">
          <HeaderStat label="Overall" value={overall} accentColor={scoreColor(overall)} />
          <HeaderStat label="AI sessions" value={num(prof?.sessions)} />
          <HeaderStat label="AI spend 30d" value={fmtUsd(num(prof?.aiCostUsd))} />
        </div>
      </div>
    </Surface>
  );
}

function HeaderStat({ label, value, accentColor }: { label: string; value: React.ReactNode; accentColor?: string }) {
  return (
    <div>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tabular-nums text-ink" style={accentColor ? { color: accentColor } : undefined}>
        {value}
      </div>
    </div>
  );
}

function ScoreBreakdown({ prof }: { prof: EmployeeAiProficiency }) {
  return (
    <Surface>
      <SectionTitle
        eyebrow="Proficiency"
        title="Score breakdown · the 4 D's"
        description="Weighted toward discernment and diligence — where unverified AI output concentrates org risk."
      />
      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
        {DIMENSIONS.map((d) => {
          const value = num(prof?.scores?.[d.key]);
          const weightPct = Math.round(num(FOUR_D_WEIGHTS?.[d.key]) * 100);
          return (
            <div key={d.key}>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-baseline gap-2">
                  <span className="text-sm font-medium text-ink">{d.label}</span>
                  <span className="text-[11px] text-muted">{d.blurb}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-muted tabular-nums">{weightPct}% wt</span>
                  <span className="text-sm font-semibold tabular-nums" style={{ color: scoreColor(value) }}>
                    {value}
                  </span>
                </div>
              </div>
              <div className="mt-1.5">
                <ScoreBar value={value} />
              </div>
            </div>
          );
        })}
      </div>
    </Surface>
  );
}

function SessionHistory({ sessions }: { sessions: ReadonlyArray<AiSession> }) {
  const ordered = useMemo(
    () => [...(sessions ?? [])].sort((a, b) => (b?.at ?? "").localeCompare(a?.at ?? "")),
    [sessions],
  );
  return (
    <Surface pad="none" className="overflow-hidden">
      <div className="p-5 pb-3">
        <SectionTitle
          eyebrow="Audit trail"
          title="AI session history"
          description="Reviewed sessions with model, cost, and output-quality score."
        />
      </div>
      {ordered.length === 0 ? (
        <div className="px-5 pb-6">
          <EmptyState title="No sessions" description="This employee has no reviewed AI sessions in the trailing 30 days." />
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-y border-line bg-sunken/50 text-left text-xs text-muted">
                <th className="px-5 py-2 font-medium">Date</th>
                <th className="px-3 py-2 font-medium">Task</th>
                <th className="px-3 py-2 font-medium">Model</th>
                <th className="px-3 py-2 font-medium text-right">Tokens</th>
                <th className="px-3 py-2 font-medium text-right">Cost</th>
                <th className="px-5 py-2 font-medium text-right">Quality</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {ordered.map((s) => {
                const quality = num(s?.quality);
                return (
                <tr key={s.id} className="hover:bg-sunken/40">
                  <td className="px-5 py-2.5 text-muted whitespace-nowrap tabular-nums">{fmtDate(s?.at ?? "")}</td>
                  <td className="px-3 py-2.5 text-ink max-w-[260px]">{s?.task ?? ""}</td>
                  <td className="px-3 py-2.5 text-body whitespace-nowrap font-mono text-xs">{s?.model ?? ""}</td>
                  <td className="px-3 py-2.5 text-body text-right tabular-nums">{num(s?.tokens).toLocaleString()}</td>
                  <td className="px-3 py-2.5 text-body text-right tabular-nums">{fmtUsd(num(s?.costUsd))}</td>
                  <td className="px-5 py-2.5 text-right">
                    <div className="inline-flex items-center gap-2 justify-end">
                      <span className="hidden sm:inline-block w-16">
                        <ScoreBar value={quality} />
                      </span>
                      <Pill tone={qualityTone(quality)}>{quality}</Pill>
                    </div>
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Surface>
  );
}

function CoachingList({ coaching }: { coaching: ReadonlyArray<CoachingSuggestion> }) {
  return (
    <Surface>
      <SectionTitle
        eyebrow="Recommendations"
        title="Coaching suggestions"
        description="AI-generated, dimension-targeted next steps."
      />
      {(coaching ?? []).length === 0 ? (
        <div className="mt-3">
          <EmptyState title="On track" description="No open coaching items — proficiency is healthy across all four D's." />
        </div>
      ) : (
        <ul className="mt-4 space-y-3">
          {(coaching ?? []).map((c) => (
            <li key={c.id} className="rounded-lg border border-line bg-canvas p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Pill tone="accent">{DIM_LABEL[c.dimension] ?? c.dimension ?? "—"}</Pill>
                  <span className="text-sm font-medium text-ink">{c.title}</span>
                </div>
                <StatusPill value={c.priority} tone={PRIORITY_TONE[c.priority] ?? "neutral"} />
              </div>
              <p className="mt-1.5 text-xs text-muted leading-relaxed">{c.detail}</p>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}

function ManagerNotes({ notes }: { notes: ReadonlyArray<ManagerNote> }) {
  const ordered = useMemo(
    () => [...(notes ?? [])].sort((a, b) => (b?.at ?? "").localeCompare(a?.at ?? "")),
    [notes],
  );
  return (
    <Surface>
      <SectionTitle
        eyebrow="Evidence"
        title="Manager notes"
        description="Observations logged by reviewers and people leaders."
      />
      {ordered.length === 0 ? (
        <div className="mt-3">
          <EmptyState title="No notes yet" description="No manager observations have been logged for this employee." />
        </div>
      ) : (
        <ol className="mt-4 space-y-4">
          {ordered.map((n) => (
            <li key={n.id} className="relative pl-4 border-l-2 border-line">
              <span className="absolute -left-[5px] top-1.5 h-2 w-2 rounded-full bg-info-line" aria-hidden />
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink">{n?.author ?? "—"}</span>
                <span className="text-[11px] text-muted tabular-nums">{fmtDate(n?.at ?? "")}</span>
              </div>
              <p className="mt-1 text-xs text-muted leading-relaxed">{n?.note ?? ""}</p>
            </li>
          ))}
        </ol>
      )}
    </Surface>
  );
}

function Leaderboard({ onSelect, selectedId }: { onSelect: (id: string) => void; selectedId: string }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Surface>
        <SectionTitle
          eyebrow="Leaderboard"
          title="Top performers"
          description="Highest overall AI proficiency — candidates to mentor peers."
        />
        <LeaderRows rows={TOP_PERFORMERS ?? []} positive onSelect={onSelect} selectedId={selectedId} />
      </Surface>
      <Surface>
        <SectionTitle
          eyebrow="Leaderboard"
          title="Needs support"
          description="Below the 70 solid threshold — prioritize for coaching."
        />
        {(NEEDS_SUPPORT ?? []).length === 0 ? (
          <div className="mt-3">
            <EmptyState title="No one below threshold" description="Every tracked employee is at or above solid proficiency." />
          </div>
        ) : (
          <LeaderRows rows={NEEDS_SUPPORT} onSelect={onSelect} selectedId={selectedId} />
        )}
      </Surface>
    </div>
  );
}

function LeaderRows({
  rows,
  positive = false,
  onSelect,
  selectedId,
}: {
  rows: ReadonlyArray<EmployeeAiProficiency>;
  positive?: boolean;
  onSelect: (id: string) => void;
  selectedId: string;
}) {
  return (
    <ul className="mt-4 divide-y divide-line">
      {(rows ?? []).map((p, i) => {
        const emp = resolveEmployee(p);
        const active = p.employeeId === selectedId;
        const overall = num(p.overall);
        return (
          <li key={p.employeeId}>
            <button
              onClick={() => onSelect(p.employeeId)}
              className={`w-full text-left py-2.5 flex items-center gap-3 transition-colors ${
                active ? "bg-sunken" : "hover:bg-sunken/50"
              }`}
            >
              <span
                className={`grid place-items-center h-6 w-6 rounded-full text-[11px] font-semibold tabular-nums ${
                  positive ? "bg-success-bg text-success-fg" : "bg-danger-bg text-danger-fg"
                }`}
              >
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-ink truncate">{emp.name}</div>
                <div className="text-xs text-muted truncate">{emp.role} · {emp.team}</div>
              </div>
              <div className="w-24 shrink-0">
                <ScoreBar value={overall} />
              </div>
              <span className="w-9 text-right text-sm font-semibold tabular-nums" style={{ color: scoreColor(overall) }}>
                {overall}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

// ===========================================================================
// Primitives — score bar + ring (0-100, colored by band)
// ===========================================================================

function ScoreBar({ value }: { value: number }) {
  const v = clamp100(value);
  return (
    <div className="h-1.5 w-full rounded-full bg-sunken overflow-hidden">
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${v}%`, backgroundColor: scoreColor(v) }}
      />
    </div>
  );
}

function ScoreRing({ value, size = 76 }: { value: number; size?: number }) {
  const v = clamp100(value);
  const stroke = 7;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const dash = (v / 100) * c;
  const color = scoreColor(v);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-sunken"
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
      <div className="absolute inset-0 grid place-items-center">
        <span className="text-lg font-semibold tabular-nums" style={{ color }}>
          {v}
        </span>
      </div>
    </div>
  );
}
