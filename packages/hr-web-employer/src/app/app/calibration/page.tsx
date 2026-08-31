"use client";
/**
 * 9-Box Performance × Potential calibration matrix.
 */
import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Action, Avatar, EmptyState, PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";

type GridItem = { id: string; employee_id: string; employee_name: string; team: string; manager_name: string; promotion_ready: boolean; risk_flags: string[] };
type Grid = { grid: Record<string, GridItem[]>; cells: Record<string, { label: string; interpretation: string }>; n_placements: number };
type ManagerSig = {
  manager_id: string; manager_name: string; n_reports: number;
  avg_performance: number; avg_potential: number;
  spread_performance: number; spread_potential: number;
  bias_flags: string[];
};
type Highlights = {
  promotion_ready: any[]; stars: any[]; retention_risk: any[]; underperformers: any[];
};

export default function CalibrationPage() {
  const [view, setView] = useState<"grid" | "managers" | "highlights">("grid");
  const gridQ = useQuery({ queryKey: ["calib-grid"], queryFn: () => apiFetch<Grid>("/calibration/grid") });
  const mgrQ = useQuery({ queryKey: ["calib-managers"], queryFn: () => apiFetch<{ managers: ManagerSig[] }>("/calibration/managers") });
  const highQ = useQuery({ queryKey: ["calib-highlights"], queryFn: () => apiFetch<Highlights>("/calibration/highlights") });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Performance · Calibration"
        title="9-Box Calibration"
        subtitle="Place every report on a performance × potential grid. Calibrate across managers. Surface bias patterns before the review cycle locks."
      />

      <div className="flex flex-wrap gap-2">
        {([["grid", "9-box grid"], ["managers", "Manager calibration"], ["highlights", "Promotion + risk highlights"]] as const).map(([k, lbl]) => (
          <Action key={k} variant={view === k ? "primary" : "subtle"} size="sm" onClick={() => setView(k)}>{lbl}</Action>
        ))}
      </div>

      {view === "grid" && gridQ.data && <NineBoxGrid grid={gridQ.data} />}
      {view === "managers" && (
        <Surface>
          <SectionTitle eyebrow="Manager calibration" title="Rater behaviour patterns" description="Each manager's distribution of ratings + flagged biases." />
          {mgrQ.data?.managers.length === 0 ? (
            <div className="mt-3"><EmptyState title="No manager data yet" description="Place at least one report to surface calibration." /></div>
          ) : (
            <div className="mt-4 space-y-3">
              {(mgrQ.data?.managers ?? []).map((m) => (
                <div key={m.manager_id} className="rounded-md border border-line bg-canvas p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-sm font-semibold text-ink">{m.manager_name}</div>
                      <div className="text-xs text-muted">{m.n_reports} reports · avg perf {m.avg_performance} · avg pot {m.avg_potential}</div>
                    </div>
                    <Pill tone={m.bias_flags.length === 0 ? "success" : m.bias_flags.length >= 2 ? "danger" : "warn"}>
                      {m.bias_flags.length} flag{m.bias_flags.length === 1 ? "" : "s"}
                    </Pill>
                  </div>
                  {m.bias_flags.length > 0 && (
                    <ul className="mt-2 space-y-1 text-xs text-body">
                      {m.bias_flags.map((f, i) => <li key={i}>• {f}</li>)}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          )}
        </Surface>
      )}
      {view === "highlights" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <Surface>
            <SectionTitle eyebrow="Promotion ready" title={`${highQ.data?.promotion_ready.length ?? 0} candidates`} />
            <HighlightList items={highQ.data?.promotion_ready ?? []} />
          </Surface>
          <Surface>
            <SectionTitle eyebrow="Retention risk" title={`${highQ.data?.retention_risk.length ?? 0} top performers`} description="Highest performers — flight risk if not protected." />
            <HighlightList items={highQ.data?.retention_risk ?? []} />
          </Surface>
          <Surface>
            <SectionTitle eyebrow="Stars" title={`${highQ.data?.stars.length ?? 0} on the top-right`} description="3-3 cell: succession + retention focus." />
            <HighlightList items={highQ.data?.stars ?? []} />
          </Surface>
          <Surface>
            <SectionTitle eyebrow="Underperformers" title={`${highQ.data?.underperformers.length ?? 0} need coaching`} description="1-1 cell: coach hard or manage out." />
            <HighlightList items={highQ.data?.underperformers ?? []} />
          </Surface>
        </div>
      )}
    </div>
  );
}

function HighlightList({ items }: { items: any[] }) {
  if (items.length === 0) return <div className="text-sm text-muted mt-2">None.</div>;
  return (
    <ul className="mt-3 divide-y divide-line">
      {items.map((p) => (
        <li key={p.id} className="py-2 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 min-w-0">
            <Avatar name={p.employee_name} size={28} />
            <div className="min-w-0">
              <div className="text-sm font-medium text-ink">{p.employee_name}</div>
              <div className="text-xs text-muted">{p.team} · {p.cell_label}</div>
            </div>
          </div>
          {p.risk_flags && p.risk_flags.length > 0 && <Pill tone="warn">{p.risk_flags.length} bias flag</Pill>}
        </li>
      ))}
    </ul>
  );
}

function NineBoxGrid({ grid }: { grid: Grid }) {
  // Rows: potential 3 (top) → 1 (bottom). Cols: performance 1 (left) → 3 (right).
  const rows = [3, 2, 1];
  const cols = [1, 2, 3];
  const POT_LABEL = { 1: "Limited potential", 2: "Growth potential", 3: "High potential" };
  const PERF_LABEL = { 1: "Below bar", 2: "Meeting bar", 3: "Exceeding bar" };
  return (
    <Surface>
      <SectionTitle eyebrow="9-Box" title="Performance × Potential" description="Click a cell to read its talent-management interpretation." />
      <div className="mt-4 overflow-x-auto">
        <div className="min-w-[640px]">
          <div className="grid grid-cols-[120px_repeat(3,minmax(0,1fr))] gap-2">
            <div />
            {cols.map((c) => (
              <div key={c} className="text-xs uppercase tracking-eyebrow text-muted text-center pb-1">{(PERF_LABEL as any)[c]}</div>
            ))}
            {rows.map((r) => (
              // A bare <> cannot carry a key, so React warned "Each child in a
              // list should have a unique key" for every row of the 9-box grid.
              // The keys on the elements INSIDE the fragment do not satisfy it:
              // the keyed thing has to be what map() returns.
              <Fragment key={`row-${r}`}>
                <div key={`lbl-${r}`} className="text-xs uppercase tracking-eyebrow text-muted flex items-center">{(POT_LABEL as any)[r]}</div>
                {cols.map((c) => {
                  const key = `${c}-${r}`;
                  const items = grid.grid[key] ?? [];
                  const cell = grid.cells[key];
                  // Visual emphasis: top-right corner is the bright spot
                  const hot = c === 3 && r >= 2;
                  return (
                    <div
                      key={key}
                      className={`rounded-md border border-line bg-canvas p-2 min-h-[140px] flex flex-col ${hot ? "ring-1 ring-ink/15" : ""}`}
                    >
                      <div className="text-2xs uppercase tracking-eyebrow text-muted">{cell?.label}</div>
                      <div className="text-2xs text-muted mt-0.5 line-clamp-2">{cell?.interpretation}</div>
                      <div className="mt-2 flex flex-wrap gap-1.5 flex-1">
                        {items.map((p) => (
                          <span key={p.id} title={`${p.employee_name} · ${p.team}`} className="inline-flex items-center gap-1 rounded-full bg-surface border border-line px-2 py-0.5 text-2xs text-ink">
                            <Avatar name={p.employee_name} size={16} />
                            {p.employee_name.split(" ")[0]}
                            {p.promotion_ready && <span className="text-[8px] text-success-fg">●</span>}
                          </span>
                        ))}
                      </div>
                      {items.length > 0 && (
                        <div className="text-2xs text-muted mt-1">{items.length} placed</div>
                      )}
                    </div>
                  );
                })}
              </Fragment>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 flex items-center gap-3 text-2xs uppercase tracking-eyebrow text-muted">
        <span>● = promotion-ready signal</span>
        <span>· {grid.n_placements} total placements</span>
      </div>
    </Surface>
  );
}
