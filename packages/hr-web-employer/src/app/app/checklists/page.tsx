"use client";

/**
 * Onboarding / offboarding checklists — templated task lists per hire/exit.
 *
 * Complements /app/onboarding (document packets): checklists coordinate the
 * WORK — payroll setup (deep-linked to the payroll invite flow), equipment,
 * intros, access removal, final-check trigger — with assignees, due dates
 * and live progress. Default templates are seeded server-side.
 */
import { useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState } from "@/components/ds";

type Employee = {
  id: string;
  legal_name: string;
  email: string;
  job_title?: string | null;
  status: string;
};

type Template = {
  id: string;
  name: string;
  kind: "onboarding" | "offboarding";
  items: { title: string; category?: string; assignee_role?: string; due_days_offset?: number; link?: string | null }[];
};

type Task = {
  id: string;
  title: string;
  category: string;
  assignee_role: string;
  due_date: string | null;
  link: string | null;
  status: "open" | "done" | "skipped";
};

type ChecklistT = {
  id: string;
  kind: string;
  name: string;
  status: string;
  employee_id: string;
  employee_name: string | null;
  created_at: string | null;
  progress: { done: number; total: number };
  tasks: Task[];
};

const CATEGORY_TONE: Record<string, "info" | "success" | "warn" | "neutral" | "danger"> = {
  payroll: "warn",
  docs: "info",
  access: "danger",
  equipment: "neutral",
  intro: "success",
  general: "neutral",
};

export default function ChecklistsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-muted">Loading…</div>}>
      <ChecklistsInner />
    </Suspense>
  );
}

