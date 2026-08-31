"use client";
/**
 * Workflow Automations — visual trigger → action builder + run history.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Action, EmptyState, PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import { IconCheck, IconClose, IconSparkle } from "@/components/icons";

type Trigger = { key: string; label: string; category: string; schedule: boolean };
type ActionDef = { key: string; label: string; category: string };
type Taxonomy = { triggers: Trigger[]; actions: ActionDef[] };
type Template = { id: string; name: string; description: string; trigger_key: string; filters: Record<string, string>; actions: { key: string; label: string }[] };
type AutoAction = { key: string; label: string; params?: Record<string, any> };
type Automation = {
  id: string; name: string; description: string;
  trigger_key: string; filters: Record<string, string>; actions: AutoAction[];
  enabled: boolean; template_id?: string | null;
  runs_total: number; runs_success: number; runs_failed: number;
  last_run_at?: string | null; last_run_status?: string | null;
  created_at: string;
};
type Run = {
  id: string; automation_id: string; automation_name: string;
  triggered_at: string; trigger_key: string;
  actions_attempted: number; actions_succeeded: number;
  status: string; log: string[];
};

const STATUS_TONE: Record<string, "success" | "warn" | "danger" | "neutral"> = {
  success: "success", partial: "warn", failed: "danger", pending: "neutral",
};

export default function AutomationsPage() {
  const [tab, setTab] = useState<"library" | "templates" | "runs">("library");
  const taxQ = useQuery({ queryKey: ["auto-tax"], queryFn: () => apiFetch<Taxonomy>("/automations/taxonomy") });
  const tplQ = useQuery({ queryKey: ["auto-tpl"], queryFn: () => apiFetch<{ items: Template[] }>("/automations/templates") });
  const autoQ = useQuery({ queryKey: ["auto-list"], queryFn: () => apiFetch<{ items: Automation[] }>("/automations") });
  const runsQ = useQuery({ queryKey: ["auto-runs"], queryFn: () => apiFetch<{ items: Run[] }>("/automations/runs") });

  const taxonomy = taxQ.data;
  const templates = tplQ.data?.items ?? [];
  const automations = autoQ.data?.items ?? [];
  const runs = runsQ.data?.items ?? [];

  async function installTemplate(id: string) {
    await apiPost(`/automations/templates/${id}/install`, {});
    autoQ.refetch();
    setTab("library");
  }

  async function trigger(id: string) {
    await apiPost(`/automations/${id}/trigger`, {});
    runsQ.refetch();
    autoQ.refetch();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="AI Ops · Automations"
        title="Workflow Automations"
        subtitle="When X happens, do Y. Build your own loops or install from the library. Every run is audit-trailed."
      />

      <div className="flex flex-wrap gap-2">
        {([
          ["library", `Installed (${automations.length})`],
          ["templates", `Library (${templates.length})`],
          ["runs", `Run history (${runs.length})`],
        ] as const).map(([k, lbl]) => (
          <Action key={k} variant={tab === k ? "primary" : "subtle"} size="sm" onClick={() => setTab(k)}>{lbl}</Action>
        ))}
      </div>

      {tab === "library" && (
        <Surface>
          <SectionTitle eyebrow="Your automations" title="Installed and active" />
          {automations.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="No automations installed"
                description="Install one from the library, or build your own."
                action={<Action variant="primary" onClick={() => setTab("templates")}>Browse library</Action>}
              />
            </div>
          ) : (
            <div className="mt-4 space-y-3">
              {automations.map((a) => (
                <div key={a.id} className="rounded-md border border-line bg-canvas p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="text-sm font-semibold text-ink">{a.name}</div>
                        {a.enabled ? <Pill tone="success">enabled</Pill> : <Pill tone="neutral">paused</Pill>}
                      </div>
                      <div className="text-xs text-muted mt-0.5">{a.description}</div>
                      <div className="mt-2 flex flex-wrap items-center gap-1.5">
                        <Pill tone="info">trigger: {a.trigger_key}</Pill>
                        {a.actions.map((act, i) => (
                          <Pill key={i} tone="neutral">→ {act.label || act.key}</Pill>
                        ))}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Action variant="subtle" size="sm" onClick={() => trigger(a.id)}>
                        <IconSparkle /> Run now
                      </Action>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-3 text-2xs uppercase tracking-eyebrow text-muted">
                    <span>{a.runs_total} runs</span>
                    <span>{a.runs_success} success</span>
                    <span>{a.runs_failed} failed</span>
                    {a.last_run_at && (
                      <span>last {new Date(a.last_run_at).toLocaleString()}{a.last_run_status ? ` · ${a.last_run_status}` : ""}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Surface>
      )}

      {tab === "templates" && (
        <Surface>
          <SectionTitle eyebrow="Library" title="Pre-built automations" description="One-click install. Each maps to an existing AI agent or workflow." />
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            {templates.map((t) => (
              <div key={t.id} className="rounded-md border border-line bg-canvas p-4">
                <div className="text-sm font-semibold text-ink">{t.name}</div>
                <div className="text-xs text-muted mt-0.5">{t.description}</div>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  <Pill tone="info">trigger: {t.trigger_key}</Pill>
                  {t.actions.map((act, i) => (
                    <Pill key={i} tone="neutral">→ {act.label}</Pill>
                  ))}
                </div>
                <div className="mt-3">
                  <Action variant="primary" size="sm" onClick={() => installTemplate(t.id)}>
                    <IconCheck /> Install
                  </Action>
                </div>
              </div>
            ))}
          </div>
        </Surface>
      )}

      {tab === "runs" && (
        <Surface>
          <SectionTitle eyebrow="Run history" title="Recent automation runs" description="Audit-trailed. Useful when something fires unexpectedly." />
          {runs.length === 0 ? (
            <div className="mt-3"><EmptyState title="No runs yet" description="Trigger an automation to see runs here." /></div>
          ) : (
            <div className="mt-4 space-y-2">
              {runs.map((r) => (
                <div key={r.id} className="rounded-md border border-line bg-canvas p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-ink">{r.automation_name}</div>
                      <div className="text-xs text-muted">{new Date(r.triggered_at).toLocaleString()} · trigger {r.trigger_key}</div>
                    </div>
                    <Pill tone={STATUS_TONE[r.status] ?? "neutral"}>{r.status}</Pill>
                  </div>
                  <div className="mt-2 text-2xs uppercase tracking-eyebrow text-muted">
                    {r.actions_succeeded}/{r.actions_attempted} actions succeeded
                  </div>
                  {r.log.length > 0 && (
                    <ul className="mt-1 text-xs text-body space-y-0.5">
                      {r.log.map((line, i) => <li key={i} className="font-mono">• {line}</li>)}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </Surface>
      )}

      {/* Taxonomy reference for the curious */}
      {taxonomy && tab === "library" && (
        <Surface>
          <SectionTitle eyebrow="Taxonomy" title="Available triggers + actions" description="Build your own automation by combining these." />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div>
              <div className="fp-eyebrow mb-1">Triggers</div>
              <div className="flex flex-wrap gap-1">
                {taxonomy.triggers.map((t) => <Pill key={t.key} tone="neutral">{t.label}</Pill>)}
              </div>
            </div>
            <div>
              <div className="fp-eyebrow mb-1">Actions</div>
              <div className="flex flex-wrap gap-1">
                {taxonomy.actions.map((a) => <Pill key={a.key} tone="neutral">{a.label}</Pill>)}
              </div>
            </div>
          </div>
        </Surface>
      )}
    </div>
  );
}
