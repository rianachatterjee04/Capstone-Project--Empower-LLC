"use client";
/**
 * Employee home — "My Stuff" task inbox.
 *
 * The landing is an ACTION FEED, not a dashboard: the things assigned to ME
 * that need doing (sign a doc, finish an onboarding step, self-assessment due,
 * open a 1:1 agenda), ranked by urgency. Under it, a shortcut row to the four
 * real jobs, and a right rail with time-off balance, what's coming up, and my
 * current 1:1. Everything fails soft to a calm empty state.
 */
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { getUserContext } from "@/lib/auth";

import { Surface, SectionTitle, Pill, LinkAction, EmptyState, Divider } from "@/components/ds";
import { useShellState } from "@/components/ShellState";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Task = { id: string; title: string; description?: string; status: string; priority: string; source: string; due_at?: string | null };
type ChecklistTaskT = { id: string; title: string; assignee_role: string; due_date: string | null; link: string | null; status: string };
type ChecklistT = { id: string; kind: string; name: string; status: string; progress: { done: number; total: number }; tasks: ChecklistTaskT[] };
type Review = { id: string; cycle: string; status: string };
type Packet = { id: string; status: string; requested_items: Record<string, any>; submitted_items: Record<string, any> };
type Series = { id: string; cadence: string; next_date: string | null; title: string; meeting_count: number };
type MyBalance = { employee_id: string | null; policy?: string | null; balance_hours?: number; balance_days?: number | null; note?: string };
type CalItem = { id: string; kind: string; title: string; detail: string; start: string; tone?: string; cta_label?: string; cta_href?: string };

type ActionKind = "sign" | "onboarding" | "review" | "task" | "oneonone";

type ActionItem = {
  key: string;
  kind: ActionKind;
  title: string;
  detail: string;
  href: string;
  cta: string;
  dueTs: number | null;
};

const KIND_LABEL: Record<ActionKind, string> = {
  sign: "Sign",
  onboarding: "Onboarding",
  review: "Review",
  task: "Task",
  oneonone: "1:1",
};

function timeOfDayGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function dueLabel(ts: number | null): { label: string; tone: "danger" | "warn" | "neutral" } {
  if (ts == null) return { label: "When you can", tone: "neutral" };
  const days = Math.round((ts - Date.now()) / (1000 * 60 * 60 * 24));
  if (days < 0) return { label: `${Math.abs(days)}d overdue`, tone: "danger" };
  if (days === 0) return { label: "Due today", tone: "warn" };
  if (days === 1) return { label: "Due tomorrow", tone: "warn" };
  if (days <= 7) return { label: `Due in ${days}d`, tone: "warn" };
  return { label: `Due ${new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`, tone: "neutral" };
}

const ACTIVE_ONB = ["pending", "in_progress", "submitted"];

