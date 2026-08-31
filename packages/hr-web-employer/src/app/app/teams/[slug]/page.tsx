"use client";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Avatar, LinkAction, Divider } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type TaskItem = {
  id: string;
  title: string;
  status: "todo" | "doing" | "blocked" | "done";
  priority: "low" | "normal" | "high" | "urgent";
  source: string;
  owner_name?: string | null;
  related_employee_name?: string | null;
  due_at?: string | null;
  ai_generated?: boolean;
};
type Workspace = {
  team: string;
  slug: string;
  manager: string;
  mission: string;
  primary_skills: string[];
  goals: { title: string; owner: string; due: string }[];
  headcount: number;
  employees: { id: string; legal_name: string; job_title: string; status: string }[];
  hiring: { open_reqs: number; candidates: { id: string; full_name: string; status: string; ai_score?: number; job_title?: string }[] };
  onboarding_open: number;
  risk: { high: any[]; medium: any[] };
  tasks: { items: TaskItem[]; open: number; overdue: number };
  projects: { project: string; total: number; done: number; completion_percent: number }[];
};

const PRIORITY_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  urgent: "danger",
  high: "warn",
  normal: "neutral",
  low: "neutral",
};

function dueLabel(due?: string | null): { label: string; tone: "danger" | "warn" | "neutral" } {
  if (!due) return { label: "—", tone: "neutral" };
  const d = new Date(due);
  const now = new Date();
  const days = Math.round((d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (days < 0) return { label: `${Math.abs(days)}d overdue`, tone: "danger" };
  if (days <= 2) return { label: `${days}d`, tone: "warn" };
  return { label: `${days}d`, tone: "neutral" };
}

export default function TeamWorkspacePage() {
  const params = useParams<{ slug: string }>();
  const slug = params?.slug ?? "";
  const q = useQuery({
    queryKey: ["team", slug],
    queryFn: () => apiFetch<Workspace>(`/teams/${slug}`),
    enabled: !!slug,
    refetchInterval: 60_000,
  });

  const w = q.data;

  if (q.isLoading) {
    return (
      <div className="space-y-6 fp-fade-in">
        <PageHeader eyebrow="Team" title="Loading…" />
      </div>
    );
  }

  if (q.error || !w) {
    return (
      <div className="space-y-6 fp-fade-in">
        <PageHeader eyebrow="Team" title="Not found" subtitle="That team doesn't exist yet." />
        <Surface><EmptyState title="Try the team list" action={<LinkAction href="/app/teams" size="sm" variant="primary">All teams</LinkAction>} /></Surface>
      </div>
    );
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow={`Team · ${w.manager}`}
        title={w.team}
        subtitle={w.mission}
        actions={
          <>
            <LinkAction href={`/app/work?owner_name=${encodeURIComponent(w.manager)}`} variant="subtle">Open work</LinkAction>
            <LinkAction href="/app/org-design" variant="primary"><IconSparkle /> Org design</LinkAction>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Headcount" value={w.headcount} />
        <Stat label="Open reqs" value={w.hiring.open_reqs} tone={w.hiring.open_reqs ? "warn" : "neutral"} />
        <Stat label="Onboarding" value={w.onboarding_open} />
        <Stat label="Tasks open" value={w.tasks.open} tone={w.tasks.open ? "info" : "neutral"} />
        <Stat label="Tasks overdue" value={w.tasks.overdue} tone={w.tasks.overdue ? "warn" : "neutral"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Goals + projects */}
        <Surface className="lg:col-span-2">
          <SectionTitle eyebrow="Goals" title="What this team is delivering" />
          {w.goals.length === 0 ? (
            <EmptyState title="No goals set" />
          ) : (
            <ul className="mt-3 divide-y divide-rule">
              {w.goals.map((g, i) => (
                <li key={i} className="py-3 flex items-center justify-between gap-2">
                  <div>
                    <div className="text-sm font-medium text-ink">{g.title}</div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">{g.owner} · due {g.due}</div>
                  </div>
                  <Pill tone="neutral">on track</Pill>
                </li>
              ))}
            </ul>
          )}

          {w.projects.length > 0 && (
            <>
              <Divider className="my-4" />
              <SectionTitle eyebrow="Projects" title="Workforce execution" />
              <div className="mt-3 space-y-2">
                {w.projects.map((p) => (
                  <div key={p.project}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-ink">{p.project}</span>
                      <span className="text-2xs uppercase tracking-eyebrow text-muted tabular-nums">{p.done}/{p.total}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-sunken overflow-hidden">
                      <div className="h-full bg-accent" style={{ width: `${p.completion_percent}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </Surface>

        {/* People + skills */}
        <Surface>
          <SectionTitle eyebrow="People" title="Who's on the team" trailing={<Link href="/app/people" className="text-xs underline text-muted hover:text-ink">All people →</Link>} />
          {w.employees.length === 0 ? (
            <div className="mt-3 text-sm text-muted">No employees match this department yet.</div>
          ) : (
            <ul className="mt-3 space-y-2 max-h-80 overflow-auto -mx-1 px-1">
              {w.employees.map((e) => (
                <li key={e.id}>
                  <Link href={`/app/people/${e.id}?tab=twin`} className="flex items-center gap-2 rounded-md px-2 py-1.5 hover:bg-sunken transition-colors duration-150 ease-calm">
                    <Avatar name={e.legal_name} size={24} />
                    <div className="min-w-0">
                      <div className="text-sm text-ink truncate">{e.legal_name}</div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">{e.job_title ?? "—"}</div>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {w.primary_skills.length > 0 && (
            <>
              <Divider className="my-3" />
              <div className="fp-eyebrow mb-1">Primary skills</div>
              <div className="flex flex-wrap gap-1">
                {w.primary_skills.map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}
              </div>
            </>
          )}
        </Surface>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Tasks */}
        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow="Work"
            title="In flight on this team"
            description="Pulled from the workforce execution layer."
            trailing={<LinkAction href={`/app/work?department=${encodeURIComponent(w.team)}`} size="sm" variant="subtle">Open in work hub</LinkAction>}
          />
          {w.tasks.items.length === 0 ? (
            <div className="mt-3"><EmptyState title="No tasks for this team yet" /></div>
          ) : (
            <ul className="mt-3 divide-y divide-rule">
              {w.tasks.items.slice(0, 8).map((t) => {
                const d = dueLabel(t.due_at);
                return (
                  <li key={t.id} className="py-2.5 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={t.status === "done" ? "text-sm line-through text-muted" : "text-sm text-ink"}>{t.title}</span>
                        <Pill tone={PRIORITY_TONE[t.priority]}>{t.priority}</Pill>
                        {t.ai_generated && <span className="text-2xs uppercase tracking-eyebrow text-muted flex items-center gap-1"><IconSparkle size={12} /> AI</span>}
                      </div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                        {t.owner_name ?? "—"}{t.related_employee_name ? ` · re: ${t.related_employee_name}` : ""}
                      </div>
                    </div>
                    <Pill tone={d.tone}>{d.label}</Pill>
                  </li>
                );
              })}
            </ul>
          )}
        </Surface>

        {/* Risk + hiring */}
        <div className="space-y-5">
          <Surface>
            <SectionTitle eyebrow="Risk" title="People signals" />
            <div className="mt-3 space-y-2">
              {(w.risk.high ?? []).map((p: any) => (
                <RiskRow key={p.employee_id} name={p.name} band="high" drivers={p.drivers ?? []} />
              ))}
              {(w.risk.medium ?? []).map((p: any) => (
                <RiskRow key={p.employee_id} name={p.name} band="medium" drivers={p.drivers ?? []} />
              ))}
              {(w.risk.high ?? []).length + (w.risk.medium ?? []).length === 0 && (
                <div className="text-sm text-muted">No elevated risk on this team.</div>
              )}
            </div>
          </Surface>

          <Surface>
            <SectionTitle eyebrow="Hiring" title="Pipeline" trailing={<Link href="/app/talent" className="text-xs underline text-muted hover:text-ink">All talent →</Link>} />
            <div className="mt-3 space-y-2">
              {w.hiring.candidates.length === 0 ? (
                <div className="text-sm text-muted">No candidates currently scoped to this team.</div>
              ) : (
                w.hiring.candidates.slice(0, 6).map((c) => (
                  <div key={c.id} className="rounded-md border border-line p-2 flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="text-sm text-ink truncate">{c.full_name}</div>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">{c.job_title ?? "—"} · {c.status}</div>
                    </div>
                    {c.ai_score != null && <Pill tone={c.ai_score >= 75 ? "success" : c.ai_score >= 55 ? "warn" : "danger"}>{c.ai_score}</Pill>}
                  </div>
                ))
              )}
            </div>
          </Surface>
        </div>
      </div>
    </div>
  );
}

function RiskRow({ name, band, drivers }: { name: string; band: "high" | "medium"; drivers: string[] }) {
  return (
    <div className={`rounded-md border p-3 ${band === "high" ? "border-danger-line bg-danger-bg/40" : "border-warn-line bg-warn-bg/30"}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-semibold text-ink">{name}</div>
        <Pill tone={band === "high" ? "danger" : "warn"}>{band}</Pill>
      </div>
      {drivers.length > 0 && (
        <ul className="mt-1 text-xs text-body space-y-0.5">
          {drivers.slice(0, 3).map((d, i) => <li key={i}>• {d}</li>)}
        </ul>
      )}
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "info" | "warn" | "danger" }) {
  const ring: Record<string, string> = {
    neutral: "",
    info: "ring-1 ring-info-line",
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
