"use client";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";
import { Pill, Action, PageHeader, Surface, SectionTitle } from "@/components/ds";
import { IconSparkle, IconCheck } from "@/components/icons";
import { VideoInterviewer, AnswerSubmission, InterviewMode } from "@/components/VideoInterviewer";

type Job = { id: string; title: string; description: string };
type Candidate = { id: string; full_name: string; email: string; resume_text?: string | null; job_posting_id: string };

type Question = { id: string; competency: string; question: string; rationale?: string };
type AnswerScore = {
  question_id: string;
  competency: string;
  question: string;
  answer: string;
  score: number;
  signals: Record<string, number>;
  strengths: string[];
  gaps: string[];
  follow_up: string;
  mode?: string;
  duration_sec?: number;
  subscores?: Record<string, number>;
  presentation_signals?: Record<string, number>;
};
type Summary = {
  overall_score: number;
  band: string;
  recommendation: string;
  strengths: string[];
  risks: string[];
  narrative: string;
  competency_scores: Record<string, number>;
  answers: AnswerScore[];
  fairness_note: string;
  dimension_scores?: Record<string, number>;
  modes_used?: string[];
  total_duration_sec?: number;
};
type SessionAnswer = {
  question_id: string;
  answer: string;
  mode?: string;
  duration_sec?: number;
  words_per_minute?: number;
  has_face?: boolean;
  media_meta?: Record<string, unknown>;
};
type Session = {
  id: string;
  candidate_id?: string;
  candidate_name?: string;
  job_id?: string;
  job_title: string;
  questions: Question[];
  answers: SessionAnswer[];
  summary?: Summary | null;
  created_at: string;
  completed_at?: string | null;
  status: string;
};

const DIMENSION_LABEL: Record<string, string> = {
  technical: "Technical depth",
  communication: "Communication",
  expression: "Expression",
  structure: "Structure (STAR)",
  ownership: "Ownership",
};

const DIMENSION_ORDER = ["technical", "communication", "expression", "structure", "ownership"];

function ScoreBadge({ score, band }: { score: number; band?: string }) {
  const tone: "success" | "warn" | "danger" =
    score >= 75 ? "success" : score >= 55 ? "warn" : "danger";
  return (
    <Pill tone={tone}>
      {score}
      {band ? <span className="opacity-70">· {band}</span> : null}
    </Pill>
  );
}

function ModePill({ mode }: { mode?: string }) {
  if (!mode) return null;
  const label = mode === "video" ? "Video" : mode === "audio" ? "Audio" : "Written";
  const tone: "info" | "accent" | "neutral" =
    mode === "video" ? "info" : mode === "audio" ? "accent" : "neutral";
  return <Pill tone={tone}>{label}</Pill>;
}

function DimensionBar({ label, value }: { label: string; value: number }) {
  const safe = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-2xs uppercase tracking-eyebrow text-muted">
        <span>{label}</span>
        <span className="font-mono tabular-nums text-ink">{safe}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-sunken overflow-hidden">
        <div className="h-full bg-ink/80" style={{ width: `${safe}%` }} />
      </div>
    </div>
  );
}

function PresentationGrid({ signals }: { signals: Record<string, number> }) {
  const pace = Math.round(signals.pace_wpm ?? 0);
  const filler = Math.round((signals.filler_density ?? 0) * 100);
  const confidence = Math.round(signals.confidence_words ?? 0);
  const hedge = Math.round(signals.hedge_words ?? 0);
  const sentiment = (signals.sentiment ?? 0).toFixed(2);
  const wordCount = Math.round(signals.word_count ?? 0);
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
      <Stat label="Pace" value={`${pace} wpm`} />
      <Stat label="Filler" value={`${filler}%`} />
      <Stat label="Confidence words" value={confidence} />
      <Stat label="Hedge words" value={hedge} />
      <Stat label="Sentiment" value={sentiment} />
      <Stat label="Word count" value={wordCount} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-canvas px-2 py-1.5">
      <div className="text-2xs uppercase tracking-eyebrow text-muted">{label}</div>
      <div className="text-sm font-medium text-ink tabular-nums">{value}</div>
    </div>
  );
}