export default function Home() {
  const [ctx, setCtx] = useState<{ email: string | null } | null>(null);
  useEffect(() => { getUserContext().then((c) => setCtx({ email: c.email })); }, []);
  const { openAssistant } = useShellState();

  const tasksQ = useQuery({ queryKey: ["my-tasks-home"], queryFn: () => apiFetch<{ items: Task[] }>("/tasks?owner_role=employee"), retry: false, refetchInterval: 60_000 });
  const checklistsQ = useQuery({ queryKey: ["my-checklists-home"], queryFn: () => apiFetch<ChecklistT[]>("/checklists/me"), retry: false });
  const reviewsQ = useQuery({ queryKey: ["my-reviews-home"], queryFn: () => apiFetch<{ reviews: Review[] }>("/reviews"), retry: false });
  const packetsQ = useQuery({ queryKey: ["my-packets-home"], queryFn: () => apiFetch<Packet[]>("/onboarding/packets"), retry: false });
  const seriesQ = useQuery({ queryKey: ["my-series-home"], queryFn: () => apiFetch<{ items: Series[] }>("/one-on-ones/series"), retry: false });
  const balanceQ = useQuery({ queryKey: ["my-balance-home"], queryFn: () => apiFetch<MyBalance>("/timeoff/balances/me"), retry: false });
  const calendarQ = useQuery({ queryKey: ["my-calendar-home"], queryFn: () => apiFetch<{ items: CalItem[] }>("/calendar?days=45"), retry: false });

  const firstName = ctx?.email?.split("@")[0]?.split(".")[0]?.replace(/^\w/, (ch) => ch.toUpperCase());

  const nextSeries = useMemo(() => {
    const items = (seriesQ.data?.items ?? []).filter((s) => s.next_date);
    items.sort((a, b) => (a.next_date! < b.next_date! ? -1 : 1));
    return items[0] ?? (seriesQ.data?.items ?? [])[0] ?? null;
  }, [seriesQ.data]);

  const actions = useMemo<ActionItem[]>(() => {
    const out: ActionItem[] = [];
    const now = Date.now();

    // Open tasks assigned to me
    for (const t of tasksQ.data?.items ?? []) {
      if (t.status === "done") continue;
      const isDoc = /document|sign|policy|acknowledge|handbook/i.test(`${t.title} ${t.source}`);
      out.push({
        key: `task-${t.id}`,
        kind: isDoc ? "sign" : "task",
        title: t.title,
        detail: t.description || (isDoc ? "Review and acknowledge." : "Assigned to you."),
        href: "/app/work",
        cta: isDoc ? "Open" : "Do it",
        dueTs: t.due_at ? new Date(t.due_at).getTime() : null,
      });
    }

    // Onboarding checklist tasks that are mine and still open
    for (const cl of checklistsQ.data ?? []) {
      for (const t of cl.tasks) {
        if (t.assignee_role !== "employee" || t.status === "done") continue;
        out.push({
          key: `cl-${t.id}`,
          kind: "onboarding",
          title: t.title,
          detail: cl.name,
          href: t.link || "/app/onboarding",
          cta: "Complete",
          dueTs: t.due_date ? new Date(t.due_date).getTime() : now,
        });
      }
    }

    // Onboarding packet still in progress
    const activePacket = (packetsQ.data ?? []).find((p) => ACTIVE_ONB.includes(p.status));
    if (activePacket) {
      const req = Object.keys(activePacket.requested_items ?? {});
      const remaining = req.filter((k) => !(activePacket.submitted_items ?? {})[k]).length;
      out.push({
        key: `packet-${activePacket.id}`,
        kind: "onboarding",
        title: "Finish your onboarding paperwork",
        detail: remaining > 0 ? `${remaining} item${remaining !== 1 ? "s" : ""} left to submit` : "Submit for HR review",
        href: "/app/onboarding",
        cta: "Continue",
        dueTs: now,
      });
    }

    // Self-assessment due (review in draft)
    for (const r of reviewsQ.data?.reviews ?? []) {
      if (r.status === "draft") {
        out.push({
          key: `review-${r.id}`,
          kind: "review",
          title: "Your self-assessment is due",
          detail: `Review cycle: ${r.cycle}`,
          href: "/app/performance",
          cta: "Start",
          dueTs: now,
        });
      }
    }

    // Upcoming 1:1 agenda
    if (nextSeries?.next_date) {
      out.push({
        key: `oneonone-${nextSeries.id}`,
        kind: "oneonone",
        title: "Open your 1:1 agenda",
        detail: `${nextSeries.title} · next ${nextSeries.next_date}`,
        href: "/app/one-on-ones",
        cta: "Open",
        dueTs: new Date(nextSeries.next_date).getTime(),
      });
    }

    out.sort((a, b) => (a.dueTs ?? Number.MAX_SAFE_INTEGER) - (b.dueTs ?? Number.MAX_SAFE_INTEGER));
    return out;
  }, [tasksQ.data, checklistsQ.data, packetsQ.data, reviewsQ.data, nextSeries]);

  const loading = tasksQ.isLoading && checklistsQ.isLoading && reviewsQ.isLoading;
  const bal = balanceQ.data;
  const comingUp = (calendarQ.data?.items ?? []).slice(0, 3);

  return (
    <div className="space-y-7 fp-fade-in">
      {/* Hero */}
      <section>
        <div className="fp-eyebrow mb-1">{new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })} · my stuff</div>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h1 className="text-3xl font-semibold tracking-tight text-ink">
            {timeOfDayGreeting()}{firstName ? `, ${firstName}` : ""}.{" "}
            <span className="text-muted">
              {actions.length > 0 ? `${actions.length} thing${actions.length !== 1 ? "s" : ""} need you.` : "You're all caught up."}
            </span>
          </h1>
          <button
            onClick={openAssistant}
            className="h-9 px-3 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm flex items-center gap-2 text-sm"
          >
            <IconSparkle /> Ask HR anything
          </button>
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Action feed */}
        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow="Action feed"
            title="What needs you"
            description="Everything assigned to you, in one place — ranked by what's due."
            trailing={<Link href="/app/work" className="text-xs underline text-muted hover:text-ink">All my tasks →</Link>}
          />
          <div className="mt-4">
            {loading ? (
              <div className="text-sm text-muted">Loading your inbox…</div>
            ) : actions.length === 0 ? (
              <EmptyState
                title="Inbox zero. Nice."
                description="When HR or your manager assigns something — a doc to sign, an onboarding step, a review — it shows up here."
              />
            ) : (
              <ul className="divide-y divide-rule">
                {actions.map((a) => {
                  const due = dueLabel(a.dueTs);
                  return (
                    <li key={a.key} className="py-3 first:pt-0 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-2xs uppercase tracking-eyebrow text-muted">{KIND_LABEL[a.kind]}</span>
                          <span className="text-sm font-semibold text-ink">{a.title}</span>
                          <Pill tone={due.tone}>{due.label}</Pill>
                        </div>
                        <div className="text-sm text-muted mt-0.5 truncate">{a.detail}</div>
                      </div>
                      <LinkAction href={a.href} size="sm" variant="primary" className="shrink-0">
                        {a.cta} <IconArrowUpRight />
                      </LinkAction>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </Surface>

        {/* Right rail */}
        <div className="space-y-4">
          {/* Time-off balance */}
          <Surface>
            <SectionTitle eyebrow="Time off" title="My balance" trailing={<Link href="/app/pto" className="text-xs underline text-muted hover:text-ink">Request →</Link>} />
            <div className="mt-3">
              {bal && (bal.balance_hours ?? 0) >= 0 && bal.employee_id ? (
                <div className="rounded-md border border-line bg-canvas p-3">
                  <div className="text-2xl font-semibold text-ink tabular-nums">
                    {bal.balance_days != null ? `${bal.balance_days}d` : `${bal.balance_hours ?? 0}h`}
                  </div>
                  <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                    {bal.policy || "available"}{bal.balance_days != null ? ` · ${bal.balance_hours ?? 0}h` : ""}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-muted">{bal?.note || "No time-off policy assigned yet."}</div>
              )}
            </div>
          </Surface>

          {/* Current 1:1 */}
          <Surface>
            <SectionTitle eyebrow="Check-ins" title="My 1:1" trailing={<Link href="/app/one-on-ones" className="text-xs underline text-muted hover:text-ink">Open →</Link>} />
            <div className="mt-3">
              {nextSeries ? (
                <Link href="/app/one-on-ones" className="block rounded-md border border-line bg-canvas p-3 hover:bg-sunken transition-colors duration-150 ease-calm">
                  <div className="text-sm font-medium text-ink truncate">{nextSeries.title}</div>
                  <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                    {nextSeries.cadence}{nextSeries.next_date ? ` · next ${nextSeries.next_date}` : ""}
                  </div>
                </Link>
              ) : (
                <div className="text-sm text-muted">No 1:1 scheduled yet.</div>
              )}
            </div>
          </Surface>

          {/* Coming up */}
          <Surface>
            <SectionTitle eyebrow="Company" title="Coming up" />
            <div className="mt-3">
              {comingUp.length === 0 ? (
                <div className="text-sm text-muted">Nothing on the calendar.</div>
              ) : (
                <ul className="space-y-1.5">
                  {comingUp.map((c) => (
                    <li key={c.id}>
                      <Link href={c.cta_href || "/app"} className="flex items-start justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-sunken transition-colors duration-150 ease-calm">
                        <div className="min-w-0">
                          <div className="text-sm text-ink truncate">{c.title}</div>
                          <div className="text-2xs uppercase tracking-eyebrow text-muted">{new Date(c.start).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</div>
                        </div>
                        <span className="text-muted shrink-0 mt-0.5"><IconArrowUpRight /></span>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Surface>
        </div>
      </div>

      {/* Shortcut row — the four real jobs */}
      <div>
        <div className="fp-eyebrow mb-2">Jump to</div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Request time off", href: "/app/pto" },
            { label: "My pay & docs", href: "/app/payroll" },
            { label: "My 1:1s & goals", href: "/app/one-on-ones" },
            { label: "My profile", href: "/app/twin" },
          ].map((q) => (
            <Link key={q.label} href={q.href} className="group rounded-lg border border-line bg-surface px-3.5 py-3 text-sm text-body hover:text-ink hover:bg-sunken transition-colors duration-150 ease-calm flex items-center justify-between">
              <span>{q.label}</span>
              <span className="text-muted group-hover:text-ink"><IconArrowUpRight /></span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
