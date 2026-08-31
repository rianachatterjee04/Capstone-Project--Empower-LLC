"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPatch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, LinkAction, EmptyState, Divider, Avatar } from "@/components/ds";
import { IconArrowUpRight, IconSparkle, IconCircle, IconCheck } from "@/components/icons";

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
  department?: string | null;
  related_employee_name?: string | null;
  due_at?: string | null;
  ai_generated: boolean;
  ai_rationale?: string | null;
  tags: string[];
  objective_id?: string | null;
  key_result_id?: string | null;
};

type GoalsResponse = {
  items: {
    id: string;
    title: string;
    team?: string | null;
    cycle: string;
    key_results: { id: string; title: string }[];
  }[];
};

type Summary = { total: number; open: number; urgent: number; ai_generated_open: number; overdue: number };

type Project = {
  project: string; total: number; todo: number; doing: number; blocked: number; done: number;
  completion_percent: number; owner_roles: string[]; departments: string[]; sources: string[];
};

const PRIORITY_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  urgent: "danger",
  high: "warn",
  normal: "neutral",
  low: "neutral",
};

const STATUS_TONE: Record<string, "neutral" | "info" | "warn" | "success" | "danger"> = {
  todo: "neutral",
  doing: "info",
  blocked: "danger",
  done: "success",
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

function dueLabel(due?: string | null): { label: string; tone: "danger" | "warn" | "neutral" | "success" } {
  if (!due) return { label: "No due date", tone: "neutral" };
  const d = new Date(due);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  const days = Math.round(diffMs / (1000 * 60 * 60 * 24));
  if (days < 0)  return { label: `${Math.abs(days)}d overdue`, tone: "danger" };
  if (days === 0) return { label: "Due today",  tone: "warn" };
  if (days === 1) return { label: "Due tomorrow", tone: "warn" };
  if (days <= 7)  return { label: `Due in ${days}d`, tone: "warn" };
  return { label: `Due ${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}`, tone: "neutral" };
}

type Lane = "all" | "owed_by_me" | "owed_by_team" | "ai_proposed" | "completed";

const LANES: { id: Lane; label: string; eyebrow: string }[] = [
  { id: "all",           label: "All work",       eyebrow: "Org" },
  { id: "owed_by_me",    label: "Owed by me",     eyebrow: "Personal" },
  { id: "owed_by_team",  label: "Owed by team",   eyebrow: "Manager" },
  { id: "ai_proposed",   label: "AI proposed",    eyebrow: "AI Ops" },
  { id: "completed",     label: "Completed",      eyebrow: "Archive" },
];

export default function WorkPage() {
  const qc = useQueryClient();
  const [lane, setLane] = useState<Lane>("all");
  const [projectFilter, setProjectFilter] = useState<string>("");
  const [search, setSearch] = useState("");

  const tasksQ = useQuery({
    queryKey: ["tasks"],
    queryFn: () => apiFetch<{ items: Task[] }>("/tasks"),
    refetchInterval: 60_000,
  });
  const summaryQ = useQuery({
    queryKey: ["tasks-summary"],
    queryFn: () => apiFetch<Summary>("/tasks/summary"),
    refetchInterval: 60_000,
  });
  const projectsQ = useQuery({
    queryKey: ["tasks-projects"],
    queryFn: () => apiFetch<{ items: Project[] }>("/tasks/projects"),
    refetchInterval: 60_000,
  });
  const goalsQ = useQuery({
    queryKey: ["goals-light"],
    queryFn: () => apiFetch<GoalsResponse>("/goals"),
    staleTime: 5 * 60_000,
  });

  const allKRs = useMemo(() => {
    const list: { objective_id: string; objective_title: string; kr_id: string; kr_title: string }[] = [];
    for (const o of goalsQ.data?.items ?? []) {
      for (const kr of o.key_results) {
        list.push({ objective_id: o.id, objective_title: o.title, kr_id: kr.id, kr_title: kr.title });
      }
    }
    return list;
  }, [goalsQ.data]);

  const [linkOpen, setLinkOpen] = useState<string>("");
  async function linkToKR(taskId: string, objective_id: string | null, key_result_id: string | null) {
    await apiPost(`/tasks/${taskId}/link-kr`, { objective_id, key_result_id });
    setLinkOpen("");
    await qc.invalidateQueries({ queryKey: ["tasks"] });
    await qc.invalidateQueries({ queryKey: ["goals"] });
  }

  const all = tasksQ.data?.items ?? [];

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return all.filter((t) => {
      if (projectFilter && (t.project ?? "") !== projectFilter) return false;
      if (q && !`${t.title} ${t.description ?? ""} ${t.related_employee_name ?? ""} ${t.project ?? ""}`.toLowerCase().includes(q)) return false;
      if (lane === "owed_by_me")    return t.owner_role === "employee";  // demo: treat 'employee' as 'me'
      if (lane === "owed_by_team")  return (t.owner_role === "manager" || t.owner_role === "hr") && t.status !== "done";
      if (lane === "ai_proposed")   return t.ai_generated && t.status !== "done";
      if (lane === "completed")     return t.status === "done";
      return true;
    });
  }, [all, lane, projectFilter, search]);

  // Group by project for the main column
  const byProject = useMemo(() => {
    const m = new Map<string, Task[]>();
    for (const t of filtered) {
      const k = t.project ?? "Unassigned";
      m.set(k, [...(m.get(k) ?? []), t]);
    }
    return Array.from(m.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [filtered]);

  const projects = projectsQ.data?.items ?? [];
  const summary = summaryQ.data;

  async function setStatus(t: Task, status: Task["status"]) {
    await apiPatch(`/tasks/${t.id}`, { status });
    await qc.invalidateQueries({ queryKey: ["tasks"] });
    await qc.invalidateQueries({ queryKey: ["tasks-summary"] });
    await qc.invalidateQueries({ queryKey: ["tasks-projects"] });
  }

  async function orchestrateOnboarding() {
    await apiPost("/tasks/orchestrate/onboarding", {
      employee_name: "Demo New Hire",
      role: "Software Engineer",
      manager_name: "Sam Rivera",
    });
    await qc.invalidateQueries({ queryKey: ["tasks"] });
    await qc.invalidateQueries({ queryKey: ["tasks-summary"] });
    await qc.invalidateQueries({ queryKey: ["tasks-projects"] });
  }

  async function orchestrateCycle() {
    await apiPost("/tasks/orchestrate/review-cycle", { cycle_name: "Q3 review cycle" });
    await qc.invalidateQueries({ queryKey: ["tasks"] });
    await qc.invalidateQueries({ queryKey: ["tasks-projects"] });
  }

  // Add task composer state
  const [composeOpen, setComposeOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newProject, setNewProject] = useState("");
  const [newPriority, setNewPriority] = useState<Task["priority"]>("normal");
  const [newOwner, setNewOwner] = useState("");
  const [newDue, setNewDue] = useState("");
  const [creating, setCreating] = useState(false);

  async function createTask() {
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      await apiPost("/tasks", {
        title: newTitle,
        project: newProject || "Just for me",
        priority: newPriority,
        owner_name: newOwner || "You",
        owner_role: "employee",
        due_at: newDue ? new Date(newDue).toISOString() : null,
        source: "manual",
      });
      setNewTitle("");
      setNewProject("");
      setNewOwner("");
      setNewDue("");
      setComposeOpen(false);
      await qc.invalidateQueries({ queryKey: ["tasks"] });
      await qc.invalidateQueries({ queryKey: ["tasks-summary"] });
      await qc.invalidateQueries({ queryKey: ["tasks-projects"] });
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Workspace"
        title="Work hub"
        subtitle="Every onboarding, review, comp, compliance, and learning workflow shows up here as concrete work. Auto-orchestrated by the agents."
        actions={
          <>
            <Action variant="subtle" onClick={orchestrateOnboarding}>
              <IconSparkle /> Orchestrate onboarding
            </Action>
            <Action variant="subtle" onClick={orchestrateCycle}>
              <IconSparkle /> Open review cycle
            </Action>
            <Action variant="primary" onClick={() => setComposeOpen((v) => !v)}>
              {composeOpen ? "Cancel" : "Add task"}
            </Action>
          </>
        }
      />

      {composeOpen && (
        <Surface pad="sm">
          <SectionTitle eyebrow="Compose" title="New task" />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-5 gap-2">
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Task title"
              className="md:col-span-2 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newProject}
              onChange={(e) => setNewProject(e.target.value)}
              placeholder="Project"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newOwner}
              onChange={(e) => setNewOwner(e.target.value)}
              placeholder="Owner"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newDue}
              onChange={(e) => setNewDue(e.target.value)}
              type="date"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <select
              value={newPriority}
              onChange={(e) => setNewPriority(e.target.value as Task["priority"])}
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink"
            >
              <option value="low">Low priority</option>
              <option value="normal">Normal priority</option>
              <option value="high">High priority</option>
              <option value="urgent">Urgent</option>
            </select>
            <Action variant="primary" onClick={createTask} disabled={!newTitle.trim() || creating}>
              {creating ? "Creating…" : "Create task"}
            </Action>
            <span className="text-xs text-muted">Owner defaults to You · project defaults to "Just for me"</span>
          </div>
        </Surface>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Total" value={summary?.total ?? "—"} />
        <Stat label="Open" value={summary?.open ?? "—"} />
        <Stat label="AI proposed" value={summary?.ai_generated_open ?? "—"} tone="info" />
        <Stat label="Urgent" value={summary?.urgent ?? "—"} tone={(summary?.urgent ?? 0) > 0 ? "danger" : "neutral"} />
        <Stat label="Overdue" value={summary?.overdue ?? "—"} tone={(summary?.overdue ?? 0) > 0 ? "warn" : "neutral"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr_280px] gap-5">
        {/* Lane rail */}
        <Surface pad="sm">
          <div className="fp-eyebrow mb-2">Lanes</div>
          <nav className="space-y-0.5">
            {LANES.map((l) => {
              const isActive = lane === l.id;
              return (
                <button
                  key={l.id}
                  onClick={() => setLane(l.id)}
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
                </button>
              );
            })}
          </nav>
          <Divider className="my-3" />
          <div className="fp-eyebrow mb-2">Projects</div>
          <div className="space-y-0.5 max-h-72 overflow-auto -mx-1 px-1">
            <button
              onClick={() => setProjectFilter("")}
              className={["w-full text-left rounded-md px-2 py-1.5 text-sm", projectFilter === "" ? "bg-canvas text-ink" : "text-body hover:bg-sunken"].join(" ")}
            >
              All projects
            </button>
            {projects.map((p) => (
              <button
                key={p.project}
                onClick={() => setProjectFilter(p.project === projectFilter ? "" : p.project)}
                className={["w-full text-left rounded-md px-2 py-1.5 text-sm", projectFilter === p.project ? "bg-canvas text-ink" : "text-body hover:bg-sunken"].join(" ")}
              >
                <div className="flex items-center justify-between">
                  <span className="truncate">{p.project}</span>
                  <span className="text-2xs tabular-nums text-muted">{p.done}/{p.total}</span>
                </div>
                <div className="mt-1 h-1 rounded-full bg-sunken overflow-hidden">
                  <div className="h-full bg-accent" style={{ width: `${p.completion_percent}%` }} />
                </div>
              </button>
            ))}
          </div>
        </Surface>

        {/* Main column */}
        <div className="space-y-4">
          <Surface pad="sm">
            <div className="flex items-center gap-2">
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search tasks, projects, people…"
                className="flex-1 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface placeholder:text-muted"
              />
              {projectFilter && <Pill tone="info">{projectFilter}</Pill>}
            </div>
          </Surface>

          {filtered.length === 0 ? (
            <Surface><EmptyState title="No tasks in this lane" description="Try another lane, clear the project filter, or orchestrate a workflow above." /></Surface>
          ) : (
            byProject.map(([project, items]) => (
              <Surface key={project} pad="sm">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <div className="fp-eyebrow">Project</div>
                    <div className="text-sm font-semibold text-ink">{project}</div>
                  </div>
                  <div className="text-2xs uppercase tracking-eyebrow text-muted">{items.length} task{items.length !== 1 ? "s" : ""}</div>
                </div>
                <ul className="divide-y divide-rule">
                  {items.map((t) => {
                    const due = dueLabel(t.due_at);
                    return (
                      <li key={t.id} className="py-3 flex items-start gap-3">
                        {/* Status checkbox */}
                        <button
                          onClick={() => setStatus(t, t.status === "done" ? "todo" : "done")}
                          className={[
                            "mt-0.5 h-5 w-5 rounded-full border flex items-center justify-center transition-colors duration-150 ease-calm shrink-0",
                            t.status === "done"
                              ? "bg-success-fg border-success-fg text-canvas"
                              : "bg-surface border-line text-muted hover:bg-sunken",
                          ].join(" ")}
                          title={t.status === "done" ? "Mark as todo" : "Mark as done"}
                        >
                          {t.status === "done" ? <IconCheck size={12} /> : null}
                        </button>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className={["text-sm font-medium", t.status === "done" ? "line-through text-muted" : "text-ink"].join(" ")}>{t.title}</span>
                            <Pill tone={PRIORITY_TONE[t.priority]}>{t.priority}</Pill>
                            <Pill tone={STATUS_TONE[t.status]}>{t.status}</Pill>
                            <Pill tone="neutral">{SOURCE_LABEL[t.source] ?? t.source}</Pill>
                            {t.ai_generated && <span className="text-2xs uppercase tracking-eyebrow text-muted flex items-center gap-1"><IconSparkle size={12}/> AI</span>}
                          </div>
                          {t.description && <div className="text-xs text-muted mt-0.5">{t.description}</div>}
                          {t.ai_rationale && <div className="text-xs text-muted mt-0.5 italic">{t.ai_rationale}</div>}
                          <div className="mt-1.5 flex items-center gap-2 flex-wrap text-2xs uppercase tracking-eyebrow">
                            {t.owner_name && (
                              <span className="flex items-center gap-1 text-muted">
                                <Avatar name={t.owner_name} size={16} /> {t.owner_name}
                                {t.owner_role ? <span className="opacity-60">· {t.owner_role}</span> : null}
                              </span>
                            )}
                            {t.related_employee_name && (
                              <span className="text-muted">re: {t.related_employee_name}</span>
                            )}
                            {t.department && <span className="text-muted">{t.department}</span>}
                            <Pill tone={due.tone}>{due.label}</Pill>
                            {t.key_result_id ? (
                              <button
                                onClick={() => linkToKR(t.id, null, null)}
                                className="text-info-fg hover:text-ink"
                                title="Unlink from key result"
                              >
                                · linked to KR (clear)
                              </button>
                            ) : (
                              <button
                                onClick={() => setLinkOpen(linkOpen === t.id ? "" : t.id)}
                                className="text-muted hover:text-ink"
                              >
                                · link to KR
                              </button>
                            )}
                          </div>

                          {linkOpen === t.id && (
                            <div className="mt-2 rounded-md border border-line bg-canvas p-2 max-h-40 overflow-auto">
                              <div className="fp-eyebrow mb-1">Link to a key result</div>
                              {allKRs.length === 0 ? (
                                <div className="text-xs text-muted">No key results available.</div>
                              ) : (
                                <ul className="space-y-0.5">
                                  {allKRs.map((kr) => (
                                    <li key={kr.kr_id}>
                                      <button
                                        onClick={() => linkToKR(t.id, kr.objective_id, kr.kr_id)}
                                        className="w-full text-left rounded px-2 py-1 text-xs text-body hover:bg-sunken"
                                      >
                                        <div className="font-medium text-ink truncate">{kr.kr_title}</div>
                                        <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">{kr.objective_title}</div>
                                      </button>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          )}
                        </div>

                        <div className="shrink-0 flex items-center gap-1">
                          {t.status !== "done" && t.status !== "doing" && (
                            <button onClick={() => setStatus(t, "doing")} className="text-2xs uppercase tracking-eyebrow text-muted hover:text-ink">start</button>
                          )}
                          {t.status === "doing" && (
                            <button onClick={() => setStatus(t, "blocked")} className="text-2xs uppercase tracking-eyebrow text-muted hover:text-ink">block</button>
                          )}
                          {t.status === "blocked" && (
                            <button onClick={() => setStatus(t, "doing")} className="text-2xs uppercase tracking-eyebrow text-muted hover:text-ink">unblock</button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </Surface>
            ))
          )}
        </div>

        {/* Insight rail */}
        <div className="space-y-4">
          <Surface pad="sm">
            <SectionTitle eyebrow="Auto-orchestration" title="How tasks land here" />
            <ul className="mt-3 space-y-2 text-sm text-body">
              <li>• <strong>Onboarding</strong> agent emits Day-1 → 90d task chain per new hire.</li>
              <li>• <strong>Performance</strong> cycle creates self / peer / manager / calibration tasks.</li>
              <li>• <strong>Comp</strong> cycle creates proposal → calibration → finance → communicate.</li>
              <li>• <strong>Compliance</strong> agent escalates aging cases + stale training.</li>
              <li>• <strong>Workforce planning</strong> agent surfaces understaffing risks as planning tasks.</li>
            </ul>
            <Divider className="my-3" />
            <LinkAction href="/app/agents" variant="subtle" className="w-full">
              <IconSparkle /> See agent runs
            </LinkAction>
          </Surface>

          <Surface pad="sm">
            <SectionTitle eyebrow="Activity" title="Sources active" />
            <div className="mt-3 flex flex-wrap gap-1">
              {Array.from(new Set(all.map((t) => t.source))).map((s) => (
                <Pill key={s} tone="neutral">{SOURCE_LABEL[s] ?? s}</Pill>
              ))}
              {all.length === 0 && <span className="text-xs text-muted">—</span>}
            </div>
          </Surface>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" | "info" | "danger" }) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
    warn: "ring-1 ring-warn-line",
    info: "ring-1 ring-info-line",
    danger: "ring-1 ring-danger-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
