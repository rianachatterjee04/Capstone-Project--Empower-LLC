"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import { Button } from "@/components/Button";

type Prediction = {
  employee_id: string;
  name: string;
  department: string | null;
  risk_score: number;
  band: string;
  drivers: string[];
  suggested_actions: string[];
  is_heuristic: boolean;
  note: string;
};

const BAND_COLOR: Record<string, string> = {
  high: "bg-rose-50 border-rose-200 text-rose-900",
  medium: "bg-amber-50 border-amber-200 text-amber-900",
  low: "bg-emerald-50 border-emerald-200 text-emerald-900",
};

export default function InsightsPage() {
  const [open, setOpen] = useState<string | null>(null);
  const q = useQuery({
    queryKey: ["attrition-demo"],
    queryFn: () => apiFetch<{ items: Prediction[] }>("/attrition/demo"),
  });

  const items = q.data?.items ?? [];
  const high = items.filter((p) => p.band === "high").length;
  const medium = items.filter((p) => p.band === "medium").length;
  const low = items.filter((p) => p.band === "low").length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-2xl font-semibold">Predictive Insights</div>
          <div className="text-sm text-black/60">
            Flight-risk and retention signals. Explainable drivers, not black-box scores.
          </div>
        </div>
        <Button variant="secondary" onClick={() => q.refetch()}>Refresh</Button>
      </div>

      {/* The endpoint is /attrition/demo. The screen said "Total employees
          scored 5" and gave Avery Chen a flight risk of 80, for a company with
          one employee. Naming a person and scoring their likelihood of leaving
          is the most sensitive output in this product; the existing "triage
          only" disclaimer says do not act on it alone, which is a different
          claim from these are not your people. */}
      {items.length > 0 && (
        <div className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm text-black/80">
          <div className="font-medium">A worked example, not your employees</div>
          <div className="mt-1">
            These {items.length} people are the illustrative cohort shipped with the product.
            Scoring your own workforce needs tenure, performance ratings, engagement, compa-ratio
            and time since the last raise or promotion recorded against your employees.
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-xs text-black/40 uppercase">Total employees scored</div>
          <div className="text-2xl font-bold">{items.length}</div>
        </div>
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
          <div className="text-xs text-rose-800 uppercase">High risk</div>
          <div className="text-2xl font-bold text-rose-900">{high}</div>
        </div>
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
          <div className="text-xs text-amber-800 uppercase">Medium risk</div>
          <div className="text-2xl font-bold text-amber-900">{medium}</div>
        </div>
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
          <div className="text-xs text-emerald-800 uppercase">Low risk</div>
          <div className="text-2xl font-bold text-emerald-900">{low}</div>
        </div>
      </div>

      <div className="space-y-3">
        {items.map((p) => {
          const isOpen = open === p.employee_id;
          return (
            <div key={p.employee_id} className={`rounded-2xl border p-4 ${BAND_COLOR[p.band] ?? "border-black/10"}`}>
              <button
                className="w-full flex items-center justify-between gap-3 text-left"
                onClick={() => setOpen(isOpen ? null : p.employee_id)}
              >
                <div>
                  <div className="text-sm font-semibold">{p.name}</div>
                  <div className="text-xs">{p.department ?? "—"}</div>
                </div>
                <div className="text-right">
                  <div className="text-3xl font-extrabold">{p.risk_score}</div>
                  <div className="text-xs uppercase tracking-wide">{p.band} risk</div>
                </div>
              </button>
              {isOpen && (
                <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="rounded-xl bg-white/70 border border-black/10 p-3">
                    <div className="text-xs uppercase tracking-wide text-black/40 mb-1">Why this score</div>
                    <ul className="text-sm space-y-1">{p.drivers.map((d, i) => <li key={i}>• {d}</li>)}</ul>
                  </div>
                  <div className="rounded-xl bg-white/70 border border-black/10 p-3">
                    <div className="text-xs uppercase tracking-wide text-black/40 mb-1">Suggested actions</div>
                    <ul className="text-sm space-y-1">{p.suggested_actions.map((d, i) => <li key={i}>→ {d}</li>)}</ul>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="text-xs text-black/50 italic">
        Heuristic model intended for triage only. Do not use as the sole basis for any retention or comp decision.
      </div>
    </div>
  );
}
