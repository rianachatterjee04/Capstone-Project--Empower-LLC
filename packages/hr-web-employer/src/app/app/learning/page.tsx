"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

type Course = {
  id: string;
  title: string;
  provider: string;
  level: string;
  duration_minutes: number;
  skills: string[];
  is_compliance: boolean;
};

type Path = {
  from_role: string;
  to_role: string;
  skill_gap: {
    target_role: string;
    known: string[];
    needed: string[];
    gap: string[];
    coverage_percent: number;
  };
  recommended_courses: Course[];
  estimated_hours: number;
  next_steps: string[];
};

type NearestRole = { role: string; coverage_percent: number; matched_skills: string[]; missing_skills: string[] };

function CourseCard({ c }: { c: Course }) {
  return (
    <div className="rounded-xl border border-black/10 p-3 bg-white hover:border-black/30">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-sm font-semibold">{c.title}</div>
          <div className="text-xs text-black/50">{c.provider} · {c.level}</div>
        </div>
        {c.is_compliance && (
          <span className="rounded-full bg-amber-50 border border-amber-200 px-2 py-0.5 text-[10px] text-amber-800 font-semibold uppercase">
            Required
          </span>
        )}
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {(c.skills ?? []).map((s) => <span key={s} className="rounded-full bg-black/[0.03] px-2 py-0.5 text-[10px]">{s}</span>)}
      </div>
      <div className="mt-2 text-xs text-black/60">{Math.round(c.duration_minutes / 60)} hours</div>
    </div>
  );
}

export default function LearningPage() {
  const [currentSkills, setCurrentSkills] = useState("python, sql, react");
  const [currentRole, setCurrentRole] = useState("software engineer");
  const [targetRole, setTargetRole] = useState("senior software engineer");
  const [path, setPath] = useState<Path | null>(null);
  const [near, setNear] = useState<NearestRole[] | null>(null);
  const [loading, setLoading] = useState(false);

  const compQ = useQuery({
    queryKey: ["learning-compliance"],
    queryFn: () => apiFetch<{ items: Course[] }>("/learning/compliance-required"),
  });

  async function generatePath() {
    setLoading(true);
    try {
      const skills = currentSkills.split(",").map((s) => s.trim()).filter(Boolean);
      const p = await apiPost<Path>("/learning/path", {
        current_role: currentRole,
        target_role: targetRole,
        current_skills: skills,
      });
      setPath(p);
      const n = await apiPost<{ items: NearestRole[] }>("/learning/nearest-roles", { current_skills: skills });
      setNear(n.items);
    } finally {
      setLoading(false);
    }
  }

  const required = compQ.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Learning</div>
        <div className="text-sm text-black/60">
          Skills-based learning paths, role-aware course recommendations, and internal mobility suggestions.
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-5 space-y-3">
        <div className="text-sm font-semibold">Build a learning path</div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Input label="Current role" value={currentRole} onChange={(e) => setCurrentRole(e.target.value)} />
          <Input label="Target role" value={targetRole} onChange={(e) => setTargetRole(e.target.value)} />
          <Input label="Current skills (comma separated)" value={currentSkills} onChange={(e) => setCurrentSkills(e.target.value)} />
        </div>
        <Button onClick={generatePath} disabled={loading}>{loading ? "Generating…" : "Generate path"}</Button>
      </div>

      {path && (
        <div className="rounded-2xl border-2 border-black/10 p-5 space-y-4 bg-gradient-to-br from-sky-50 to-violet-50">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs uppercase tracking-wide text-black/40">Learning path</div>
              <div className="text-xl font-semibold">{path.from_role} → {path.to_role}</div>
              <div className="text-sm text-black/60">Estimated effort: {path.estimated_hours} hours</div>
            </div>
            <div className="text-right">
              <div className="text-3xl font-extrabold">{path.skill_gap?.coverage_percent ?? 0}%</div>
              <div className="text-xs uppercase tracking-wide text-black/50">current coverage</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="rounded-xl bg-white border border-black/10 p-3">
              <div className="text-xs uppercase tracking-wide text-emerald-700 mb-1">You already know</div>
              <div className="flex flex-wrap gap-1">
                {(path.skill_gap?.known ?? []).length === 0 && <span className="text-xs text-black/40">none yet</span>}
                {(path.skill_gap?.known ?? []).map((s) => <span key={s} className="rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-xs text-emerald-800">{s}</span>)}
              </div>
            </div>
            <div className="rounded-xl bg-white border border-black/10 p-3">
              <div className="text-xs uppercase tracking-wide text-rose-700 mb-1">Gap to close</div>
              <div className="flex flex-wrap gap-1">
                {(path.skill_gap?.gap ?? []).length === 0 && <span className="text-xs text-black/40">no gap 🎉</span>}
                {(path.skill_gap?.gap ?? []).map((s) => <span key={s} className="rounded-full bg-rose-50 border border-rose-200 px-2 py-0.5 text-xs text-rose-800">{s}</span>)}
              </div>
            </div>
            <div className="rounded-xl bg-white border border-black/10 p-3">
              <div className="text-xs uppercase tracking-wide text-indigo-700 mb-1">Next steps</div>
              <ul className="text-xs space-y-0.5">{(path.next_steps ?? []).map((n, i) => <li key={i}>• {n}</li>)}</ul>
            </div>
          </div>

          <div>
            <div className="text-sm font-semibold mb-2">Recommended courses</div>
            {(path.recommended_courses ?? []).length === 0 ? (
              <div className="text-sm text-black/40">You already meet the target skill profile.</div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {(path.recommended_courses ?? []).map((c) => <CourseCard key={c.id} c={c} />)}
              </div>
            )}
          </div>
        </div>
      )}

      {near && near.length > 0 && (
        <div className="rounded-2xl border border-black/10 p-5">
          <div className="text-sm font-semibold mb-3">Internal mobility — nearest roles</div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {near.map((r) => (
              <div key={r.role} className="rounded-xl border border-black/10 p-3">
                <div className="flex items-center justify-between">
                  <div className="text-sm font-semibold capitalize">{r.role}</div>
                  <div className="text-xs font-mono">{r.coverage_percent}%</div>
                </div>
                <div className="mt-1 text-xs text-emerald-700">+ {(r.matched_skills ?? []).join(", ") || "—"}</div>
                <div className="mt-0.5 text-xs text-rose-700">↑ {(r.missing_skills ?? []).join(", ") || "ready"}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
        <div className="text-sm font-semibold text-amber-900 mb-2">Required compliance training</div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
          {required.map((c) => <CourseCard key={c.id} c={c} />)}
        </div>
      </div>
    </div>
  );
}
