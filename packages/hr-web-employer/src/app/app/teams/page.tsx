"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState } from "@/components/ds";
import { IconArrowUpRight } from "@/components/icons";

type TeamSummary = {
  slug: string;
  name: string;
  manager: string;
  mission: string;
  headcount: number;
  open_reqs: number;
  onboarding_open: number;
  tasks_open: number;
  tasks_overdue: number;
  high_risk: number;
  medium_risk: number;
  is_template?: boolean;
  template_note?: string | null;
};

const healthTone = (t: TeamSummary): "success" | "warn" | "danger" | "neutral" => {
  if (t.high_risk > 0 || t.tasks_overdue >= 3) return "danger";
  if (t.medium_risk > 0 || t.tasks_overdue > 0 || t.open_reqs > 0 || t.onboarding_open > 0) return "warn";
  return "success";
};

export default function TeamsPage() {
  const q = useQuery({
    queryKey: ["teams-summary"],
    queryFn: () => apiFetch<{ items: TeamSummary[] }>("/teams/summary"),
    refetchInterval: 60_000,
  });

  const teams = q.data?.items ?? [];

  const totalHeadcount = teams.reduce((s, t) => s + (t.headcount ?? 0), 0);
  const totalOpenReqs = teams.reduce((s, t) => s + t.open_reqs, 0);
  const totalOverdue = teams.reduce((s, t) => s + t.tasks_overdue, 0);
  const totalHighRisk = teams.reduce((s, t) => s + t.high_risk, 0);
  const templates = teams.filter((t) => t.is_template).length;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="People"
        title="Team workspaces"
        subtitle="Each department gets a daily operating page — goals, hiring, onboarding, tasks, risk, and learning."
      />

      {/* "Departments 5 · Headcount 0 · Open requisitions 5" for a company with
          one employee and two open reqs. Headcount was the only real number on
          the row; the departments, their managers, missions, goals and req
          counts are templates the product ships. Three constants beside one
          true zero is why the screen read as broken. */}
      {templates > 0 && (
        <Surface pad="md">
          <div className="fp-eyebrow">Department templates</div>
          <p className="mt-1 text-sm text-body">
            {templates === teams.length ? "All " : `${templates} of `}
            {teams.length} departments below are templates shipped with the product. Their
            manager, mission, goals and requisition counts are examples; headcount is counted
            from your own employee records, which is why it reads {totalHeadcount}.
          </p>
        </Surface>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="Departments" value={teams.length} hint={templates ? `${templates} template` : undefined} />
        <Stat label="Headcount" value={totalHeadcount} hint="from your employee records" />
        <Stat
          label="Open requisitions"
          value={totalOpenReqs}
          tone={totalOpenReqs ? "warn" : "neutral"}
          hint={templates ? "template figure" : undefined}
        />
        <Stat label="Overdue tasks" value={totalOverdue} tone={totalOverdue ? "warn" : "neutral"} />
      </div>

      {q.isLoading ? (
        <Surface><EmptyState title="Loading…" /></Surface>
      ) : teams.length === 0 ? (
        <Surface><EmptyState title="No teams configured" /></Surface>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {teams.map((t) => (
            <Link
              key={t.slug}
              href={`/app/teams/${t.slug}`}
              className="group block rounded-lg border border-line bg-surface hover:bg-canvas transition-colors duration-150 ease-calm p-5"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="fp-eyebrow">{t.manager}</div>
                  <div className="text-lg font-semibold text-ink tracking-tight">{t.name}</div>
                </div>
                <Pill tone={healthTone(t)}>{healthTone(t)}</Pill>
              </div>
              <p className="mt-2 text-sm text-muted line-clamp-3">{t.mission}</p>
              <div className="mt-4 grid grid-cols-2 gap-2 text-2xs uppercase tracking-eyebrow text-muted">
                <Mini label="Headcount" value={t.headcount} />
                <Mini label="Open reqs" value={t.open_reqs} />
                <Mini label="Onboarding" value={t.onboarding_open} />
                <Mini label="Tasks" value={`${t.tasks_open}/${t.tasks_overdue} overdue`} />
                {t.high_risk + t.medium_risk > 0 && <Mini label="Risk" value={`${t.high_risk}H · ${t.medium_risk}M`} />}
              </div>
              <div className="mt-4 text-sm text-muted flex items-center justify-end gap-1 group-hover:text-ink">
                Open workspace <IconArrowUpRight />
              </div>
            </Link>
          ))}
        </div>
      )}

      {totalHighRisk > 0 && (
        <Surface>
          <SectionTitle eyebrow="Org-wide" title="Heads-up" />
          <p className="mt-3 text-sm text-body">
            {totalHighRisk} employee{totalHighRisk !== 1 ? "s are" : " is"} flagged high-risk across the company. Open the workforce risk engine for the full picture.
          </p>
          <div className="mt-3">
            <Link href="/app/risk" className="text-sm underline text-ink">Open workforce risk →</Link>
          </div>
        </Surface>
      )}
    </div>
  );
}

function Stat({ label, value, tone = "neutral", hint }: {
  label: string;
  value: React.ReactNode;
  tone?: "neutral" | "warn" | "danger";
  /** Where the number came from — "from your employee records" vs "template figure". */
  hint?: string;
}) {
  const ring: Record<string, string> = {
    neutral: "",
    warn: "ring-1 ring-warn-line",
    danger: "ring-1 ring-danger-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 text-2xs text-muted">{hint}</div>}
    </div>
  );
}

function Mini({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div>{label}</div>
      <div className="text-sm text-ink mt-0.5 normal-case tracking-normal">{value}</div>
    </div>
  );
}