function ChecklistsInner() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const initialKind = params.get("kind") === "offboarding" ? "offboarding" : "onboarding";

  const [kind, setKind] = useState<"onboarding" | "offboarding">(initialKind);
  const [employeeId, setEmployeeId] = useState(params.get("employee") ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const employeesQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });
  const templatesQ = useQuery({
    queryKey: ["checklist-templates"],
    queryFn: () => apiFetch<Template[]>("/checklists/templates"),
  });
  const listsQ = useQuery({
    queryKey: ["checklists"],
    queryFn: () => apiFetch<ChecklistT[]>("/checklists"),
  });

  const start = useMutation({
    mutationFn: () =>
      apiPost<{ id: string; task_count: number }>("/checklists/instantiate", {
        employee_id: employeeId,
        kind,
      }),
    onSuccess: async (r) => {
      setMsg(`Checklist started with ${r.task_count} tasks.`);
      setOpenId(r.id);
      await qc.invalidateQueries({ queryKey: ["checklists"] });
    },
    onError: (e) => setMsg((e as Error).message),
  });

  const toggleTask = useMutation({
    mutationFn: ({ task, done }: { task: Task; done: boolean }) =>
      apiPost(`/checklists/tasks/${task.id}/${done ? "complete" : "reopen"}`, {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["checklists"] }),
  });

  const lists = listsQ.data ?? [];
  const active = lists.filter((l) => l.status === "active");
  const completed = lists.filter((l) => l.status !== "active");
  const template = (templatesQ.data ?? []).find((t) => t.kind === kind);

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Workflow"
        title="Checklists"
        subtitle="Templated onboarding & offboarding task lists — payroll setup, equipment, intros, access removal — with owners, due dates and progress."
      />

      <Surface>
        <SectionTitle
          eyebrow="Start"
          title="New checklist"
          description="Due dates are anchored to the employee's start date (onboarding) or today (offboarding)."
        />
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <label className="block">
            <div className="mb-1 text-xs text-muted">Type</div>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as "onboarding" | "offboarding")}
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            >
              <option value="onboarding">Onboarding</option>
              <option value="offboarding">Offboarding</option>
            </select>
          </label>
          <label className="block flex-1 min-w-[240px]">
            <div className="mb-1 text-xs text-muted">Employee</div>
            <select
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              className="w-full h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            >
              <option value="">Select employee…</option>
              {(employeesQ.data ?? []).map((e) => (
                <option key={e.id} value={e.id}>
                  {e.legal_name} · {e.job_title ?? "—"}
                </option>
              ))}
            </select>
          </label>
          <button
            className="h-9 px-4 rounded-md bg-accent text-accent-fg hover:opacity-90 transition-opacity duration-150 ease-calm text-sm disabled:opacity-40"
            disabled={!employeeId || start.isPending}
            onClick={() => start.mutate()}
          >
            {start.isPending ? "Starting…" : `Start ${kind}`}
          </button>
        </div>
        {template && (
          <div className="mt-3 text-xs text-muted">
            Template “{template.name}”: {template.items.length} tasks
            {" — "}
            {template.items.slice(0, 4).map((i) => i.title).join(" · ")}
            {template.items.length > 4 ? " · …" : ""}
          </div>
        )}
        {msg && <div className="mt-3 text-sm text-body">{msg}</div>}
      </Surface>

      <div>
        <SectionTitle eyebrow="In flight" title="Active checklists" description={`${active.length} running`} />
        <div className="mt-3 space-y-3">
          {listsQ.isLoading ? (
            <div className="text-sm text-muted">Loading…</div>
          ) : active.length === 0 ? (
            <EmptyState title="Nothing in flight" description="Start an onboarding or offboarding checklist above." />
          ) : (
            active.map((cl) => (
              <ChecklistCard
                key={cl.id}
                cl={cl}
                open={openId === cl.id}
                onToggleOpen={() => setOpenId(openId === cl.id ? null : cl.id)}
                onToggleTask={(task, done) => toggleTask.mutate({ task, done })}
                busy={toggleTask.isPending}
              />
            ))
          )}
        </div>
      </div>

      {completed.length > 0 && (
        <div>
          <SectionTitle eyebrow="Done" title="Completed" description={`${completed.length} finished`} />
          <div className="mt-3 space-y-3">
            {completed.map((cl) => (
              <ChecklistCard
                key={cl.id}
                cl={cl}
                open={openId === cl.id}
                onToggleOpen={() => setOpenId(openId === cl.id ? null : cl.id)}
                onToggleTask={(task, done) => toggleTask.mutate({ task, done })}
                busy={toggleTask.isPending}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ChecklistCard({
  cl,
  open,
  onToggleOpen,
  onToggleTask,
  busy,
}: {
  cl: ChecklistT;
  open: boolean;
  onToggleOpen: () => void;
  onToggleTask: (task: Task, done: boolean) => void;
  busy: boolean;
}) {
  const pct = cl.progress.total ? Math.round((cl.progress.done / cl.progress.total) * 100) : 0;
  return (
    <Surface>
      <button className="w-full text-left" onClick={onToggleOpen}>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-medium text-ink truncate">{cl.name}</div>
            <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
              {cl.kind} · {cl.progress.done}/{cl.progress.total} tasks
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <div className="w-28 h-1.5 rounded-full bg-sunken overflow-hidden">
              <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
            </div>
            <Pill tone={cl.status === "completed" ? "success" : "info"}>{cl.status}</Pill>
          </div>
        </div>
      </button>

      {open && (
        <ul className="mt-4 divide-y divide-rule">
          {cl.tasks.map((t) => (
            <li key={t.id} className="py-2.5 flex items-center justify-between gap-3">
              <label className="flex items-center gap-3 min-w-0 cursor-pointer">
                <input
                  type="checkbox"
                  checked={t.status === "done"}
                  disabled={busy}
                  onChange={(e) => onToggleTask(t, e.target.checked)}
                  className="h-4 w-4 rounded border-line accent-current"
                />
                <span className={`text-sm truncate ${t.status === "done" ? "line-through text-muted" : "text-ink"}`}>
                  {t.title}
                </span>
              </label>
              <div className="flex items-center gap-2 shrink-0">
                <Pill tone={CATEGORY_TONE[t.category] ?? "neutral"}>{t.category}</Pill>
                <span className="text-2xs uppercase tracking-eyebrow text-muted">{t.assignee_role}</span>
                {t.due_date && <span className="text-xs text-muted">due {t.due_date}</span>}
                {t.link && (
                  <Link href={t.link} className="text-xs underline text-muted hover:text-ink">
                    Open
                  </Link>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Surface>
  );
}
