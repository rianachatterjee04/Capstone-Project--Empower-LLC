"use client";
/**
 * AI Productivity Analytics — an AI-economy operating dashboard that reframes
 * productivity around *leverage*: how many hours each employee/team recovered
 * by delegating manual work to AI, how many automations they shipped, how many
 * recurring tasks they eliminated, and the dollar value of all of it.
 *
 * Renders entirely from deterministic mock data + helpers in
 * "@/lib/aiWorkforce2"; there is no backend and no Math.random() at import.
 * The one interactive control (blended hourly rate) recomputes cost savings
 * live in React state — the mock figures are the floor, the slider re-prices
 * the recovered hours on top.
 */
import { useMemo, useState } from "react";
import {
  PRODUCTIVITY,
  PRODUCTIVITY_SUMMARY,
  WORKFORCE_MEMBERS,
  getWorkforceMember,
  scoreColor,
  type Productivity,
  type Trend,
} from "@/lib/aiWorkforce2";
import { PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import { useLiveData } from "@/lib/useLiveData";

// ---------------------------------------------------------------------------
// Local presentation helpers (color decisions live here, data lives in lib)
// ---------------------------------------------------------------------------

const usd = (n: number) =>
  (Number(n) || 0).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });

const pct = (n: number) => `${Math.round((Number(n) || 0) * 100)}%`;

/** A standard manual-effort baseline so "hours automated" reads like a story. */
const MANUAL_BASELINE_HOURS = 40;

// ---------------------------------------------------------------------------
// Live-data normalization
//
// The live API returns raw DB rows (snake_case columns, numerics possibly as
// strings, and several fields the page needs entirely absent). normalize() maps
// each row — mock-shaped OR live-shaped OR partial — into a fully-populated
// `Productivity` object so every downstream property access is safe.
// ---------------------------------------------------------------------------

/** Coerce anything (number | numeric-string | null | undefined) to a number. */
function num(v: unknown): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** Coerce anything to a non-empty string, falling back to a default. */
function str(v: unknown, fallback = ""): string {
  if (typeof v === "string") return v;
  if (v == null) return fallback;
  return String(v);
}

const TRENDS: ReadonlySet<string> = new Set<Trend>(["up", "down", "flat"]);

/** Coerce an unknown value to a valid Trend, defaulting to "flat". */
function asTrend(v: unknown): Trend {
  const s = typeof v === "string" ? v.toLowerCase() : "";
  return (TRENDS.has(s) ? s : "flat") as Trend;
}

/**
 * Normalize one raw row (mock OR live DB row) into the camelCase `Productivity`
 * shape the page renders. Every field gets a safe default so no access crashes.
 *   live cols:  employee_id, employee_name, hours_saved, automations,
 *               tasks_eliminated, cost_savings_usd, (department), (trend?)
 *   mock fields: memberId, name, hoursSaved, automationsCreated,
 *               tasksEliminated, costSavingsUsd, hoursAutomatedVsWorked, trend
 */
function normalizeRow(r: any): Productivity {
  const row = r ?? {};
  return {
    memberId: str(row.memberId ?? row.member_id ?? row.employee_id ?? row.id),
    name: str(
      row.name ?? row.employee_name ?? row.memberId ?? row.member_id,
      "Unknown",
    ),
    hoursSaved: num(row.hoursSaved ?? row.hours_saved),
    automationsCreated: num(
      row.automationsCreated ?? row.automations_created ?? row.automations,
    ),
    tasksEliminated: num(row.tasksEliminated ?? row.tasks_eliminated),
    costSavingsUsd: num(row.costSavingsUsd ?? row.cost_savings_usd),
    hoursAutomatedVsWorked: num(
      row.hoursAutomatedVsWorked ?? row.hours_automated_vs_worked,
    ),
    trend: asTrend(row.trend),
  };
}

/** Normalize a raw API payload (array | single row | nullish) into rows. */
function normalizeProductivity(raw: any): Productivity[] {
  const list = Array.isArray(raw) ? raw : raw == null ? [] : [raw];
  return list.map(normalizeRow);
}

/** Slider bounds for the blended fully-loaded hourly rate. */
const RATE_MIN = 40;
const RATE_MAX = 160;
const RATE_DEFAULT = 95;

