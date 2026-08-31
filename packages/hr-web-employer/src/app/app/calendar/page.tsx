"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Avatar } from "@/components/ds";
import { IconArrowUpRight } from "@/components/icons";

type CalEvent = {
  id: string;
  kind: string;
  title: string;
  detail?: string;
  subject?: string | null;
  start: string;
  end?: string | null;
  all_day: boolean;
  tone: "neutral" | "info" | "warn" | "success" | "danger";
  cta_label?: string | null;
  cta_href?: string | null;
  /** An illustrative entry shipped with the product, not from your records. */
  is_sample?: boolean;
};
type CalResponse = { items: CalEvent[]; counts: Record<string, number>; window_days: number };

const KIND_LABEL: Record<string, string> = {
  pto: "Time off",
  anniversary: "Anniversary",
  cycle: "Cycle",
  learning: "Learning",
  hiring: "Hiring",
  onboarding: "Onboarding",
  system: "System",
};

const TONE_PILL: Record<string, "info" | "warn" | "success" | "danger" | "neutral"> = {
  info: "info", warn: "warn", success: "success", danger: "danger", neutral: "neutral",
};

function dayKey(iso: string): string {
  return new Date(iso).toDateString();
}

function formatDay(iso: string): { day: string; weekday: string; month: string; raw: Date } {
  const d = new Date(iso);
  return {
    day: d.getDate().toString().padStart(2, "0"),
    weekday: d.toLocaleDateString(undefined, { weekday: "short" }),
    month: d.toLocaleDateString(undefined, { month: "short" }),
    raw: d,
  };
}

export default function CalendarPage() {
  const [window_, setWindow] = useState(30);
  const [kind, setKind] = useState<string>("");
  const q = useQuery({
    queryKey: ["calendar", window_],
    queryFn: () => apiFetch<CalResponse>(`/calendar?days=${window_}`),
    refetchInterval: 90_000,
  });

  const items = q.data?.items ?? [];
  const filtered = useMemo(() => kind ? items.filter((e) => e.kind === kind) : items, [items, kind]);

  // Group by day
  const groups = useMemo(() => {
    const m = new Map<string, CalEvent[]>();
    for (const e of filtered) {
      const k = e.start ? dayKey(e.start) : "Unknown";
      m.set(k, [...(m.get(k) ?? []), e]);
    }
    return Array.from(m.entries()).map(([day, events]) => ({ day, events })).sort((a, b) => new Date(a.day).getTime() - new Date(b.day).getTime());
  }, [filtered]);

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Operations"
        title="People calendar"
        subtitle="Time off · anniversaries · cycle milestones · hiring · learning — all on one clean timeline."
        actions={
          <select
            value={window_}
            onChange={(e) => setWindow(Number(e.target.value))}
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink"
          >
            {[14, 30, 60, 90].map((d) => <option key={d} value={d}>Next {d} days</option>)}
          </select>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Events" value={items.length} />
        <Stat label="This week" value={items.filter((e) => {
          const days = (new Date(e.start).getTime() - Date.now()) / 86_400_000;
          return days >= -1 && days <= 7;
        }).length} />
        <Stat label="Kinds" value={Object.keys(q.data?.counts ?? {}).length} />
        <Stat label="Window" value={`${q.data?.window_days ?? "—"}d`} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        <button onClick={() => setKind("")} className={`text-xs rounded-md px-3 py-1.5 border ${kind === "" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>All</button>
        {Object.entries(q.data?.counts ?? {}).map(([k, n]) => (
          <button
            key={k}
            onClick={() => setKind(kind === k ? "" : k)}
            className={`text-xs rounded-md px-3 py-1.5 border ${kind === k ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
          >
            {KIND_LABEL[k] ?? k} · {n}
          </button>
        ))}
      </div>

      {q.isLoading ? (
        <Surface><EmptyState title="Loading…" /></Surface>
      ) : filtered.length === 0 ? (
        <Surface><EmptyState title="No events in this window" description="Try expanding the window or clearing the filter." /></Surface>
      ) : (
        <div className="space-y-3">
          {groups.map(({ day, events }) => {
            const d = formatDay(day);
            const isToday = d.raw.toDateString() === new Date().toDateString();
            return (
              <Surface key={day} pad="sm">
                <div className="flex items-start gap-4">
                  <div className="shrink-0 w-14 text-center">
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">{d.month}</div>
                    <div className={`text-2xl font-bold tabular-nums ${isToday ? "text-ink" : "text-body"}`}>{d.day}</div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">{d.weekday}</div>
                    {isToday && <div className="mt-1 text-2xs uppercase tracking-eyebrow text-ink font-bold">today</div>}
                  </div>
                  <div className="flex-1 min-w-0 space-y-2">
                    {events.map((e) => (
                      <div key={e.id} className="rounded-md border border-line bg-canvas hover:bg-sunken transition-colors duration-150 ease-calm">
                        <div className="px-3 py-2.5 flex items-start justify-between gap-3">
                          <div className="min-w-0 flex items-start gap-2.5">
                            {e.subject ? <Avatar name={e.subject} size={26} /> : <span className="h-6 w-6 rounded-full bg-sunken inline-block shrink-0" aria-hidden />}
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-sm font-medium text-ink">{e.title}</span>
                                {/* "Diego Marin · offer expires" and "SOC 2 training
                                    due · 3 employees overdue" sat on the same timeline
                                    as PTO and start dates read from this org's records.
                                    The second is a compliance claim about a company
                                    with one employee. */}
                                {e.is_sample && (
                                  <span className="rounded bg-sunken px-1.5 py-0.5 text-2xs uppercase tracking-wide text-muted">
                                    sample
                                  </span>
                                )}
                                <Pill tone={TONE_PILL[e.tone] ?? "neutral"}>{KIND_LABEL[e.kind] ?? e.kind}</Pill>
                              </div>
                              {e.detail && <div className="text-xs text-muted mt-0.5 line-clamp-2">{e.detail}</div>}
                              {e.end && e.end !== e.start && (
                                <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                                  → {new Date(e.end).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                                </div>
                              )}
                            </div>
                          </div>
                          {e.cta_href && (
                            <Link href={e.cta_href} className="text-xs text-muted hover:text-ink flex items-center gap-1 shrink-0">
                              {e.cta_label ?? "Open"} <IconArrowUpRight />
                            </Link>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </Surface>
            );
          })}
        </div>
      )}

      <p className="text-xs text-muted">Calendar pulls live PTO + employee anniversaries from your HR data, plus cycle and operational milestones.</p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4">
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
