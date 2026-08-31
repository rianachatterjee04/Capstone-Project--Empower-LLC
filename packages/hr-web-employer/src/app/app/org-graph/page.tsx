"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { SampleBanner } from "@/components/SampleBanner";

import { PageHeader, Surface, SectionTitle, Pill, EmptyState, Divider, Avatar } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Node = {
  id: string; name: string; title: string | null; department: string | null;
  manager_id: string | null; depth: number; x: number; y: number; span: number;
  is_manager: boolean;
  /** True when this node came from the invented fallback org, not your employees. */
  is_sample?: boolean;
  attrition_band: "low" | "medium" | "high";
  succession: "none" | "groom" | "ready";
  hiring_reqs: number;
};
type Edge = { source: string; target: string; kind: string };
type Graph = {
  nodes: Node[]; edges: Edge[];
  viewbox: { width: number; height: number };
  departments: string[];
  summary: {
    total_nodes: number; managers: number; max_depth: number;
    high_risk: Node[]; ready_successors: Node[]; overloaded_managers: Node[];
    hiring_hotspots: { department: string; open_reqs: number }[];
  };
};

type Overlay = "none" | "attrition" | "succession" | "hiring" | "span";

const OVERLAY_LABEL: Record<Overlay, string> = {
  none: "No overlay",
  attrition: "Attrition risk",
  succession: "Succession",
  hiring: "Hiring hotspots",
  span: "Manager span",
};

function nodeFill(n: Node, overlay: Overlay): string {
  if (overlay === "attrition") {
    if (n.attrition_band === "high") return "#FEE2E2";
    if (n.attrition_band === "medium") return "#FEF3C7";
    return "#DCFCE7";
  }
  if (overlay === "succession") {
    if (n.succession === "ready") return "#DCFCE7";
    if (n.succession === "groom") return "#FEF3C7";
    return "#FFFFFF";
  }
  if (overlay === "hiring") {
    return n.hiring_reqs > 0 ? "#E0F2FE" : "#FFFFFF";
  }
  if (overlay === "span") {
    if (n.span >= 9) return "#FEE2E2";
    if (n.span >= 5) return "#FEF3C7";
    if (n.span > 0) return "#DCFCE7";
    return "#FFFFFF";
  }
  return "#FFFFFF";
}

function nodeStroke(n: Node, overlay: Overlay): string {
  if (overlay === "attrition" && n.attrition_band === "high") return "#FECACA";
  if (overlay === "attrition" && n.attrition_band === "medium") return "#FDE68A";
  if (overlay === "succession" && n.succession === "ready") return "#BBF7D0";
  if (overlay === "succession" && n.succession === "groom") return "#FDE68A";
  if (overlay === "hiring" && n.hiring_reqs > 0) return "#BAE6FD";
  if (overlay === "span" && n.span >= 9) return "#FECACA";
  if (overlay === "span" && n.span >= 5) return "#FDE68A";
  return "#E2E8F0";
}