function trendMeta(trend: Trend): { glyph: string; cls: string; label: string } {
  const map: Record<Trend, { glyph: string; cls: string; label: string }> = {
    up: { glyph: "▲", cls: "text-[#16A34A]", label: "Accelerating" },
    down: { glyph: "▼", cls: "text-[#DC2626]", label: "Slowing" },
    flat: { glyph: "▬", cls: "text-muted", label: "Steady" },
  };
  return map[trend];
}

function TrendChip({ trend }: { trend: Trend }) {
  const t = trendMeta(trend);
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${t.cls}`}>
      <span aria-hidden>{t.glyph}</span>
      {t.label}
    </span>
  );
}

/** Map the automated-vs-worked ratio onto the shared 0-100 score color band. */
function leverageColor(ratio: number): string {
  return scoreColor(Math.round(ratio * 200)); // 0.50 ratio -> 100 (deep green)
}

function leverageBand(ratio: number): { label: string; tone: "success" | "info" | "warn" | "danger" } {
  if (ratio >= 0.4) return { label: "high leverage", tone: "success" };
  if (ratio >= 0.3) return { label: "leveraged", tone: "info" };
  if (ratio >= 0.18) return { label: "developing", tone: "warn" };
  return { label: "manual-heavy", tone: "danger" };
}

// KPI stat card: big number + label + trend delta -----------------------------
function Kpi({
  label,
  value,
  delta,
  trend,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  delta?: string;
  trend?: Trend;
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
      {(delta || trend) && (
        <div className="mt-1 flex items-center gap-2">
          {trend && <TrendChip trend={trend} />}
          {delta && <span className="text-xs text-muted">{delta}</span>}
        </div>
      )}
    </div>
  );
}

// Score ring/meter for the org automation rate (SVG gauge) --------------------
function RateRing({ value, size = 104 }: { value: number; size?: number }) {
  const v = Number(value) || 0;
  const stroke = 9;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, v)) / 100;
  const color = scoreColor(Math.round(v * 1.6)); // 62% -> ~100 (green)
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
          strokeDashoffset={c * (1 - clamped)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-semibold tabular-nums text-ink">{Math.round(v)}%</span>
        <span className="text-2xs uppercase tracking-eyebrow text-muted">automated</span>
      </div>
    </div>
  );
}

// Thin horizontal meter, value already a 0-100 percent ------------------------
function Meter({ value, color }: { value: number; color: string }) {
  const v = Number(value) || 0;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-sunken">
      <div
        className="h-full rounded-full transition-[width] duration-300 ease-calm"
        style={{ width: `${Math.max(3, Math.min(100, v))}%`, backgroundColor: color }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

interface TeamRollup {
  team: string;
  headcount: number;
  hoursSaved: number;
  automations: number;
  tasksEliminated: number;
  costSavingsUsd: number;
  ratio: number;
}

export default function AiProductivityPage() {
  // Interactive control: re-price recovered hours at a blended hourly rate.
  const [rate, setRate] = useState<number>(RATE_DEFAULT);

  // LIVE productivity rows with mock fallback — renders the mock until the
  // API responds with non-empty data, then swaps to live.
  //
  // The live endpoint (`/ai-workforce/productivity`) returns RAW DB rows from
  // `ai_productivity` joined to `employees`, i.e. snake_case columns
  // (employee_id, employee_name, hours_saved, automations, tasks_eliminated,
  // cost_savings_usd, ...) and numerics that may arrive as strings — NOT the
  // camelCase `Productivity` shape this page renders. The `pick` mapper below
  // normalizes every live row into that shape (snake_case -> camelCase, string
  // -> number, missing fields -> safe defaults) so no property access is ever
  // on undefined. The mock shape passes through unchanged.
  const { data: productivity, live } = useLiveData<readonly Productivity[]>(
    "/ai-workforce/productivity",
    PRODUCTIVITY,
    (j) => normalizeProductivity(j?.productivity ?? j?.rows ?? j),
  );

  // Per-person rows enriched with department + a re-priced savings figure.
  const rows = useMemo(() => {
    return (productivity ?? [])
      .map((p) => {
        const member = getWorkforceMember(p?.memberId ?? "");
        // Re-priced savings = mock task savings floor + recovered hours @ rate.
        const hoursSaved = num(p?.hoursSaved);
        const costSavingsUsd = num(p?.costSavingsUsd);
        const ratio = num(p?.hoursAutomatedVsWorked);
        const taskFloor = Math.max(0, costSavingsUsd - hoursSaved * 70);
        const repricedUsd = Math.round(taskFloor + hoursSaved * rate);
        const automatedOf = Math.round(
          Math.min(MANUAL_BASELINE_HOURS, ratio * MANUAL_BASELINE_HOURS)
        );
        return {
          p,
          team: member?.department ?? "Unassigned",
          role: member?.role ?? str(p?.name, "Unknown"),
          repricedUsd,
          automatedOf,
        };
      })
      .sort(
        (a, b) =>
          num(b.p?.hoursSaved) - num(a.p?.hoursSaved) ||
          str(a.p?.memberId).localeCompare(str(b.p?.memberId))
      );
  }, [rate, productivity]);

  // Org rollups, re-priced live. When live data is present these totals are
  // derived from the live rows; otherwise we fall back to the mock summary so
  // the headline figures still read correctly with no data.
  const org = useMemo(() => {
    const list = productivity ?? [];
    const hasLive = list.length > 0 && list !== PRODUCTIVITY;
    const repriced = (rows ?? []).reduce((s, r) => s + num(r?.repricedUsd), 0);
    const improving = list.filter((p) => p?.trend === "up").length;
    const declining = list.filter((p) => p?.trend === "down").length;
    const trend: Trend = improving > declining ? "up" : declining > improving ? "down" : "flat";

    // Prefer live-derived totals; fall back to the mock summary otherwise.
    const totalHours = hasLive
      ? Math.round(list.reduce((s, p) => s + num(p?.hoursSaved), 0))
      : num(PRODUCTIVITY_SUMMARY?.totalHoursSaved);
    const automations = hasLive
      ? list.reduce((s, p) => s + num(p?.automationsCreated), 0)
      : num(PRODUCTIVITY_SUMMARY?.totalAutomations);
    const tasksEliminated = hasLive
      ? list.reduce((s, p) => s + num(p?.tasksEliminated), 0)
      : num(PRODUCTIVITY_SUMMARY?.totalTasksEliminated);
    const avgRatio = hasLive
      ? list.reduce((s, p) => s + num(p?.hoursAutomatedVsWorked), 0) /
        (list.length || 1)
      : num(PRODUCTIVITY_SUMMARY?.avgHoursAutomatedVsWorked);
    const ratePct = avgRatio * 100;

    return {
      totalHours,
      repriced,
      automations,
      tasksEliminated,
      avgRatio,
      ratePct,
      headcount: list.length,
      improving,
      declining,
      trend,
      automatedOfBaseline: Math.round(
        Math.min(MANUAL_BASELINE_HOURS, avgRatio * MANUAL_BASELINE_HOURS)
      ),
    };
  }, [rows, productivity]);

  // Team rollups built purely from the productivity + roster rows.
  const teams = useMemo<TeamRollup[]>(() => {
    const byTeam = new Map<string, TeamRollup>();
    for (const r of rows ?? []) {
      const team = str(r?.team, "Unassigned");
      const t =
        byTeam.get(team) ??
        ({
          team,
          headcount: 0,
          hoursSaved: 0,
          automations: 0,
          tasksEliminated: 0,
          costSavingsUsd: 0,
          ratio: 0,
        } as TeamRollup);
      t.headcount += 1;
      t.hoursSaved += num(r?.p?.hoursSaved);
      t.automations += num(r?.p?.automationsCreated);
      t.tasksEliminated += num(r?.p?.tasksEliminated);
      t.costSavingsUsd += num(r?.repricedUsd);
      t.ratio += num(r?.p?.hoursAutomatedVsWorked);
      byTeam.set(team, t);
    }
    return [...byTeam.values()]
      .map((t) => ({ ...t, ratio: t.ratio / Math.max(1, t.headcount) }))
      .sort(
        (a, b) =>
          b.hoursSaved - a.hoursSaved || str(a.team).localeCompare(str(b.team))
      );
  }, [rows]);

  const maxTeamHours = Math.max(1, ...(teams ?? []).map((t) => num(t?.hoursSaved)));

  // Leaderboard: top automators by automations shipped, then hours saved.
  const leaderboard = useMemo(
    () =>
      [...(rows ?? [])].sort(
        (a, b) =>
          num(b.p?.automationsCreated) - num(a.p?.automationsCreated) ||
          num(b.p?.hoursSaved) - num(a.p?.hoursSaved) ||
          str(a.p?.memberId).localeCompare(str(b.p?.memberId))
      ),
    [rows]
  );
  const topAutomator = leaderboard[0];

  // Category breakdown of where the recovered value comes from (stacked bar).
  const valueSplit = useMemo(() => {
    const hoursValue = (rows ?? []).reduce(
      (s, r) => s + num(r?.p?.hoursSaved) * rate,
      0
    );
    const taskValue = (rows ?? []).reduce(
      (s, r) =>
        s + Math.max(0, num(r?.p?.costSavingsUsd) - num(r?.p?.hoursSaved) * 70),
      0
    );
    const total = Math.max(1, hoursValue + taskValue);
    return {
      hoursValue: Math.round(hoursValue),
      taskValue: Math.round(taskValue),
      hoursPct: (hoursValue / total) * 100,
      taskPct: (taskValue / total) * 100,
    };
  }, [rows, rate]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="People · AI Leverage"
        title="AI Productivity Analytics"
        subtitle={
          <>
            Productivity, re-framed around AI leverage. The team automated{" "}
            <span className="font-semibold text-ink tabular-nums">
              {org.automatedOfBaseline} of {MANUAL_BASELINE_HOURS} hours
            </span>{" "}
            of a standard manual week — recovering {org.totalHours} hours, shipping{" "}
            {org.automations} automations, and eliminating {org.tasksEliminated} recurring tasks across{" "}
            {org.headcount} people in the last 30 days.
          </>
        }
        actions={
          <div className="flex items-center gap-2">
            <Pill tone={live ? "success" : "neutral"}>{live ? "Live" : "Sample"}</Pill>
            <Pill tone="info">{org.headcount} contributors</Pill>
            <Pill tone={leverageBand(org.avgRatio).tone}>{leverageBand(org.avgRatio).label}</Pill>
          </div>
        }
      />

      {/* Executive KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi
          label="Hours recovered · 30d"
          value={`${org.totalHours} hrs`}
          trend={org.trend}
          delta={`${org.improving} up · ${org.declining} down`}
          tone="success"
        />
        <Kpi
          label="Automations created"
          value={org.automations}
          delta={`${org.tasksEliminated} manual tasks eliminated`}
        />
        <Kpi
          label="Cost savings · re-priced"
          value={usd(org.repriced)}
          delta={`@ ${usd(rate)}/hr blended`}
          tone="success"
        />
        <Kpi
          label="Hours-automated rate"
          value={pct(org.avgRatio)}
          delta={`${org.automatedOfBaseline}/${MANUAL_BASELINE_HOURS} hrs of a manual week`}
        />
      </div>

      {/* Leverage model: ring + interactive rate control + value split */}
      <Surface>
        <SectionTitle
          eyebrow="Leverage model"
          title="What the org recovered — and what it's worth"
          description="Drag the blended fully-loaded hourly rate to re-price every recovered hour. The category split shows how much value comes from recovered time vs. eliminated recurring tasks."
          trailing={<Pill tone="neutral">live recompute</Pill>}
        />
        <div className="mt-4 grid grid-cols-1 gap-6 lg:grid-cols-[auto_1fr_1fr] lg:items-center">
          <div className="flex items-center gap-4">
            <RateRing value={org.ratePct} />
            <div className="text-xs text-muted">
              <div className="font-semibold text-ink">Org automation rate</div>
              <div className="mt-0.5">Mean across {org.headcount} contributors</div>
              <div className="mt-1">
                <TrendChip trend={org.trend} />
              </div>
            </div>
          </div>

          {/* Interactive control */}
          <div className="rounded-xl border border-line bg-canvas p-4">
            <div className="flex items-baseline justify-between gap-2">
              <label htmlFor="rate" className="text-xs font-medium text-body">
                Blended hourly rate
              </label>
              <span className="text-sm font-semibold tabular-nums text-ink">{usd(rate)}/hr</span>
            </div>
            <input
              id="rate"
              type="range"
              min={RATE_MIN}
              max={RATE_MAX}
              step={5}
              value={rate}
              onChange={(e) => setRate(Number(e.target.value))}
              className="mt-3 w-full accent-[#0F766E]"
            />
            <div className="mt-1 flex justify-between text-2xs text-muted">
              <span>{usd(RATE_MIN)}</span>
              <span>{usd(RATE_MAX)}</span>
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
              <span className="text-xs text-muted">Recovered-time value</span>
              <span className="text-md font-semibold tabular-nums text-ink">
                {usd(org.totalHours * rate)}
              </span>
            </div>
          </div>

          {/* Category breakdown: stacked bar (divs) */}
          <div>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-xs font-medium text-body">Where the savings come from</span>
              <span className="text-xs font-semibold tabular-nums text-ink">
                {usd(valueSplit.hoursValue + valueSplit.taskValue)}
              </span>
            </div>
            <div className="mt-2 flex h-3 w-full overflow-hidden rounded-full bg-sunken">
              <div
                className="h-full"
                style={{ width: `${valueSplit.hoursPct}%`, backgroundColor: "#0F766E" }}
                title="Recovered hours"
              />
              <div
                className="h-full"
                style={{ width: `${valueSplit.taskPct}%`, backgroundColor: "#0EA5E9" }}
                title="Eliminated tasks"
              />
            </div>
            <div className="mt-3 space-y-2">
              <LegendRow color="#0F766E" label="Recovered hours" value={usd(valueSplit.hoursValue)} share={valueSplit.hoursPct} />
              <LegendRow color="#0EA5E9" label="Eliminated recurring tasks" value={usd(valueSplit.taskValue)} share={valueSplit.taskPct} />
            </div>
          </div>
        </div>
      </Surface>

      {/* Per-employee leverage table */}
      <Surface pad="none">
        <div className="p-5">
          <SectionTitle
            eyebrow="By employee"
            title="Per-person AI leverage"
            description="Hours recovered, automations shipped, recurring tasks eliminated, and the share of a standard manual week now handled by AI. Savings re-priced at the rate above."
            trailing={<span className="text-xs text-muted">{(rows ?? []).length} contributors</span>}
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] border-t border-line text-sm">
            <thead>
              <tr className="bg-sunken text-left text-2xs uppercase tracking-eyebrow text-muted">
                <th className="px-5 py-2 font-medium">Employee</th>
                <th className="px-3 py-2 text-right font-medium">Hours saved</th>
                <th className="px-3 py-2 text-right font-medium">Automations</th>
                <th className="px-3 py-2 text-right font-medium">Tasks eliminated</th>
                <th className="px-3 py-2 font-medium">Automated of week</th>
                <th className="px-3 py-2 text-right font-medium">Cost savings</th>
                <th className="px-3 py-2 font-medium">Trend</th>
                <th className="px-5 py-2 font-medium">Leverage</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(rows ?? []).map(({ p, role, team, repricedUsd, automatedOf }, i) => {
                const ratio = num(p?.hoursAutomatedVsWorked);
                const band = leverageBand(ratio);
                const ofWeekPct = (num(automatedOf) / MANUAL_BASELINE_HOURS) * 100;
                return (
                  <tr key={str(p?.memberId) || `row-${i}`} className="hover:bg-sunken/60">
                    <td className="px-5 py-3">
                      <div className="font-medium text-ink">{str(p?.name, "Unknown")}</div>
                      <div className="text-xs text-muted">{role} · {team}</div>
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums font-medium text-ink">{num(p?.hoursSaved)}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-body">{num(p?.automationsCreated)}</td>
                    <td className="px-3 py-3 text-right tabular-nums text-body">{num(p?.tasksEliminated)}</td>
                    <td className="px-3 py-3">
                      <div className="w-32">
                        <div className="flex items-baseline justify-between text-2xs text-muted">
                          <span className="tabular-nums text-body">{num(automatedOf)}/{MANUAL_BASELINE_HOURS} hrs</span>
                          <span className="tabular-nums">{Math.round(ofWeekPct)}%</span>
                        </div>
                        <div className="mt-1">
                          <Meter value={ofWeekPct} color={leverageColor(ratio)} />
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums font-medium text-ink">{usd(num(repricedUsd))}</td>
                    <td className="px-3 py-3"><TrendChip trend={asTrend(p?.trend)} /></td>
                    <td className="px-5 py-3"><Pill tone={band.tone}>{band.label}</Pill></td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="border-t border-line bg-sunken/50 text-sm font-semibold">
                <td className="px-5 py-3 text-ink">Org total</td>
                <td className="px-3 py-3 text-right tabular-nums text-ink">{org.totalHours}</td>
                <td className="px-3 py-3 text-right tabular-nums text-ink">{org.automations}</td>
                <td className="px-3 py-3 text-right tabular-nums text-ink">{org.tasksEliminated}</td>
                <td className="px-3 py-3 text-2xs text-muted">{org.automatedOfBaseline}/{MANUAL_BASELINE_HOURS} hrs avg</td>
                <td className="px-3 py-3 text-right tabular-nums text-ink">{usd(org.repriced)}</td>
                <td className="px-3 py-3" />
                <td className="px-5 py-3" />
              </tr>
            </tfoot>
          </table>
        </div>
      </Surface>

      {/* Leaderboard + team rollup */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1.1fr]">
        <Surface>
          <SectionTitle
            eyebrow="Recognition"
            title="Top automators"
            description="Ranked by automations shipped, then hours recovered. Candidates to lead the next enablement clinic."
            trailing={
              topAutomator ? (
                <Pill tone="success">{str(topAutomator.p?.name, "Unknown").split(" ")[0]} leads</Pill>
              ) : null
            }
          />
          <ul className="mt-4 space-y-3">
            {(leaderboard ?? []).map((r, i) => (
              <li
                key={str(r.p?.memberId) || `lb-${i}`}
                className="flex items-center gap-3 rounded-xl border border-line bg-canvas p-3"
              >
                <span
                  className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
                  style={{ backgroundColor: i === 0 ? "#0F766E" : "#475569" }}
                >
                  {i + 1}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-ink">{str(r.p?.name, "Unknown")}</div>
                  <div className="text-xs text-muted">{r.role} · {r.team}</div>
                </div>
                <div className="hidden text-right sm:block">
                  <div className="text-xs text-muted">hrs saved</div>
                  <div className="text-sm font-semibold tabular-nums text-ink">{num(r.p?.hoursSaved)}</div>
                </div>
                <span className="inline-flex h-8 min-w-[2.75rem] items-center justify-center gap-1 rounded-md bg-sunken px-2 text-sm font-semibold tabular-nums text-ink">
                  <span className="text-2xs font-normal text-muted">×</span>
                  {num(r.p?.automationsCreated)}
                </span>
              </li>
            ))}
          </ul>
        </Surface>

        <Surface pad="none">
          <div className="p-5">
            <SectionTitle
              eyebrow="Team rollup"
              title="Leverage by team"
              description="Hours recovered, automations, and re-priced savings rolled up by department. Bars are relative to the leading team."
              trailing={<span className="text-xs text-muted">{(teams ?? []).length} teams</span>}
            />
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-t border-line text-sm">
              <thead>
                <tr className="bg-sunken text-left text-2xs uppercase tracking-eyebrow text-muted">
                  <th className="px-5 py-2 font-medium">Team</th>
                  <th className="px-3 py-2 font-medium">Hours recovered</th>
                  <th className="px-3 py-2 text-right font-medium">Autos</th>
                  <th className="px-3 py-2 text-right font-medium">Savings</th>
                  <th className="px-5 py-2 font-medium">Rate</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {(teams ?? []).map((t, i) => (
                  <tr key={str(t?.team) || `team-${i}`} className="hover:bg-sunken/60">
                    <td className="px-5 py-3">
                      <div className="font-medium text-ink">{str(t?.team, "Unassigned")}</div>
                      <div className="text-xs text-muted">{num(t?.headcount)} {num(t?.headcount) === 1 ? "person" : "people"}</div>
                    </td>
                    <td className="px-3 py-3">
                      <div className="w-36">
                        <div className="flex items-baseline justify-between text-2xs text-muted">
                          <span className="tabular-nums text-body">{num(t?.hoursSaved)} hrs</span>
                        </div>
                        <div className="mt-1">
                          <Meter value={(num(t?.hoursSaved) / (maxTeamHours || 1)) * 100} color={leverageColor(num(t?.ratio))} />
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums text-body">{num(t?.automations)}</td>
                    <td className="px-3 py-3 text-right tabular-nums font-medium text-ink">{usd(num(t?.costSavingsUsd))}</td>
                    <td className="px-5 py-3">
                      <span
                        className="inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums text-white"
                        style={{ backgroundColor: leverageColor(num(t?.ratio)) }}
                      >
                        {pct(num(t?.ratio))}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Surface>
      </div>
    </div>
  );
}

// Legend row for the value-split stacked bar ---------------------------------
function LegendRow({
  color,
  label,
  value,
  share,
}: {
  color: string;
  label: string;
  value: string;
  share: number;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: color }} />
      <span className="flex-1 text-body">{label}</span>
      <span className="tabular-nums text-muted">{Math.round(share)}%</span>
      <span className="w-16 text-right font-semibold tabular-nums text-ink">{value}</span>
    </div>
  );
}
