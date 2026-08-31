"use client";
/**
 * Manager home — "Who needs my attention today".
 *
 * The north-star manager landing: a prioritized, TYPED action list (approvals
 * waiting · reviews due · overdue work · people at risk · new starters), every
 * row carrying an inline verb + a deep link, plus a compact team roster with
 * out-of-office and review-status badges.
 *
 * The brief is scoped to the SIGNED-IN manager (server resolves the actor →
 * manager). There is no manager-selector: a manager sees only their own team.
 * (In the current demo the API resolves the actor to the first roster manager;
 * when real per-user manager identity lands, the same call scopes automatically.)
 */
import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { Surface, SectionTitle, Pill, LinkAction, Action, EmptyState, Divider, Avatar } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";
import { useShellState } from "@/components/ShellState";

type Signal = {
  kind: string;
  severity: "urgent" | "today" | "this_week" | "low";
  title: string;
  detail: string;
  cta_label: string;
  cta_href: string;
  subject?: string | null;
};
type ManagerBrief = {
  generated_at: string;
  manager_name: string;
  department: string;
  headline: string;
  summary: string;
  counts: {
    approvals_pending: number;
    tasks_open: number;
    tasks_overdue: number;
    team_size: number;
    team_high_risk: number;
    team_medium_risk: number;
    hiring_in_motion: number;
  };
  signals: Signal[];
  suggested_actions: Signal[];
};

type Employee = {
  id: string;
  legal_name: string;
  preferred_name?: string | null;
  job_title?: string | null;
  department?: string | null;
  status: string;
};
type CalItem = { id: string; employee_id: string; employee_name: string | null; start_date: string; end_date: string; status: string };
type Review = { id: string; employee_id: string; cycle: string; status: string };

const SEV_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  urgent: "danger",
  today: "warn",
  this_week: "neutral",
  low: "neutral",
};

const KIND_LABEL: Record<string, string> = {
  approval: "Approve",
  attrition: "Retain",
  review: "Review",
  hiring: "Hiring",
  recognition: "Recognize",
  learning: "Coach",
};

function reviewBadge(status?: string): { label: string; tone: "success" | "warn" | "info" | "neutral" } {
  switch (status) {
    case "finalized": return { label: "Review done", tone: "success" };
    case "manager_submitted": return { label: "Awaiting finalize", tone: "warn" };
    case "calibration": return { label: "In calibration", tone: "info" };
    case "draft": return { label: "Self-review open", tone: "warn" };
    default: return { label: "No review", tone: "neutral" };
  }
}

function iso(d: Date) { return d.toISOString().slice(0, 10); }

