"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

type Course = { id: string; title: string; provider: string; level: string; duration_minutes: number; skills: string[]; is_compliance: boolean };
type Path = {
  from_role: string; to_role: string;
  skill_gap: { known: string[]; needed: string[]; gap: string[]; coverage_percent: number };
  recommended_courses: Course[]; estimated_hours: number; next_steps: string[];
};

export default function LearningPage() {
  const [skills, setSkills] = useState("python, sql");
  const [target, setTarget] = useState("senior software engineer");
  const [path, setPath] = useState<Path | null>(null);
  const [busy, setBusy] = useState(false);

  const compQ = useQuery({ queryKey: ["compliance"], queryFn: () => apiFetch<{ items: Course[] }>("/learning/compliance-required") });

  async function build() {
    setBusy(true);
    try {
      const out = await apiPost<Path>("/learning/path", {
        target_role: target,
        current_skills: skills.split(",").map(s => s.trim()).filter(Boolean),
      });
      setPath(out);
    } finally { setBusy(false); }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">My Growth</div>
        <div className="text-sm text-black/60">Personalised learning paths. Required compliance training.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="text-sm font-semibold">Plan my path</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Input label="Where I want to grow to" value={target} onChange={(e) => setTarget(e.target.value)} />
          <Input label="My skills" value={skills} onChange={(e) => setSkills(e.target.value)} hint="Comma-separated" />
        </div>
        <Button onClick={build} disabled={busy}>{busy ? "Building…" : "Build my plan"}</Button>
      </div>

      {path && (
        <div className="rounded-2xl border-2 border-black/10 p-5 bg-gradient-to-br from-sky-50 to-violet-50">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs uppercase tracking-wide text-black/40">Path to {path.to_role}</div>
              <div className="text-sm text-black/60">{path.estimated_hours} hours of learning</div>
            </div>
            <div className="text-right">
              <div className="text-3xl font-extrabold">{path.skill_gap.coverage_percent}%</div>
              <div className="text-xs text-black/50 uppercase">coverage</div>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="rounded-xl bg-white border border-black/10 p-2">
              <div className="text-xs text-emerald-700 uppercase">Have</div>
              <div className="text-xs">{path.skill_gap.known.join(", ") || "—"}</div>
            </div>
            <div className="rounded-xl bg-white border border-black/10 p-2">
              <div className="text-xs text-rose-700 uppercase">Gap</div>
              <div className="text-xs">{path.skill_gap.gap.join(", ") || "—"}</div>
            </div>
            <div className="rounded-xl bg-white border border-black/10 p-2">
              <div className="text-xs text-indigo-700 uppercase">Next</div>
              <ul className="text-xs space-y-0.5">{path.next_steps.map((s, i) => <li key={i}>• {s}</li>)}</ul>
            </div>
          </div>
          {path.recommended_courses.length > 0 && (
            <div className="mt-3">
              <div className="text-xs uppercase text-black/40 mb-1">Recommended courses</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {path.recommended_courses.map((c) => (
                  <div key={c.id} className="rounded-lg bg-white border border-black/10 p-2 text-xs">
                    <div className="font-semibold">{c.title}</div>
                    <div className="text-black/50">{c.provider} · {c.level} · {Math.round(c.duration_minutes / 60)}h</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      {c.skills.map((s) => <span key={s} className="rounded-full bg-black/[0.04] px-2 py-0.5">{s}</span>)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
        <div className="text-sm font-semibold text-amber-900 mb-2">Required compliance training</div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {(compQ.data?.items ?? []).map((c) => (
            <div key={c.id} className="rounded-lg bg-white border border-amber-200 p-2">
              <div className="text-sm font-semibold">{c.title}</div>
              <div className="text-xs text-black/60">{c.provider} · {Math.round(c.duration_minutes / 60)}h</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
