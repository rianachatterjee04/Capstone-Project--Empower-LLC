"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { SampleBanner } from "@/components/SampleBanner";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Avatar } from "@/components/ds";

type Role = { id: string; title: string; department: string; skills_required: string[]; seniority: string; posted_by: string };
type Employee = { id: string; name: string; skills: string[]; performance_rating: number; tenure_years: number; is_sample?: boolean };
type Match = {
  employee_id: string; employee_name: string;
  role: Role; score: number; coverage_percent: number;
  matched_skills: string[]; missing_skills: string[]; learning_hint: string;
};

function scoreTone(score: number): "success" | "warn" | "danger" {
  if (score >= 80) return "success";
  if (score >= 60) return "warn";
  return "danger";
}

export default function MarketplacePage() {
  const [selectedRole, setSelectedRole] = useState<string>("");

  const rolesQ = useQuery({ queryKey: ["mp-roles"], queryFn: () => apiFetch<{ items: Role[] }>("/marketplace/roles") });
  const poolQ = useQuery({ queryKey: ["mp-pool"], queryFn: () => apiFetch<{ items: Employee[] }>("/marketplace/demo-pool") });
  const succQ = useQuery({
    queryKey: ["mp-succession", selectedRole],
    queryFn: () => apiFetch<{ items: Match[] }>(`/marketplace/succession/${selectedRole}`),
    enabled: !!selectedRole,
  });

  const roles = rolesQ.data?.items ?? [];
  const employees = poolQ.data?.items ?? [];

  const bestByEmployee = useMemo(() => {
    const m = new Map<string, Match>();
    if (!succQ.data) return m;
    for (const x of succQ.data.items) {
      const cur = m.get(x.employee_id);
      if (!cur || cur.score < x.score) m.set(x.employee_id, x);
    }
    return m;
  }, [succQ.data]);

  const activeRole = useMemo(() => roles.find((r) => r.id === selectedRole), [roles, selectedRole]);

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="People"
        title="Talent marketplace"
        subtitle="Skills-based matching between internal employees and internal roles. Surfaces succession + stretch opportunities."
      />

      {/* The people ranked here come from /marketplace/demo-pool — the endpoint
          is named honestly, the screen was not. Ranking a named person as
          "ready now" for a role is a career claim, and it was being made about
          the sample cohort. */}
      {employees.length > 0 && (
        <Surface pad="md">
          <div className="fp-eyebrow">Worked example</div>
          <p className="mt-1 text-sm text-body">
            The {employees.length} people and {roles.length} internal roles below are an
            illustrative pool shipped with the product, not your employees. Matching runs on
            recorded skills, performance rating and tenure — connect those for your own people
            to rank real succession candidates.
          </p>
        </Surface>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Surface>
          <SectionTitle eyebrow="Open" title="Internal roles" description="Pick one to rank ready-now candidates." />
          <ul className="mt-3 divide-y divide-rule">
            {roles.map((r) => {
              const active = selectedRole === r.id;
              return (
                <li key={r.id}>
                  <button
                    onClick={() => setSelectedRole(r.id)}
                    className={`w-full text-left -mx-2 px-2 py-3 rounded-md transition-colors duration-150 ease-calm ${
                      active ? "bg-canvas" : "hover:bg-sunken/60"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-ink">{r.title}</div>
                        <div className="text-2xs uppercase tracking-eyebrow text-muted">{r.department} · {r.seniority}</div>
                      </div>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {r.skills_required.map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}
                    </div>
                  </button>
                </li>
              );
            })}
          </ul>
        </Surface>

        <Surface>
          <SectionTitle
            eyebrow="Ranked"
            title={activeRole ? `Candidates for ${activeRole.title}` : "Pick a role to see candidates"}
            description={activeRole ? `${activeRole.department} · ${activeRole.seniority}` : undefined}
          />
          {!activeRole ? (
            <EmptyState title="—" description="Select an open role on the left." />
          ) : !succQ.data ? (
            <div className="mt-3 text-sm text-muted">Loading…</div>
          ) : (
            <ul className="mt-3 divide-y divide-rule">
              {succQ.data.items.map((m) => (
                <li key={`${m.employee_id}-${m.role.id}`} className="py-3 flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2 min-w-0">
                    <Avatar name={m.employee_name} size={26} />
                    <div className="min-w-0">
                      <Link href={`/app/people/${m.employee_id}?tab=twin`} className="text-sm font-semibold text-ink hover:underline">
                        {m.employee_name}
                      </Link>
                      <div className="text-2xs uppercase tracking-eyebrow text-muted">{m.coverage_percent}% coverage</div>
                      <div className="mt-1 flex flex-wrap gap-1">
                        {m.matched_skills.slice(0, 5).map((s) => <Pill key={s} tone="success">{s}</Pill>)}
                      </div>
                      {m.missing_skills.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {m.missing_skills.slice(0, 5).map((s) => <Pill key={s} tone="danger">{s}</Pill>)}
                        </div>
                      )}
                      <div className="mt-1 text-xs text-muted">{m.learning_hint}</div>
                    </div>
                  </div>
                  <Pill tone={scoreTone(m.score)}>{m.score}</Pill>
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>

      <Surface>
        <SectionTitle eyebrow="Snapshot" title="Employee skill index" description="At a glance: who's ready for which next move." />
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {employees.map((e) => {
            const top = bestByEmployee.get(e.id);
            return (
              <Link key={e.id} href={`/app/people/${e.id}?tab=twin`} className="rounded-lg border border-line bg-canvas hover:bg-sunken transition-colors duration-150 ease-calm p-3">
                <div className="flex items-center gap-2">
                  <Avatar name={e.name} size={26} />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-ink truncate">{e.name}</div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">perf {e.performance_rating.toFixed(1)} · {e.tenure_years.toFixed(1)}y</div>
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {e.skills.slice(0, 6).map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}
                </div>
                {top && (
                  <div className="mt-2.5 flex items-center justify-between text-xs">
                    <span className="text-muted">Best fit: <span className="text-ink">{top.role.title}</span></span>
                    <Pill tone={scoreTone(top.score)}>{top.score}</Pill>
                  </div>
                )}
              </Link>
            );
          })}
        </div>
      </Surface>
    </div>
  );
}
