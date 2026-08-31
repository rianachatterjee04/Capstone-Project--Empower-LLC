"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { PIPELINE_STAGES, toStage, type Stage as SharedStage } from "@/lib/pipelineStages";

import { PageHeader, Surface, SectionTitle, Pill, Action, LinkAction, EmptyState, Divider, Avatar } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Job = { id: string; title: string; location?: string | null; status: string; description: string; created_at: string };
type Candidate = { id: string; full_name: string; email: string; status: string; ai_score?: number | null; ai_summary?: string | null; resume_text?: string | null; job_posting_id: string; created_at: string };

type MatchPayload = {
  overall_score: number;
  band: string;
  recommendation: string;
  matched_skills: string[];
  missing_skills: string[];
  bias_flags: string[];
  explanation: string;
  subscores: { skills: number; experience: number; education: number };
  semantic_similarity: number;
  certifications: string[];
  estimated_years_experience: number;
  skill_evidence: { skill: string; snippet: string }[];
};
type Ranked = Candidate & { match: MatchPayload };

// Shared with the hiring funnel and matched by the API's own list, so the
// "-> screened" move on a card can no longer be a stage the server rejects.
const STAGES = PIPELINE_STAGES;
type Stage = SharedStage;

function scoreTone(s?: number | null): "success" | "warn" | "danger" | "neutral" {
  if (s == null) return "neutral";
  if (s >= 75) return "success";
  if (s >= 55) return "warn";
  return "danger";
}

function ScoreBadge({ score, band }: { score?: number | null; band?: string }) {
  if (score == null) return <span className="text-2xs uppercase tracking-eyebrow text-muted">unscored</span>;
  return <Pill tone={scoreTone(score)}>{score}{band ? <span className="ml-1 opacity-70">· {band}</span> : null}</Pill>;
}

