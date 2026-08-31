"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

type Role = { id: string; title: string; department: string; skills_required: string[]; seniority: string; posted_by: string };
type Match = {
  employee_id: string; employee_name: string;
  role: Role; score: number; coverage_percent: number;
  matched_skills: string[]; missing_skills: string[]; learning_hint: string;
};

export default function MarketplacePage() {
  const [name, setName] = useState("You");
  const [skills, setSkills] = useState("python, sql, react");
  const [perf, setPerf] = useState(4.0);
  const [matches, setMatches] = useState<Match[]>([]);
  const [busy, setBusy] = useState(false);

  const rolesQ = useQuery({ queryKey: ["mp-roles"], queryFn: () => apiFetch<{ items: Role[] }>("/marketplace/roles") });

  async function match() {
    setBusy(true);
    try {
      const r = await apiPost<{ items: Match[] }>("/marketplace/match-employee", {
        employee_id: "me",
        employee_name: name,
        skills: skills.split(",").map((s) => s.trim()).filter(Boolean),
        performance_rating: perf,
        tenure_years: 2,
      });
      setMatches(r.items);
    } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Internal Mobility</div>
        <div className="text-sm text-black/60">See which internal roles fit you. Apply or start a learning path to close the gap.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Input label="Display name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input label="My skills" value={skills} onChange={(e) => setSkills(e.target.value)} hint="Comma-separated" />
          <Input label="Perf rating (1-5)" type="number" step="0.1" value={perf} onChange={(e) => setPerf(Number(e.target.value))} />
        </div>
        <Button onClick={match} disabled={busy}>{busy ? "Matching…" : "Find roles"}</Button>
      </div>

      {matches.length > 0 ? (
        <div className="space-y-2">
          {matches.map((m, i) => (
            <div key={i} className="rounded-2xl border border-black/10 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-sm font-semibold">{m.role.title}</div>
                  <div className="text-xs text-black/50">{m.role.department} · {m.role.seniority}</div>
                </div>
                <div className="text-right">
                  <div className="text-2xl font-bold">{m.score}</div>
                  <div className="text-[10px] uppercase text-black/40">match</div>
                </div>
              </div>
              <div className="mt-2 text-xs">
                <span className="text-emerald-700">+ {m.matched_skills.join(", ") || "—"}</span>
                <span className="mx-2 text-black/30">·</span>
                <span className="text-rose-700">↑ {m.missing_skills.join(", ") || "ready now"}</span>
              </div>
              <div className="mt-1 text-xs text-black/60">{m.learning_hint}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-black/10 p-4">
          <div className="text-sm font-semibold mb-2">Open internal roles</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {(rolesQ.data?.items ?? []).map((r) => (
              <div key={r.id} className="rounded-xl border border-black/10 p-3">
                <div className="text-sm font-semibold">{r.title}</div>
                <div className="text-xs text-black/50">{r.department} · {r.seniority}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {r.skills_required.map((s) => <span key={s} className="rounded-full bg-black/[0.04] px-2 py-0.5 text-[10px]">{s}</span>)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
