"use client";
/**
 * Org chart — real reporting lines built from employees.manager_employee_id
 * (/org-chart/tree), plus headcount by department and the trailing-12-month
 * attrition metric. Managers are assigned from an employee's profile page
 * (job change) or /employees/{id}/manager/{mid}.
 */
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { PageHeader, Surface, SectionTitle, MetricStat, Pill } from "@/components/ds";

type OrgNode = {
  id: string;
  manager_id: string | null;
  name: string;
  job_title?: string | null;
  department?: string | null;
  status?: string;
  team_size: number;
  reports: OrgNode[];
};

type TreeResponse = { roots: OrgNode[]; total: number };
type HeadcountResponse = { by_department: { department: string; count: number }[]; total: number };
type AttritionResponse = {
  window: string;
  terminations: number;
  headcount_start: number;
  headcount_end: number;
  attrition_rate: number;
  attrition_pct: number;
};

function NodeCard({ node, depth }: { node: OrgNode; depth: number }) {
  return (
    <div className={depth > 0 ? "ml-5 border-l border-line pl-4" : ""}>
      <Link
        href={`/app/people/${node.id}`}
        className="inline-flex items-baseline gap-2 rounded-md border border-line bg-surface px-3 py-2 my-1 hover:bg-sunken transition-colors duration-150 ease-calm"
      >
        <span className="text-sm font-medium text-ink">{node.name}</span>
        <span className="text-xs text-muted">{node.job_title ?? "—"}</span>
        {node.department && <span className="text-xs text-faint">· {node.department}</span>}
        {node.team_size > 0 && (
          <Pill tone="accent">
            {node.team_size} report{node.team_size === 1 ? "" : "s"}
          </Pill>
        )}
      </Link>
      {node.reports.length > 0 && (
        <div>
          {node.reports.map((child) => (
            <NodeCard key={child.id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function OrgChartPage() {
  const treeQ = useQuery({
    queryKey: ["org-chart-tree"],
    queryFn: () => apiFetch<TreeResponse>("/org-chart/tree"),
  });
  const headcountQ = useQuery({
    queryKey: ["org-chart-headcount"],
    queryFn: () => apiFetch<HeadcountResponse>("/org-chart/headcount"),
  });
  const attritionQ = useQuery({
    queryKey: ["org-chart-attrition"],
    queryFn: () => apiFetch<AttritionResponse>("/org-chart/attrition"),
  });

  if (treeQ.isLoading) return <div className="text-sm text-muted">Loading…</div>;
  if (treeQ.error) return <div className="text-sm text-danger-fg">Failed: {(treeQ.error as Error).message}</div>;

  const roots = treeQ.data?.roots ?? [];
  const hc = headcountQ.data;
  const at = attritionQ.data;
  const deptTotal = hc?.total || 1;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="People"
        title="Org chart"
        subtitle="Reporting lines from manager assignments. Click a person for their full profile & history."
      />

      {/* Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricStat label="Headcount" value={treeQ.data?.total ?? 0} />
        <MetricStat label="Departments" value={hc?.by_department.length ?? 0} />
        <MetricStat
          label="Attrition (12 mo)"
          value={at ? `${at.attrition_pct}%` : "—"}
          hint={at ? `${at.terminations} departure${at.terminations === 1 ? "" : "s"}` : undefined}
        />
        <MetricStat label="Top-level leaders" value={roots.length} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Tree */}
        <Surface className="lg:col-span-2 overflow-x-auto">
          <SectionTitle title="Reporting lines" />
          {roots.length === 0 ? (
            <div className="mt-3 text-sm text-muted">
              No employees yet — or no managers assigned. Assign managers from an employee&apos;s profile.
            </div>
          ) : (
            <div className="mt-3 min-w-[480px]">
              {roots.map((r) => (
                <NodeCard key={r.id} node={r} depth={0} />
              ))}
            </div>
          )}
        </Surface>

        {/* Headcount by department */}
        <Surface>
          <SectionTitle title="Headcount by department" />
          <div className="mt-3 space-y-2.5">
            {(hc?.by_department ?? []).map(({ department, count }) => (
              <div key={department}>
                <div className="flex items-center justify-between text-sm">
                  <span className="truncate text-body">{department}</span>
                  <span className="font-mono text-xs text-muted tabular-nums">{count}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-sunken overflow-hidden">
                  <div className="h-full bg-accent" style={{ width: `${Math.min(100, (count / deptTotal) * 100)}%` }} />
                </div>
              </div>
            ))}
            {(hc?.by_department ?? []).length === 0 && <div className="text-sm text-muted">—</div>}
          </div>
          {at && (
            <div className="mt-4 rounded-md bg-canvas border border-line p-3 text-xs text-muted">
              Attrition = departures ÷ average headcount ({at.terminations} ÷ avg(
              {at.headcount_start}, {at.headcount_end})) = {at.attrition_pct}%
            </div>
          )}
        </Surface>
      </div>
    </div>
  );
}
