"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Divider } from "@/components/ds";
import { IconArrowUpRight } from "@/components/icons";

type ActivityEvent = {
  id: string;
  kind: string;
  title: string;
  detail: string;
  actor?: string | null;
  actor_role?: string | null;
  subject?: string | null;
  cta_href?: string | null;
  severity: "neutral" | "info" | "warn" | "success" | "danger";
  created_at: string;
};
type Feed = { items: ActivityEvent[]; counts: Record<string, number>; kinds: string[] };

const KIND_LABEL: Record<string, string> = {
  workflow: "Workflow",
  agent: "Agent",
  task: "Task",
  people: "People",
  compliance: "Compliance",
  comp: "Comp",
  hire: "Hire",
  system: "System",
};

const SEV_TONE: Record<string, "neutral" | "info" | "warn" | "success" | "danger"> = {
  neutral: "neutral",
  info: "info",
  warn: "warn",
  success: "success",
  danger: "danger",
};

function groupByDay(items: ActivityEvent[]): Array<{ day: string; events: ActivityEvent[] }> {
  const m = new Map<string, ActivityEvent[]>();
  for (const e of items) {
    const d = e.created_at ? new Date(e.created_at).toDateString() : "Unknown";
    m.set(d, [...(m.get(d) ?? []), e]);
  }
  return Array.from(m.entries()).map(([day, events]) => ({ day, events }));
}

function timeAgo(iso?: string) {
  if (!iso) return "—";
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

export default function ActivityPage() {
  const [kind, setKind] = useState<string>("");
  const q = useQuery({
    queryKey: ["activity", kind],
    queryFn: () => apiFetch<Feed>(`/activity/feed?limit=120${kind ? `&kind=${kind}` : ""}`),
    refetchInterval: 60_000,
  });

  const items = q.data?.items ?? [];
  const groups = useMemo(() => groupByDay(items), [items]);
  const counts = q.data?.counts ?? {};

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Operations"
        title="Activity timeline"
        subtitle="The org's universal audit-style feed. Every workflow, agent run, task update, and compliance moment in one calm timeline."
      />

      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setKind("")}
          className={`text-xs rounded-md px-3 py-1.5 border ${kind === "" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
        >
          All · {items.length}
        </button>
        {Object.entries(counts).map(([k, n]) => (
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
      ) : items.length === 0 ? (
        <Surface><EmptyState title="No activity yet" description="As workflows happen and agents run, they'll surface here." /></Surface>
      ) : (
        <div className="space-y-5">
          {groups.map(({ day, events }) => (
            <Surface key={day} pad="sm">
              <div className="fp-eyebrow mb-2 px-1">{day}</div>
              <ol className="relative">
                {events.map((e, i) => {
                  const last = i === events.length - 1;
                  return (
                    <li key={e.id} className="relative pl-7 pb-3 last:pb-0">
                      {!last && <span aria-hidden className="absolute left-[5px] top-3 bottom-0 w-px bg-line" />}
                      <span className={`absolute left-0 top-1 block h-3 w-3 rounded-full border-2 ${
                        e.severity === "danger" ? "bg-danger-fg border-danger-fg"
                        : e.severity === "warn"   ? "bg-warn-fg border-warn-fg"
                        : e.severity === "success" ? "bg-success-fg border-success-fg"
                        : e.severity === "info"   ? "bg-info-fg border-info-fg"
                        : "bg-canvas border-line"
                      }`} />
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-ink">{e.title}</span>
                            <Pill tone={SEV_TONE[e.severity] ?? "neutral"}>{KIND_LABEL[e.kind] ?? e.kind}</Pill>
                            {e.actor_role && <span className="text-2xs uppercase tracking-eyebrow text-muted">{e.actor_role}</span>}
                          </div>
                          {e.detail && <div className="text-xs text-muted mt-0.5 line-clamp-2">{e.detail}</div>}
                          <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">{timeAgo(e.created_at)}</div>
                        </div>
                        {e.cta_href && (
                          <Link href={e.cta_href} className="text-xs text-muted hover:text-ink flex items-center gap-1">
                            Open <IconArrowUpRight />
                          </Link>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ol>
            </Surface>
          ))}
        </div>
      )}

      <p className="text-xs text-muted">Timeline is derived from audit events + agent runs + workforce execution. Filter to a single kind to read a thread.</p>
    </div>
  );
}
