"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";

type AgentMeta = { key: string; name: string };
type AgentAction = {
  id: string; kind: string; title: string; target?: string;
  payload: any; approval_required: boolean; rationale: string;
};
type AgentRun = {
  id: string; agent: string; org_id: string;
  started_at: string; finished_at: string;
  summary: string; actions: AgentAction[];
  confidence: string; metrics: Record<string, any>;
  next_run_in_minutes: number; disclaimer: string;
};

const KIND_ICON: Record<string, string> = {
  send_message: "✉",
  schedule: "📅",
  draft: "✏",
  update_field: "✎",
  escalate: "⚠",
  propose: "💡",
};

function ConfidenceBadge({ value }: { value: string }) {
  const color =
    value === "high" ? "bg-emerald-100 text-emerald-800"
    : value === "medium" ? "bg-amber-100 text-amber-800"
    : "bg-slate-100 text-slate-700";
  return <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${color}`}>{value}</span>;
}

export default function AgentsPage() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string>("recruiting");
  const [running, setRunning] = useState<string | null>(null);

  // Read ?agent= from query string
  useEffect(() => {
    if (typeof window === "undefined") return;
    const p = new URLSearchParams(window.location.search).get("agent");
    if (p) setSelected(p);
  }, []);

  const agentsQ = useQuery({ queryKey: ["agents-list"], queryFn: () => apiFetch<{ items: AgentMeta[] }>("/agents") });
  const runsQ = useQuery({
    queryKey: ["agent-runs", selected],
    queryFn: () => apiFetch<{ items: AgentRun[] }>(`/agents/runs?agent=${selected}`),
  });

  const agents = agentsQ.data?.items ?? [];
  const runs = runsQ.data?.items ?? [];

  async function runAgent(key: string) {
    setRunning(key);
    try {
      await apiPost(`/agents/${key}/run`, {});
      await qc.invalidateQueries({ queryKey: ["agent-runs", key] });
    } finally {
      setRunning(null);
    }
  }

  // Approving recorded an audit event and returned 200, and the button went on
  // saying "Approve" with nothing else changed — so approving AI screening for
  // four candidates left all four unscored and invited a second click. The API
  // now reports whether the approval was recorded and that it does not execute
  // the action; this shows both.
  const [approved, setApproved] = useState<Record<string, string>>({});

  async function approveAction(agent: string, actionId: string) {
    try {
      const res = await apiPost<{ recorded?: boolean; executed?: boolean; next_step?: string }>(
        `/agents/${agent}/approve-action/${actionId}`,
        {},
      );
      setApproved((m) => ({
        ...m,
        [actionId]: res?.next_step || "Approval recorded in the audit log.",
      }));
    } catch (e: any) {
      setApproved((m) => ({ ...m, [actionId]: e?.message || "Approval failed" }));
    }
    await qc.invalidateQueries({ queryKey: ["agent-runs", agent] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Agentic HR</div>
        <div className="text-sm text-black/60">
          Six AI operators continuously surface work. Nothing executes without your approval.
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-6 gap-2">
        {agents.map((a) => (
          <button
            key={a.key}
            onClick={() => setSelected(a.key)}
            className={`rounded-xl border p-3 text-left ${selected === a.key ? "border-black ring-2 ring-black/10 bg-black/[0.02]" : "border-black/10 hover:border-black/30"}`}
          >
            <div className="text-xs uppercase text-black/40">Agent</div>
            <div className="text-sm font-semibold mt-1">{a.name}</div>
          </button>
        ))}
      </div>

      <div className="flex items-center gap-2">
        <Button onClick={() => runAgent(selected)} disabled={running !== null}>
          {running === selected ? "Running…" : `Run ${agents.find((a) => a.key === selected)?.name ?? selected}`}
        </Button>
        <Button variant="secondary" onClick={() => runsQ.refetch()}>Refresh history</Button>
      </div>

      <div className="space-y-3">
        {runs.length === 0 ? (
          <div className="rounded-2xl border border-black/10 p-6 text-center text-sm text-black/40">
            No runs yet for this agent. Click "Run" to start.
          </div>
        ) : (
          runs.map((r) => (
            <div key={r.id} className="rounded-2xl border border-black/10 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold">{r.summary}</div>
                  <div className="text-xs text-black/50">
                    {new Date(r.started_at).toLocaleString()} · next run ~{r.next_run_in_minutes}m
                  </div>
                </div>
                <ConfidenceBadge value={r.confidence} />
              </div>

              {r.actions.length > 0 && (
                <div className="mt-3 space-y-2">
                  {r.actions.map((a) => (
                    <div key={a.id} className="flex items-start justify-between rounded-xl border border-black/10 p-3">
                      <div className="flex-1">
                        <div className="text-sm font-medium">{KIND_ICON[a.kind] ?? "•"} {a.title}</div>
                        {a.rationale && <div className="text-xs text-black/60 mt-0.5">{a.rationale}</div>}
                        {a.target && <div className="text-[10px] text-black/40 mt-0.5 font-mono">{a.target}</div>}
                      </div>
                      <div className="flex flex-col gap-1 items-end">
                        {a.approval_required ? (
                          approved[a.id] ? (
                            <span className="text-[10px] uppercase text-emerald-700">
                              approved · recorded
                            </span>
                          ) : (
                            <button
                              onClick={() => approveAction(r.agent, a.id)}
                              className="rounded-lg bg-black text-white text-xs px-3 py-1.5"
                            >
                              Approve
                            </button>
                          )
                        ) : (
                          <span className="text-[10px] uppercase text-emerald-700">auto</span>
                        )}
                        <span className="text-[10px] uppercase text-black/40">{a.kind}</span>
                      </div>
                      {approved[a.id] && (
                        <div className="mt-1 text-[11px] text-black/60">{approved[a.id]}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {Object.keys(r.metrics || {}).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  {Object.entries(r.metrics).map(([k, v]) => (
                    <span key={k} className="rounded-full bg-black/[0.04] px-2 py-0.5">
                      <span className="text-black/50">{k}:</span> {typeof v === "object" ? JSON.stringify(v).slice(0, 80) : String(v)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="text-xs text-black/40">
        Agent recommendations are advisory. Final actions require human approval per your org's policy.
      </div>
    </div>
  );
}
