"use client";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Divider, KeyValue } from "@/components/ds";

type NodeType = "human" | "ai_agent" | "contractor" | "bot";

type WFNode = {
  id: string;
  type: NodeType;
  name: string;
  role: string;
  team: string;
  manager_id: string | null;
  skills: string[];
  performance: Record<string, any>;
  compensation: Record<string, any>;
  cost_annual: number | null;
  permissions: string[];
  /** null when nothing on record supports a score. Not a low score. */
  trust_score: number | null;
  source?: "employee_record" | "sample_profile";
  trust_basis?: string | null;
  risk_score: number;
  ai_interactions: Record<string, any>;
  depth: number; x: number; y: number; span: number;
};
type Edge = { source: string; target: string; kind: string };
type Graph = {
  as_of: string;
  filters: { type: string | null; team: string | null };
  nodes: WFNode[];
  edges: Edge[];
  viewbox: { width: number; height: number };
  summary: {
    total_workforce: number;
    headcount_by_type: Record<string, number>;
    total_workforce_cost: number;
    avg_trust: number | null;
    workers_without_a_cost?: number;
    workers_without_a_trust_score?: number;
    avg_trust_ai: number | null;
    ai_agent_count: number;
    bot_count: number;
    human_count: number;
    contractor_count: number;
  };
  provenance?: { employee_records: number; sample_profiles: number; note: string };
};
type NodeDetail = {
  node: WFNode;
  manager: WFNode | null;
  direct_reports: WFNode[];
  report_count: number;
};

const TYPE_META: Record<NodeType, { label: string; fill: string; stroke: string; dot: string }> = {
  human:      { label: "Human",      fill: "#EFF6FF", stroke: "#BFDBFE", dot: "#2563EB" },
  ai_agent:   { label: "AI agent",   fill: "#F5F3FF", stroke: "#DDD6FE", dot: "#7C3AED" },
  contractor: { label: "Contractor", fill: "#FFF7ED", stroke: "#FED7AA", dot: "#EA580C" },
  bot:        { label: "Bot",        fill: "#ECFEFF", stroke: "#A5F3FC", dot: "#0891B2" },
};

const TYPES: NodeType[] = ["human", "ai_agent", "contractor", "bot"];

function trustTone(score: number): "success" | "warn" | "danger" {
  if (score >= 75) return "success";
  if (score >= 50) return "warn";
  return "danger";
}
function riskTone(score: number): "success" | "warn" | "danger" {
  if (score >= 60) return "danger";
  if (score >= 35) return "warn";
  return "success";
}
function money(n?: number): string {
  if (n == null) return "—";
  return `$${Math.round(n).toLocaleString()}`;
}

