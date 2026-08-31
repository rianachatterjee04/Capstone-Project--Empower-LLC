"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, LinkAction, EmptyState, Divider } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

/* ---------------------------------------------------------------------------
 * Types echo only the slices of each API we consume here.
 * ------------------------------------------------------------------------- */
type Priority = {
  id: string; kind: string; title: string; detail: string;
  urgency: "urgent" | "today" | "this_week";
  cta_label: string; cta_href: string; impact: string; icon: string;
};
type Recommendation = {
  id: string; headline: string; rationale: string;
  confidence: "low" | "medium" | "high";
  requires_approval_by: string[];
  suggested_action: string;
  horizon_days: number;
};
type CPOReport = { headline: string; summary: string; priorities: Priority[]; recommendations: Recommendation[]; generated_at: string };

type AgentAction = {
  id: string; kind: string; title: string; target?: string;
  payload: any; approval_required: boolean; rationale: string;
};
type AgentRun = {
  id: string; agent: string;
  started_at: string;
  summary: string; actions: AgentAction[];
  confidence: "low" | "medium" | "high";
};

type CaseItem = {
  id: string; category: string; severity: "high" | "medium" | "low";
  status: string; is_anonymous: boolean; created_at: string | null;
  summary?: string;
};

/* ---------------------------------------------------------------------------
 * Lane definitions — drives the side rail.
 * ------------------------------------------------------------------------- */
type LaneId = "approvals" | "agent_actions" | "case_triage" | "my_reviews";

const LANES: { id: LaneId; label: string; eyebrow: string }[] = [
  // Labelled "Priorities", not "Approvals". This lane reads CPO priorities and
  // recommendations; /app/approvals reads the approvals queue. Calling both
  // "Approvals" put a 3 on this rail while that page correctly said inbox
  // zero, and a reader has no way to tell that those are different questions.
  { id: "approvals",     label: "Priorities",    eyebrow: "Workflow" },
  { id: "agent_actions", label: "Agent actions", eyebrow: "AI Ops" },
  { id: "case_triage",   label: "Case triage",   eyebrow: "Compliance" },
  { id: "my_reviews",    label: "My drafts",     eyebrow: "Performance" },
];

const URGENCY_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  urgent: "danger",
  today: "warn",
  this_week: "neutral",
};
const SEV_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  high: "danger",
  medium: "warn",
  low: "neutral",
};

/* ---------------------------------------------------------------------------
 * Page
 * ------------------------------------------------------------------------- */
