"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPatch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Divider } from "@/components/ds";
import { IconCheck, IconSparkle } from "@/components/icons";

type Task = {
  id: string;
  title: string;
  description?: string;
  status: "todo" | "doing" | "blocked" | "done";
  priority: "low" | "normal" | "high" | "urgent";
  source: string;
  project?: string | null;
  owner_name?: string | null;
  owner_role?: string | null;
  due_at?: string | null;
  ai_generated: boolean;
  ai_rationale?: string | null;
  tags: string[];
};

const PRIORITY_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  urgent: "danger",
  high: "warn",
  normal: "neutral",
  low: "neutral",
};

const SOURCE_LABEL: Record<string, string> = {
  onboarding: "Onboarding",
  offboarding: "Offboarding",
  performance: "Performance",
  comp: "Compensation",
  compliance: "Compliance",
  learning: "Learning",
  manual: "Manual",
};

function dueLabel(due?: string | null): { label: string; tone: "danger" | "warn" | "neutral" } {
  if (!due) return { label: "No due date", tone: "neutral" };
  const d = new Date(due);
  const now = new Date();
  const days = Math.round((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (days < 0) return { label: `${Math.abs(days)}d overdue`, tone: "danger" };
  if (days === 0) return { label: "Due today", tone: "warn" };
  if (days === 1) return { label: "Due tomorrow", tone: "warn" };
  if (days <= 7) return { label: `Due in ${days}d`, tone: "warn" };
  return { label: `Due ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`, tone: "neutral" };
}

export default function EmployeeWorkPage() {
  const qc = useQueryClient();
  // Employee lens: only employee-owned tasks. Falls back to all if API doesn't
  // know the user yet.
  const q = useQuery({
    queryKey: ["my-tasks"],
    queryFn: () => apiFetch<{ items: Task[] }>("/tasks?owner_role=employee"),
    refetchInterval: 60_000,
  });
  const items = q.data?.items ?? [];

  const [filter, setFilter] = useState<"open" | "done">("open");
  const filtered = useMemo(() => items.filter((t) => filter === "done" ? t.status === "done" : t.status !== "done"), [items, filter]);

  const byProject = useMemo(() => {
    const m = new Map<string, Task[]>();
    for (const t of filtered) {
      const k = t.project ?? "Just for me";
      m.set(k, [...(m.get(k) ?? []), t]);
    }
    return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  async function setStatus(t: Task, status: Task["status"]) {
    await apiPatch(`/tasks/${t.id}`, { status });
    await qc.invalidateQueries({ queryKey: ["my-tasks"] });
  }

  const overdue = items.filter((t) => {
    if (t.status === "done" || !t.due_at) return false;
    return new Date(t.due_at) < new Date();
  }).length;

  return (
    <div className="space-y-6 fp-fade-in">
      <PageHeader
        eyebrow="Today"
        title="My tasks"
        subtitle="Onboarding, learning, performance, and HR follow-ups — all in one place."
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Open" value={items.filter((t) => t.status !== "done").length} />
        <Stat label="Done" value={items.filter((t) => t.status === "done").length} tone="success" />
        <Stat label="Overdue" value={overdue} tone={overdue ? "warn" : "neutral"} />
        <Stat label="AI-assigned" value={items.filter((t) => t.ai_generated && t.status !== "done").length} tone="info" />
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => setFilter("open")}
          className={`text-xs rounded-md px-3 py-1.5 border ${filter === "open" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
        >
          Open
        </button>
        <button
          onClick={() => setFilter("done")}
          className={`text-xs rounded-md px-3 py-1.5 border ${filter === "done" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
        >
          Done
        </button>
      </div>

      {filtered.length === 0 ? (
        <Surface>
          <EmptyState
            title={filter === "open" ? "Inbox zero. Nice." : "Nothing completed yet"}
            description={filter === "open" ? "When HR or your manager assigns work, it shows up here." : undefined}
          />
        </Surface>
      ) : (
        byProject.map(([project, list]) => (
          <Surface key={project} pad="sm">
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="fp-eyebrow">Project</div>
                <div className="text-sm font-semibold text-ink">{project}</div>
              </div>
              <div className="text-2xs uppercase tracking-eyebrow text-muted">{list.length} task{list.length !== 1 ? "s" : ""}</div>
            </div>
            <ul className="divide-y divide-rule">
              {list.map((t) => {
                const due = dueLabel(t.due_at);
                return (
                  <li key={t.id} className="py-3 flex items-start gap-3">
                    <button
                      onClick={() => setStatus(t, t.status === "done" ? "todo" : "done")}
                      className={[
                        "mt-0.5 h-5 w-5 rounded-full border flex items-center justify-center transition-colors duration-150 ease-calm shrink-0",
                        t.status === "done"
                          ? "bg-success-fg border-success-fg text-canvas"
                          : "bg-surface border-line text-muted hover:bg-sunken",
                      ].join(" ")}
                    >
                      {t.status === "done" ? <IconCheck size={12} /> : null}
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={t.status === "done" ? "text-sm line-through text-muted" : "text-sm font-medium text-ink"}>{t.title}</span>
                        <Pill tone={PRIORITY_TONE[t.priority]}>{t.priority}</Pill>
                        <Pill tone="neutral">{SOURCE_LABEL[t.source] ?? t.source}</Pill>
                        {t.ai_generated && <span className="text-2xs uppercase tracking-eyebrow text-muted flex items-center gap-1"><IconSparkle size={12}/> AI</span>}
                      </div>
                      {t.description && <div className="text-xs text-muted mt-0.5">{t.description}</div>}
                      {t.ai_rationale && <div className="text-xs text-muted mt-0.5 italic">{t.ai_rationale}</div>}
                      <div className="mt-1.5 flex items-center gap-2 text-2xs uppercase tracking-eyebrow text-muted">
                        {t.owner_role ? <span>{t.owner_role}</span> : null}
                        <Pill tone={due.tone}>{due.label}</Pill>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          </Surface>
        ))
      )}

      <Divider />
      <p className="text-xs text-muted">Tasks live in a single workforce execution layer — anything HR, your manager, or the agents propose will surface here.</p>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" | "info" }) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    info: "ring-1 ring-info-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
