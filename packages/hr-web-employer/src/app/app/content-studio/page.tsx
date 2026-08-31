"use client";
import { useState } from "react";
import { apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

type JDOut = {
  title: string; level: string; department: string; location: string;
  summary: string;
  responsibilities: string[]; required_skills: string[]; nice_to_have: string[];
  compensation_note: string; inclusion_statement: string; notes?: string;
};

type Scorecard = {
  role: string;
  rubric: { competency: string; levels: { score: number; name: string; description: string }[]; evidence_prompts: string[] }[];
  fairness_note: string;
};

type FeedbackOut = {
  original: string;
  detected: { flags: { term?: string; kind: string; suggestion: string }[]; word_count: number };
  rewrite: string;
  disclaimer: string;
};

type OnboardingOut = {
  employee: string; role: string; manager: string; start_date: string;
  pre_day_1: string[]; first_week: string[]; first_30_days: string[];
  first_60_days: string[]; first_90_days: string[]; skill_focus: string[];
  checklist_owner_roles: string[];
};

const TABS = ["JD", "Scorecard", "Feedback", "Onboarding"] as const;
type Tab = (typeof TABS)[number];

export default function ContentStudioPage() {
  const [tab, setTab] = useState<Tab>("JD");

  // JD state
  const [jdTitle, setJdTitle] = useState("Senior Software Engineer");
  const [jdLevel, setJdLevel] = useState("senior");
  const [jdDept, setJdDept] = useState("Engineering");
  const [jdLocation, setJdLocation] = useState("Remote");
  const [jdOut, setJdOut] = useState<JDOut | null>(null);

  // Scorecard state
  const [scRole, setScRole] = useState("Senior Software Engineer");
  const [scOut, setScOut] = useState<Scorecard | null>(null);

  // Feedback state
  const [fbName, setFbName] = useState("the employee");
  const [fbText, setFbText] = useState("She is a great team player but a bit too aggressive in meetings. Brings energy and is nice to have on the team.");
  const [fbOut, setFbOut] = useState<FeedbackOut | null>(null);

  // Onboarding state
  const [obName, setObName] = useState("Avery Chen");
  const [obRole, setObRole] = useState("Senior Software Engineer");
  const [obManager, setObManager] = useState("Sam Rivera");
  const [obStart, setObStart] = useState("2026-06-01");
  const [obOut, setObOut] = useState<OnboardingOut | null>(null);

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Content Studio</div>
        <div className="text-sm text-black/60">
          AI drafting for JDs, interview scorecards, balanced feedback, and onboarding plans. Every draft is human-reviewed before sending.
        </div>
      </div>

      <div className="flex gap-1">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-xl px-3 py-1.5 text-sm ${tab === t ? "bg-black text-white" : "border border-black/15 hover:bg-black/5"}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "JD" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-black/10 p-4 space-y-3">
            <div className="text-sm font-semibold">Generate job description</div>
            <Input label="Job title" value={jdTitle} onChange={(e) => setJdTitle(e.target.value)} />
            <Input label="Level" value={jdLevel} onChange={(e) => setJdLevel(e.target.value)} />
            <Input label="Department" value={jdDept} onChange={(e) => setJdDept(e.target.value)} />
            <Input label="Location" value={jdLocation} onChange={(e) => setJdLocation(e.target.value)} />
            <Button onClick={async () => setJdOut(await apiPost<JDOut>("/content/job-description", { title: jdTitle, level: jdLevel, department: jdDept, location: jdLocation }))}>Generate JD</Button>
          </div>
          {jdOut && (
            <div className="rounded-2xl border border-black/10 p-4 space-y-3">
              <div className="text-xs uppercase text-black/40">Draft JD</div>
              <div className="text-lg font-semibold">{jdOut.title} · {jdOut.level} · {jdOut.department} · {jdOut.location}</div>
              <div className="text-sm">{jdOut.summary}</div>
              <div>
                <div className="text-xs uppercase text-black/40 mb-1">Responsibilities</div>
                <ul className="text-sm space-y-0.5">{jdOut.responsibilities.map((r, i) => <li key={i}>• {r}</li>)}</ul>
              </div>
              <div>
                <div className="text-xs uppercase text-black/40 mb-1">Required skills</div>
                <div className="flex flex-wrap gap-1">{jdOut.required_skills.map((s) => <span key={s} className="rounded-full bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-xs text-emerald-800">{s}</span>)}</div>
              </div>
              <div className="text-xs text-black/50 italic">{jdOut.inclusion_statement}</div>
            </div>
          )}
        </div>
      )}

      {tab === "Scorecard" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-black/10 p-4 space-y-3">
            <div className="text-sm font-semibold">Generate interview scorecard</div>
            <Input label="Role" value={scRole} onChange={(e) => setScRole(e.target.value)} />
            <Button onClick={async () => setScOut(await apiPost<Scorecard>("/content/interview-scorecard", { role: scRole }))}>Generate</Button>
          </div>
          {scOut && (
            <div className="rounded-2xl border border-black/10 p-4 space-y-3 max-h-[60vh] overflow-y-auto">
              <div className="text-xs uppercase text-black/40">Scorecard · {scOut.role}</div>
              {scOut.rubric.map((c) => (
                <div key={c.competency} className="rounded-xl border border-black/10 p-3">
                  <div className="text-sm font-semibold uppercase tracking-wide">{c.competency.replace(/_/g, " ")}</div>
                  <div className="mt-1 grid grid-cols-5 gap-1 text-xs">
                    {c.levels.map((l) => (
                      <div key={l.score} className="rounded bg-black/[0.04] p-1">
                        <div className="font-semibold">{l.score} · {l.name}</div>
                        <div className="text-black/60">{l.description}</div>
                      </div>
                    ))}
                  </div>
                  <div className="mt-2 text-xs">
                    <div className="text-black/40 uppercase tracking-wider">Probes</div>
                    <ul className="space-y-0.5">{c.evidence_prompts.map((p, i) => <li key={i}>• {p}</li>)}</ul>
                  </div>
                </div>
              ))}
              <div className="text-xs text-black/50 italic">{scOut.fairness_note}</div>
            </div>
          )}
        </div>
      )}

      {tab === "Feedback" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-black/10 p-4 space-y-3">
            <div className="text-sm font-semibold">Balance manager feedback</div>
            <Input label="Employee name" value={fbName} onChange={(e) => setFbName(e.target.value)} />
            <Textarea label="Draft feedback" rows={6} value={fbText} onChange={(e) => setFbText(e.target.value)} />
            <Button onClick={async () => setFbOut(await apiPost<FeedbackOut>("/content/feedback/rewrite", { text: fbText, employee_name: fbName }))}>Detect + rewrite</Button>
          </div>
          {fbOut && (
            <div className="rounded-2xl border border-black/10 p-4 space-y-3">
              <div className="text-xs uppercase text-black/40">AI flags ({fbOut.detected.flags.length})</div>
              {fbOut.detected.flags.length === 0 ? (
                <div className="text-sm text-emerald-700">No vague or biased language detected.</div>
              ) : (
                <div className="space-y-1">
                  {fbOut.detected.flags.map((f, i) => (
                    <div key={i} className="rounded-lg bg-amber-50 border border-amber-200 p-2 text-xs">
                      <span className="font-semibold uppercase">{f.kind}</span>
                      {f.term ? <> · "{f.term}"</> : null} — {f.suggestion}
                    </div>
                  ))}
                </div>
              )}
              <div className="text-xs uppercase text-black/40 pt-2">Rewritten draft</div>
              <div className="text-sm whitespace-pre-line">{fbOut.rewrite}</div>
              <div className="text-xs text-black/50 italic">{fbOut.disclaimer}</div>
            </div>
          )}
        </div>
      )}

      {tab === "Onboarding" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-2xl border border-black/10 p-4 space-y-3">
            <div className="text-sm font-semibold">Generate onboarding plan</div>
            <Input label="Employee name" value={obName} onChange={(e) => setObName(e.target.value)} />
            <Input label="Role" value={obRole} onChange={(e) => setObRole(e.target.value)} />
            <Input label="Manager name" value={obManager} onChange={(e) => setObManager(e.target.value)} />
            <Input label="Start date" value={obStart} onChange={(e) => setObStart(e.target.value)} />
            <Button onClick={async () => setObOut(await apiPost<OnboardingOut>("/content/onboarding-plan", { employee_name: obName, role: obRole, manager_name: obManager, start_date: obStart }))}>Generate plan</Button>
          </div>
          {obOut && (
            <div className="rounded-2xl border border-black/10 p-4 space-y-3 max-h-[60vh] overflow-y-auto">
              <div className="text-xs uppercase text-black/40">Day-1 plan · {obOut.employee} · {obOut.role}</div>
              {[
                ["Pre-Day 1", obOut.pre_day_1],
                ["First week", obOut.first_week],
                ["First 30 days", obOut.first_30_days],
                ["First 60 days", obOut.first_60_days],
                ["First 90 days", obOut.first_90_days],
              ].map(([label, items]) => (
                <div key={label as string}>
                  <div className="text-xs uppercase text-black/40 mb-1">{label as string}</div>
                  <ul className="text-sm space-y-0.5">{(items as string[]).map((t, i) => <li key={i}>• {t}</li>)}</ul>
                </div>
              ))}
              {obOut.skill_focus.length > 0 && (
                <div>
                  <div className="text-xs uppercase text-black/40 mb-1">Skill focus</div>
                  <div className="flex flex-wrap gap-1">{obOut.skill_focus.map((s) => <span key={s} className="rounded-full bg-black/[0.04] px-2 py-0.5 text-xs">{s}</span>)}</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