export default function InterviewAIPage() {
  const [jobId, setJobId] = useState<string>("");
  const [candidateId, setCandidateId] = useState<string>("");
  const [jobTitle, setJobTitle] = useState("");
  const [jobDescription, setJobDescription] = useState("");
  const [resumeText, setResumeText] = useState("");
  const [nQuestions, setNQuestions] = useState(7);
  const [sessionMode, setSessionMode] = useState<InterviewMode>("video");

  const [session, setSession] = useState<Session | null>(null);
  // Track which questions have already been answered + which is currently being captured.
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(null);
  // Free-form notes for any questions left in written mode (acts as backup transcript).
  const [writtenAnswers, setWrittenAnswers] = useState<Record<string, string>>({});
  const [perAnswerScores, setPerAnswerScores] = useState<Record<string, AnswerScore>>({});
  const [submittedMeta, setSubmittedMeta] = useState<Record<string, { mode: string; duration_sec: number; words_per_minute: number }>>({});
  const [generating, setGenerating] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const jobsQ = useQuery({ queryKey: ["jobs"], queryFn: () => apiFetch<Job[]>("/recruiting/jobs") });
  const candsQ = useQuery({ queryKey: ["candidates"], queryFn: () => apiFetch<Candidate[]>("/recruiting/candidates") });
  const sessionsQ = useQuery({ queryKey: ["ai-interview-sessions"], queryFn: () => apiFetch<{ items: Session[] }>("/ai-interview/sessions") });

  // Pick up jobId / candidateId from query string
  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const j = params.get("jobId");
    const c = params.get("candidateId");
    const m = (params.get("mode") || "").toLowerCase();
    if (j) setJobId(j);
    if (c) setCandidateId(c);
    if (m === "video" || m === "audio" || m === "written") setSessionMode(m);
  }, []);

  // Auto-fill from job + candidate selection
  useEffect(() => {
    const j = jobsQ.data?.find((x) => x.id === jobId);
    if (j) {
      setJobTitle(j.title);
      setJobDescription(j.description);
    }
  }, [jobId, jobsQ.data]);

  useEffect(() => {
    const c = candsQ.data?.find((x) => x.id === candidateId);
    if (c) setResumeText(c.resume_text ?? "");
  }, [candidateId, candsQ.data]);

  const selectedCandidate = useMemo(
    () => candsQ.data?.find((c) => c.id === candidateId),
    [candidateId, candsQ.data]
  );

  async function startSession() {
    setError(null);
    if (!jobTitle) {
      setError("Job title is required.");
      return;
    }
    setGenerating(true);
    try {
      const sess = await apiPost<Session>("/ai-interview/sessions", {
        job_id: jobId || null,
        candidate_id: candidateId || null,
        candidate_name: selectedCandidate?.full_name ?? null,
        job_title: jobTitle,
        job_description: jobDescription,
        resume_text: resumeText,
        n_questions: nQuestions,
        provider: "auto",
      });
      setSession(sess);
      setWrittenAnswers({});
      setPerAnswerScores({});
      setSubmittedMeta({});
      setActiveQuestionId(sess.questions[0]?.id ?? null);
    } catch (e: any) {
      setError(e?.message ?? "Failed to start session");
    } finally {
      setGenerating(false);
    }
  }

  async function submitFromInterviewer(qid: string, a: AnswerSubmission) {
    if (!session) return;
    try {
      const res = await apiPost<{ scored: AnswerScore }>(`/ai-interview/sessions/${session.id}/answer`, {
        question_id: qid,
        answer: a.transcript,
        mode: a.mode,
        duration_sec: a.duration_sec,
        words_per_minute: a.words_per_minute,
        has_face: a.has_face,
        media_meta: a.media_meta,
      });
      setPerAnswerScores((prev) => ({ ...prev, [qid]: res.scored }));
      setSubmittedMeta((prev) => ({
        ...prev,
        [qid]: { mode: a.mode, duration_sec: a.duration_sec, words_per_minute: a.words_per_minute },
      }));
      setWrittenAnswers((prev) => ({ ...prev, [qid]: a.transcript }));
      // auto-advance to the next unscored question
      const nextQ = session.questions.find((q) => q.id !== qid && !perAnswerScores[q.id]);
      setActiveQuestionId(nextQ ? nextQ.id : null);
    } catch (e: any) {
      setError(e?.message ?? "Failed to submit answer");
    }
  }

  async function submitWritten(qid: string) {
    if (!session) return;
    const text = (writtenAnswers[qid] ?? "").trim();
    if (!text) return;
    const words = text.split(/\s+/).filter(Boolean).length;
    // Treat written as instant — no duration captured.
    await submitFromInterviewer(qid, {
      transcript: text,
      mode: "written",
      duration_sec: 0,
      words_per_minute: 0,
      has_face: false,
      media_meta: { kind: "written" },
    });
    // The shared helper will advance; nothing extra to do.
    void words;
  }

  async function completeSession() {
    if (!session) return;
    setCompleting(true);
    try {
      const updated = await apiPost<Session>(`/ai-interview/sessions/${session.id}/complete`, {});
      setSession(updated);
    } catch (e: any) {
      setError(e?.message ?? "Failed to complete session");
    } finally {
      setCompleting(false);
    }
  }

  const sessions = sessionsQ.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring · AI"
        title="AI Interviewer"
        subtitle="Structured, competency-based questions. AI asks aloud, records video / audio, transcribes in-browser, then scores on technical, communication, expression, structure & ownership. Always human-reviewed."
      />

      {/* Setup */}
      {!session && (
        <Surface>
          <SectionTitle eyebrow="Setup" title="Set up the interview" />
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="block">
                <div className="mb-1 text-sm font-medium text-ink">Job (optional)</div>
                <select
                  className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
                  value={jobId}
                  onChange={(e) => setJobId(e.target.value)}
                >
                  <option value="">— Free-form —</option>
                  {(jobsQ.data ?? []).map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-sm font-medium text-ink">Candidate (optional)</div>
                <select
                  className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
                  value={candidateId}
                  onChange={(e) => setCandidateId(e.target.value)}
                >
                  <option value="">— Anonymous candidate —</option>
                  {(candsQ.data ?? [])
                    .filter((c) => !jobId || c.job_posting_id === jobId)
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.full_name}
                      </option>
                    ))}
                </select>
              </label>
              <Input label="Job title" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
              <Input
                label="Number of questions"
                type="number"
                min={3}
                max={12}
                value={nQuestions}
                onChange={(e) => setNQuestions(Math.max(3, Math.min(12, Number(e.target.value) || 7)))}
              />
            </div>

            <div>
              <div className="mb-1 text-sm font-medium text-ink">Interview mode</div>
              <div className="flex flex-wrap items-center gap-2">
                {(["video", "audio", "written"] as InterviewMode[]).map((m) => (
                  <Action
                    key={m}
                    variant={sessionMode === m ? "primary" : "subtle"}
                    size="sm"
                    onClick={() => setSessionMode(m)}
                  >
                    {m === "video" ? "Video + AI" : m === "audio" ? "Audio + AI" : "Written"}
                  </Action>
                ))}
                <span className="text-2xs uppercase tracking-eyebrow text-muted ml-2">
                  Candidates can switch per question · Chrome / Edge recommended for live transcript
                </span>
              </div>
            </div>

            <Textarea label="Job description" rows={5} value={jobDescription} onChange={(e) => setJobDescription(e.target.value)} />
            <Textarea label="Resume text (optional)" rows={5} value={resumeText} onChange={(e) => setResumeText(e.target.value)} />
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={startSession} disabled={generating}>
                {generating ? "Generating questions…" : "Start AI interview"}
              </Button>
              {error && <span className="text-sm text-danger-fg">{error}</span>}
            </div>
            <div className="text-2xs uppercase tracking-eyebrow text-muted">
              Provider tries the LLM first if OPENAI_API_KEY is configured; otherwise uses the local question bank. All recordings stay client-side — only the transcript + duration is sent for scoring.
            </div>
          </div>
        </Surface>
      )}

      {/* Active session */}
      {session && !session.summary && (
        <div className="space-y-4">
          <Surface pad="sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="fp-eyebrow">Interview in progress</div>
                <div className="text-md font-semibold text-ink">
                  {session.job_title}
                  {session.candidate_name ? ` · ${session.candidate_name}` : ""}
                </div>
                <div className="text-xs text-muted mt-0.5">
                  {Object.keys(perAnswerScores).length} of {session.questions.length} answered · default mode <span className="font-medium text-ink">{sessionMode}</span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Action
                  variant="subtle"
                  onClick={() => {
                    setSession(null);
                    setWrittenAnswers({});
                    setPerAnswerScores({});
                    setActiveQuestionId(null);
                    setSubmittedMeta({});
                  }}
                >
                  Abandon
                </Action>
                <Action variant="primary" onClick={completeSession} disabled={completing}>
                  {completing ? "Scoring…" : "Complete & summarize"}
                </Action>
              </div>
            </div>
          </Surface>

          <div className="space-y-4">
            {session.questions.map((q, idx) => {
              const scored = perAnswerScores[q.id];
              const isActive = activeQuestionId === q.id;
              const meta = submittedMeta[q.id];
              return (
                <Surface key={q.id} pad="md">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="fp-eyebrow">
                        Q{idx + 1} · {q.competency.replace(/_/g, " ")}
                      </div>
                      <div className="text-sm font-semibold text-ink mt-0.5">{q.question}</div>
                      {q.rationale && <div className="text-xs text-muted mt-1">{q.rationale}</div>}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      {scored && <ScoreBadge score={scored.score} />}
                      {scored && <ModePill mode={scored.mode || meta?.mode} />}
                      {meta?.duration_sec ? (
                        <Pill tone="neutral">{meta.duration_sec}s</Pill>
                      ) : null}
                    </div>
                  </div>

                  {/* Answer capture area */}
                  <div className="mt-3">
                    {scored && !isActive ? (
                      <div className="rounded-md border border-line bg-canvas p-3 space-y-3">
                        <div className="flex items-center justify-between">
                          <div className="text-2xs uppercase tracking-eyebrow text-muted">Captured transcript</div>
                          <Action variant="subtle" size="sm" onClick={() => setActiveQuestionId(q.id)}>
                            Re-record
                          </Action>
                        </div>
                        <div className="text-sm text-ink whitespace-pre-wrap leading-relaxed">
                          {scored.answer || <span className="text-muted">No transcript captured.</span>}
                        </div>
                      </div>
                    ) : (
                      <PerQuestionCapture
                        key={`${q.id}-${isActive ? "active" : "idle"}`}
                        question={q}
                        defaultMode={sessionMode}
                        writtenValue={writtenAnswers[q.id] ?? ""}
                        onWrittenChange={(v) => setWrittenAnswers((prev) => ({ ...prev, [q.id]: v }))}
                        onSubmit={(a) => submitFromInterviewer(q.id, a)}
                        onSubmitWritten={() => submitWritten(q.id)}
                      />
                    )}
                  </div>

                  {scored && (
                    <div className="mt-4 space-y-4 border-t border-line pt-4">
                      {scored.subscores && Object.keys(scored.subscores).length > 0 && (
                        <div>
                          <div className="fp-eyebrow mb-2">Dimension scores</div>
                          <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                            {DIMENSION_ORDER.filter((k) => scored.subscores?.[k] !== undefined).map((k) => (
                              <DimensionBar key={k} label={DIMENSION_LABEL[k]} value={scored.subscores![k]} />
                            ))}
                          </div>
                        </div>
                      )}

                      {scored.presentation_signals && Object.keys(scored.presentation_signals).length > 0 && (
                        <div>
                          <div className="fp-eyebrow mb-2">Presentation signals</div>
                          <PresentationGrid signals={scored.presentation_signals} />
                        </div>
                      )}

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <div className="fp-eyebrow text-success-fg mb-1">Strengths</div>
                          {scored.strengths.length === 0 ? (
                            <div className="text-xs text-muted">—</div>
                          ) : (
                            <ul className="text-xs space-y-1 text-body">
                              {scored.strengths.map((s, i) => (
                                <li key={i}>• {s}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                        <div>
                          <div className="fp-eyebrow text-danger-fg mb-1">Gaps / follow-ups</div>
                          {scored.gaps.length === 0 ? (
                            <div className="text-xs text-muted">—</div>
                          ) : (
                            <ul className="text-xs space-y-1 text-body">
                              {scored.gaps.map((s, i) => (
                                <li key={i}>• {s}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </div>

                      {scored.follow_up && (
                        <div className="rounded-md border border-line bg-canvas px-3 py-2 text-xs text-body">
                          <span className="fp-eyebrow mr-2">Suggested follow-up</span>
                          {scored.follow_up}
                        </div>
                      )}

                      <div className="flex flex-wrap items-center gap-3 text-2xs uppercase tracking-eyebrow text-muted">
                        {Object.entries(scored.signals).map(([k, v]) => (
                          <span key={k}>
                            <span className="text-muted">{k}:</span>{" "}
                            <span className="text-ink font-mono tabular-nums">{Math.round(v * 100)}%</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </Surface>
              );
            })}
          </div>
        </div>
      )}

      {/* Completed session — summary */}
      {session?.summary && (
        <div className="space-y-4">
          <Surface pad="lg">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="fp-eyebrow">Interview summary</div>
                <div className="text-xl font-semibold text-ink mt-1">
                  {session.job_title}
                  {session.candidate_name ? ` · ${session.candidate_name}` : ""}
                </div>
                <div className="mt-1 text-sm font-medium text-ink uppercase tracking-wide">
                  {session.summary.recommendation.replace(/_/g, " ")}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {(session.summary.modes_used ?? []).map((m) => (
                    <ModePill key={m} mode={m} />
                  ))}
                  {session.summary.total_duration_sec ? (
                    <Pill tone="neutral">{Math.round(session.summary.total_duration_sec)}s total</Pill>
                  ) : null}
                </div>
              </div>
              <div className="text-right">
                <div className="text-4xl font-bold text-ink tabular-nums">{session.summary.overall_score}</div>
                <div className="fp-eyebrow">overall · {session.summary.band}</div>
              </div>
            </div>

            <div className="mt-4 text-sm text-body leading-relaxed">{session.summary.narrative}</div>

            {session.summary.dimension_scores && Object.keys(session.summary.dimension_scores).length > 0 && (
              <div className="mt-5">
                <div className="fp-eyebrow mb-2">Dimension roll-up</div>
                <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                  {DIMENSION_ORDER.filter((k) => session.summary?.dimension_scores?.[k] !== undefined).map((k) => (
                    <DimensionBar key={k} label={DIMENSION_LABEL[k]} value={session.summary!.dimension_scores![k]} />
                  ))}
                </div>
              </div>
            )}

            <div className="mt-5">
              <div className="fp-eyebrow mb-2">Competency scores</div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {Object.entries(session.summary.competency_scores).map(([comp, score]) => (
                  <div key={comp} className="rounded-md border border-line bg-canvas p-3">
                    <div className="text-2xs uppercase tracking-eyebrow text-muted capitalize">{comp.replace(/_/g, " ")}</div>
                    <div className="text-lg font-semibold text-ink mt-0.5 tabular-nums">{score}</div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="fp-eyebrow text-success-fg mb-1">Strengths</div>
                <ul className="text-sm text-body space-y-1">
                  {session.summary.strengths.map((s, i) => (
                    <li key={i}>• {s}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="fp-eyebrow text-danger-fg mb-1">Risks</div>
                <ul className="text-sm text-body space-y-1">
                  {session.summary.risks.map((s, i) => (
                    <li key={i}>• {s}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="mt-5 rounded-md border border-warn-line bg-warn-bg text-warn-fg text-xs px-3 py-2">
              ⚖ {session.summary.fairness_note}
            </div>
          </Surface>

          <Action
            variant="subtle"
            onClick={() => {
              setSession(null);
              setWrittenAnswers({});
              setPerAnswerScores({});
              setActiveQuestionId(null);
              setSubmittedMeta({});
            }}
          >
            Start another interview
          </Action>
        </div>
      )}

      {/* Past sessions */}
      <Surface pad="sm">
        <SectionTitle eyebrow="History" title="Past interview sessions" />
        {sessions.length === 0 ? (
          <div className="text-sm text-muted py-6 text-center">No sessions yet</div>
        ) : (
          <div className="divide-y divide-line mt-2">
            {sessions.map((s) => (
              <div key={s.id} className="py-2 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-ink">
                    {s.job_title}
                    {s.candidate_name ? ` · ${s.candidate_name}` : ""}
                  </div>
                  <div className="text-xs text-muted">
                    {new Date(s.created_at).toLocaleString()} · {s.status}
                    {s.summary?.modes_used?.length ? ` · ${s.summary.modes_used.join(", ")}` : ""}
                  </div>
                </div>
                {s.summary ? (
                  <ScoreBadge score={s.summary.overall_score} band={s.summary.band} />
                ) : (
                  <Pill tone="warn">in progress</Pill>
                )}
              </div>
            ))}
          </div>
        )}
      </Surface>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-question capture — lets the candidate switch mode for this question,
// then either runs the live VideoInterviewer or falls back to a written pad.
// ---------------------------------------------------------------------------
function PerQuestionCapture({
  question,
  defaultMode,
  writtenValue,
  onWrittenChange,
  onSubmit,
  onSubmitWritten,
}: {
  question: Question;
  defaultMode: InterviewMode;
  writtenValue: string;
  onWrittenChange: (v: string) => void;
  onSubmit: (a: AnswerSubmission) => void;
  onSubmitWritten: () => void;
}) {
  const [mode, setMode] = useState<InterviewMode>(defaultMode);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="text-2xs uppercase tracking-eyebrow text-muted mr-1">Capture mode</div>
        {(["video", "audio", "written"] as InterviewMode[]).map((m) => (
          <Action
            key={m}
            variant={mode === m ? "primary" : "subtle"}
            size="sm"
            onClick={() => setMode(m)}
          >
            {m === "video" ? "Video" : m === "audio" ? "Audio" : "Written"}
          </Action>
        ))}
      </div>

      {mode === "written" ? (
        <div className="space-y-2">
          <div className="rounded-md border border-line bg-canvas p-3">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                <div className="fp-eyebrow">Question</div>
                <div className="text-sm font-semibold text-ink">{question.question}</div>
              </div>
              <Action
                variant="subtle"
                size="sm"
                onClick={() => {
                  if (typeof window === "undefined" || !window.speechSynthesis) return;
                  window.speechSynthesis.cancel();
                  window.speechSynthesis.speak(new SpeechSynthesisUtterance(question.question));
                }}
              >
                <IconSparkle /> AI reads aloud
              </Action>
            </div>
            <textarea
              value={writtenValue}
              rows={4}
              onChange={(e) => onWrittenChange(e.target.value)}
              placeholder="Type the candidate's response (or notes you took during the live call)…"
              className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:bg-surface"
            />
          </div>
          <div className="flex items-center justify-end">
            <Action variant="primary" onClick={onSubmitWritten} disabled={!writtenValue.trim()}>
              <IconCheck /> Score this answer
            </Action>
          </div>
        </div>
      ) : (
        <VideoInterviewer
          mode={mode}
          question={question.question}
          rationale={question.rationale}
          onSubmit={onSubmit}
        />
      )}
    </div>
  );
}
