"use client";
/**
 * Workforce AI Proficiency — enterprise AI observability for how effectively
 * teams and employees work *with* AI, scored across the 4 D's (delegation,
 * description, discernment, diligence). Renders entirely from deterministic
 * mock data + scoring in "@/lib/workforceAi"; no backend.
 */
import { useMemo, useState } from "react";
import {
  EMPLOYEES,
  EMPLOYEE_PROFICIENCY,
  TEAM_PROFICIENCY,
  AI_SESSIONS,
  COACHING_SUGGESTIONS,
  MANAGER_NOTES,
  TOP_PERFORMERS,
  NEEDS_SUPPORT,
  FOUR_D_WEIGHTS,
  scoreColor,
  scoreBand,
  getEmployee,
  type FourDs,
  type Trend,
  type Severity,
  type EmployeeAiProficiency,
} from "@/lib/workforceAi";
import { PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import { useLiveData } from "@/lib/useLiveData";

// Coerce anything (number, numeric string, null, undefined, NaN) to a finite
// number, defaulting to 0. Keeps every downstream math/render call safe.
function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

// Some live payloads ship nested objects (e.g. `scores`) as JSON strings.
// Parse defensively and only accept a plain object; otherwise return {}.
function asObject(v: unknown): Record<string, unknown> {
  if (v && typeof v === "object" && !Array.isArray(v)) {
    return v as Record<string, unknown>;
  }
  if (typeof v === "string" && v.trim()) {
    try {
      const parsed = JSON.parse(v);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      /* not JSON — fall through to empty */
    }
  }
  return {};
}

const VALID_TRENDS: ReadonlyArray<Trend> = ["up", "down", "flat"];
function asTrend(v: unknown): Trend {
  return VALID_TRENDS.includes(v as Trend) ? (v as Trend) : "flat";
}

// Map a flat live proficiency row ({ employee_id, delegation, ..., ai_cost_usd })
// — or one with a nested/stringified `scores` object — into the nested
// EmployeeAiProficiency shape the page renders from. Every field is coerced to
// its expected type with a safe default so no later property access can fail.
function adaptProficiency(rows: any): EmployeeAiProficiency[] {
  const list = Array.isArray(rows) ? rows : [];
  return list.map((raw): EmployeeAiProficiency => {
    const r = raw && typeof raw === "object" ? raw : {};
    // `scores` may be a nested object, a JSON string, or absent (flat row).
    const s = asObject(r.scores);
    const scores: FourDs = {
      delegation: num(r.delegation ?? s.delegation),
      description: num(r.description ?? s.description),
      discernment: num(r.discernment ?? s.discernment),
      diligence: num(r.diligence ?? s.diligence),
    };
    const overall =
      r.overall != null
        ? num(r.overall)
        : Math.round(
            (scores.delegation + scores.description + scores.discernment + scores.diligence) / 4,
          );
    return {
      employeeId: String(r.employee_id ?? r.employeeId ?? ""),
      scores,
      overall,
      aiCostUsd: num(r.ai_cost_usd ?? r.aiCostUsd),
      sessions: num(r.sessions),
      trend: asTrend(r.trend),
    };
  });
}

// ---------------------------------------------------------------------------
// Local presentation helpers (color decisions live here, scoring lives in lib)
// ---------------------------------------------------------------------------

const BAND_TONE: Record<ReturnType<typeof scoreBand>, "success" | "info" | "warn" | "danger"> = {
  strong: "success",
  solid: "info",
  developing: "warn",
  "at-risk": "danger",
};

const SEVERITY_TONE: Record<Severity, "success" | "warn" | "danger" | "info"> = {
  low: "info",
  medium: "warn",
  high: "danger",
  critical: "danger",
};

const FOUR_D_META: { key: keyof FourDs; label: string; blurb: string }[] = [
  { key: "delegation", label: "Delegation", blurb: "Routing the right work to AI" },
  { key: "description", label: "Description", blurb: "Clear prompts & specs" },
  { key: "discernment", label: "Discernment", blurb: "Judging & correcting output" },
  { key: "diligence", label: "Diligence", blurb: "Verifying & owning results" },
];

const usd = (n: number) =>
  (Number(n) || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usd2 = (n: number) =>
  (Number(n) || 0).toLocaleString("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

function fmtTime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function TrendChip({ trend }: { trend: Trend }) {
  const map: Record<Trend, { glyph: string; cls: string; label: string }> = {
    up: { glyph: "▲", cls: "text-[#16A34A]", label: "Improving" },
    down: { glyph: "▼", cls: "text-[#DC2626]", label: "Declining" },
    flat: { glyph: "▬", cls: "text-muted", label: "Steady" },
  };
  const t = map[trend];
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${t.cls}`}>
      <span aria-hidden>{t.glyph}</span>
      {t.label}
    </span>
  );
}

// 0-100 score ring (SVG gauge) ------------------------------------------------
function ScoreRing({ value, size = 96 }: { value: number; size?: number }) {
  const stroke = 8;
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
        <span className="text-xl font-semibold tabular-nums text-ink">{value}</span>
        <span className="text-2xs uppercase tracking-eyebrow text-muted">/100</span>
      </div>
    </div>
  );
}

// horizontal 0-100 score bar --------------------------------------------------
function ScoreBar({
  label,
  value,
  hint,
}: {
  label: string;
  value: number;
  hint?: string;
}) {
  const color = scoreColor(value);
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-medium text-body">{label}</span>
        <span className="text-xs font-semibold tabular-nums text-ink">{value}</span>
      </div>
      <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-sunken">
        <div
          className="h-full rounded-full transition-[width] duration-300 ease-calm"
          style={{ width: `${Math.max(2, value)}%`, backgroundColor: color }}
        />
      </div>
      {hint && <div className="mt-0.5 text-2xs text-muted">{hint}</div>}
    </div>
  );
}

// sparkline of quality across an employee's recent sessions -------------------
function Sparkline({ values, width = 96, height = 26 }: { values: number[]; width?: number; height?: number }) {
  if (values.length === 0) {
    return <div className="text-2xs text-muted">no sessions</div>;
  }
  const max = 100;
  const min = 0;
  const step = values.length > 1 ? width / (values.length - 1) : width;
  const pts = values.map((v, i) => {
    const x = i * step;
    const y = height - ((v - min) / (max - min)) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const last = values[values.length - 1];
  return (
    <svg width={width} height={height} className="overflow-visible">
      <polyline points={pts.join(" ")} fill="none" stroke={scoreColor(last)} strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" />
      {values.map((v, i) => (
        <circle key={i} cx={i * step} cy={height - ((v - min) / (max - min)) * height} r={1.6} fill={scoreColor(v)} />
      ))}
    </svg>
  );
}

// KPI stat card with a small trend line --------------------------------------
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
  trend?: { trend: Trend; text: string };
  tone?: "neutral" | "success" | "warn" | "danger";
}) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
  };
  return (
    <div className={`rounded-xl border border-line bg-surface p-4 shadow-soft ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-ink">{value}</div>
      <div className="mt-1 flex items-center gap-2">
        {trend && <TrendChip trend={trend.trend} />}
        {hint && <span className="text-xs text-muted">{hint}</span>}
        {trend && <span className="text-xs text-muted">{trend.text}</span>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function WorkforceAiPage() {
  const [activeTeam, setActiveTeam] = useState<string | null>(null);

  // Live per-employee 4-D proficiency rows, mock-first then live. The live
  // payload uses flat snake_case fields, so adapt it to EmployeeAiProficiency.
  const { data: proficiency, live } = useLiveData(
    "/ai-workforce/proficiency",
    EMPLOYEE_PROFICIENCY,
    (j) => adaptProficiency(j?.proficiency ?? j?.rows ?? j?.data ?? j),
  );

  // Org-level rollups derived from imported data.
  const org = useMemo(() => {
    const rows = proficiency ?? [];
    const count = rows.length;
    const proficiencies = rows.map((p) => num(p?.overall));
    const orgScore = Math.round(proficiencies.reduce((a, b) => a + b, 0) / (count || 1));
    const aiSpend = rows.reduce((s, p) => s + num(p?.aiCostUsd), 0);
    const sessions = rows.reduce((s, p) => s + num(p?.sessions), 0);
    const activeUsers = rows.filter((p) => num(p?.sessions) > 0).length;
    const improving = rows.filter((p) => p?.trend === "up").length;
    const declining = rows.filter((p) => p?.trend === "down").length;
    const weekTrend: Trend = improving > declining ? "up" : declining > improving ? "down" : "flat";
    // Mean of each D across the org for the radar-style summary.
    const dMeans = FOUR_D_META.map(({ key }) => {
      const vals = rows.map((p) => num(p?.scores?.[key]));
      return Math.round(vals.reduce((a, b) => a + b, 0) / (count || 1));
    });
    // indexOf can be -1 on an empty/degenerate set; fall back to the first D.
    const weakIdx = count > 0 ? dMeans.indexOf(Math.min(...dMeans)) : 0;
    const weakestD = FOUR_D_META[weakIdx >= 0 ? weakIdx : 0];
    return {
      orgScore,
      aiSpend,
      sessions,
      activeUsers,
      headcount: EMPLOYEES.length,
      weekTrend,
      improving,
      declining,
      dMeans,
      weakestD,
    };
  }, [proficiency]);

  const teams = useMemo(
    () => [...TEAM_PROFICIENCY].sort((a, b) => b.overall - a.overall),
    []
  );

  // Per-employee rows, optionally filtered to the selected team, ranked.
  const employeeRows = useMemo(() => {
    return [...(proficiency ?? [])]
      .map((p) => ({ p, emp: getEmployee(p?.employeeId)! }))
      .filter((r) => r.emp && (activeTeam ? r.emp.team === activeTeam : true))
      .sort((a, b) => num(b.p?.overall) - num(a.p?.overall));
  }, [activeTeam, proficiency]);

  // Recent AI usage sorted newest-first for the audit trail.
  const recentSessions = useMemo(
    () => [...AI_SESSIONS].sort((a, b) => b.at.localeCompare(a.at)),
    []
  );

  // Quality sparkline values per employee (chronological).
  const sparkByEmployee = useMemo(() => {
    const map = new Map<string, number[]>();
    [...AI_SESSIONS]
      .sort((a, b) => a.at.localeCompare(b.at))
      .forEach((s) => {
        const arr = map.get(s.employeeId) ?? [];
        arr.push(s.quality);
        map.set(s.employeeId, arr);
      });
    return map;
  }, []);

  // Highest-priority coaching alerts first.
  const alerts = useMemo(() => {
    const rank: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 };
    return [...COACHING_SUGGESTIONS].sort((a, b) => rank[a.priority] - rank[b.priority]);
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="People · AI Enablement"
        title="Workforce AI Proficiency"
        subtitle="How effectively teams work with AI, scored across the 4 D's — delegation, description, discernment, diligence — alongside AI usage cost. Spot top performers, surface who needs support, and govern spend."
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
            <Pill tone="info">{org.activeUsers}/{org.headcount} active</Pill>
            <Pill tone={BAND_TONE[scoreBand(org.orgScore)]}>{scoreBand(org.orgScore)}</Pill>
          </div>
        }
      />

      {/* Executive KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi
          label="Org AI proficiency"
          value={`${org.orgScore}`}
          tone={BAND_TONE[scoreBand(org.orgScore)] === "success" ? "success" : BAND_TONE[scoreBand(org.orgScore)] === "danger" ? "danger" : "neutral"}
          trend={{ trend: org.weekTrend, text: `${org.improving} up · ${org.declining} down` }}
        />
        <Kpi
          label="Active AI users"
          value={`${org.activeUsers}`}
          hint={`of ${org.headcount} · ${org.sessions} sessions / 30d`}
        />
        <Kpi
          label="AI spend · 30d"
          value={usd(org.aiSpend)}
          hint={`${usd2(org.aiSpend / (org.activeUsers || 1))} avg / user`}
        />
        <Kpi
          label="Weakest dimension"
          value={org.weakestD?.label ?? "—"}
          tone="warn"
          hint={`${org.dMeans[FOUR_D_META.findIndex((m) => m.key === org.weakestD?.key)] ?? 0} org avg`}
        />
      </div>

      {/* Org 4-D summary + gauge */}
      <Surface>
        <SectionTitle
          eyebrow="The 4 D's"
          title="Organization-wide proficiency profile"
          description="Weighted overall blends discernment (30%) and diligence (25%) highest — unverified AI output is where org risk concentrates."
          trailing={<Pill tone="neutral">weighting fixed</Pill>}
        />
        <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-[auto_1fr] md:items-center">
          <div className="flex items-center gap-4">
            <ScoreRing value={org.orgScore} />
            <div className="text-xs text-muted">
              <div className="font-semibold text-ink">Org rollup</div>
              <div className="mt-0.5">Mean of {org.headcount} employees</div>
              <div className="mt-1">
                <TrendChip trend={org.weekTrend} />
              </div>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {FOUR_D_META.map(({ key, label, blurb }, i) => (
              <ScoreBar
                key={key}
                label={`${label} · ${Math.round(FOUR_D_WEIGHTS[key] * 100)}% weight`}
                value={org.dMeans[i]}
                hint={blurb}
              />
            ))}
          </div>
        </div>
      </Surface>

      {/* Team proficiency dashboard */}
      <Surface>
        <SectionTitle
          eyebrow="By team"
          title="Team AI proficiency & cost"
          description="Select a team to filter the employee table below. Score bars show the 4 D's per team; spend is trailing 30 days."
          trailing={
            activeTeam ? (
              <button onClick={() => setActiveTeam(null)} className="text-xs font-medium text-accent-softFg underline-offset-2 hover:underline">
                Clear filter ({activeTeam})
              </button>
            ) : (
              <span className="text-xs text-muted">{teams.length} teams</span>
            )
          }
        />
        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {teams.map((t) => {
            const selected = activeTeam === t.team;
            return (
              <button
                key={t.team}
                onClick={() => setActiveTeam(selected ? null : t.team)}
                className={`rounded-xl border p-4 text-left transition-colors duration-150 ease-calm hover:bg-sunken ${
                  selected ? "border-ink/30 bg-sunken" : "border-line bg-surface"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-ink">{t.team}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {t.headcount} people · {t.sessions} sessions · {usd(t.aiCostUsd)} spend
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span
                      className="rounded-md px-2 py-0.5 text-sm font-semibold tabular-nums text-white"
                      style={{ backgroundColor: scoreColor(t.overall) }}
                    >
                      {t.overall}
                    </span>
                    <TrendChip trend={t.trend} />
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2">
                  {FOUR_D_META.map(({ key, label }) => (
                    <ScoreBar key={key} label={label} value={t.scores[key]} />
                  ))}
                </div>
              </button>
            );
          })}
        </div>
      </Surface>

      {/* Employee proficiency table */}
      <Surface pad="none">
        <div className="p-5">
          <SectionTitle
            eyebrow="By employee"
            title={activeTeam ? `Employees · ${activeTeam}` : "All employees · proficiency & spend"}
            description="Per-person 4 D's, overall band, AI cost, and a quality sparkline across recent AI sessions."
            trailing={<span className="text-xs text-muted">{employeeRows.length} shown</span>}
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] border-t border-line text-sm">
            <thead>
              <tr className="bg-sunken text-left text-2xs uppercase tracking-eyebrow text-muted">
                <th className="px-5 py-2 font-medium">Employee</th>
                <th className="px-3 py-2 font-medium">Overall</th>
                <th className="px-3 py-2 font-medium">Deleg.</th>
                <th className="px-3 py-2 font-medium">Descr.</th>
                <th className="px-3 py-2 font-medium">Discern.</th>
                <th className="px-3 py-2 font-medium">Dilig.</th>
                <th className="px-3 py-2 text-right font-medium">AI cost</th>
                <th className="px-3 py-2 text-right font-medium">Sessions</th>
                <th className="px-3 py-2 font-medium">Quality trend</th>
                <th className="px-5 py-2 font-medium">Band</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {employeeRows.map(({ p, emp }) => (
                <tr key={p.employeeId} className="hover:bg-sunken/60">
                  <td className="px-5 py-3">
                    <div className="font-medium text-ink">{emp.name}</div>
                    <div className="text-xs text-muted">{emp.role} · {emp.team}</div>
                  </td>
                  <td className="px-3 py-3">
                    <span
                      className="inline-flex h-7 w-9 items-center justify-center rounded-md text-xs font-semibold tabular-nums text-white"
                      style={{ backgroundColor: scoreColor(p.overall) }}
                    >
                      {p.overall}
                    </span>
                  </td>
                  {FOUR_D_META.map(({ key }) => (
                    <td key={key} className="px-3 py-3">
                      <DScoreCell value={p.scores[key]} />
                    </td>
                  ))}
                  <td className="px-3 py-3 text-right tabular-nums text-body">{usd2(p.aiCostUsd)}</td>
                  <td className="px-3 py-3 text-right tabular-nums text-body">{p.sessions}</td>
                  <td className="px-3 py-3">
                    <Sparkline values={sparkByEmployee.get(p.employeeId) ?? []} />
                  </td>
                  <td className="px-5 py-3">
                    <Pill tone={BAND_TONE[scoreBand(p.overall)]}>{scoreBand(p.overall)}</Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Surface>

      {/* Top performers + needs support */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Surface>
          <SectionTitle
            eyebrow="Recognition"
            title="Top performers"
            description="Highest weighted 4-D proficiency. Candidates to lead enablement clinics."
            trailing={<Pill tone="success">healthy</Pill>}
          />
          <ul className="mt-4 space-y-3">
            {TOP_PERFORMERS.map((p, i) => (
              <PerformerRow key={p.employeeId} p={p} rank={i + 1} />
            ))}
          </ul>
        </Surface>

        <Surface>
          <SectionTitle
            eyebrow="Intervention"
            title="Employees needing support"
            description="Below the 'solid' threshold (70). Prioritize for coaching before AI-assisted work expands."
            trailing={<Pill tone="danger">{NEEDS_SUPPORT.length} flagged</Pill>}
          />
          {NEEDS_SUPPORT.length === 0 ? (
            <div className="mt-4 text-sm text-muted">Everyone is at a solid proficiency or above.</div>
          ) : (
            <ul className="mt-4 space-y-3">
              {NEEDS_SUPPORT.map((p) => {
                const weak = FOUR_D_META.reduce((min, m) =>
                  p.scores[m.key] < p.scores[min.key] ? m : min
                );
                return (
                  <li key={p.employeeId} className="rounded-xl border border-line bg-canvas p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold text-ink">{getEmployee(p.employeeId)?.name}</div>
                        <div className="text-xs text-muted">{getEmployee(p.employeeId)?.team}</div>
                      </div>
                      <span
                        className="rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums text-white"
                        style={{ backgroundColor: scoreColor(p.overall) }}
                      >
                        {p.overall}
                      </span>
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <Pill tone="warn">weakest: {weak.label} {p.scores[weak.key]}</Pill>
                      <TrendChip trend={p.trend} />
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Surface>
      </div>

      {/* Coaching alert cards */}
      <Surface>
        <SectionTitle
          eyebrow="Action queue"
          title="Coaching alerts"
          description="Targeted, per-dimension nudges generated from session evidence. Resolve high-severity items first."
          trailing={
            <span className="text-xs text-muted">
              {alerts.filter((a) => a.priority === "high" || a.priority === "critical").length} high-priority
            </span>
          }
        />
        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {alerts.map((a) => {
            const dim = FOUR_D_META.find((m) => m.key === a.dimension);
            return (
              <div key={a.id} className="rounded-xl border border-line bg-canvas p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-semibold text-ink">{a.title}</div>
                  <Pill tone={SEVERITY_TONE[a.priority]}>{a.priority}</Pill>
                </div>
                <div className="mt-1 text-xs text-muted">
                  {getEmployee(a.employeeId)?.name} · targets {dim?.label}
                </div>
                <p className="mt-2 text-xs leading-relaxed text-body">{a.detail}</p>
              </div>
            );
          })}
        </div>
      </Surface>

      {/* Audit trail: AI usage + manager notes */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.4fr_1fr]">
        <Surface pad="none">
          <div className="p-5">
            <SectionTitle
              eyebrow="Evidence"
              title="AI usage audit trail"
              description="Recent AI sessions with model, token cost, and reviewer-assigned output quality."
              trailing={<span className="text-xs text-muted">{recentSessions.length} of {AI_SESSIONS.length}</span>}
            />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-t border-line text-sm">
              <thead>
                <tr className="bg-sunken text-left text-2xs uppercase tracking-eyebrow text-muted">
                  <th className="px-5 py-2 font-medium">When</th>
                  <th className="px-3 py-2 font-medium">Employee · Task</th>
                  <th className="px-3 py-2 font-medium">Model</th>
                  <th className="px-3 py-2 text-right font-medium">Cost</th>
                  <th className="px-5 py-2 font-medium">Quality</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {recentSessions.map((s) => (
                  <tr key={s.id} className="hover:bg-sunken/60">
                    <td className="whitespace-nowrap px-5 py-3 text-xs text-muted">{fmtTime(s.at)}</td>
                    <td className="px-3 py-3">
                      <div className="font-medium text-ink">{getEmployee(s.employeeId)?.name}</div>
                      <div className="text-xs text-muted">{s.task}</div>
                    </td>
                    <td className="px-3 py-3">
                      <span className="rounded-md border border-line bg-surface px-1.5 py-0.5 font-mono text-2xs text-body">
                        {s.model}
                      </span>
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums text-body">{usd2(s.costUsd)}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <span
                          className="inline-block h-2 w-2 rounded-full"
                          style={{ backgroundColor: scoreColor(s.quality) }}
                        />
                        <span className="tabular-nums text-body">{s.quality}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Surface>

        <Surface>
          <SectionTitle
            eyebrow="Trail"
            title="Manager notes timeline"
            description="Qualitative context behind the scores, newest first."
          />
          <ol className="mt-4 space-y-4">
            {[...MANAGER_NOTES]
              .sort((a, b) => b.at.localeCompare(a.at))
              .map((n) => (
                <li key={n.id} className="relative border-l border-line pl-4">
                  <span className="absolute -left-[5px] top-1 h-2.5 w-2.5 rounded-full border-2 border-surface bg-[#0EA5E9]" />
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-semibold text-ink">{getEmployee(n.employeeId)?.name}</span>
                    <span className="text-2xs text-muted">{fmtTime(n.at)}</span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-body">{n.note}</p>
                  <div className="mt-1 text-2xs text-muted">— {n.author}</div>
                </li>
              ))}
          </ol>
        </Surface>
      </div>
    </div>
  );
}

// Small inline 4-D cell: number + thin bar -----------------------------------
function DScoreCell({ value }: { value: number }) {
  const color = scoreColor(value);
  return (
    <div className="w-16">
      <div className="text-xs font-medium tabular-nums text-ink">{value}</div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-sunken">
        <div className="h-full rounded-full" style={{ width: `${Math.max(4, value)}%`, backgroundColor: color }} />
      </div>
    </div>
  );
}

function PerformerRow({ p, rank }: { p: EmployeeAiProficiency; rank: number }) {
  const emp = getEmployee(p.employeeId);
  return (
    <li className="flex items-center gap-3 rounded-xl border border-line bg-canvas p-3">
      <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#0F766E] text-xs font-semibold text-white">
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-ink">{emp?.name}</div>
        <div className="text-xs text-muted">{emp?.role} · {emp?.team}</div>
      </div>
      <div className="hidden items-center gap-1 sm:flex">
        {FOUR_D_META.map(({ key }) => (
          <span
            key={key}
            title={key}
            className="inline-block h-6 w-1.5 rounded-full"
            style={{ backgroundColor: scoreColor(p.scores[key]), opacity: 0.35 + (p.scores[key] / 100) * 0.65 }}
          />
        ))}
      </div>
      <span
        className="rounded-md px-2 py-0.5 text-sm font-semibold tabular-nums text-white"
        style={{ backgroundColor: scoreColor(p.overall) }}
      >
        {p.overall}
      </span>
    </li>
  );
}