export default function OrgGraphPage() {
  const q = useQuery({ queryKey: ["org-graph"], queryFn: () => apiFetch<Graph>("/org-graph") });
  const [overlay, setOverlay] = useState<Overlay>("attrition");
  const [hovered, setHovered] = useState<string>("");
  const [selected, setSelected] = useState<string>("");

  const g = q.data;

  const byId = useMemo(() => {
    const m = new Map<string, Node>();
    for (const n of g?.nodes ?? []) m.set(n.id, n);
    return m;
  }, [g]);

  // An org chart is read as a statement of who reports to whom, and these
  // nodes additionally carry an attrition band and a succession rating --
  // claims about named people. When they are invented, say so above the chart.
  const allSample = !!g?.nodes.length && g.nodes.every((n) => n.is_sample);

  const active = selected || hovered;
  const activeNode = active ? byId.get(active) : undefined;

  return (
    <div className="space-y-7 fp-fade-in">
      {allSample && (
        <SampleBanner
          what="people"
          note="This chart is an illustrative example org. None of these people, reporting lines, attrition bands or succession ratings come from your own records."
        />
      )}
      <PageHeader
        eyebrow="People"
        title="Org graph"
        subtitle="Interactive reporting graph with calm AI overlays — attrition, succession, hiring, and manager span."
        actions={
          <select
            value={overlay}
            onChange={(e) => setOverlay(e.target.value as Overlay)}
            className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink"
          >
            {(Object.keys(OVERLAY_LABEL) as Overlay[]).map((k) => (
              <option key={k} value={k}>{OVERLAY_LABEL[k]}</option>
            ))}
          </select>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="People" value={g?.summary.total_nodes ?? "—"} />
        <Stat label="Managers" value={g?.summary.managers ?? "—"} />
        <Stat label="Max depth" value={g?.summary.max_depth ?? "—"} />
        <Stat label="High risk" value={g?.summary.high_risk.length ?? "—"} tone={(g?.summary.high_risk.length ?? 0) ? "danger" : "neutral"} />
        <Stat label="Ready successors" value={g?.summary.ready_successors.length ?? "—"} tone={(g?.summary.ready_successors.length ?? 0) ? "success" : "neutral"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-5">
        {/* Graph */}
        <Surface pad="sm">
          {!g ? (
            <EmptyState title="Loading…" />
          ) : g.nodes.length === 0 ? (
            <EmptyState title="No org data" description="Seed the directory to render the graph." />
          ) : (
            <div className="rounded-md border border-line bg-canvas overflow-auto">
              <svg
                viewBox={`0 0 ${g.viewbox.width} ${g.viewbox.height}`}
                className="w-full"
                style={{ minHeight: 360 }}
              >
                {/* Edges */}
                {g.edges.map((e, i) => {
                  const s = byId.get(e.source);
                  const t = byId.get(e.target);
                  if (!s || !t) return null;
                  const isActive = active === e.source || active === e.target;
                  return (
                    <line
                      key={i}
                      x1={s.x}
                      y1={s.y + 18}
                      x2={t.x}
                      y2={t.y - 18}
                      stroke={isActive ? "#0F172A" : "#E2E8F0"}
                      strokeWidth={isActive ? 1.5 : 1}
                    />
                  );
                })}
                {/* Nodes */}
                {g.nodes.map((n) => {
                  const isActive = active === n.id;
                  return (
                    <g
                      key={n.id}
                      onMouseEnter={() => setHovered(n.id)}
                      onMouseLeave={() => setHovered("")}
                      onClick={() => setSelected(n.id === selected ? "" : n.id)}
                      style={{ cursor: "pointer" }}
                    >
                      <rect
                        x={n.x - 78}
                        y={n.y - 18}
                        width={156}
                        height={42}
                        rx={10}
                        ry={10}
                        fill={nodeFill(n, overlay)}
                        stroke={isActive ? "#0F172A" : nodeStroke(n, overlay)}
                        strokeWidth={isActive ? 1.5 : 1}
                      />
                      <text
                        x={n.x}
                        y={n.y - 2}
                        textAnchor="middle"
                        fontSize="11"
                        fontWeight="600"
                        fill="#0F172A"
                      >
                        {n.name}
                      </text>
                      <text
                        x={n.x}
                        y={n.y + 12}
                        textAnchor="middle"
                        fontSize="9"
                        letterSpacing="0.06em"
                        fill="#475569"
                      >
                        {(n.title ?? "—").toUpperCase()}
                      </text>
                      {/* Overlay badge */}
                      {overlay === "attrition" && n.attrition_band !== "low" && (
                        <circle cx={n.x + 70} cy={n.y - 14} r="5" fill={n.attrition_band === "high" ? "#8B2B25" : "#7A5A1B"} />
                      )}
                      {overlay === "succession" && n.succession !== "none" && (
                        <circle cx={n.x + 70} cy={n.y - 14} r="5" fill={n.succession === "ready" ? "#2F5D3A" : "#7A5A1B"} />
                      )}
                      {overlay === "hiring" && n.hiring_reqs > 0 && (
                        <circle cx={n.x + 70} cy={n.y - 14} r="5" fill="#34384B" />
                      )}
                      {overlay === "span" && n.span > 0 && (
                        <text x={n.x + 65} y={n.y - 10} fontSize="9" fontWeight="600" fill="#475569">{n.span}</text>
                      )}
                    </g>
                  );
                })}
              </svg>
            </div>
          )}
          <Divider className="my-3" />
          <LegendRow overlay={overlay} />
        </Surface>

        {/* Detail + summary */}
        <div className="space-y-5">
          <Surface>
            <SectionTitle eyebrow="Detail" title={activeNode ? activeNode.name : "Hover or click a node"} />
            {activeNode ? (
              <>
                <div className="mt-3 flex items-center gap-2">
                  <Avatar name={activeNode.name} size={32} />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-ink truncate">{activeNode.title ?? "—"}</div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">{activeNode.department ?? "—"}</div>
                  </div>
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <Pill tone={activeNode.attrition_band === "high" ? "danger" : activeNode.attrition_band === "medium" ? "warn" : "success"}>
                    Attrition · {activeNode.attrition_band}
                  </Pill>
                  {activeNode.succession !== "none" && (
                    <Pill tone={activeNode.succession === "ready" ? "success" : "warn"}>
                      Succession · {activeNode.succession}
                    </Pill>
                  )}
                  {activeNode.is_manager && <Pill tone="neutral">Span · {activeNode.span}</Pill>}
                  {activeNode.hiring_reqs > 0 && <Pill tone="info">+{activeNode.hiring_reqs} reqs</Pill>}
                </div>
                <Divider className="my-3" />
                <div className="flex flex-col gap-1.5 text-sm">
                  <Link href={`/app/people/${activeNode.id}?tab=twin`} className="flex items-center justify-between rounded-md hover:bg-sunken px-2 py-1.5 text-body hover:text-ink">
                    <span>Open digital twin</span><IconArrowUpRight />
                  </Link>
                  <Link href={`/app/comp`} className="flex items-center justify-between rounded-md hover:bg-sunken px-2 py-1.5 text-body hover:text-ink">
                    <span>Run comp review</span><IconArrowUpRight />
                  </Link>
                </div>
              </>
            ) : (
              <div className="mt-3 text-sm text-muted">Pick a node to see its risk + succession + hiring context, with one-click jumps to comp and twin.</div>
            )}
          </Surface>

          <Surface>
            <SectionTitle eyebrow="Overlay summary" title="What the graph is showing" />
            <div className="mt-3 space-y-2 text-sm">
              {(g?.summary.high_risk ?? []).length > 0 && (
                <div>
                  <div className="fp-eyebrow text-danger-fg">High risk</div>
                  <div className="text-body">{(g?.summary.high_risk ?? []).map((n) => n.name).join(" · ")}</div>
                </div>
              )}
              {(g?.summary.ready_successors ?? []).length > 0 && (
                <div>
                  <div className="fp-eyebrow text-success-fg">Ready successors</div>
                  <div className="text-body">{(g?.summary.ready_successors ?? []).map((n) => `${n.name} → ${n.title ?? ""}`).join(" · ")}</div>
                </div>
              )}
              {(g?.summary.hiring_hotspots ?? []).length > 0 && (
                <div>
                  <div className="fp-eyebrow text-info-fg">Hiring hotspots</div>
                  <div className="text-body">{(g?.summary.hiring_hotspots ?? []).map((h) => `${h.department} · ${h.open_reqs}`).join(" · ")}</div>
                </div>
              )}
              {(g?.summary.overloaded_managers ?? []).length > 0 && (
                <div>
                  <div className="fp-eyebrow text-warn-fg">Overloaded managers</div>
                  <div className="text-body">{(g?.summary.overloaded_managers ?? []).map((n) => `${n.name} (${n.span})`).join(" · ")}</div>
                </div>
              )}
              {(!g || (g.summary.high_risk.length + g.summary.ready_successors.length + g.summary.hiring_hotspots.length + g.summary.overloaded_managers.length === 0)) && (
                <div className="text-sm text-muted">Org graph reads calm — nothing pressing across overlays.</div>
              )}
            </div>
          </Surface>
        </div>
      </div>

      <p className="text-xs text-muted">Overlays are calibrated for SMB org shape. Click a node to open its digital twin or jump into comp review.</p>
    </div>
  );
}

function LegendRow({ overlay }: { overlay: Overlay }) {
  const items: { color: string; label: string }[] = (() => {
    switch (overlay) {
      case "attrition":  return [{ color: "#FEE2E2", label: "high" }, { color: "#FEF3C7", label: "medium" }, { color: "#DCFCE7", label: "low" }];
      case "succession": return [{ color: "#DCFCE7", label: "ready" }, { color: "#FEF3C7", label: "groom" }];
      case "hiring":     return [{ color: "#E0F2FE", label: "open reqs" }];
      case "span":       return [{ color: "#FEE2E2", label: "9+" }, { color: "#FEF3C7", label: "5–8" }, { color: "#DCFCE7", label: "1–4" }];
      default: return [];
    }
  })();
  if (items.length === 0) return null;
  return (
    <div className="flex items-center gap-3 text-2xs uppercase tracking-eyebrow text-muted">
      <span>Legend</span>
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5">
          <span className="inline-block w-3 h-3 rounded-sm border border-line" style={{ background: it.color }} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "danger" | "success" }) {
  const ring: Record<string, string> = {
    neutral: "",
    danger: "ring-1 ring-danger-line",
    success: "ring-1 ring-success-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