export default function InboxPage() {
  const qc = useQueryClient();
  const [active, setActive] = useState<LaneId>("approvals");

  const cpoQ = useQuery({
    queryKey: ["cpo-report-inbox-page"],
    queryFn: () => apiFetch<CPOReport>("/cpo/report"),
    refetchInterval: 60_000,
  });
  const agentsQ = useQuery({
    queryKey: ["agent-runs-inbox"],
    queryFn: () => apiFetch<{ items: AgentRun[] }>("/agents/runs"),
    refetchInterval: 90_000,
  });
  const casesQ = useQuery({
    queryKey: ["ombudsman-inbox"],
    queryFn: () => apiFetch<{ role_view: string; items: CaseItem[] }>("/ombudsman"),
    refetchInterval: 120_000,
  });

  // Approvals = CPO priorities (urgent first), then CPO recommendations.
  type ApprovalRow = {
    id: string;
    title: string;
    detail: string;
    urgency: string;
    href: string;
    cta: string;
    meta?: string;
    tone: "danger" | "warn" | "neutral";
  };
  const approvals = useMemo<ApprovalRow[]>(() => {
    const r = cpoQ.data;
    if (!r) return [];
    const prio: ApprovalRow[] = r.priorities.map((p) => ({
      id: p.id,
      title: p.title,
      detail: p.detail,
      urgency: p.urgency.replace("_", " "),
      tone: URGENCY_TONE[p.urgency] ?? "neutral",
      href: p.cta_href,
      cta: p.cta_label,
      meta: `${p.kind} · impact ${p.impact}`,
    }));
    const recs: ApprovalRow[] = r.recommendations.map((rec) => ({
      id: rec.id,
      title: rec.headline,
      detail: rec.suggested_action,
      urgency: `${rec.horizon_days || "—"}d horizon`,
      tone: rec.confidence === "medium" ? "warn" : "neutral",
      href: "/app/command-center",
      cta: "Review",
      meta: `Approval: ${rec.requires_approval_by.join(" · ")}`,
    }));
    return [...prio, ...recs];
  }, [cpoQ.data]);

  // Agent actions = each run's approval-required actions.
  const agentActions = useMemo(() => {
    const runs = agentsQ.data?.items ?? [];
    const rows: { id: string; agent: string; agentLabel: string; title: string; detail: string; runId: string; kind: string }[] = [];
    for (const run of runs) {
      for (const a of run.actions) {
        if (!a.approval_required) continue;
        rows.push({
          id: a.id,
          agent: run.agent,
          agentLabel: run.agent.replace(/_/g, " "),
          title: a.title,
          detail: a.rationale,
          runId: run.id,
          kind: a.kind,
        });
      }
    }
    return rows;
  }, [agentsQ.data]);

  const [approving, setApproving] = useState<string | null>(null);
  async function approveAction(agent: string, actionId: string) {
    setApproving(actionId);
    try {
      await apiPost(`/agents/${agent}/approve-action/${actionId}`, {});
      await qc.invalidateQueries({ queryKey: ["agent-runs-inbox"] });
    } finally {
      setApproving(null);
    }
  }

  // Cases — high severity / open
  const caseRows = useMemo(() => {
    const items = casesQ.data?.items ?? [];
    const open = items.filter((c) => c.status !== "closed");
    return open.sort((a, b) => {
      const order = { high: 0, medium: 1, low: 2 } as Record<string, number>;
      return (order[a.severity] ?? 9) - (order[b.severity] ?? 9);
    });
  }, [casesQ.data]);

  // DRAFTS ARE NOT WIRED, SO THERE ARE NONE.
  //
  // This used to return two hardcoded rows — "Your Q2 self review" and "2 peer
  // reviews requested" — under a comment saying "show realistic placeholders
  // ... Empty state is honest". The empty state was never reached, because the
  // array was never empty. The rail counted them as 2 items of work waiting on
  // the reader, and both CTAs opened /app/performance, which correctly says
  // "No review cycle is running yet".
  //
  // An inbox is a list of things you have to do. Two of its four lanes
  // disagreeing with the pages they link to is how a user learns to ignore the
  // count.
  const myDrafts: { id: string; title: string; detail: string; href: string; cta: string }[] = useMemo(
    () => [],
    [],
  );

  // Lane counts for the rail
  const counts: Record<LaneId, number> = {
    approvals: approvals.length,
    agent_actions: agentActions.length,
    case_triage: caseRows.length,
    my_reviews: myDrafts.length,
  };

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Workspace"
        title="Inbox"
        subtitle={cpoQ.data?.headline ?? "Everything that needs you, grouped by workflow."}
        actions={
          <>
            <Action variant="subtle" onClick={() => { cpoQ.refetch(); agentsQ.refetch(); casesQ.refetch(); }}>Refresh</Action>
            <LinkAction href="/app/command-center" variant="primary">Open command center</LinkAction>
          </>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-5">
        {/* Lane rail */}
        <Surface pad="sm">
          <div className="fp-eyebrow mb-2">Lanes</div>
          <nav className="space-y-0.5">
            {LANES.map((l) => {
              const isActive = active === l.id;
              const n = counts[l.id];
              return (
                <button
                  key={l.id}
                  onClick={() => setActive(l.id)}
                  className={[
                    "w-full flex items-center justify-between rounded-md px-2.5 py-2 text-sm",
                    "transition-colors duration-150 ease-calm",
                    isActive ? "bg-canvas text-ink" : "text-body hover:bg-sunken hover:text-ink",
                  ].join(" ")}
                >
                  <span>
                    <span className="block text-2xs uppercase tracking-eyebrow text-muted">{l.eyebrow}</span>
                    <span className="font-medium">{l.label}</span>
                  </span>
                  <span className="text-xs tabular-nums text-muted">{n}</span>
                </button>
              );
            })}
          </nav>
          <Divider className="my-3" />
          <p className="text-xs text-muted px-1">
            Lanes read the live CPO, agent and ombudsman APIs. Review drafts appear
            here once a performance cycle is running.
          </p>
        </Surface>

        {/* Lane content */}
        <div>
          {active === "approvals" && (
            <Surface>
              <SectionTitle
                eyebrow="CPO + recommendations"
                title="Priorities & recommendations"
                description="From the CPO report. The approvals queue itself is on /app/approvals."
              />
              <div className="mt-3">
                {approvals.length === 0 ? (
                  <EmptyState title="Inbox zero" description="Nothing waiting on you." />
                ) : (
                  <ul className="divide-y divide-rule">
                    {approvals.map((p) => (
                      <li key={p.id} className="py-3 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-ink">{p.title}</span>
                            <Pill tone={p.tone ?? "neutral"}>{p.urgency}</Pill>
                            {p.meta && <span className="text-2xs uppercase tracking-eyebrow text-muted">{p.meta}</span>}
                          </div>
                          <div className="text-sm text-muted mt-0.5">{p.detail}</div>
                        </div>
                        <LinkAction href={p.href} size="sm" variant="subtle">
                          {p.cta} <IconArrowUpRight />
                        </LinkAction>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Surface>
          )}

          {active === "agent_actions" && (
            <Surface>
              <SectionTitle
                eyebrow="HR agents"
                title="Actions awaiting your approval"
                description="Each row was proposed by an AI agent. Approve to record, then execute in-context."
                trailing={<Link href="/app/agents" className="text-xs underline text-muted hover:text-ink">All agents →</Link>}
              />
              <div className="mt-3">
                {agentActions.length === 0 ? (
                  <EmptyState
                    title="No agent actions pending"
                    description="Run an agent from the command center to populate this lane."
                    action={<LinkAction href="/app/agents" size="sm" variant="primary">Open agents</LinkAction>}
                  />
                ) : (
                  <ul className="divide-y divide-rule">
                    {agentActions.map((a) => (
                      <li key={`${a.runId}-${a.id}`} className="py-3 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-ink">{a.title}</span>
                            <Pill tone="info">{a.kind.replace("_", " ")}</Pill>
                            <span className="text-2xs uppercase tracking-eyebrow text-muted">{a.agentLabel} agent</span>
                          </div>
                          <div className="text-sm text-muted mt-0.5">{a.detail}</div>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <LinkAction href={`/app/agents?agent=${a.agent}`} size="sm" variant="subtle">View</LinkAction>
                          <Action
                            size="sm"
                            variant="primary"
                            onClick={() => approveAction(a.agent, a.id)}
                            disabled={approving === a.id}
                          >
                            {approving === a.id ? "Recording…" : "Approve"}
                          </Action>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Surface>
          )}

          {active === "case_triage" && (
            <Surface>
              <SectionTitle
                eyebrow="Ombudsman"
                title="Cases needing triage"
                description="Confidentiality-first. Cases here are visible to HR + legal only."
                trailing={<Link href="/app/ombudsman" className="text-xs underline text-muted hover:text-ink">Open ombudsman →</Link>}
              />
              <div className="mt-3">
                {caseRows.length === 0 ? (
                  <EmptyState title="No open cases" description="Reports submitted here will surface for triage." />
                ) : (
                  <ul className="divide-y divide-rule">
                    {caseRows.map((c) => (
                      <li key={c.id} className="py-3 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold capitalize text-ink">{c.category.replace(/_/g, " ")}</span>
                            <Pill tone={SEV_TONE[c.severity] ?? "neutral"}>{c.severity}</Pill>
                            <span className="text-2xs uppercase tracking-eyebrow text-muted">{c.is_anonymous ? "anonymous" : "named"} · {c.status}</span>
                          </div>
                          {c.summary && <div className="text-sm text-muted mt-0.5 line-clamp-2">{c.summary}</div>}
                          {c.created_at && <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">{new Date(c.created_at).toLocaleString()}</div>}
                        </div>
                        <LinkAction href="/app/ombudsman" size="sm" variant="subtle">
                          Triage <IconArrowUpRight />
                        </LinkAction>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </Surface>
          )}

          {active === "my_reviews" && (
            <Surface>
              <SectionTitle
                eyebrow="Performance"
                title="My drafts"
                description="Reviews you owe and peer feedback you've been asked for."
                trailing={<Link href="/app/performance" className="text-xs underline text-muted hover:text-ink">Open cycle →</Link>}
              />
              <div className="mt-3">
                {myDrafts.length === 0 ? (
                  <EmptyState title="No drafts in your queue" />
                ) : (
                  <ul className="divide-y divide-rule">
                    {myDrafts.map((d) => (
                      <li key={d.id} className="py-3 flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-semibold text-ink">{d.title}</div>
                          <div className="text-sm text-muted mt-0.5">{d.detail}</div>
                        </div>
                        <LinkAction href={d.href} size="sm" variant="subtle">{d.cta} <IconArrowUpRight /></LinkAction>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-2xs uppercase tracking-eyebrow text-muted mt-3">
                  AI · <IconSparkle /> coach checks vague language inline as you draft.
                </p>
              </div>
            </Surface>
          )}
        </div>
      </div>

      <p className="text-xs text-muted">
        Inbox is generated from the live CPO + agents + ombudsman APIs. Nothing is auto-acted; every approval writes to the audit log.
      </p>
    </div>
  );
}
