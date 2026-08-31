"use client";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider } from "@/components/ds";

type OrgNode = { id: string; name: string; job_title: string | null; department: string | null; manager_id: string | null };
type OrgInsight = { kind: string; severity: "high" | "medium" | "low"; subject: string; detail: string; recommendation: string };
type Analysis = {
  employees: number; managers: number; layers: number; avg_span: number; max_span: number;
  dept_headcount: Record<string, number>;
  insights: OrgInsight[];
  nodes: OrgNode[];
};

const SEV_TONE: Record<string, "danger" | "warn" | "neutral"> = {
  high: "danger",
  medium: "warn",
  low: "neutral",
};

function buildTree(nodes: OrgNode[]) {
  const children = new Map<string | null, OrgNode[]>();
  for (const n of nodes) {
    const k = n.manager_id ?? null;
    children.set(k, [...(children.get(k) ?? []), n]);
  }
  return children;
}

function TreeNode({ node, children, depth }: { node: OrgNode; children: Map<string | null, OrgNode[]>; depth: number }) {
  const kids = children.get(node.id) ?? [];
  return (
    <div className="text-sm">
      <div className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-sunken/60 transition-colors duration-150 ease-calm" style={{ paddingLeft: `${depth * 14 + 4}px` }}>
        <span className="text-faint">{depth > 0 ? "└" : "■"}</span>
        <div className="min-w-0 flex-1">
          <div className="text-ink font-medium truncate">{node.name}</div>
          <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">{node.job_title ?? "—"} · {node.department ?? "—"}</div>
        </div>
      </div>
      {kids.map((k) => (
        <TreeNode key={k.id} node={k} children={children} depth={depth + 1} />
      ))}
    </div>
  );
}

export default function OrgDesignPage() {
  const q = useQuery({ queryKey: ["org-design"], queryFn: () => apiFetch<Analysis>("/org-design/analyze") });
  const a = q.data;

  const tree = useMemo(() => (a ? buildTree(a.nodes) : null), [a]);
  const roots = useMemo(() => (a ? a.nodes.filter((n) => !n.manager_id) : []), [a]);

  const insightsBySev = useMemo(() => {
    if (!a) return { high: [], medium: [], low: [] };
    const out: Record<string, OrgInsight[]> = { high: [], medium: [], low: [] };
    for (const i of a.insights) out[i.severity].push(i);
    return out;
  }, [a]);

  const deptTotal = useMemo(() => {
    if (!a) return 0;
    return Object.values(a.dept_headcount).reduce((s, n) => s + n, 0) || 1;
  }, [a]);

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="People"
        title="Org design"
        subtitle="Manager span · layers · consolidation candidates · departmental imbalance. Calibrated for SMB scale."
        actions={<Action variant="subtle" onClick={() => q.refetch()}>Re-analyze</Action>}
      />

      {/* Headline metrics — calm, single-line */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Summary label="Employees" value={a?.employees ?? "—"} />
        <Summary label="Managers" value={a?.managers ?? "—"} />
        <Summary label="Layers" value={a?.layers ?? "—"} />
        <Summary label="Avg span" value={a?.avg_span ?? "—"} />
        <Summary label="Max span" value={a?.max_span ?? "—"} />
      </div>

      {/* AI insights */}
      <Surface>
        <SectionTitle eyebrow="AI insights" title="What to adjust" description="Heuristic recommendations calibrated for SMB org shape. Confirm before acting." />
        {a && a.insights.length === 0 ? (
          <div className="mt-4"><EmptyState title="Org shape looks healthy" description="No imbalances detected at this size." /></div>
        ) : (
          <div className="mt-4 space-y-2">
            {(["high", "medium", "low"] as const).flatMap((sev) =>
              insightsBySev[sev].map((i, idx) => (
                <div key={`${sev}-${idx}`} className="rounded-md border border-line bg-canvas p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-ink">{i.subject}</span>
                        <Pill tone={SEV_TONE[i.severity]}>{i.severity}</Pill>
                        <span className="text-2xs uppercase tracking-eyebrow text-muted">{i.kind.replace(/_/g, " ")}</span>
                      </div>
                      <div className="text-xs text-body mt-1">{i.detail}</div>
                      <div className="text-xs text-muted mt-1">→ {i.recommendation}</div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </Surface>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Dept headcount */}
        <Surface>
          <SectionTitle eyebrow="Distribution" title="Department headcount" />
          <div className="mt-4 space-y-2.5">
            {a && Object.keys(a.dept_headcount).length > 0 ? (
              Object.entries(a.dept_headcount)
                .sort((x, y) => y[1] - x[1])
                .map(([dept, n]) => (
                  <div key={dept}>
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-ink">{dept}</span>
                      <span className="font-mono text-xs text-muted">{n}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-sunken overflow-hidden">
                      <div className="h-full bg-accent" style={{ width: `${Math.min(100, (n / deptTotal) * 100)}%` }} />
                    </div>
                  </div>
                ))
            ) : (
              <div className="text-sm text-muted">—</div>
            )}
          </div>
        </Surface>

        {/* Org tree */}
        <Surface className="lg:col-span-2">
          <SectionTitle eyebrow="Hierarchy" title="Org tree" description="Light reporting graph from employee records." />
          <div className="mt-3 max-h-[420px] overflow-auto -mx-2 px-2">
            {!a || !tree ? (
              <div className="text-sm text-muted py-6 text-center">Loading…</div>
            ) : roots.length === 0 ? (
              <EmptyState title="No top-level managers" description="Set a top-level manager to render the tree." />
            ) : (
              <Divider className="my-2" />
            )}
            {a && tree && roots.map((root) => (
              <TreeNode key={root.id} node={root} children={tree} depth={0} />
            ))}
          </div>
        </Surface>
      </div>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-surface p-4">
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
