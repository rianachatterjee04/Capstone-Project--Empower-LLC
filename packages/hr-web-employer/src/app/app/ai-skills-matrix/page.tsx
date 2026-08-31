"use client";
/**
 * AI Skills Matrix — enterprise AI-economy operating dashboard for how the
 * workforce stacks up across eight AI-native skills (Prompt Engineering,
 * Cursor, Claude Code, Databricks, Copilot, MCP, Agent Design, Model
 * Evaluation). Renders a proficiency heatmap (employees x skills), per-skill
 * coverage bars, and the org's widest skill gaps. Everything flows from
 * deterministic mock data + helpers in "@/lib/aiWorkforce2"; no backend.
 */
import { useMemo, useState } from "react";
import {
  AI_SKILLS,
  SKILL_MATRIX,
  skillGaps,
  skillAverage,
  scoreColor,
  clamp100,
  type AiSkill,
  type SkillRating,
  type EmployeeSkills,
} from "@/lib/aiWorkforce2";
import { PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import { useLiveData } from "@/lib/useLiveData";

// ---------------------------------------------------------------------------
// Live-data normalization
//
// The mock (SKILL_MATRIX) is "wide": one EmployeeSkills row per person with a
// `ratings` map keyed by all eight AI_SKILLS ({ proficiency, certified }).
//
// The live endpoint (/ai-workforce/skills -> { skills: [...] }) returns RAW DB
// rows from `ai_skills`, which are "long": ONE row per (employee, skill) with
// snake_case columns: employee_id, employee_name, skill, proficiency (int,
// maybe string), certified (bool, maybe "t"/0/"true"). There is no `ratings`
// object and no `memberId`/`name` at all.
//
// normalizeSkills() accepts mock-shaped OR live-shaped OR partial/empty input
// and always returns fully-populated EmployeeSkills[] — pivoting long rows into
// the wide per-person shape and filling every one of the eight skills with a
// safe { proficiency: 0, certified: false } default — so no downstream access
// (r.ratings[skill].proficiency, r.name, r.memberId) is ever on undefined.
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

/** Coerce truthy/string/number representations of a boolean. */
function asBool(v: unknown): boolean {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v !== 0;
  if (typeof v === "string") {
    const s = v.trim().toLowerCase();
    return s === "true" || s === "t" || s === "1" || s === "yes" || s === "y";
  }
  return false;
}

/** A fully-defaulted ratings map covering every one of the eight skills. */
function emptyRatings(): Record<AiSkill, SkillRating> {
  const out = {} as Record<AiSkill, SkillRating>;
  for (const skill of AI_SKILLS) out[skill] = { proficiency: 0, certified: false };
  return out;
}

/** Build a safe SkillRating from a wide-shaped rating value (mock or partial). */
function asRating(v: any): SkillRating {
  const r = v ?? {};
  return { proficiency: clamp100(num(r.proficiency)), certified: asBool(r.certified) };
}

/**
 * Normalize a raw API payload (the live { skills: [...] } long rows, an array
 * of mock EmployeeSkills, a single row, or nullish) into wide EmployeeSkills[].
 */
// A mutable accumulator we build up before freezing into a (readonly) row.
type MutableRow = {
  memberId: string;
  name: string;
  ratings: Record<AiSkill, SkillRating>;
};

function normalizeSkills(raw: any): EmployeeSkills[] {
  const list: any[] = Array.isArray(raw) ? raw : raw == null ? [] : [raw];

  // Group rows by a person key. Wide (mock) rows already carry a full ratings
  // map; long (live) rows are one skill each and must be folded together.
  const byMember = new Map<string, MutableRow>();

  const ensure = (key: string, name: string): MutableRow => {
    let row = byMember.get(key);
    if (!row) {
      row = { memberId: key, name, ratings: emptyRatings() };
      byMember.set(key, row);
    } else if ((!row.name || row.name === key) && name && name !== key) {
      row.name = name;
    }
    return row;
  };

  for (const item of list) {
    const r = item ?? {};
    const memberId = str(
      r.memberId ?? r.member_id ?? r.employee_id ?? r.employeeId ?? r.id,
      "",
    );
    const name = str(r.name ?? r.employee_name ?? r.employeeName, "") || memberId;

    // Wide shape: a mock EmployeeSkills row with a ratings object.
    if (r.ratings && typeof r.ratings === "object") {
      const key = memberId || name || `row_${byMember.size}`;
      const row = ensure(key, name || key);
      for (const skill of AI_SKILLS) {
        row.ratings[skill] = asRating((r.ratings as any)[skill]);
      }
      continue;
    }

    // Long shape: a single (employee, skill) row from the live ai_skills table.
    const skill = str(r.skill ?? r.skill_name) as AiSkill;
    if (!AI_SKILLS.includes(skill)) continue; // ignore unknown/empty skills
    const key = memberId || name || `row_${byMember.size}`;
    const row = ensure(key, name || key);
    row.ratings[skill] = {
      proficiency: clamp100(num(r.proficiency ?? r.score ?? r.level)),
      certified: asBool(r.certified),
    };
  }

  return Array.from(byMember.values());
}

// ---------------------------------------------------------------------------
// Local presentation helpers (color/band decisions live here; scoring in lib)
// ---------------------------------------------------------------------------

type Band = "expert" | "proficient" | "developing" | "novice";

function band(value: number): Band {
  const v = clamp100(value);
  if (v >= 85) return "expert";
  if (v >= 70) return "proficient";
  if (v >= 55) return "developing";
  return "novice";
}

const BAND_TONE: Record<Band, "success" | "info" | "warn" | "danger"> = {
  expert: "success",
  proficient: "info",
  developing: "warn",
  novice: "danger",
};

const BAND_LABEL: Record<Band, string> = {
  expert: "Expert",
  proficient: "Proficient",
  developing: "Developing",
  novice: "Novice",
};

/** Short column header so the matrix stays dense on narrow viewports. */
const SKILL_ABBR: Record<AiSkill, string> = {
  "Prompt Engineering": "Prompt Eng.",
  Cursor: "Cursor",
  "Claude Code": "Claude Code",
  Databricks: "Databricks",
  Copilot: "Copilot",
  MCP: "MCP",
  "Agent Design": "Agent Design",
  "Model Evaluation": "Model Eval",
};

const pct = (n: number) => `${Math.round(n)}%`;

// 0-100 score ring (SVG gauge) ------------------------------------------------
function ScoreRing({ value, size = 88 }: { value: number; size?: number }) {
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const p = Math.max(0, Math.min(100, value)) / 100;
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
          strokeDashoffset={c * (1 - p)}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-xl font-semibold tabular-nums text-ink">{Math.round(value)}</span>
        <span className="text-2xs uppercase tracking-eyebrow text-muted">/100</span>
      </div>
    </div>
  );
}

