"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Divider, LinkAction } from "@/components/ds";
import { IconArrowUpRight, IconCheck, IconCircle, IconSparkle } from "@/components/icons";

type Step = {
  id: string;
  title: string;
  description: string;
  owner: string;
  cta_label?: string | null;
  cta_href?: string | null;
  done: boolean;
};
type Checklist = {
  generated_at: string;
  steps: Step[];
  summary: { done: number; total: number; completion_percent: number; next_step_id: string | null; complete: boolean };
};

export default function SetupPage() {
  const q = useQuery({
    queryKey: ["setup-checklist"],
    queryFn: () => apiFetch<Checklist>("/setup/checklist"),
    refetchInterval: 30_000,
  });
  const c = q.data;

  const next = c?.steps.find((s) => s.id === c.summary.next_step_id);
  const completedSteps = c?.steps.filter((s) => s.done) ?? [];
  const openSteps = c?.steps.filter((s) => !s.done) ?? [];

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Onboarding"
        title="Set up Foundry"
        subtitle="A calm guided checklist. As you complete steps elsewhere, they tick off here automatically."
        actions={<LinkAction href="/app/settings" variant="primary">Open settings</LinkAction>}
      />

      <Surface pad="lg">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="fp-eyebrow">Progress</div>
            <div className="mt-1 text-4xl font-bold tracking-tight text-ink tabular-nums">
              {c?.summary.completion_percent ?? "—"}%
            </div>
            <div className="mt-1 text-sm text-muted">
              {c?.summary.done ?? "—"} of {c?.summary.total ?? "—"} steps complete
            </div>
          </div>
          {next ? (
            <Link
              href={next.cta_href ?? "/app/settings"}
              className="rounded-lg border border-line bg-canvas hover:bg-sunken transition-colors duration-150 ease-calm px-4 py-3 max-w-sm"
            >
              <div className="fp-eyebrow flex items-center gap-1.5"><IconSparkle size={12} /> Next step</div>
              <div className="text-sm font-semibold text-ink mt-1">{next.title}</div>
              <div className="text-xs text-muted mt-0.5 line-clamp-2">{next.description}</div>
              <div className="mt-2 text-xs text-ink flex items-center gap-1">{next.cta_label ?? "Open"} <IconArrowUpRight /></div>
            </Link>
          ) : c?.summary.complete ? (
            <Pill tone="success">All set — Foundry is ready</Pill>
          ) : null}
        </div>
        <div className="mt-4 h-2 rounded-full bg-sunken overflow-hidden">
          <div className="h-full bg-accent transition-all duration-200" style={{ width: `${c?.summary.completion_percent ?? 0}%` }} />
        </div>
      </Surface>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Surface>
          <SectionTitle eyebrow="Open" title="Steps to complete" />
          {openSteps.length === 0 ? (
            <EmptyState title="Nothing left" description="Foundry is fully configured. Nice." />
          ) : (
            <ul className="mt-3 space-y-2">
              {openSteps.map((s) => (
                <li key={s.id} className="rounded-md border border-line bg-canvas p-3">
                  <div className="flex items-start gap-3">
                    <span className="mt-1 h-4 w-4 rounded-full border-2 border-line bg-surface shrink-0" />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-ink">{s.title}</div>
                      <div className="text-xs text-muted mt-0.5">{s.description}</div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">Owner · {s.owner}</div>
                    </div>
                    {s.cta_href && (
                      <Link href={s.cta_href} className="text-xs text-ink hover:underline flex items-center gap-1 shrink-0">
                        {s.cta_label ?? "Open"} <IconArrowUpRight />
                      </Link>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Surface>

        <Surface>
          <SectionTitle eyebrow="Done" title="Already complete" />
          {completedSteps.length === 0 ? (
            <div className="mt-3 text-sm text-muted">Nothing complete yet. Start with the first open step on the left.</div>
          ) : (
            <ul className="mt-3 space-y-2">
              {completedSteps.map((s) => (
                <li key={s.id} className="rounded-md border border-success-line bg-success-bg/40 p-3">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 h-4 w-4 rounded-full bg-success-fg text-canvas flex items-center justify-center shrink-0"><IconCheck size={10} /></span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-success-fg">{s.title}</div>
                      <div className="text-xs text-success-fg/80 mt-0.5 line-through decoration-success-line">{s.description}</div>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>

      <p className="text-xs text-muted">
        This checklist updates live from the rest of Foundry — connect an integration, invite an employee, or install an agent and the relevant step ticks off automatically.
      </p>
    </div>
  );
}
