"use client";
/**
 * Admin / owner home — "People Ops Cockpit".
 *
 * Two calm bands:
 *   1. Lifecycle in motion — onboarding + offboarding in progress (progress
 *      rings) and the active review-cycle completion tracker.
 *   2. Health at a glance — headcount, open reqs, turnover trend, latest eNPS.
 *
 * ONE primary action ("+ Hire / Onboard"). Reports + org chart are one click
 * away, not spread across the home as charts.
 */
import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { Surface, SectionTitle, Pill, LinkAction, EmptyState, Divider } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";
import { useShellState } from "@/components/ShellState";

type Packet = {
  id: string;
  employee_id: string;
  status: string;
  requested_items: Record<string, any>;
  submitted_items: Record<string, any>;
  created_at: string;
};
type Checklist = {
  id: string;
  kind: string;
  name: string;
  status: string;
  employee_name: string | null;
  progress: { done: number; total: number };
};
type Employee = { id: string; legal_name: string; preferred_name?: string | null; status: string };
type Cycle = { name: string; status: string; opened_at?: string | null; closed_at?: string | null };
type Review = { id: string; employee_id: string; cycle: string; status: string };
type Headcount = { by_department: Record<string, number> | { department: string; count: number }[]; total: number };
type Job = { id: string; title: string; status: string };
type Attrition = { attrition_pct: number; terminations: number; window: string };
type Survey = { id: string; title: string; type: string; status: string; response_count: number };
type SurveyResults = { enps: number | null; response_count: number; participation_rate: number | null };

const ACTIVE_ONB = ["pending", "in_progress", "submitted", "completed", "verified"];

function pct(done: number, total: number) {
  if (!total) return 0;
  return Math.round((done / total) * 100);
}

/** Small progress ring — SVG, currentColor-friendly. */
function Ring({ value, size = 40 }: { value: number; size?: number }) {
  const stroke = 4;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const off = circ * (1 - Math.max(0, Math.min(100, value)) / 100);
  const tone = value >= 100 ? "text-success-fg" : value >= 50 ? "text-accent" : "text-warn-fg";
  return (
    <span className="relative inline-flex items-center justify-center shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth={stroke} className="text-line" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth={stroke}
          strokeDasharray={circ} strokeDashoffset={off} strokeLinecap="round" className={tone}
        />
      </svg>
      <span className="absolute text-[10px] font-semibold tabular-nums text-ink">{value}</span>
    </span>
  );
}