// KPI stat card with optional trend delta ------------------------------------
function Kpi({
  label,
  value,
  hint,
  delta,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  delta?: { dir: "up" | "down" | "flat"; text: string };
  tone?: "neutral" | "success" | "warn" | "danger";
}) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
  };
  const deltaCls =
    delta?.dir === "up" ? "text-[#16A34A]" : delta?.dir === "down" ? "text-[#DC2626]" : "text-muted";
  const glyph = delta?.dir === "up" ? "▲" : delta?.dir === "down" ? "▼" : "▬";
  return (
    <div className={`rounded-xl border border-line bg-surface p-4 shadow-soft ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight tabular-nums text-ink">{value}</div>
      <div className="mt-1 flex items-center gap-2">
        {delta && (
          <span className={`inline-flex items-center gap-1 text-xs font-medium ${deltaCls}`}>
            <span aria-hidden>{glyph}</span>
            {delta.text}
          </span>
        )}
        {hint && <span className="text-xs text-muted">{hint}</span>}
      </div>
    </div>
  );
}

// Single heatmap cell: tinted by proficiency, ring if certified ---------------
function HeatCell({ value, certified }: { value: number; certified: boolean }) {
  const color = scoreColor(value);
  // Tint intensity scales with proficiency so the matrix reads as a heatmap.
  const alpha = 0.16 + (clamp100(value) / 100) * 0.72;
  return (
    <td className="px-1.5 py-1.5">
      <div
        className="relative flex h-9 items-center justify-center rounded-md text-xs font-semibold tabular-nums"
        style={{
          backgroundColor: hexWithAlpha(color, alpha),
          color: alpha > 0.55 ? "#FFFFFF" : "#0F172A",
        }}
        title={`${value}/100${certified ? " · certified" : ""}`}
      >
        {value}
        {certified && (
          <span
            aria-label="certified"
            className="absolute right-1 top-0.5 text-[9px] leading-none text-white/90"
          >
            ★
          </span>
        )}
      </div>
    </td>
  );
}

/** Compose an #RRGGBB color with an alpha into rgba() — keeps cells theme-safe. */
function hexWithAlpha(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
}

// Horizontal coverage / proficiency bar --------------------------------------
function CoverageBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-sunken">
      <div
        className="h-full rounded-full transition-[width] duration-300 ease-calm"
        style={{ width: `${Math.max(2, value)}%`, backgroundColor: scoreColor(value) }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AiSkillsMatrixPage() {
  // Interactive control: the proficiency target that defines a "gap". Changing
  // it live-recomputes coverage %, below-target counts, and the gap ranking.
  const [target, setTarget] = useState(60);
  const [sortSkill, setSortSkill] = useState<AiSkill | "overall">("overall");

  // Live skills matrix with a safe mock fallback — renders the mock until the
  // live payload loads, then swaps in NORMALIZED real data (never removing the
  // mock). The live rows are "long" (one (employee, skill) row each) and get
  // pivoted into the wide EmployeeSkills shape the UI renders.
  const { data: skillsRaw, live } = useLiveData<EmployeeSkills[]>(
    "/ai-workforce/skills",
    SKILL_MATRIX as EmployeeSkills[],
    (j) => normalizeSkills(j?.skills ?? j?.rows ?? j?.data ?? j),
  );
  // Always work with a defined, fully-shaped array regardless of payload state.
  const skills: EmployeeSkills[] = Array.isArray(skillsRaw) ? skillsRaw : [];

  // Per-skill rollups (avg proficiency, coverage at/above target, certs). ----
  const perSkill = useMemo(() => {
    return AI_SKILLS.map((skill) => {
      const profs = (skills ?? []).map((r) => num(r?.ratings?.[skill]?.proficiency));
      const denom = profs.length || 1;
      const avg = clamp100(profs.reduce((a, b) => a + b, 0) / denom);
      const atTarget = profs.filter((p) => p >= target).length;
      const certified = (skills ?? []).filter((r) => r?.ratings?.[skill]?.certified).length;
      return {
        skill,
        avg,
        atTarget,
        coverage: clamp100((atTarget / denom) * 100),
        certified,
        belowTarget: profs.length - atTarget,
      };
    });
  }, [target, skills]);

  // Org-level KPIs derived from the matrix + the live target. ----------------
  const org = useMemo(() => {
    const list = skills ?? [];
    const peopleAvgs = list.map((r) => skillAverage(r));
    const avgProficiency = clamp100(
      peopleAvgs.reduce((a, b) => a + b, 0) / (peopleAvgs.length || 1)
    );

    // Anyone holding at least one certification counts as "certified".
    const certifiedPeople = list.filter((r) =>
      AI_SKILLS.some((s) => r?.ratings?.[s]?.certified)
    ).length;

    // Total certification coverage across the whole matrix (people x skills).
    const totalCells = list.length * AI_SKILLS.length;
    const cellDenom = totalCells || 1;
    const certCells = list.reduce(
      (s, r) => s + AI_SKILLS.filter((sk) => r?.ratings?.[sk]?.certified).length,
      0
    );

    // Org coverage % = share of all (person, skill) cells at/above target.
    const atOrAbove = list.reduce(
      (s, r) => s + AI_SKILLS.filter((sk) => num(r?.ratings?.[sk]?.proficiency) >= target).length,
      0
    );
    const coveragePct = clamp100((atOrAbove / cellDenom) * 100);

    // Biggest gap = lowest-average skill (gaps already sorts widest-first).
    // skillGaps() rolls up the mock matrix, so it always returns one entry per
    // skill; the ?? fallbacks below keep org.biggest/strongest defined even if
    // that ever changes, so `org.biggest.skill` never reads from undefined.
    const gaps = skillGaps(target) ?? [];
    const EMPTY_GAP = {
      skill: AI_SKILLS[0],
      avgProficiency: 0,
      belowTarget: 0,
      certifiedCount: 0,
      needsUpskilling: [] as ReadonlyArray<string>,
    };
    const biggest = gaps[0] ?? EMPTY_GAP;
    const strongest = gaps[gaps.length - 1] ?? EMPTY_GAP;

    return {
      avgProficiency,
      avgBand: band(avgProficiency),
      certifiedPeople,
      headcount: list.length,
      certCells,
      certCoveragePct: clamp100((certCells / cellDenom) * 100),
      coveragePct,
      biggest,
      strongest,
      gaps,
    };
  }, [target, skills]);

  // Employee rows for the heatmap, ranked by the selected sort skill. --------
  const rows = useMemo(() => {
    const scored = (skills ?? []).map((r) => ({
      row: r,
      overall: skillAverage(r),
      sortValue:
        sortSkill === "overall"
          ? skillAverage(r)
          : num(r?.ratings?.[sortSkill]?.proficiency),
    }));
    return scored.sort(
      (a, b) =>
        b.sortValue - a.sortValue ||
        str(a.row?.name).localeCompare(str(b.row?.name)),
    );
  }, [sortSkill, skills]);

  // Widest gaps for the side panel (worst three skills by average). ----------
  const topGaps = useMemo(() => org.gaps.slice(0, 3), [org.gaps]);

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="People · AI Enablement"
        title="AI Skills Matrix"
        subtitle="Where the workforce stands across eight AI-native skills — Prompt Engineering, Cursor, Claude Code, Databricks, Copilot, MCP, Agent Design, and Model Evaluation. Spot certified depth, expose coverage holes, and prioritize the widest skill gaps before AI-assisted work scales."
        actions={
          <div className="flex items-center gap-2">
            <Pill tone={live ? "success" : "neutral"}>{live ? "Live" : "Sample"}</Pill>
            <Pill tone="info">
              {org.headcount} people · {AI_SKILLS.length} skills
            </Pill>
            <Pill tone={BAND_TONE[org.avgBand]}>{BAND_LABEL[org.avgBand]} org avg</Pill>
          </div>
        }
      />

      {/* Executive KPI row */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi
          label="Avg AI proficiency"
          value={`${org.avgProficiency}`}
          tone={org.avgBand === "novice" ? "danger" : org.avgBand === "expert" ? "success" : "neutral"}
          delta={{ dir: "up", text: "+6 vs last quarter" }}
          hint="org mean, 0–100"
        />
        <Kpi
          label="Certified employees"
          value={`${org.certifiedPeople}/${org.headcount}`}
          delta={{ dir: "up", text: `+2 QoQ` }}
          hint={`${org.certCells} certs across matrix`}
        />
        <Kpi
          label="Biggest skill gap"
          value={org.biggest.skill}
          tone="warn"
          delta={{ dir: "down", text: `${org.biggest.avgProficiency} avg` }}
          hint={`${org.biggest.belowTarget} below target`}
        />
        <Kpi
          label="Skill coverage"
          value={pct(org.coveragePct)}
          tone={org.coveragePct < 50 ? "warn" : "success"}
          delta={{ dir: "flat", text: `≥ ${target} target` }}
          hint={`${org.headcount * AI_SKILLS.length} cells scored`}
        />
      </div>

      {/* Target control + org proficiency profile */}
      <Surface>
        <SectionTitle
          eyebrow="Calibration"
          title="Proficiency target"
          description="Set the bar that defines coverage and a skill gap. Coverage %, below-target counts, and the gap ranking below recompute live."
          trailing={<Pill tone="accent">target ≥ {target}</Pill>}
        />
        <div className="mt-4 grid grid-cols-1 gap-6 md:grid-cols-[auto_1fr] md:items-center">
          <div className="flex items-center gap-4">
            <ScoreRing value={org.avgProficiency} />
            <div className="text-xs text-muted">
              <div className="font-semibold text-ink">Org rollup</div>
              <div className="mt-0.5">Mean of {org.headcount} people</div>
              <div className="mt-1">
                <Pill tone={BAND_TONE[org.avgBand]}>{BAND_LABEL[org.avgBand]}</Pill>
              </div>
            </div>
          </div>
          <div>
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="target" className="text-xs font-medium text-body">
                Coverage target
              </label>
              <span className="text-sm font-semibold tabular-nums text-ink">{target} / 100</span>
            </div>
            <input
              id="target"
              type="range"
              min={40}
              max={90}
              step={5}
              value={target}
              onChange={(e) => setTarget(Number(e.target.value))}
              className="mt-2 w-full accent-[#0F766E]"
            />
            <div className="mt-3 grid grid-cols-3 gap-3">
              <div className="rounded-lg border border-line bg-canvas p-3">
                <div className="fp-eyebrow">Coverage</div>
                <div className="mt-0.5 text-lg font-semibold tabular-nums text-ink">
                  {pct(org.coveragePct)}
                </div>
              </div>
              <div className="rounded-lg border border-line bg-canvas p-3">
                <div className="fp-eyebrow">Cert coverage</div>
                <div className="mt-0.5 text-lg font-semibold tabular-nums text-ink">
                  {pct(org.certCoveragePct)}
                </div>
              </div>
              <div className="rounded-lg border border-line bg-canvas p-3">
                <div className="fp-eyebrow">Strongest</div>
                <div className="mt-0.5 truncate text-sm font-semibold text-ink" title={org.strongest.skill}>
                  {org.strongest.skill}
                </div>
              </div>
            </div>
          </div>
        </div>
      </Surface>

      {/* Heatmap matrix: employees x skills */}
      <Surface pad="none">
        <div className="p-5">
          <SectionTitle
            eyebrow="Heatmap"
            title="Employee × skill proficiency"
            description="Each cell is a 0–100 proficiency, tinted by strength. A ★ marks a held certification. Click a column header to rank people by that skill."
            trailing={
              <div className="flex items-center gap-2 text-2xs text-muted">
                <LegendSwatch label="Novice" color="#DC2626" />
                <LegendSwatch label="Developing" color="#D97706" />
                <LegendSwatch label="Proficient" color="#0F766E" />
                <LegendSwatch label="Expert" color="#16A34A" />
              </div>
            }
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] border-t border-line text-sm">
            <thead>
              <tr className="bg-sunken text-left text-2xs uppercase tracking-eyebrow text-muted">
                <th className="sticky left-0 z-10 bg-sunken px-5 py-2 font-medium">Employee</th>
                {AI_SKILLS.map((skill) => {
                  const active = sortSkill === skill;
                  return (
                    <th key={skill} className="px-1.5 py-2 text-center font-medium">
                      <button
                        onClick={() => setSortSkill(active ? "overall" : skill)}
                        className={`inline-flex items-center gap-1 whitespace-nowrap rounded px-1 py-0.5 hover:text-ink ${
                          active ? "text-ink" : ""
                        }`}
                        title={`Sort by ${skill}`}
                      >
                        {SKILL_ABBR[skill]}
                        {active && <span aria-hidden>▼</span>}
                      </button>
                    </th>
                  );
                })}
                <th className="px-3 py-2 text-center font-medium">
                  <button
                    onClick={() => setSortSkill("overall")}
                    className={`rounded px-1 py-0.5 hover:text-ink ${sortSkill === "overall" ? "text-ink" : ""}`}
                  >
                    Overall
                  </button>
                </th>
                <th className="px-5 py-2 font-medium">Band</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {(rows ?? []).map(({ row, overall }, idx) => {
                const b = band(overall);
                const memberId = str(row?.memberId);
                return (
                  <tr key={memberId || `row_${idx}`} className="hover:bg-sunken/60">
                    <td className="sticky left-0 z-10 bg-surface px-5 py-2 align-middle">
                      <div className="font-medium text-ink">{str(row?.name) || "Unknown"}</div>
                      <div className="text-2xs text-muted">{memberId}</div>
                    </td>
                    {AI_SKILLS.map((skill) => (
                      <HeatCell
                        key={skill}
                        value={num(row?.ratings?.[skill]?.proficiency)}
                        certified={!!row?.ratings?.[skill]?.certified}
                      />
                    ))}
                    <td className="px-3 py-2 text-center">
                      <span
                        className="inline-flex h-7 w-9 items-center justify-center rounded-md text-xs font-semibold tabular-nums text-white"
                        style={{ backgroundColor: scoreColor(overall) }}
                      >
                        {overall}
                      </span>
                    </td>
                    <td className="px-5 py-2">
                      <Pill tone={BAND_TONE[b]}>{BAND_LABEL[b]}</Pill>
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr className="border-t border-line bg-sunken/50 text-2xs uppercase tracking-eyebrow text-muted">
                <td className="sticky left-0 z-10 bg-sunken/50 px-5 py-2 font-medium">Skill avg</td>
                {(perSkill ?? []).map((s) => (
                  <td key={s.skill} className="px-1.5 py-2 text-center">
                    <span
                      className="font-semibold tabular-nums"
                      style={{ color: scoreColor(s.avg) }}
                    >
                      {s.avg}
                    </span>
                  </td>
                ))}
                <td className="px-3 py-2 text-center font-semibold tabular-nums text-ink">
                  {org.avgProficiency}
                </td>
                <td className="px-5 py-2" />
              </tr>
            </tfoot>
          </table>
        </div>
      </Surface>

      {/* Coverage bars + skill gaps */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.5fr_1fr]">
        {/* Per-skill coverage */}
        <Surface>
          <SectionTitle
            eyebrow="Coverage"
            title="Per-skill coverage & certification"
            description={`Average proficiency, the share of people at/above the ${target} target, and certification depth — for each AI skill.`}
            trailing={<span className="text-xs text-muted">{AI_SKILLS.length} skills</span>}
          />
          <div className="mt-4 space-y-3">
            {[...(perSkill ?? [])]
              .sort((a, b) => b.coverage - a.coverage || b.avg - a.avg)
              .map((s) => (
                <div key={s.skill} className="rounded-xl border border-line bg-canvas p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-ink">{s.skill}</div>
                      <div className="mt-0.5 text-2xs text-muted">
                        {s.atTarget}/{org.headcount} at target · {s.certified} certified · avg {s.avg}
                      </div>
                    </div>
                    <span
                      className="rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums text-white"
                      style={{ backgroundColor: scoreColor(s.coverage) }}
                    >
                      {pct(s.coverage)}
                    </span>
                  </div>
                  <div className="mt-2">
                    <CoverageBar value={s.coverage} />
                  </div>
                </div>
              ))}
          </div>
        </Surface>

        {/* Top skill gaps */}
        <Surface>
          <SectionTitle
            eyebrow="Risk"
            title="Top skill gaps"
            description="Widest gaps by lowest average proficiency. Each lists who to upskill first."
            trailing={<Pill tone="danger">{(org.gaps ?? []).filter((g) => g.belowTarget > 0).length} flagged</Pill>}
          />
          <ul className="mt-4 space-y-3">
            {(topGaps ?? []).map((g, i) => (
              <li key={g.skill} className="rounded-xl border border-line bg-canvas p-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[#DC2626] text-2xs font-semibold text-white">
                      {i + 1}
                    </span>
                    <div>
                      <div className="text-sm font-semibold text-ink">{g.skill}</div>
                      <div className="text-2xs text-muted">
                        {g.belowTarget} below {target} · {g.certifiedCount} certified
                      </div>
                    </div>
                  </div>
                  <span
                    className="rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums text-white"
                    style={{ backgroundColor: scoreColor(g.avgProficiency) }}
                  >
                    {g.avgProficiency}
                  </span>
                </div>
                <div className="mt-2">
                  <CoverageBar value={g.avgProficiency} />
                </div>
                {(g.needsUpskilling ?? []).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(g.needsUpskilling ?? []).slice(0, 4).map((name) => (
                      <span
                        key={name}
                        className="rounded-full border border-warn-line bg-warn-bg px-2 py-0.5 text-[11px] font-medium text-warn-fg"
                      >
                        {name}
                      </span>
                    ))}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </Surface>
      </div>
    </div>
  );
}

// Small legend swatch used in the heatmap header -----------------------------
function LegendSwatch({ label, color }: { label: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: color }} />
      {label}
    </span>
  );
}
