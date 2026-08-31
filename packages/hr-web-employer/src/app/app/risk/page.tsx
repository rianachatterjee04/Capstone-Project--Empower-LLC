"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/Button";

type Alert = {
  id: string; kind: string; severity: "high"|"medium"|"low";
  subject: string; drivers: string[]; recommended_action: string;
  /** "employee_record" or "sample_workforce". */
  source?: string;
  confidence: string; generated_at: string;
};
type Summary = {
  counts: Record<string, number>; score: number; headline: string; alerts: Alert[];
  coverage?: {
    your_employees_scanned: number;
    your_active_employees: number;
    sample_people_scanned: number;
    alerts_from_sample: number;
    alerts_from_your_data?: number;
    needs: string[];
    note: string;
  };
};

const SEV_COLOR: Record<string, string> = {
  high: "border-rose-300 bg-rose-50 text-rose-900",
  medium: "border-amber-300 bg-amber-50 text-amber-900",
  low: "border-slate-200 bg-slate-50 text-slate-800",
};

const KIND_LABEL: Record<string, string> = {
  attrition: "Attrition",
  burnout: "Burnout",
  compliance: "Compliance",
  comp_equity: "Pay equity",
  manager: "Manager risk",
  hiring: "Hiring health",
};

export default function RiskPage() {
  const [filter, setFilter] = useState<string>("all");
  const q = useQuery({ queryKey: ["risk-scan"], queryFn: () => apiFetch<Summary>("/workforce-risk/scan") });
  const s = q.data;
  const filtered = (s?.alerts ?? []).filter((a) => filter === "all" || a.kind === filter);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-2xl font-semibold">Workforce Risk Engine</div>
          <div className="text-sm text-black/60">Continuously scans attrition, burnout, comp equity, compliance, manager, and hiring signals.</div>
        </div>
        <Button variant="secondary" onClick={() => q.refetch()}>Re-scan</Button>
      </div>

      <div className="rounded-2xl border-2 border-black/10 p-5 bg-gradient-to-br from-rose-50 to-amber-50">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs uppercase tracking-wide text-black/40">Workforce Risk Score</div>
            <div className="text-3xl font-extrabold">{s?.score ?? "—"}/100</div>
            <div className="text-sm text-black/70 mt-1">{s?.headline ?? "Loading…"}</div>
            {/* Every layer of this engine reads a sample workforce. The page
                said "High-severity workforce risk detected — review today" and
                named people who do not work here. */}
            {s?.coverage && s.coverage.your_employees_scanned === 0 && (
              <div className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-black/80">
                <div className="font-medium">Which layers ran on your data</div>
                <div className="mt-1">{s.coverage.note}</div>
                <div className="mt-2 text-xs text-black/60">
                  To scan your own people this engine needs:{" "}
                  {s.coverage.needs.join("; ")}.
                </div>
              </div>
            )}
          </div>
          <div className="grid grid-cols-3 gap-2 text-center">
            {Object.entries(s?.counts ?? {}).map(([k, n]) => (
              <div key={k} className="rounded-xl bg-white border border-black/10 px-3 py-2 min-w-[6rem]">
                <div className="text-[10px] uppercase text-black/40">{KIND_LABEL[k] ?? k}</div>
                <div className="text-lg font-semibold">{n}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <button onClick={() => setFilter("all")} className={`text-xs rounded-full px-3 py-1 ${filter === "all" ? "bg-black text-white" : "border border-black/15"}`}>All</button>
        {Object.keys(s?.counts ?? {}).map((k) => (
          <button key={k} onClick={() => setFilter(k)} className={`text-xs rounded-full px-3 py-1 ${filter === k ? "bg-black text-white" : "border border-black/15"}`}>
            {KIND_LABEL[k] ?? k}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {filtered.length === 0 ? (
          <div className="rounded-2xl border border-black/10 p-6 text-center text-sm text-black/40">
            No alerts in this category.
          </div>
        ) : (
          filtered.map((a) => (
            <div key={a.id} className={`rounded-2xl border-2 p-4 ${SEV_COLOR[a.severity]}`}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-wide opacity-80">{KIND_LABEL[a.kind] ?? a.kind} · {a.severity}</div>
                  <div className="text-base font-semibold mt-0.5">
                    {a.subject}
                    {a.source === "sample_workforce" && (
                      <span className="ml-2 align-middle rounded bg-black/5 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-black/50">
                        sample person
                      </span>
                    )}
                  </div>
                </div>
                <span className="text-[10px] uppercase font-bold opacity-70">{a.confidence} conf</span>
              </div>
              <div className="mt-2">
                <div className="text-xs uppercase opacity-70">Drivers</div>
                <ul className="text-sm mt-0.5 space-y-0.5">
                  {a.drivers.map((d, i) => <li key={i}>• {d}</li>)}
                </ul>
              </div>
              <div className="mt-2 text-sm font-medium">
                → {a.recommended_action}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="text-xs text-black/40">
        This is a heuristic risk model. Every action should be validated by the manager and HR before any retention or comp decision.
      </div>
    </div>
  );
}
