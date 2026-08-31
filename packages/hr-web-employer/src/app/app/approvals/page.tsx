"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Avatar, Divider } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Approval = {
  id: string;
  kind: string;
  title: string;
  detail: string;
  requested_by?: string | null;
  requires_role: string;
  severity: "urgent" | "normal" | "low";
  created_at: string;
  cta_label: string;
  cta_href: string;
  approve_endpoint?: string | null;
  deny_endpoint?: string | null;
  payload: Record<string, unknown>;
};
type Unavailable = { topic: string; reason: string; needs: string };
type ApprovalsResponse = {
  items: Approval[];
  counts: { total: number; by_kind: Record<string, number>; by_severity: Record<string, number> };
  unavailable?: Unavailable[];
};

const KIND_LABEL: Record<string, string> = {
  pto: "PTO",
  onboarding_packet: "Onboarding",
  offer: "Offer",
  agent_action: "Agent action",
  comp_letter: "Compensation",
  expense: "Expense",
};

const SEV_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  urgent: "danger",
  normal: "warn",
  low: "neutral",
};

export default function ApprovalsPage() {
  const qc = useQueryClient();
  const [kind, setKind] = useState<string>("");
  const [busy, setBusy] = useState<string>("");

  const q = useQuery({
    queryKey: ["approvals", kind],
    queryFn: () => apiFetch<ApprovalsResponse>(`/approvals-center${kind ? `?kind=${kind}` : ""}`),
    refetchInterval: 60_000,
  });
  const data = q.data;
  const items = data?.items ?? [];
  const counts = data?.counts;

  const urgentCount = counts?.by_severity?.urgent ?? 0;

  async function approve(a: Approval) {
    if (!a.approve_endpoint) return;
    setBusy(a.id);
    try {
      await apiPost(a.approve_endpoint, {});
    } catch {}
    setBusy("");
    await q.refetch();
    await qc.invalidateQueries({ queryKey: ["cpo-priority-count"] });
  }
  async function deny(a: Approval) {
    if (!a.deny_endpoint) return;
    setBusy(a.id);
    try {
      await apiPost(a.deny_endpoint, {});
    } catch {}
    setBusy("");
    await q.refetch();
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Operations"
        title="Approvals"
        subtitle="One queue for everything you owe — PTO, comp, packets, offers, and agent actions. Approve, deny, or open the workflow."
        actions={<Action variant="subtle" onClick={() => q.refetch()}>Refresh</Action>}
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Pending" value={counts?.total ?? "—"} />
        <Stat label="Urgent" value={urgentCount} tone={urgentCount ? "danger" : "neutral"} />
        <Stat label="Routine" value={counts?.by_severity?.normal ?? "—"} tone={(counts?.by_severity?.normal ?? 0) ? "warn" : "neutral"} />
        <Stat label="Sources" value={Object.keys(counts?.by_kind ?? {}).length} />
      </div>

      {/* Kind filter chips */}
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setKind("")}
          className={`text-xs rounded-md px-3 py-1.5 border ${kind === "" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
        >
          All {counts?.total ? `· ${counts.total}` : ""}
        </button>
        {Object.entries(counts?.by_kind ?? {}).map(([k, n]) => (
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
        <Surface>
          <EmptyState title="Inbox zero" description="Nothing waiting on you." />
        </Surface>
      ) : (
        <Surface pad="sm">
          <ul className="divide-y divide-rule">
            {items.map((a) => (
              <li key={a.id} className="py-3 flex items-start justify-between gap-3">
                <div className="flex items-start gap-3 min-w-0 flex-1">
                  {a.requested_by ? <Avatar name={a.requested_by} size={32} /> : <span className="h-8 w-8 rounded-full bg-sunken inline-block shrink-0" aria-hidden />}
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-ink">{a.title}</span>
                      <Pill tone={SEV_TONE[a.severity] ?? "neutral"}>{a.severity}</Pill>
                      <Pill tone="neutral">{KIND_LABEL[a.kind] ?? a.kind}</Pill>
                      <span className="text-2xs uppercase tracking-eyebrow text-muted">{a.requires_role}</span>
                    </div>
                    <div className="text-sm text-muted mt-0.5 line-clamp-2">{a.detail}</div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <Link
                    href={a.cta_href}
                    className="h-7 px-2.5 rounded-md text-xs text-body border border-line bg-surface hover:bg-sunken flex items-center gap-1"
                  >
                    Open <IconArrowUpRight />
                  </Link>
                  {a.deny_endpoint && (
                    <Action variant="subtle" size="sm" onClick={() => deny(a)} disabled={busy === a.id}>
                      Deny
                    </Action>
                  )}
                  {a.approve_endpoint && (
                    <Action variant="primary" size="sm" onClick={() => approve(a)} disabled={busy === a.id}>
                      {busy === a.id ? "…" : "Approve"}
                    </Action>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Surface>
      )}

      <Surface inset hairline={false} className="bg-transparent p-0">
        <SectionTitle eyebrow="Related" title="Where these came from" />
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "PTO queue", href: "/app/pto" },
            { label: "Onboarding", href: "/app/onboarding" },
            { label: "Talent pipeline", href: "/app/talent" },
            { label: "Agent actions", href: "/app/agents", aiHinted: true },
            { label: "Comp review", href: "/app/comp", aiHinted: true },
            { label: "Inbox", href: "/app/inbox" },
            { label: "Activity timeline", href: "/app/activity" },
            { label: "Notifications", href: "/app/notifications" },
          ].map((q) => (
            <Link key={q.label} href={q.href} className="group rounded-lg border border-line bg-surface px-3.5 py-3 text-sm text-body hover:text-ink hover:bg-sunken transition-colors duration-150 ease-calm flex items-center justify-between">
              <span className="flex items-center gap-2">
                {q.label}
                {q.aiHinted && <span className="text-2xs uppercase tracking-eyebrow text-muted group-hover:text-ink">AI</span>}
              </span>
              <span className="text-muted group-hover:text-ink"><IconArrowUpRight /></span>
            </Link>
          ))}
        </div>
      </Surface>

      {/* Two invented approvals used to sit in this list — a comp letter and a
          promotion with an "89% role-fit per marketplace" — beside real offers
          and agent actions, with nothing marking them apart. A queue exists to
          be acted on; a fake row in it teaches the user to distrust the real
          ones. The gap is stated instead. */}
      {(q.data?.unavailable?.length ?? 0) > 0 && (
        <Surface pad="lg">
          <div className="fp-eyebrow">Not routed here yet</div>
          <ul className="mt-2 space-y-2">
            {(q.data?.unavailable ?? []).map((u) => (
              <li key={u.topic} className="text-sm">
                <span className="font-medium text-ink">{u.topic}</span>
                <span className="text-body"> — {u.reason}</span>
                <span className="block text-xs text-muted">Needs: {u.needs}</span>
              </li>
            ))}
          </ul>
        </Surface>
      )}
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "danger" | "warn" }) {
  const ring: Record<string, string> = {
    neutral: "",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