export function AdminHome() {
  const { openAssistant } = useShellState();

  const packetsQ = useQuery({ queryKey: ["adm-packets"], queryFn: () => apiFetch<Packet[]>("/onboarding/packets"), retry: false });
  const checklistsQ = useQuery({ queryKey: ["adm-checklists"], queryFn: () => apiFetch<Checklist[]>("/checklists"), retry: false });
  const employeesQ = useQuery({ queryKey: ["adm-employees"], queryFn: () => apiFetch<Employee[]>("/employees"), retry: false });
  const cyclesQ = useQuery({ queryKey: ["adm-cycles"], queryFn: () => apiFetch<{ cycles: Cycle[] }>("/reviews/cycles"), retry: false });
  const reviewsQ = useQuery({ queryKey: ["adm-reviews"], queryFn: () => apiFetch<{ reviews: Review[] }>("/reviews"), retry: false });
  const headcountQ = useQuery({ queryKey: ["adm-headcount"], queryFn: () => apiFetch<Headcount>("/org-chart/headcount"), retry: false });
  const jobsQ = useQuery({ queryKey: ["adm-jobs"], queryFn: () => apiFetch<Job[]>("/recruiting/jobs"), retry: false });
  const attritionQ = useQuery({ queryKey: ["adm-attrition"], queryFn: () => apiFetch<Attrition>("/org-chart/attrition"), retry: false });
  const surveysQ = useQuery({ queryKey: ["adm-surveys"], queryFn: () => apiFetch<{ items: Survey[] }>("/engagement/surveys"), retry: false });

  const empName = useMemo(() => {
    const m = new Map<string, string>();
    for (const e of employeesQ.data ?? []) m.set(e.id, e.preferred_name || e.legal_name);
    return m;
  }, [employeesQ.data]);

  // Onboarding in motion (packets not yet activated, with real progress).
  const onboarding = useMemo(() => {
    return (packetsQ.data ?? [])
      .filter((p) => ACTIVE_ONB.includes(p.status))
      .map((p) => {
        const req = Object.keys(p.requested_items ?? {});
        const total = req.length || 4;
        const done = req.filter((k) => (p.submitted_items ?? {})[k]).length;
        return { id: p.id, name: empName.get(p.employee_id) || "New hire", status: p.status, pct: pct(done, total), done, total };
      })
      .sort((a, b) => a.pct - b.pct)
      .slice(0, 5);
  }, [packetsQ.data, empName]);

  // Offboarding in motion (checklists of kind offboarding, not complete).
  const offboarding = useMemo(() => {
    return (checklistsQ.data ?? [])
      .filter((c) => c.kind === "offboarding" && c.status !== "completed")
      .map((c) => ({ id: c.id, name: c.employee_name || c.name, status: c.status, pct: pct(c.progress.done, c.progress.total), done: c.progress.done, total: c.progress.total }))
      .slice(0, 5);
  }, [checklistsQ.data]);

  // Active review cycle + completion tracker.
  const activeCycle = useMemo(() => (cyclesQ.data?.cycles ?? []).find((c) => c.status === "open") ?? (cyclesQ.data?.cycles ?? [])[0] ?? null, [cyclesQ.data]);
  const cycleReviews = useMemo(() => {
    const rs = reviewsQ.data?.reviews ?? [];
    const scoped = activeCycle ? rs.filter((r) => r.cycle === activeCycle.name) : rs;
    const total = scoped.length;
    const finalized = scoped.filter((r) => r.status === "finalized").length;
    return { total, finalized, pct: pct(finalized, total) };
  }, [reviewsQ.data, activeCycle]);

  const headcountTotal = headcountQ.data?.total ?? null;
  const openReqs = (jobsQ.data ?? []).filter((j) => ["open", "published", "active"].includes(j.status)).length;
  const attritionPct = attritionQ.data?.attrition_pct ?? null;

  // Latest eNPS — pull results for the most recent survey (fail-soft).
  const latestSurvey = useMemo(() => {
    const items = surveysQ.data?.items ?? [];
    return items.find((s) => s.status === "open") ?? items.find((s) => s.status === "closed") ?? items[0] ?? null;
  }, [surveysQ.data]);
  const resultsQ = useQuery({
    queryKey: ["adm-survey-results", latestSurvey?.id],
    queryFn: () => apiFetch<SurveyResults>(`/engagement/surveys/${latestSurvey!.id}/results`),
    enabled: !!latestSurvey?.id,
    retry: false,
  });
  const enps = resultsQ.data?.enps ?? null;
  const responseCount = resultsQ.data?.response_count ?? 0;

  const lifecycleEmpty = onboarding.length === 0 && offboarding.length === 0 && cycleReviews.total === 0;

  return (
    <div className="space-y-7 fp-fade-in">
      {/* Header */}
      <section>
        <div className="fp-eyebrow mb-1">
          {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })} · people ops
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-ink">People Ops Cockpit</h1>
            <p className="mt-2 text-sm text-body max-w-2xl">
              Everyone in motion, and the health of the org — at a glance. Reports and the org chart are one click away.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <LinkAction href="/app/onboarding" variant="primary">+ Hire / Onboard</LinkAction>
            <button
              onClick={openAssistant}
              className="h-9 px-3 rounded-md border border-line bg-surface text-ink hover:bg-sunken transition-colors duration-150 ease-calm flex items-center gap-2 text-sm"
            >
              <IconSparkle /> Ask the assistant
            </button>
          </div>
        </div>
      </section>

      {/* Band 1 — Lifecycle in motion */}
      <Surface>
        <SectionTitle
          eyebrow="Lifecycle in motion"
          title="Who's moving through the org right now"
          description="Onboarding, offboarding, and the live review cycle — with real completion."
        />
        {lifecycleEmpty ? (
          <div className="mt-4"><EmptyState title="Nothing in motion" description="No active onboarding, offboarding, or review cycle right now." /></div>
        ) : (
          <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-5">
            {/* Onboarding */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="fp-eyebrow">Onboarding</div>
                <Link href="/app/onboarding" className="text-xs underline text-muted hover:text-ink">Open →</Link>
              </div>
              {onboarding.length === 0 ? (
                <div className="text-sm text-muted">No one onboarding.</div>
              ) : (
                <ul className="space-y-2">
                  {onboarding.map((o) => (
                    <li key={o.id} className="flex items-center gap-3 rounded-md border border-line bg-canvas px-3 py-2">
                      <Ring value={o.pct} />
                      <div className="min-w-0">
                        <div className="text-sm text-ink truncate">{o.name}</div>
                        <div className="text-2xs uppercase tracking-eyebrow text-muted">{o.status.replace("_", " ")} · {o.done}/{o.total} docs</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Offboarding */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="fp-eyebrow">Offboarding</div>
                <Link href="/app/offboarding" className="text-xs underline text-muted hover:text-ink">Open →</Link>
              </div>
              {offboarding.length === 0 ? (
                <div className="text-sm text-muted">No one offboarding.</div>
              ) : (
                <ul className="space-y-2">
                  {offboarding.map((o) => (
                    <li key={o.id} className="flex items-center gap-3 rounded-md border border-line bg-canvas px-3 py-2">
                      <Ring value={o.pct} />
                      <div className="min-w-0">
                        <div className="text-sm text-ink truncate">{o.name}</div>
                        <div className="text-2xs uppercase tracking-eyebrow text-muted">{o.done}/{o.total} tasks</div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Review cycle tracker */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="fp-eyebrow">Review cycle</div>
                <Link href="/app/performance" className="text-xs underline text-muted hover:text-ink">Open →</Link>
              </div>
              {!activeCycle ? (
                <div className="text-sm text-muted">No cycle running.</div>
              ) : (
                <div className="rounded-md border border-line bg-canvas px-3 py-3 flex items-center gap-3">
                  <Ring value={cycleReviews.pct} size={52} />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-ink truncate">{activeCycle.name}</div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">
                      {cycleReviews.finalized}/{cycleReviews.total} finalized
                    </div>
                    <Pill tone={activeCycle.status === "open" ? "info" : "neutral"}>{activeCycle.status}</Pill>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </Surface>

      {/* Band 2 — Health at a glance */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="fp-eyebrow">Health at a glance</div>
          <div className="flex items-center gap-3 text-xs">
            <Link href="/app/reports" className="underline text-muted hover:text-ink">Reports →</Link>
            <Link href="/app/org" className="underline text-muted hover:text-ink">Org chart →</Link>
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <HealthStat label="Headcount" value={headcountTotal ?? "—"} hint="active people" href="/app/people" />
          <HealthStat label="Open reqs" value={jobsQ.data ? openReqs : "—"} hint="hiring now" href="/app/recruiting" />
          <HealthStat
            label="Turnover (12mo)"
            value={attritionPct != null ? `${attritionPct}%` : "—"}
            hint={attritionQ.data ? `${attritionQ.data.terminations} left` : "trailing"}
            href="/app/analytics"
            tone={attritionPct != null && attritionPct >= 15 ? "warn" : "neutral"}
          />
          {/* An eNPS is a number about a group of people. The tile named the
              survey but not how many answered it, so a score computed from a
              seeded response set looked the same as one from a real round. */}
          <HealthStat
            label="Latest eNPS"
            value={enps != null ? enps : "—"}
            hint={
              latestSurvey
                ? `${latestSurvey.title} · ${responseCount} response${responseCount === 1 ? "" : "s"}`
                : "no survey"
            }
            href="/app/engagement"
            tone={enps != null ? (enps >= 30 ? "success" : enps >= 0 ? "warn" : "danger") : "neutral"}
          />
        </div>
      </div>
    </div>
  );
}

function HealthStat({ label, value, hint, href, tone = "neutral" }: { label: string; value: React.ReactNode; hint?: string; href: string; tone?: "neutral" | "success" | "warn" | "danger" }) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
  };
  return (
    <Link href={href} className={`group rounded-lg border border-line bg-surface p-4 hover:bg-sunken transition-colors duration-150 ease-calm ${ring[tone]}`}>
      <div className="flex items-center justify-between">
        <div className="fp-eyebrow">{label}</div>
        <span className="text-muted group-hover:text-ink"><IconArrowUpRight /></span>
      </div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted truncate">{hint}</div>}
    </Link>
  );
}
