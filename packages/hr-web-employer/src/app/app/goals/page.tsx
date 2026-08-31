"use client";
import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPatch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider, Avatar } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type KeyResult = {
  id: string;
  title: string;
  metric_label: string;
  target: number;
  current: number;
  direction: "up" | "down";
  owner?: string | null;
  status: "on_track" | "at_risk" | "off_track" | "done";
  progress_pct: number;
  linked_task_count?: number;
  linked_task_done?: number;
};

type Objective = {
  id: string;
  title: string;
  owner: string;
  team?: string | null;
  cycle: string;
  status: "on_track" | "at_risk" | "off_track" | "done";
  key_results: KeyResult[];
  progress_pct: number;
};

type GoalsResponse = {
  items: Objective[];
  summary: {
    total: number; on_track: number; at_risk: number; off_track: number;
    avg_progress_pct: number;
    cycles: string[];
    teams: string[];
  };
  provenance?: { all_sample: boolean; note: string | null };
};

const STATUS_TONE: Record<string, "success" | "warn" | "danger" | "info"> = {
  on_track: "success",
  at_risk: "warn",
  off_track: "danger",
  done: "info",
};

export default function GoalsPage() {
  const qc = useQueryClient();
  const [cycle, setCycle] = useState<string>("");
  const [team, setTeam] = useState<string>("");

  const q = useQuery({
    queryKey: ["goals", cycle, team],
    queryFn: () => apiFetch<GoalsResponse>(`/goals?${cycle ? `cycle=${encodeURIComponent(cycle)}&` : ""}${team ? `team=${encodeURIComponent(team)}` : ""}`),
    refetchInterval: 90_000,
  });
  const data = q.data;
  const objectives = data?.items ?? [];

  async function nudgeProgress(o: Objective, kr: KeyResult, direction: "up" | "down") {
    const step = Math.max(1, Math.round((kr.target - kr.current) * 0.1));
    const next = direction === "up" ? kr.current + step : Math.max(0, kr.current - step);
    await apiPatch(`/goals/${o.id}/key-results/${kr.id}`, { current: next });
    await qc.invalidateQueries({ queryKey: ["goals", cycle, team] });
  }

  // Add objective composer state
  const [composeOpen, setComposeOpen] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newOwner, setNewOwner] = useState("");
  const [newTeam, setNewTeam] = useState("");
  const [newCycle, setNewCycle] = useState("Q3 2026");
  const [newKR, setNewKR] = useState("");
  const [newKRMetric, setNewKRMetric] = useState("metric");
  const [newKRTarget, setNewKRTarget] = useState(100);
  const [creating, setCreating] = useState(false);

  async function createObjective() {
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const key_results: any[] = [];
      if (newKR.trim()) {
        key_results.push({
          title: newKR,
          metric_label: newKRMetric || "metric",
          target: Number(newKRTarget) || 100,
          current: 0,
          direction: "up",
        });
      }
      await apiPost("/goals", {
        title: newTitle,
        owner: newOwner || "Org",
        team: newTeam || null,
        cycle: newCycle,
        key_results,
      });
      setNewTitle("");
      setNewOwner("");
      setNewTeam("");
      setNewKR("");
      setComposeOpen(false);
      await qc.invalidateQueries({ queryKey: ["goals", cycle, team] });
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Performance"
        title="Goals & OKRs"
        subtitle="The strategic layer between performance and execution. Objectives, key results, and progress that everyone can see."
        actions={
          <Action variant="primary" onClick={() => setComposeOpen((v) => !v)}>
            {composeOpen ? "Cancel" : "Add objective"}
          </Action>
        }
      />

      {/* "Objectives 5 · On track 4 · At risk 1 · Avg progress 75%" for an
          organisation with one employee in Operations and none of the teams
          these objectives belong to. Same rule as the recognition feed: an
          objective owned by somebody not in your employee records is a sample
          one. */}
      {q.data?.provenance?.all_sample && q.data.provenance.note && (
        <Surface pad="md">
          <div className="fp-eyebrow">Example objectives</div>
          <p className="mt-1 text-sm text-body">{q.data.provenance.note}</p>
        </Surface>
      )}

      {composeOpen && (
        <Surface pad="sm">
          <SectionTitle eyebrow="Compose" title="New objective" description="Optionally seed it with one key result; you can add more later." />
          <div className="mt-3 grid grid-cols-1 md:grid-cols-4 gap-2">
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Objective title"
              className="md:col-span-2 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newOwner}
              onChange={(e) => setNewOwner(e.target.value)}
              placeholder="Owner"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newTeam}
              onChange={(e) => setNewTeam(e.target.value)}
              placeholder="Team"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newCycle}
              onChange={(e) => setNewCycle(e.target.value)}
              placeholder="Cycle (e.g. Q3 2026)"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newKR}
              onChange={(e) => setNewKR(e.target.value)}
              placeholder="First key result (optional)"
              className="md:col-span-2 h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newKRMetric}
              onChange={(e) => setNewKRMetric(e.target.value)}
              placeholder="Metric label"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
            <input
              value={newKRTarget}
              onChange={(e) => setNewKRTarget(Number(e.target.value))}
              type="number"
              placeholder="Target"
              className="h-9 rounded-md border border-line bg-canvas px-3 text-sm text-ink outline-none focus:bg-surface"
            />
          </div>
          <div className="mt-2 flex items-center gap-2">
            <Action variant="primary" onClick={createObjective} disabled={!newTitle.trim() || creating}>
              {creating ? "Creating…" : "Create objective"}
            </Action>
          </div>
        </Surface>
      )}

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Objectives" value={data?.summary.total ?? "—"} />
        <Stat label="On track" value={data?.summary.on_track ?? "—"} tone="success" />
        <Stat label="At risk" value={data?.summary.at_risk ?? "—"} tone={(data?.summary.at_risk ?? 0) > 0 ? "warn" : "neutral"} />
        <Stat label="Off track" value={data?.summary.off_track ?? "—"} tone={(data?.summary.off_track ?? 0) > 0 ? "danger" : "neutral"} />
        <Stat label="Avg progress" value={`${data?.summary.avg_progress_pct ?? "—"}%`} />
      </div>

      <div className="flex flex-wrap gap-1.5">
        <button onClick={() => setCycle("")} className={`text-xs rounded-md px-3 py-1.5 border ${cycle === "" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>All cycles</button>
        {(data?.summary.cycles ?? []).map((c) => (
          <button key={c} onClick={() => setCycle(cycle === c ? "" : c)} className={`text-xs rounded-md px-3 py-1.5 border ${cycle === c ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>{c}</button>
        ))}
        <span className="flex-1" />
        <button onClick={() => setTeam("")} className={`text-xs rounded-md px-3 py-1.5 border ${team === "" ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>All teams</button>
        {(data?.summary.teams ?? []).map((t) => (
          <button key={t} onClick={() => setTeam(team === t ? "" : t)} className={`text-xs rounded-md px-3 py-1.5 border ${team === t ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>{t}</button>
        ))}
      </div>

      {q.isLoading ? (
        <Surface><EmptyState title="Loading…" /></Surface>
      ) : objectives.length === 0 ? (
        <Surface><EmptyState title="No objectives in this filter" /></Surface>
      ) : (
        <div className="space-y-4">
          {objectives.map((o) => (
            <Surface key={o.id}>
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="fp-eyebrow">{o.team ?? "Org"} · {o.cycle}</div>
                  <div className="text-lg font-semibold text-ink tracking-tight">{o.title}</div>
                  <div className="text-sm text-muted mt-0.5 flex items-center gap-2">
                    <Avatar name={o.owner} size={20} /> <span>{o.owner}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Pill tone={STATUS_TONE[o.status]}>{o.status.replace("_", " ")}</Pill>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-ink tabular-nums">{o.progress_pct}%</div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">overall</div>
                  </div>
                </div>
              </div>

              <div className="mt-3 h-1.5 rounded-full bg-sunken overflow-hidden">
                <div className="h-full bg-accent" style={{ width: `${o.progress_pct}%` }} />
              </div>

              <Divider className="my-4" />

              <div className="fp-eyebrow mb-2">Key results</div>
              <ul className="space-y-3">
                {o.key_results.map((kr) => (
                  <li key={kr.id} className="rounded-md border border-line bg-canvas p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-ink">{kr.title}</span>
                          <Pill tone={STATUS_TONE[kr.status]}>{kr.status.replace("_", " ")}</Pill>
                        </div>
                        <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5">
                          {kr.metric_label} · target {kr.target}{kr.direction === "down" ? " (lower is better)" : ""}
                        </div>
                      </div>
                      <div className="shrink-0 text-right">
                        <div className="text-lg font-semibold text-ink tabular-nums">{kr.progress_pct}%</div>
                        <div className="text-2xs uppercase tracking-eyebrow text-muted">{kr.current} / {kr.target}</div>
                      </div>
                    </div>
                    <div className="mt-2 h-1 rounded-full bg-sunken overflow-hidden">
                      <div className={`h-full ${kr.status === "off_track" ? "bg-danger-fg" : kr.status === "at_risk" ? "bg-warn-fg" : "bg-accent"}`} style={{ width: `${kr.progress_pct}%` }} />
                    </div>
                    <div className="mt-2 flex items-center gap-1.5 text-2xs uppercase tracking-eyebrow">
                      <button onClick={() => nudgeProgress(o, kr, "up")} className="text-muted hover:text-ink">+ Bump</button>
                      <button onClick={() => nudgeProgress(o, kr, "down")} className="text-muted hover:text-ink">- Walk back</button>
                      <span className="flex-1" />
                      {(kr.linked_task_count ?? 0) > 0 && (
                        <span className="text-muted">
                          {kr.linked_task_done ?? 0} / {kr.linked_task_count} tasks done
                        </span>
                      )}
                      <a
                        href={`/app/work?kr=${kr.id}`}
                        className="text-muted hover:text-ink"
                        title="View linked tasks in Work hub"
                      >
                        {(kr.linked_task_count ?? 0) > 0 ? "Open tasks →" : "Link tasks →"}
                      </a>
                    </div>
                  </li>
                ))}
              </ul>
            </Surface>
          ))}
        </div>
      )}

      <p className="text-xs text-muted">Goals connect to the workforce execution layer — link tasks to an objective from the Work hub to feed progress automatically (coming soon).</p>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "success" | "warn" | "danger" }) {
  const ring: Record<string, string> = {
    neutral: "",
    success: "ring-1 ring-success-line",
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