export function ManagerHome() {
  const { openAssistant } = useShellState();

  // Signed-in manager's brief — server scopes to the actor. No selector.
  const briefQ = useQuery({
    queryKey: ["manager-brief-me"],
    queryFn: () => apiFetch<ManagerBrief>("/manager-brief/today"),
    refetchInterval: 60_000,
  });
  const b = briefQ.data;
  const department = b?.department;

  // Compact team roster — department-scoped, with OOO + review badges.
  const employeesQ = useQuery({
    queryKey: ["employees-roster"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });
  const today = iso(new Date());
  const oooQ = useQuery({
    queryKey: ["team-ooo", today],
    queryFn: () => apiFetch<CalItem[]>(`/timeoff/calendar?start=${today}&end=${today}`),
    retry: false,
  });
  const reviewsQ = useQuery({
    queryKey: ["team-reviews"],
    queryFn: () => apiFetch<{ reviews: Review[] }>("/reviews"),
    retry: false,
  });

  const roster = useMemo(() => {
    const all = employeesQ.data ?? [];
    const active = all.filter((e) => !["terminated", "offboarded"].includes(e.status));
    const scoped = department ? active.filter((e) => e.department === department) : active;
    return (scoped.length ? scoped : active).slice(0, 8);
  }, [employeesQ.data, department]);

  const outToday = useMemo(() => {
    const set = new Set<string>();
    for (const c of oooQ.data ?? []) if (c.status === "approved") set.add(c.employee_id);
    return set;
  }, [oooQ.data]);

  const reviewByEmp = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of reviewsQ.data?.reviews ?? []) if (!m.has(r.employee_id)) m.set(r.employee_id, r.status);
    return m;
  }, [reviewsQ.data]);

  const c = b?.counts;
  const signals = b?.signals ?? [];

  return (
    <div className="space-y-7 fp-fade-in">
      {/* Header */}
      <section>
        <div className="fp-eyebrow mb-1">
          {new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })} · manager
        </div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-ink max-w-3xl">
              Who needs my attention today
            </h1>
            <p className="mt-2 text-sm text-body max-w-2xl">
              {b?.summary ?? "Pulling together approvals, reviews, and people signals for your team…"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            {b?.manager_name && (
              <Pill tone="neutral">
                <Avatar name={b.manager_name} size={16} />
                <span className="ml-1">{b.manager_name}{b.department ? ` · ${b.department}` : ""}</span>
              </Pill>
            )}
            <button
              onClick={openAssistant}
              className="h-9 px-3 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm flex items-center gap-2 text-sm"
            >
              <IconSparkle /> Ask the assistant
            </button>
          </div>
        </div>
      </section>

      {/* Typed counts */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <CountStat label="Approvals waiting" value={c?.approvals_pending ?? "—"} href="/app/pto" tone={(c?.approvals_pending ?? 0) > 0 ? "warn" : "neutral"} />
        <CountStat label="Reviews on you" value={reviewsQ.data ? (reviewsQ.data.reviews.filter((r) => r.status === "manager_submitted" || r.status === "draft").length) : "—"} href="/app/performance" tone="neutral" />
        <CountStat label="Overdue work" value={c?.tasks_overdue ?? "—"} href="/app/work?owner_role=manager" tone={(c?.tasks_overdue ?? 0) > 0 ? "danger" : "neutral"} />
        <CountStat label="People at risk" value={c ? c.team_high_risk + c.team_medium_risk : "—"} href="/app/risk" tone={(c?.team_high_risk ?? 0) > 0 ? "danger" : (c?.team_medium_risk ?? 0) > 0 ? "warn" : "neutral"} />
        <CountStat label="New starters" value={c?.hiring_in_motion ?? "—"} href="/app/talent" tone="neutral" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Typed action list */}
        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow="Action feed"
            title="What needs you today"
            description="Ranked by urgency. Every row is a decision you can make from here."
            trailing={<Link href="/app/inbox" className="text-xs underline text-muted hover:text-ink">Open inbox →</Link>}
          />
          <div className="mt-4">
            {briefQ.isLoading ? (
              <div className="text-sm text-muted">Loading your brief…</div>
            ) : signals.length === 0 ? (
              <EmptyState title="Nothing urgent" description="Steady week. A good time to invest in 1:1s and growth conversations." />
            ) : (
              <ul className="divide-y divide-rule">
                {signals.map((s, i) => (
                  <li key={i} className="py-3 first:pt-0 flex items-start justify-between gap-3">
                    <div className="min-w-0 flex items-start gap-3">
                      {s.subject && <Avatar name={s.subject} size={28} />}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-2xs uppercase tracking-eyebrow text-muted">{KIND_LABEL[s.kind] ?? s.kind}</span>
                          <span className="text-sm font-semibold text-ink">{s.title}</span>
                          <Pill tone={SEV_TONE[s.severity] ?? "neutral"}>{s.severity.replace("_", " ")}</Pill>
                        </div>
                        <div className="text-sm text-muted mt-0.5">{s.detail}</div>
                      </div>
                    </div>
                    <LinkAction href={s.cta_href} size="sm" variant="primary" className="shrink-0">
                      {s.cta_label} <IconArrowUpRight />
                    </LinkAction>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {(b?.suggested_actions ?? []).length > 0 && (
            <>
              <Divider className="my-4" />
              <div className="fp-eyebrow mb-2">Calm actions worth doing</div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {b!.suggested_actions.slice(0, 4).map((s, i) => (
                  <Link key={i} href={s.cta_href} className="block rounded-md border border-line bg-canvas px-3 py-2 hover:bg-sunken transition-colors duration-150 ease-calm">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm text-ink flex items-center gap-2">
                          {s.subject && <Avatar name={s.subject} size={18} />}
                          <span className="truncate">{s.title}</span>
                        </div>
                        <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5 truncate">{s.detail}</div>
                      </div>
                      <span className="text-muted shrink-0"><IconArrowUpRight /></span>
                    </div>
                  </Link>
                ))}
              </div>
            </>
          )}
        </Surface>

        {/* Team roster */}
        <Surface>
          <SectionTitle
            eyebrow="My team"
            title={department ? `${department}` : "Direct reports"}
            trailing={<Link href="/app/people" className="text-xs underline text-muted hover:text-ink">Directory →</Link>}
          />
          <div className="mt-3">
            {employeesQ.isLoading ? (
              <div className="text-sm text-muted">Loading team…</div>
            ) : roster.length === 0 ? (
              <EmptyState title="No team yet" description="Your direct reports will appear here." />
            ) : (
              <ul className="space-y-1">
                {roster.map((e) => {
                  const name = e.preferred_name || e.legal_name;
                  const out = outToday.has(e.id);
                  const rb = reviewBadge(reviewByEmp.get(e.id));
                  return (
                    <li key={e.id}>
                      <Link href={`/app/people/${e.id}`} className="flex items-center justify-between gap-2 rounded-md px-2 py-2 hover:bg-sunken transition-colors duration-150 ease-calm">
                        <div className="flex items-center gap-2 min-w-0">
                          <Avatar name={name} size={26} />
                          <div className="min-w-0">
                            <div className="text-sm text-ink truncate">{name}</div>
                            <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">{e.job_title || e.department || "—"}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 shrink-0">
                          {out && <Pill tone="warn">Out today</Pill>}
                          <Pill tone={rb.tone}>{rb.label}</Pill>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
          <Divider className="my-3" />
          <div className="grid grid-cols-2 gap-2">
            <LinkAction href="/app/one-on-ones" variant="subtle" className="w-full">1:1s</LinkAction>
            <LinkAction href="/app/performance" variant="subtle" className="w-full">Reviews</LinkAction>
          </div>
        </Surface>
      </div>

      {b?.generated_at && (
        <p className="text-xs text-muted">Scoped to your team · brief generated {new Date(b.generated_at).toLocaleString()}.</p>
      )}
    </div>
  );
}

function CountStat({ label, value, href, tone = "neutral" }: { label: string; value: React.ReactNode; href: string; tone?: "neutral" | "warn" | "danger" }) {
  const ring = tone === "danger" ? "ring-1 ring-danger-line" : tone === "warn" ? "ring-1 ring-warn-line" : "";
  return (
    <Link href={href} className={`rounded-md border border-line bg-surface p-4 hover:bg-sunken transition-colors duration-150 ease-calm ${ring}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </Link>
  );
}
