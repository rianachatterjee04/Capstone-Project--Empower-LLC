"use client";
/**
 * Skills Graph — first-class skills taxonomy with clusters + supply/demand.
 */
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Action, EmptyState, PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";

type SkillStat = { skill: string; cluster_id: string; cluster_name: string; supply: number; demand: number; gap: number; adjacents: string[]; clusters?: string[] };

// A skill can serve more than one cluster (postgres is both Python backend and
// Data engineering). Naming only the first would tell a reader the bench sits
// in one team when it is shared.
function clusterLabel(s: SkillStat): string {
  const all = s.clusters ?? [];
  return all.length > 1 ? all.join(" · ") : s.cluster_name;
}
type ClusterStat = { id: string; name: string; supply: number; demand: number; gap: number; top_skills: string[]; top_adjacents: string[]; health: "ok" | "watch" | "gap" | "critical" };
type Graph = {
  clusters: ClusterStat[];
  skills: SkillStat[];
  top_gaps: SkillStat[];
  top_surplus: SkillStat[];
  total_skills_tracked: number;
  summary: { supply_total: number; demand_total: number; net_gap: number };
};

const HEALTH_TONE: Record<string, "success" | "info" | "warn" | "danger"> = {
  ok: "success", watch: "info", gap: "warn", critical: "danger",
};

export default function SkillsPage() {
  const [active, setActive] = useState<string | null>(null);
  const graphQ = useQuery({ queryKey: ["skills-graph"], queryFn: () => apiFetch<Graph>("/skills-graph") });
  const g = graphQ.data;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="People · Skills"
        title="Skills Graph"
        subtitle="Skills as a navigable graph — clusters, adjacencies, internal supply (employees), and demand (open reqs). Shows where to hire, where to retrain, and where you have surplus capacity."
      />

      {g && (
        <Surface pad="md">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Skills tracked" value={g.total_skills_tracked} />
            <Stat label="Internal supply" value={g.summary.supply_total} hint="Employees with skill" />
            <Stat label="Open demand" value={g.summary.demand_total} hint="Reqs needing skill" />
            <Stat label="Net gap" value={g.summary.net_gap} hint="Top hiring priority" />
          </div>
        </Surface>
      )}

      {/* Clusters */}
      <Surface>
        <SectionTitle eyebrow="Clusters" title="Skill clusters · health snapshot" description="Each cluster aggregates the skills inside it." />
        {graphQ.isLoading ? (
          <div className="mt-4 text-sm text-muted">Computing…</div>
        ) : !g ? (
          <div className="mt-4"><EmptyState title="No data" description="Add candidates + jobs to populate the graph." /></div>
        ) : (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {g.clusters.map((c) => (
              <button
                key={c.id}
                onClick={() => setActive(c.id)}
                className={`text-left rounded-md border p-3 bg-canvas hover:bg-sunken transition-colors ${active === c.id ? "border-ink/40" : "border-line"}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-ink truncate">{c.name}</div>
                    <div className="text-xs text-muted">Supply {c.supply} · Demand {c.demand}</div>
                  </div>
                  <Pill tone={HEALTH_TONE[c.health]}>{c.health}</Pill>
                </div>
                <div className="mt-3 flex items-end justify-between">
                  <div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">Gap</div>
                    <div className="text-xl font-semibold text-ink tabular-nums">{c.gap > 0 ? `+${c.gap}` : c.gap}</div>
                  </div>
                  <div className="text-right text-2xs uppercase tracking-eyebrow text-muted">
                    {c.top_skills.length} core · {c.top_adjacents.length} adjacent
                  </div>
                </div>
                <div className="mt-2 flex flex-wrap gap-1">
                  {c.top_skills.slice(0, 4).map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}
                </div>
              </button>
            ))}
          </div>
        )}
      </Surface>

      {/* Drill-in: skills inside selected cluster */}
      {g && active && (
        <Surface>
          <SectionTitle eyebrow="Cluster detail" title={g.clusters.find((c) => c.id === active)?.name ?? ""} description="Per-skill supply / demand / gap and adjacent skills employees could pivot to." />
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
            {g.skills.filter((s) => s.cluster_id === active).map((s) => (
              <div key={`${s.cluster_id}:${s.skill}`} className="rounded-md border border-line bg-canvas p-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="text-sm font-semibold text-ink">{s.skill}</div>
                    <div className="text-xs text-muted">Supply {s.supply} · Demand {s.demand}</div>
                  </div>
                  <Pill tone={s.gap > 0 ? "warn" : s.gap < 0 ? "success" : "neutral"}>
                    gap {s.gap > 0 ? `+${s.gap}` : s.gap}
                  </Pill>
                </div>
                {s.adjacents.length > 0 && (
                  <div className="mt-2 text-2xs uppercase tracking-eyebrow text-muted">
                    Adjacent: <span className="text-body normal-case tracking-normal">{s.adjacents.join(", ")}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </Surface>
      )}

      {/* Top gaps + top surplus.

          Keys below are cluster+skill, not skill. A skill can belong to more
          than one cluster — postgres is in both "Python backend" and "Data
          engineering" — so the same name appears twice, legitimately, and React
          warned that it would duplicate or omit one of the rows. The display
          already distinguishes them by showing the cluster underneath; only the
          key was ambiguous. */}
      {g && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Surface>
            <SectionTitle eyebrow="Hiring priorities" title="Top skill gaps" description="Demand > supply." />
            {g.top_gaps.length === 0 ? (
              <div className="mt-3 text-sm text-muted">No gaps detected.</div>
            ) : (
              <ul className="mt-3 divide-y divide-line">
                {g.top_gaps.map((s) => (
                  <li key={`${s.cluster_id}:${s.skill}`} className="py-2 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-ink">{s.skill}</div>
                      <div className="text-xs text-muted">{clusterLabel(s)}</div>
                    </div>
                    <Pill tone="warn">+{s.gap}</Pill>
                  </li>
                ))}
              </ul>
            )}
          </Surface>
          <Surface>
            <SectionTitle eyebrow="Internal surplus" title="Where you have bench depth" description="Supply > demand — opportunity for internal mobility or pivot." />
            {g.top_surplus.length === 0 ? (
              <div className="mt-3 text-sm text-muted">No surplus detected.</div>
            ) : (
              <ul className="mt-3 divide-y divide-line">
                {g.top_surplus.map((s) => (
                  <li key={`${s.cluster_id}:${s.skill}`} className="py-2 flex items-center justify-between">
                    <div>
                      <div className="text-sm font-medium text-ink">{s.skill}</div>
                      <div className="text-xs text-muted">{clusterLabel(s)}</div>
                    </div>
                    <Pill tone="success">{s.gap}</Pill>
                  </li>
                ))}
              </ul>
            )}
          </Surface>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-md border border-line bg-canvas p-3">
      <div className="text-2xs uppercase tracking-eyebrow text-muted">{label}</div>
      <div className="mt-1 text-xl font-semibold text-ink tabular-nums">{value}</div>
      {hint && <div className="text-2xs text-muted mt-0.5">{hint}</div>}
    </div>
  );
}