export default function WorkforceGraphPage() {
  const [typeFilter, setTypeFilter] = useState<NodeType | "">("");
  const [selected, setSelected] = useState<string | null>(null);

  const q = useQuery({
    queryKey: ["workforce-graph", typeFilter],
    queryFn: () => apiFetch<Graph>(`/workforce/graph${typeFilter ? `?type=${typeFilter}` : ""}`),
    refetchInterval: 120_000,
  });
  const data = q.data;

  const detailQ = useQuery({
    queryKey: ["workforce-node", selected],
    queryFn: () => apiFetch<NodeDetail>(`/workforce/node/${selected}`),
    enabled: !!selected,
  });

  const nodeById = useMemo(() => {
    const m: Record<string, WFNode> = {};
    (data?.nodes ?? []).forEach((n) => (m[n.id] = n));
    return m;
  }, [data]);

  const s = data?.summary;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Workforce Intelligence"
        title="Workforce Graph"
        subtitle="The org chart for the AI era — humans, AI agents, contractors, and bots in one map, each scored for trust and risk from what is actually on record. A worker with nothing to score is shown unscored rather than given a number. No HRIS or hiring marketplace can show you this."
      />

      {/* "Total workforce 11" for an organisation with one employee, with a
          trust score on every node, under a header claiming no HRIS can show
          you this. The claim is a good one — it has to be about the customer's
          own workforce to mean anything. */}
      {data?.provenance && data.provenance.sample_profiles > 0 && (
        <Surface pad="md">
          <div className="fp-eyebrow">What is on this map</div>
          <p className="mt-1 text-sm text-body">{data.provenance.note}</p>
        </Surface>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Total workforce" value={s?.total_workforce ?? "—"} />
        <Stat label="Humans" value={s?.human_count ?? "—"} />
        <Stat label="AI agents" value={s?.ai_agent_count ?? "—"} tone="info" />
        <Stat label="Bots + contractors" value={s ? s.bot_count + s.contractor_count : "—"} />
        <Stat
          label="Avg trust"
          value={s?.avg_trust ?? "Not scored"}
          tone={s?.avg_trust == null ? "neutral" : s.avg_trust >= 75 ? "success" : "warn"}
        />
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        <button
          onClick={() => setTypeFilter("")}
          className={`text-xs rounded-md px-3 py-1.5 border ${typeFilter === "" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
        >
          All workers
        </button>
        {TYPES.map((t) => (
          <button
            key={t}
            onClick={() => setTypeFilter(typeFilter === t ? "" : t)}
            className={`text-xs rounded-md px-3 py-1.5 border inline-flex items-center gap-1.5 ${typeFilter === t ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}
          >
            <span className="inline-block h-2 w-2 rounded-full" style={{ background: TYPE_META[t].dot }} />
            {TYPE_META[t].label}
            <span className="text-muted">{s?.headcount_by_type?.[t] ?? 0}</span>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* The living map */}
        <div className="lg:col-span-2">
          <Surface pad="sm">
            <SectionTitle eyebrow="The living map" title="Reporting graph" description="Click any node to open its drill-in panel." />
            {q.isLoading ? (
              <EmptyState title="Loading workforce…" />
            ) : !data || data.nodes.length === 0 ? (
              <EmptyState title="No workers in this filter" />
            ) : (
              <div className="mt-3 overflow-auto rounded-md border border-line bg-canvas">
                <svg
                  viewBox={`0 0 ${data.viewbox.width} ${data.viewbox.height}`}
                  width="100%"
                  style={{ minWidth: 640, maxHeight: 560 }}
                >
                  {data.edges.map((e, i) => {
                    const a = nodeById[e.source];
                    const b = nodeById[e.target];
                    if (!a || !b) return null;
                    return (
                      <line
                        key={i}
                        x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                        stroke="#CBD5E1" strokeWidth={1}
                      />
                    );
                  })}
                  {data.nodes.map((n) => {
                    const meta = TYPE_META[n.type];
                    const isSel = selected === n.id;
                    return (
                      <g key={n.id} transform={`translate(${n.x},${n.y})`} style={{ cursor: "pointer" }} onClick={() => setSelected(n.id)}>
                        <rect
                          x={-64} y={-22} width={128} height={44} rx={8}
                          fill={meta.fill}
                          stroke={isSel ? meta.dot : meta.stroke}
                          strokeWidth={isSel ? 2.5 : 1.25}
                        />
                        <circle cx={-52} cy={-8} r={4} fill={meta.dot} />
                        <text x={-44} y={-4} fontSize={9} fill="#334155" fontWeight={600}>
                          {n.name.length > 16 ? n.name.slice(0, 15) + "…" : n.name}
                        </text>
                        <text x={-52} y={9} fontSize={7.5} fill="#64748B">
                          {n.role.length > 22 ? n.role.slice(0, 21) + "…" : n.role}
                        </text>
                        {/* Trust dot. A node with no score gets a grey dash,
                            not a red circle: an employee we hold no
                            performance data on is unscored, and colouring that
                            as low trust is an accusation. */}
                        <circle
                          cx={52}
                          cy={-10}
                          r={7}
                          fill={
                            n.trust_score == null
                              ? "#94A3B8"
                              : n.trust_score >= 75
                                ? "#16A34A"
                                : n.trust_score >= 50
                                  ? "#D97706"
                                  : "#DC2626"
                          }
                        />
                        <text x={52} y={-7.5} fontSize={7} fill="#FFFFFF" textAnchor="middle" fontWeight={700}>
                          {n.trust_score ?? "–"}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
            )}
            <div className="mt-2 flex flex-wrap gap-3 text-2xs text-muted">
              {TYPES.map((t) => (
                <span key={t} className="inline-flex items-center gap-1.5">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: TYPE_META[t].dot }} />
                  {TYPE_META[t].label}
                </span>
              ))}
              <span className="inline-flex items-center gap-1.5">
                <span className="inline-block h-2.5 w-2.5 rounded-full bg-[#16A34A]" /> trust score (green ≥75)
              </span>
            </div>
          </Surface>
        </div>

        {/* Drill-in panel */}
        <div>
          <Surface pad="sm">
            <SectionTitle eyebrow="Drill-in" title="Node panel" />
            {!selected ? (
              <EmptyState title="Select a worker" description="Click a node on the map to inspect skills, comp/cost, trust and risk." />
            ) : detailQ.isLoading ? (
              <EmptyState title="Loading…" />
            ) : detailQ.data ? (
              <NodePanel detail={detailQ.data} />
            ) : (
              <EmptyState title="Not found" />
            )}
          </Surface>
        </div>
      </div>
    </div>
  );
}

function NodePanel({ detail }: { detail: NodeDetail }) {
  const n = detail.node;
  const meta = TYPE_META[n.type];
  return (
    <div className="mt-2 space-y-3">
      <div className="flex items-center gap-2">
        <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: meta.dot }} />
        <div className="min-w-0">
          <div className="text-base font-semibold text-ink tracking-tight">{n.name}</div>
          <div className="text-2xs uppercase tracking-eyebrow text-muted">{meta.label} · {n.role} · {n.team}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <ScoreCard
          label="Trust"
          value={n.trust_score}
          tone={n.trust_score == null ? "warn" : trustTone(n.trust_score)}
          note={n.trust_score == null ? n.trust_basis ?? "not scored" : undefined}
        />
        <ScoreCard label="Risk" value={n.risk_score} tone={riskTone(n.risk_score)} />
      </div>

      <Divider />

      <KeyValue label="Cost / year" value={
        n.compensation.kind === "salary" ? `${money(n.compensation.annual_loaded)} loaded`
        : n.compensation.kind === "run_cost" ? `${money(n.compensation.annual_run_cost)} run cost`
        : `${money(n.compensation.annual_cost)} contract`
      } />
      <KeyValue label="Performance" value={n.performance.summary ?? "—"} />
      {n.performance.attrition_band && (
        <KeyValue label="Attrition band" value={
          <Pill tone={n.performance.attrition_band === "high" ? "danger" : n.performance.attrition_band === "medium" ? "warn" : "success"}>
            {n.performance.attrition_band}
          </Pill>
        } />
      )}
      {n.ai_interactions?.autonomy && (
        <>
          <KeyValue label="Autonomy" value={<Pill tone="info">{n.ai_interactions.autonomy}</Pill>} />
          <KeyValue label="Runs / 30d" value={n.ai_interactions.runs_30d ?? "—"} />
          <KeyValue label="Approvals" value={`${n.ai_interactions.approvals_granted ?? 0} ok · ${n.ai_interactions.approvals_pending ?? 0} pending`} />
        </>
      )}

      <Divider />
      <div className="fp-eyebrow mb-1">Skills</div>
      <div className="flex flex-wrap gap-1.5">
        {(n.skills ?? []).length === 0 ? <span className="text-2xs text-muted">—</span> :
          n.skills.map((s) => <Pill key={s}>{s}</Pill>)}
      </div>

      <div className="fp-eyebrow mb-1 mt-2">Permissions / scopes</div>
      <div className="flex flex-wrap gap-1.5">
        {(n.permissions ?? []).map((p) => <span key={p} className="text-2xs rounded border border-line bg-canvas px-1.5 py-0.5 text-muted font-mono">{p}</span>)}
      </div>

      <Divider />
      <KeyValue label="Manager" value={detail.manager?.name ?? "—"} />
      <KeyValue label="Direct reports" value={detail.report_count} />
      {detail.direct_reports.length > 0 && (
        <ul className="mt-1 space-y-1">
          {detail.direct_reports.map((r) => (
            <li key={r.id} className="text-2xs text-body flex items-center gap-1.5">
              <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: TYPE_META[r.type].dot }} />
              {r.name} · <span className="text-muted">{r.role}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ScoreCard({ label, value, tone, note }: {
  label: string;
  value: number | null;
  tone: "success" | "warn" | "danger";
  note?: string;
}) {
  const bg: Record<string, string> = { success: "bg-success-bg text-success-fg", warn: "bg-warn-bg text-warn-fg", danger: "bg-danger-bg text-danger-fg" };
  return (
    <div className={`rounded-md p-3 ${bg[tone]}`}>
      <div className="text-2xs uppercase tracking-eyebrow opacity-80">{label}</div>
      <div className="text-2xl font-bold tabular-nums">{value ?? "Not scored"}</div>
      {note && <div className="mt-0.5 text-2xs opacity-80">{note}</div>}
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" | "info" }) {
  const ring: Record<string, string> = {
    neutral: "", success: "ring-1 ring-success-line", warn: "ring-1 ring-warn-line", info: "ring-1 ring-accent/40",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
