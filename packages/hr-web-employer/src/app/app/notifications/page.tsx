"use client";
import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, Pill, Action, EmptyState, Divider } from "@/components/ds";
import { IconArrowUpRight, IconCheck, IconSparkle } from "@/components/icons";

type Notification = {
  id: string;
  title: string;
  detail: string;
  topic: string;
  severity: "info" | "warn" | "danger" | "success";
  cta_label: string;
  cta_href: string;
  actor?: string | null;
  read: boolean;
  snoozed_until?: string | null;
  created_at: string;
};
type NotifResponse = {
  items: Notification[];
  counts: { total: number; unread: number; by_topic: Record<string, number> };
  topics: string[];
  provenance?: { sample_notifications: number; all_sample: boolean; note: string | null };
};

const SEV_TONE: Record<string, "danger" | "warn" | "success" | "info"> = {
  danger: "danger",
  warn: "warn",
  success: "success",
  info: "info",
};
const TOPIC_LABEL: Record<string, string> = {
  hiring: "Hiring",
  compliance: "Compliance",
  risk: "Risk",
  learning: "Learning",
  recognition: "Recognition",
  system: "System",
};

function timeAgo(iso?: string) {
  if (!iso) return "—";
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 60) return "just now";
  if (d < 3600) return `${Math.round(d / 60)}m ago`;
  if (d < 86400) return `${Math.round(d / 3600)}h ago`;
  return `${Math.round(d / 86400)}d ago`;
}

export default function NotificationsPage() {
  const qc = useQueryClient();
  const [topic, setTopic] = useState<string>("");
  const [unreadOnly, setUnreadOnly] = useState(false);

  const q = useQuery({
    queryKey: ["notifications", topic, unreadOnly],
    queryFn: () => apiFetch<NotifResponse>(`/notifications?${unreadOnly ? "unread_only=true&" : ""}${topic ? `topic=${topic}` : ""}`),
    refetchInterval: 60_000,
  });

  const items = q.data?.items ?? [];

  async function markRead(id: string, read: boolean) {
    await apiPost(`/notifications/${id}/${read ? "read" : "unread"}`, {});
    await q.refetch();
  }

  async function markAllRead() {
    await apiPost("/notifications/read-all", {});
    await q.refetch();
  }

  async function snooze(id: string) {
    await apiPost(`/notifications/${id}/snooze`, { hours: 24 });
    await q.refetch();
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Operations"
        title="Notifications"
        subtitle="Proactive alerts grouped by topic. Mark as read, snooze, or open the workflow."
        actions={
          <>
            <Action variant="subtle" onClick={() => setUnreadOnly((v) => !v)}>
              {unreadOnly ? "Show all" : "Unread only"}
            </Action>
            <Action variant="primary" onClick={markAllRead}>
              <IconCheck /> Mark all read
            </Action>
          </>
        }
      />

      {/* A notification is a claim that something HAPPENED. The feed led with
          "Avery Chen flagged high attrition risk · 2H AGO · Compa-ratio below
          0.85" — about a person who does not work here — and another said
          "2 high-severity ombudsman" while the ombudsman page correctly showed
          zero cases. */}
      {q.data?.provenance?.all_sample && q.data.provenance.note && (
        <Surface pad="md">
          <div className="fp-eyebrow">Example alerts</div>
          <p className="mt-1 text-sm text-body">{q.data.provenance.note}</p>
        </Surface>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Total" value={q.data?.counts.total ?? "—"} />
        <Stat label="Unread" value={q.data?.counts.unread ?? "—"} tone={(q.data?.counts.unread ?? 0) > 0 ? "warn" : "neutral"} />
        <Stat label="Topics" value={Object.keys(q.data?.counts.by_topic ?? {}).length} />
        <Stat label="Snoozed" value={(q.data?.items ?? []).filter((n) => n.snoozed_until).length} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setTopic("")}
          className={`text-xs rounded-md px-3 py-1.5 border ${topic === "" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
        >
          All topics
        </button>
        {(q.data?.topics ?? []).map((t) => (
          <button
            key={t}
            onClick={() => setTopic(topic === t ? "" : t)}
            className={`text-xs rounded-md px-3 py-1.5 border ${topic === t ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
          >
            {TOPIC_LABEL[t] ?? t}
            <span className="ml-1.5 text-2xs uppercase tracking-eyebrow opacity-70">{q.data?.counts.by_topic?.[t] ?? 0}</span>
          </button>
        ))}
      </div>

      {q.isLoading ? (
        <Surface><EmptyState title="Loading…" /></Surface>
      ) : items.length === 0 ? (
        <Surface><EmptyState title="Nothing new" description="When the agents detect something worth your attention it'll show up here." /></Surface>
      ) : (
        <Surface pad="sm">
          <ul className="divide-y divide-rule">
            {items.map((n) => (
              <li key={n.id} className={`py-3 ${n.read ? "opacity-70" : ""}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3 min-w-0 flex-1">
                    <span className={`mt-1 inline-block h-2.5 w-2.5 rounded-full border-2 shrink-0 ${
                      n.severity === "danger" ? "bg-danger-fg border-danger-fg"
                      : n.severity === "warn" ? "bg-warn-fg border-warn-fg"
                      : n.severity === "success" ? "bg-success-fg border-success-fg"
                      : "bg-info-fg border-info-fg"
                    }`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-ink">{n.title}</span>
                        <Pill tone="neutral">{TOPIC_LABEL[n.topic] ?? n.topic}</Pill>
                        <Pill tone={SEV_TONE[n.severity] ?? "info"}>{n.severity}</Pill>
                        {n.actor && <span className="text-2xs uppercase tracking-eyebrow text-muted">{n.actor}</span>}
                      </div>
                      <div className="text-sm text-muted mt-0.5">{n.detail}</div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">{timeAgo(n.created_at)}</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Link href={n.cta_href} className="h-7 px-2.5 rounded-md text-xs text-body border border-line bg-surface hover:bg-sunken flex items-center gap-1">
                      {n.cta_label} <IconArrowUpRight />
                    </Link>
                    <button onClick={() => snooze(n.id)} className="h-7 px-2.5 rounded-md text-xs text-body border border-line bg-surface hover:bg-sunken">
                      Snooze 24h
                    </button>
                    <Action
                      variant={n.read ? "subtle" : "primary"}
                      size="sm"
                      onClick={() => markRead(n.id, !n.read)}
                    >
                      {n.read ? "Mark unread" : "Mark read"}
                    </Action>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Surface>
      )}
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "warn" }) {
  const ring: Record<string, string> = { neutral: "", warn: "ring-1 ring-warn-line" };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