function MatchDetail({ match }: { match: MatchPayload }) {
  return (
    <div className="space-y-3">
      <p className="text-sm text-body">{match.explanation}</p>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <Subscore label="Skills"     value={`${Math.round(match.subscores.skills * 100)}%`} />
        <Subscore label="Semantic"   value={`${Math.round(match.semantic_similarity * 100)}%`} />
        <Subscore label="Experience" value={`${match.estimated_years_experience.toFixed(1)} yrs`} />
      </div>
      {match.matched_skills.length > 0 && (
        <ChipRow label="Matched" tone="success" chips={match.matched_skills} />
      )}
      {match.missing_skills.length > 0 && (
        <ChipRow label="Missing" tone="danger" chips={match.missing_skills} />
      )}
      {match.skill_evidence.length > 0 && (
        <div>
          <div className="fp-eyebrow mb-1">Evidence</div>
          <ul className="space-y-1">
            {match.skill_evidence.slice(0, 4).map((e, i) => (
              <li key={i} className="rounded-md bg-canvas border border-line px-2.5 py-1.5 text-xs">
                <span className="font-medium text-ink">{e.skill}</span>
                <span className="text-muted"> — “{e.snippet}”</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {match.bias_flags.length > 0 && (
        <div className="rounded-md border border-warn-line bg-warn-bg text-warn-fg text-xs px-3 py-2">
          {match.bias_flags.join(" · ")}
        </div>
      )}
    </div>
  );
}

function Subscore({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-line bg-surface px-2.5 py-1.5">
      <div className="fp-eyebrow">{label}</div>
      <div className="text-sm font-semibold text-ink tabular-nums">{value}</div>
    </div>
  );
}

function ChipRow({ label, tone, chips }: { label: string; tone: "success" | "danger"; chips: string[] }) {
  return (
    <div>
      <div className="fp-eyebrow mb-1">{label}</div>
      <div className="flex flex-wrap gap-1">
        {chips.map((c) => <Pill key={c} tone={tone}>{c}</Pill>)}
      </div>
    </div>
  );
}

export default function TalentPage() {
  const qc = useQueryClient();
  const [selectedJob, setSelectedJob] = useState<string>("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [ranked, setRanked] = useState<Ranked[] | null>(null);
  const [running, setRunning] = useState(false);

  const jobsQ = useQuery({ queryKey: ["jobs"], queryFn: () => apiFetch<Job[]>("/recruiting/jobs") });
  const candsQ = useQuery({ queryKey: ["candidates"], queryFn: () => apiFetch<Candidate[]>("/recruiting/candidates") });

  const jobs = jobsQ.data ?? [];
  const cands = candsQ.data ?? [];
  const jobCands = useMemo(() => cands.filter((c) => !selectedJob || c.job_posting_id === selectedJob), [cands, selectedJob]);

  const { byStage, unrecognised } = useMemo(() => {
    const m = new Map<Stage, Candidate[]>();
    const unrecognised: Candidate[] = [];
    for (const s of STAGES) m.set(s, []);
    for (const c of jobCands) {
      // An unrecognised status used to be dropped into "new", so three
      // candidates stored as "interviewing" were drawn as fresh applicants.
      const k = toStage(c.status);
      if (k === null) {
        unrecognised.push(c);
        continue;
      }
      m.set(k, [...(m.get(k) ?? []), c]);
    }
    return { byStage: m, unrecognised };
  }, [jobCands]);

  async function runAIRanking() {
    if (!selectedJob) return;
    setRunning(true);
    try {
      const res = await apiPost<{ items: Ranked[] }>(`/resume-ai/screen-job/${selectedJob}`, {});
      setRanked(res.items);
      await qc.invalidateQueries({ queryKey: ["candidates"] });
    } finally {
      setRunning(false);
    }
  }

  async function moveStage(cand: Candidate, stage: Stage) {
    await apiPost(`/recruiting/candidates/${cand.id}/stage?stage=${stage}`, {});
    await qc.invalidateQueries({ queryKey: ["candidates"] });
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Hiring"
        title="Talent pipeline"
        subtitle="One pipeline, six stages, explainable AI ranking. Move candidates, run the screener, launch an AI interview."
        actions={
          <>
            <select
              className="h-9 rounded-md border border-line bg-surface px-3 text-sm text-ink"
              value={selectedJob}
              onChange={(e) => { setSelectedJob(e.target.value); setRanked(null); }}
            >
              <option value="">All jobs</option>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>{j.title} · {j.status}</option>
              ))}
            </select>
            <Action onClick={runAIRanking} disabled={!selectedJob || running} variant="primary">
              <IconSparkle />
              {running ? "Ranking…" : "Run AI ranking"}
            </Action>
            <LinkAction href={`/app/interview-ai${selectedJob ? `?jobId=${selectedJob}` : ""}`} variant="subtle">
              Open AI interviewer
            </LinkAction>
          </>
        }
      />

      {ranked && ranked.length > 0 && (
        <Surface>
          <SectionTitle
            eyebrow="Run results"
            title="AI ranked candidates"
            description="Semantic + skills + experience + education. Open a card for the explainable match."
            trailing={
              <button onClick={() => setRanked(null)} className="text-xs underline text-muted hover:text-ink">
                Clear results
              </button>
            }
          />
          <div className="mt-4 flex gap-3 overflow-x-auto pb-2">
            {ranked.map((r, idx) => {
              const active = expanded === r.id;
              return (
                <button
                  key={r.id}
                  onClick={() => setExpanded(active ? null : r.id)}
                  className={`flex-shrink-0 w-72 text-left rounded-lg border bg-surface p-3 transition-colors duration-150 ease-calm ${
                    active ? "border-ink ring-1 ring-ink/10" : "border-line hover:border-muted"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <Avatar name={r.full_name} size={26} />
                      <div className="min-w-0">
                        <div className="text-2xs uppercase tracking-eyebrow text-muted">#{idx + 1}</div>
                        <div className="text-sm font-semibold text-ink truncate">{r.full_name}</div>
                      </div>
                    </div>
                    <ScoreBadge score={r.match.overall_score} band={r.match.band} />
                  </div>
                  <div className="mt-1 text-2xs uppercase tracking-eyebrow text-muted">{r.match.recommendation}</div>
                  <div className="mt-2 text-xs text-body line-clamp-3">{r.match.explanation}</div>
                </button>
              );
            })}
          </div>
          {expanded && (() => {
            const r = ranked.find((x) => x.id === expanded);
            if (!r) return null;
            return (
              <div className="mt-4 rounded-lg border border-line bg-canvas p-4">
                <div className="flex items-center justify-between gap-2 mb-3">
                  <div className="flex items-center gap-2">
                    <Avatar name={r.full_name} size={28} />
                    <div>
                      <div className="text-sm font-semibold text-ink">{r.full_name}</div>
                      <div className="text-xs text-muted">{r.email}</div>
                    </div>
                  </div>
                  <LinkAction
                    href={`/app/interview-ai?candidateId=${r.id}${selectedJob ? `&jobId=${selectedJob}` : ""}`}
                    variant="primary"
                    size="sm"
                  >
                    <IconSparkle /> AI interview
                  </LinkAction>
                </div>
                <MatchDetail match={r.match} />
              </div>
            );
          })()}
        </Surface>
      )}

      <div>
        <SectionTitle eyebrow="Pipeline" title="Stages" description="Hover a card for stage moves and interview launch." />

        {/* A status neither this board nor the API recognises used to be drawn
            in "new". Shown, not absorbed: a candidate in an unknown state is
            somebody nobody is working. */}
        {unrecognised.length > 0 && (
          <div className="mt-3 rounded-lg border border-warn-line bg-warn-bg p-3 text-sm">
            <span className="font-medium">
              {unrecognised.length} candidate{unrecognised.length === 1 ? "" : "s"} in an
              unrecognised stage
            </span>
            <span className="text-muted">
              {" — "}
              {unrecognised.map((c) => `${c.full_name} (${c.status || "no status"})`).join(", ")}
              . These are not in any column below.
            </span>
          </div>
        )}
        <div className="mt-4 grid grid-cols-1 md:grid-cols-3 xl:grid-cols-6 gap-3">
          {STAGES.map((stage) => {
            const items = byStage.get(stage) ?? [];
            return (
              <div key={stage} className="rounded-lg border border-line bg-canvas p-3 min-h-[280px] flex flex-col">
                <div className="flex items-center justify-between mb-3">
                  <div className="fp-eyebrow capitalize">{stage}</div>
                  <span className="text-2xs uppercase tracking-eyebrow text-muted tabular-nums">{items.length}</span>
                </div>
                <div className="space-y-2 flex-1">
                  {items.length === 0 ? (
                    <div className="text-xs text-faint py-2">—</div>
                  ) : (
                    items.map((c) => (
                      <div key={c.id} className="rounded-md border border-line bg-surface p-2.5">
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <Avatar name={c.full_name} size={22} />
                            <div className="min-w-0">
                              <div className="text-sm text-ink font-medium truncate">{c.full_name}</div>
                              <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">{c.email}</div>
                            </div>
                          </div>
                          <ScoreBadge score={c.ai_score} />
                        </div>
                        {c.ai_summary && (
                          <div className="mt-1.5 text-xs text-muted line-clamp-2">{c.ai_summary}</div>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-2xs uppercase tracking-eyebrow">
                          {STAGES.filter((s) => s !== stage).map((s) => (
                            <button
                              key={s}
                              onClick={() => moveStage(c, s)}
                              className="text-muted hover:text-ink underline-offset-2 hover:underline"
                              title={`Move to ${s}`}
                            >
                              → {s}
                            </button>
                          ))}
                          <Link
                            href={`/app/interview-ai?candidateId=${c.id}${selectedJob ? `&jobId=${selectedJob}` : ""}`}
                            className="text-ink hover:underline ml-auto"
                          >
                            interview ↗
                          </Link>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <p className="text-xs text-muted">
        AI ranking and interviewing are assistive. Final hire/reject decisions require human review per your org's policy.
      </p>
    </div>
  );
}
