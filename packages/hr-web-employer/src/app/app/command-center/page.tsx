"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, LinkAction, Action, EmptyState } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Priority = { id: string; kind: string; title: string; detail: string; urgency: "urgent" | "today" | "this_week"; cta_label: string; cta_href: string; impact: string; icon: string };
type Recommendation = { id: string; headline: string; rationale: string; confidence: "low" | "medium" | "high"; requires_approval_by: string[]; suggested_action: string; horizon_days: number };
type HealthMetric = { key: string; label: string; value: number; band: "ok" | "watch" | "alert"; note: string };
type CPOReport = { headline: string; summary: string; priorities: Priority[]; recommendations: Recommendation[]; health: HealthMetric[]; generated_at: string };

const URGENCY_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  urgent: "danger",
  today: "warn",
  this_week: "neutral",
};
const BAND_TONE: Record<string, "success" | "warn" | "danger" | "neutral"> = {
  ok: "success",
  watch: "warn",
  alert: "danger",
};

const AGENTS: { key: string; label: string }[] = [
  { key: "recruiting", label: "Recruiting" },
  { key: "onboarding", label: "Onboarding" },
  { key: "compliance", label: "Compliance" },
  { key: "performance", label: "Performance" },
  { key: "compensation", label: "Compensation" },
  { key: "workforce_planning", label: "Workforce planning" },
];

export default function CommandCenter() {
  const qc = useQueryClient();
  const cpoQ = useQuery({ queryKey: ["cpo-report"], queryFn: () => apiFetch<CPOReport>("/cpo/report"), refetchInterval: 60_000 });
  const r = cpoQ.data;

  const [running, setRunning] = useState<string | null>(null);
  async function runAgent(key: string) {
    setRunning(key);
    try {
      await apiPost(`/agents/${key}/run`, {});
      await qc.invalidateQueries({ queryKey: ["cpo-report"] });
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="AI Chief People Officer"
        title={r?.headline ?? "Command center"}
        subtitle={r?.summary}
        actions={
          <>
            <Action variant="subtle" onClick={() => cpoQ.refetch()}>Refresh</Action>
            <LinkAction href="/app/exec-copilot" variant="primary">
              <IconSparkle /> Ask the copilot
            </LinkAction>
          </>
        }
      />

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        {/* Priorities */}
        <Surface className="xl:col-span-2">
          <SectionTitle eyebrow="Priorities" title="What needs attention" description="Ranked by urgency and impact." />
          <div className="mt-4">
            {(r?.priorities ?? []).length === 0 ? (
              <EmptyState title="Nothing critical right now" description="The CPO is watching. New signals will appear here." />
            ) : (
              <ul className="divide-y divide-rule">
                {r!.priorities.map((p) => (
                  <li key={p.id} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <div className="text-sm font-semibold text-ink">{p.title}</div>
                          <Pill tone={URGENCY_TONE[p.urgency] ?? "neutral"}>{p.urgency.replace("_", " ")}</Pill>
                          <span className="text-2xs uppercase tracking-eyebrow text-muted">{p.kind} · impact {p.impact}</span>
                        </div>
                        <div className="text-sm text-muted mt-0.5">{p.detail}</div>
                      </div>
                      <LinkAction href={p.cta_href} size="sm" variant="subtle">
                        {p.cta_label} <IconArrowUpRight />
                      </LinkAction>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Surface>

        {/* Right column: health + agent runner */}
        <div className="space-y-5">
          <Surface>
            <SectionTitle eyebrow="Workforce health" title="Ambient signal" />
            <div className="mt-4 space-y-2.5">
              {(r?.health ?? []).map((h) => (
                <div key={h.key} className="flex items-center justify-between border-b border-rule last:border-0 pb-2 last:pb-0">
                  <div className="min-w-0">
                    <div className="text-sm text-ink">{h.label}</div>
                    {h.note && <div className="text-xs text-muted truncate">{h.note}</div>}
                  </div>
                  <div className="flex items-center gap-2">
                    <Pill tone={BAND_TONE[h.band] ?? "neutral"}>{h.band}</Pill>
                    <div className="text-xl font-semibold text-ink tabular-nums w-8 text-right">{h.value}</div>
                  </div>
                </div>
              ))}
              {(!r || r.health.length === 0) && <div className="text-sm text-muted">Loading…</div>}
            </div>
          </Surface>

          <Surface>
            <SectionTitle
              eyebrow="HR agents"
              title="Run an operator"
              description="Each agent proposes next actions. Nothing executes without approval."
              trailing={<Link href="/app/agents" className="text-xs underline text-muted hover:text-ink">All agents →</Link>}
            />
            <div className="mt-3 space-y-1.5">
              {AGENTS.map((a) => (
                <button
                  key={a.key}
                  onClick={() => runAgent(a.key)}
                  disabled={running !== null}
                  className="w-full flex items-center justify-between rounded-md border border-line bg-canvas hover:bg-sunken transition-colors duration-150 ease-calm px-3 py-2 text-sm text-ink disabled:opacity-60"
                >
                  <span>{a.label} agent</span>
                  <span className="text-xs text-muted">{running === a.key ? "running…" : "run"}</span>
                </button>
              ))}
            </div>
          </Surface>
        </div>
      </div>

      {/* AI Recommendations */}
      <Surface>
        <SectionTitle
          eyebrow="Recommendations"
          title="What AI suggests next"
          description="Forward-looking moves with confidence and approval path."
        />
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          {(r?.recommendations ?? []).length === 0 ? (
            <div className="md:col-span-2"><EmptyState title="Nothing to propose" description="As workforce signal changes, recommendations will appear here." /></div>
          ) : r!.recommendations.map((rec) => (
            <div key={rec.id} className="rounded-lg border border-line p-4 bg-canvas">
              <div className="flex items-start justify-between gap-2">
                <div className="text-sm font-semibold text-ink">{rec.headline}</div>
                <Pill tone={rec.confidence === "high" ? "success" : rec.confidence === "medium" ? "warn" : "neutral"}>{rec.confidence}</Pill>
              </div>
              <div className="text-sm text-body mt-1">{rec.rationale}</div>
              <div className="text-sm text-muted mt-2">→ {rec.suggested_action}</div>
              <div className="mt-2 text-2xs uppercase tracking-eyebrow text-muted">
                Approval: {rec.requires_approval_by.join(" · ")} · horizon {rec.horizon_days}d
              </div>
            </div>
          ))}
        </div>
      </Surface>

      <p className="text-xs text-muted">
        Foundry People CPO is a synthesis layer — not a decision authority. Every recommendation requires human approval.
        {r?.generated_at && <> Generated {new Date(r.generated_at).toLocaleString()}.</>}
      </p>
    </div>
  );
}
