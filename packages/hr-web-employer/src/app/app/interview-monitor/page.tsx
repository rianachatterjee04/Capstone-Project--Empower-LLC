"use client";
/**
 * Recruiter LIVE MONITOR + POST-INTERVIEW OUTCOME for the adaptive AI interviewer.
 *
 * Framed as an outcome, not a tool: "Interviewed → scored → ranked. Top
 * candidates ready with evidence."
 *
 *   LIVE MONITOR      — running transcript + real-time per-competency coverage.
 *   OUTCOME           — the explainable scorecard (per-competency + evidence,
 *                        reused from the merged score-review service), the
 *                        fraud / integrity flag, the fairness note, and a rank.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { env } from "@/lib/env";
import { PageHeader, Surface, Pill, SectionTitle } from "@/components/ds";
import { Button } from "@/components/Button";
import { IconSparkle } from "@/components/icons";

const human = (c: string) => (c || "").replace(/_/g, " ");

type SessionRow = {
  id: string;
  candidate_name?: string;
  job_title: string;
  status: string;
  created_at: string;
  coverage?: { n_covered: number; n_total: number; pct_covered: number } | null;
  outcome?: Outcome | null;
};
type CoverageItem = { competency: string; label: string; signal_strength: number; probes: number; best_score: number; covered: boolean };
type CoverageMap = { competencies: CoverageItem[]; n_covered: number; n_total: number; pct_covered: number };
type StateResp = {
  session_id: string;
  coverage_map: CoverageMap;
  asked_count: number;
  max_questions: number;
  remaining_competencies: string[];
  transcript: { question: string; answer: string; competency: string; quality?: string; score?: number }[];
  done: boolean;
  status: string;
};
type RubricDim = { dimension: string; score: number; weight: number; weighted_contribution: number; confidence: number; evidence: { interviewer: string; quote: string }[]; evidence_gap: boolean };
type Outcome = {
  headline: string;
  explainable_scorecard: {
    available: boolean;
    ai_disclosure?: string;
    rubric: RubricDim[];
    overall_score: number;
    overall_score_max?: number;
    overall_confidence: number;
    adaptive_overall_score?: number;
    adaptive_recommendation?: string;
    compliance?: { framework: string; obligation: string }[];
  };
  integrity: { fraud_score: number; band: string; recommended_action: string; confidence: number; top_drivers: { category: string; points: number }[] };
  fairness: { flags: any[]; summary: { total: number; highest_severity: string } };
  coverage: CoverageMap;
};

function QualityDot({ q }: { q?: string }) {
  const tone = q === "strong" ? "bg-success" : q === "shallow" ? "bg-warn" : q === "vague" || q === "off_topic" ? "bg-danger" : "bg-line";
  return <span className={`inline-block h-2 w-2 rounded-full ${tone}`} title={q} />;
}

function CoverageBars({ cov }: { cov: CoverageMap }) {
  return (
    <div className="space-y-2.5">
      {cov.competencies.map((c) => {
        const pct = Math.round(c.signal_strength * 100);
        return (
          <div key={c.competency}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 text-body">
                {c.covered && <span className="text-success">✓</span>}
                {human(c.label)}
              </span>
              <span className="tabular-nums text-muted">{pct}% · {c.probes} probe{c.probes === 1 ? "" : "s"}</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken">
              <div className={`h-full ${c.covered ? "bg-success" : "bg-accent"}`} style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ScoreExplanation({ outcome }: { outcome: Outcome }) {
  const sc = outcome.explainable_scorecard;
  const rec = sc.adaptive_recommendation;
  const recTone = rec === "hire" ? "success" : rec === "no_hire" ? "danger" : "warn";
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="text-3xl font-semibold tabular-nums text-ink">{sc.adaptive_overall_score ?? "—"}<span className="text-lg text-muted">/100</span></div>
        {rec && <Pill tone={recTone as any}>{human(rec)}</Pill>}
        <Pill tone="neutral">confidence {(sc.overall_confidence * 100).toFixed(0)}%</Pill>
        {sc.ai_disclosure && <span className="text-xs text-muted">{sc.ai_disclosure}</span>}
      </div>
      {!sc.available && <p className="text-sm text-muted">Scorecard will populate once the interview has scored answers.</p>}
      <div className="space-y-3">
        {sc.rubric.map((d) => (
          <div key={d.dimension} className="rounded-xl border border-line bg-surface p-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-ink">{human(d.dimension)}</span>
              <span className="text-xs text-muted tabular-nums">
                {d.score.toFixed(1)}/4 · weight {(d.weight * 100).toFixed(0)}% · conf {(d.confidence * 100).toFixed(0)}%
              </span>
            </div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-sunken">
              <div className="h-full bg-accent" style={{ width: `${(d.score / 4) * 100}%` }} />
            </div>
            {d.evidence.length > 0 ? (
              <ul className="mt-2 space-y-1">
                {d.evidence.slice(0, 2).map((e, i) => (
                  <li key={i} className="rounded-lg bg-sunken px-2.5 py-1.5 text-[13px] italic text-body">“{e.quote}”</li>
                ))}
              </ul>
            ) : (
              <div className="mt-2 text-xs text-warn">No transcript evidence attached for this dimension.</div>
            )}
          </div>
        ))}
      </div>
      <p className="text-xs text-muted">
        Overall is the explicit weighted sum of the dimensions above (weights sum to 1.0) — every number reconciles and cites its evidence.
      </p>
    </div>
  );
}

function OutcomePanel({ outcome }: { outcome: Outcome }) {
  const fr = outcome.integrity;
  const frTone = fr.band === "clear" ? "success" : fr.band === "review" ? "warn" : "danger";
  const fair = outcome.fairness.summary;
  const fairTone = fair.highest_severity === "none" ? "success" : fair.highest_severity === "info" ? "neutral" : "warn";
  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-accent/20 bg-accent-soft/40 p-4">
        <div className="flex items-center gap-2 text-accent-softFg"><IconSparkle size={16} /><span className="text-xs font-medium uppercase tracking-wide">Outcome</span></div>
        <p className="mt-1.5 text-[15px] font-medium text-ink">{outcome.headline}</p>
      </div>

      <div>
        <SectionTitle eyebrow="Explainable scorecard" title="Per-competency, with evidence" />
        <div className="mt-3"><ScoreExplanation outcome={outcome} /></div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Surface className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-ink">Integrity / fraud</span>
            <Pill tone={frTone as any}>{fr.band}</Pill>
          </div>
          <div className="mt-2 text-2xl font-semibold tabular-nums text-ink">{fr.fraud_score}<span className="text-sm text-muted">/100</span></div>
          <div className="text-xs text-muted">recommended: {fr.recommended_action} · confidence {(fr.confidence * 100).toFixed(0)}%</div>
          {fr.top_drivers.length > 0 && (
            <ul className="mt-2 text-xs text-body">{fr.top_drivers.map((d) => <li key={d.category}>• {human(d.category)} (+{d.points})</li>)}</ul>
          )}
        </Surface>
        <Surface className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-ink">Fairness</span>
            <Pill tone={fairTone as any}>{fair.highest_severity === "none" ? "clean" : fair.highest_severity}</Pill>
          </div>
          <div className="mt-2 text-sm text-body">{fair.total === 0 ? "No biased or protected-class phrasing detected in the AI's questions." : `${fair.total} flag(s) on the AI's questions — review before deciding.`}</div>
        </Surface>
      </div>
      <p className="text-xs text-muted">
        AI-assisted and human-reviewed. This outcome supports a hiring decision; it must not be the sole basis for one, and must not rely on protected attributes.
      </p>
    </div>
  );
}

function Monitor({ sessionId, onCompleted }: { sessionId: string; onCompleted: () => void }) {
  const [completing, setCompleting] = useState(false);
  const q = useQuery({
    queryKey: ["adaptive-state", sessionId],
    queryFn: () => apiFetch<StateResp>(`/ai-interview/sessions/${sessionId}/state`),
    refetchInterval: (query) => (query.state.data?.status === "completed" ? false : 3000),
  });
  const full = useQuery({
    queryKey: ["adaptive-full", sessionId],
    queryFn: () => apiFetch<SessionRow>(`/ai-interview/sessions/${sessionId}`),
    refetchInterval: (query) => (query.state.data?.status === "completed" ? false : 4000),
  });

  const st = q.data;
  const outcome = full.data?.outcome ?? null;
  // next.config sets basePath: '/people', so the shareable candidate link includes it.
  const candidateLink = `${typeof window !== "undefined" ? window.location.origin : ""}/people/interview/${sessionId}`;

  async function completeNow() {
    setCompleting(true);
    try {
      await apiPost(`/ai-interview/sessions/${sessionId}/complete`, {});
      await Promise.all([q.refetch(), full.refetch()]);
      onCompleted();
    } finally { setCompleting(false); }
  }

  if (!st) return <div className="py-10 text-sm text-muted">Loading monitor…</div>;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={st.status === "completed" ? "success" : "info"}>{st.status === "completed" ? "completed" : "live"}</Pill>
        <span className="text-xs text-muted">{st.asked_count} / {st.max_questions} questions · {st.coverage_map.n_covered}/{st.coverage_map.n_total} competencies covered</span>
        {st.status !== "completed" && (
          <button onClick={completeNow} disabled={completing} className="ml-auto rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg hover:opacity-90 disabled:opacity-50">
            {completing ? "Scoring…" : "Complete & score"}
          </button>
        )}
      </div>

      <div className="rounded-xl border border-line bg-sunken/50 p-3">
        <div className="mb-1 text-xs font-medium text-body">Candidate link</div>
        <code className="block truncate text-xs text-accent-softFg">{candidateLink}</code>
      </div>

      {outcome ? (
        <OutcomePanel outcome={outcome} />
      ) : (
        <div className="grid gap-5 lg:grid-cols-[1fr_320px]">
          <div>
            <SectionTitle eyebrow="Live transcript" title="What's being said" />
            <div className="mt-3 space-y-3">
              {st.transcript.length === 0 && <p className="text-sm text-muted">Waiting for the candidate to answer the first question…</p>}
              {st.transcript.map((t, i) => (
                <div key={i} className="rounded-xl border border-line bg-surface p-3">
                  <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-wide text-faint">
                    <QualityDot q={t.quality} /> {human(t.competency)} {typeof t.score === "number" && <span className="text-muted">· {t.score}/100</span>}
                  </div>
                  <div className="text-sm text-body"><span className="text-muted">Q:</span> {t.question}</div>
                  <div className="mt-1 text-sm text-ink"><span className="text-muted">A:</span> {t.answer}</div>
                </div>
              ))}
            </div>
          </div>
          <div>
            <SectionTitle eyebrow="Coverage" title="Real-time signal" />
            <div className="mt-3"><CoverageBars cov={st.coverage_map} /></div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function InterviewMonitorPage() {
  const [active, setActive] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ candidate_name: "", job_title: "", competencies: "" });

  const list = useQuery({
    queryKey: ["adaptive-sessions"],
    queryFn: () => apiFetch<{ items: SessionRow[] }>("/ai-interview/sessions"),
    refetchInterval: 5000,
  });

  async function createSession() {
    if (!form.job_title.trim()) return;
    setCreating(true);
    try {
      const competencies = form.competencies.split(",").map((s) => s.trim().replace(/\s+/g, "_").toLowerCase()).filter(Boolean);
      const sess = await apiPost<SessionRow>("/ai-interview/sessions", {
        job_title: form.job_title,
        candidate_name: form.candidate_name || undefined,
        competencies: competencies.length ? competencies : undefined,
        n_questions: 6,
      });
      setForm({ candidate_name: "", job_title: "", competencies: "" });
      await list.refetch();
      setActive(sess.id);
    } finally { setCreating(false); }
  }

  const items = list.data?.items ?? [];

  return (
    <div className="space-y-6 fp-fade-in">
      <PageHeader
        eyebrow="AI Interviewer"
        title="Interviewed → scored → ranked"
        subtitle="Launch an adaptive interview, watch it live, and get an explainable scorecard with evidence, a fraud check, and a fairness pass — top candidates ready with the receipts."
      />

      <Surface className="p-4">
        <SectionTitle eyebrow="New adaptive interview" title="Launch in seconds" />
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          <input value={form.candidate_name} onChange={(e) => setForm({ ...form, candidate_name: e.target.value })}
            placeholder="Candidate name (optional)" className="rounded-xl border border-line bg-canvas px-3 py-2 text-sm outline-none focus:border-accent/40" />
          <input value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })}
            placeholder="Job title (e.g. Backend Engineer)" className="rounded-xl border border-line bg-canvas px-3 py-2 text-sm outline-none focus:border-accent/40" />
          <input value={form.competencies} onChange={(e) => setForm({ ...form, competencies: e.target.value })}
            placeholder="Competencies, comma-sep (optional)" className="rounded-xl border border-line bg-canvas px-3 py-2 text-sm outline-none focus:border-accent/40" />
        </div>
        <div className="mt-3">
          <Button onClick={createSession} disabled={creating || !form.job_title.trim()}>
            {creating ? "Creating…" : "Create & get candidate link"}
          </Button>
        </div>
      </Surface>

      <div className="grid gap-5 lg:grid-cols-[300px_1fr]">
        <Surface className="p-3">
          <div className="px-1 pb-2 text-xs font-medium uppercase tracking-wide text-muted">Sessions</div>
          <div className="space-y-1">
            {items.length === 0 && <div className="px-2 py-6 text-center text-sm text-muted">No interviews yet.</div>}
            {items.map((s) => (
              <button key={s.id} onClick={() => setActive(s.id)}
                className={["w-full rounded-xl px-3 py-2.5 text-left transition", active === s.id ? "bg-accent-soft" : "hover:bg-sunken"].join(" ")}>
                <div className="flex items-center justify-between">
                  <span className="truncate text-sm font-medium text-ink">{s.candidate_name || "Candidate"}</span>
                  <Pill tone={s.status === "completed" ? "success" : "info"}>{s.status === "completed" ? "done" : "live"}</Pill>
                </div>
                <div className="truncate text-xs text-muted">{s.job_title}</div>
              </button>
            ))}
          </div>
        </Surface>

        <Surface className="p-5">
          {active ? <Monitor sessionId={active} onCompleted={() => list.refetch()} /> :
            <div className="flex h-full min-h-[300px] items-center justify-center text-center text-sm text-muted">
              Select a session to watch it live, or create one above.
            </div>}
        </Surface>
      </div>
    </div>
  );
}
