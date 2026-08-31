"use client";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";
import { Pill, Action, PageHeader, Surface, SectionTitle, EmptyState, Avatar } from "@/components/ds";
import { IconSparkle, IconCheck, IconClose, IconArrowUpRight } from "@/components/icons";
import { VideoInterviewer, AnswerSubmission, InterviewMode } from "@/components/VideoInterviewer";

// ---------------------------------------------------------------------------
// Types — mirror the backend payloads
// ---------------------------------------------------------------------------
type Job = { id: string; title: string };
type Candidate = { id: string; full_name: string; email: string };

type RefQuestion = { id: string; competency: string; question: string; rationale?: string };
type RefSubscore = Record<string, number>;
type RefPresentation = Record<string, number>;
type RefSignals = Record<string, number>;

type RefScoredAnswer = {
  question_id: string;
  competency: string;
  question: string;
  answer: string;
  score: number;
  signals: RefSignals;
  strengths: string[];
  concerns: string[];
  follow_up: string;
  mode?: string;
  duration_sec?: number;
  subscores?: RefSubscore;
  presentation_signals?: RefPresentation;
};

type RefProfile = {
  id: string;
  name: string;
  email?: string;
  title?: string;
  company?: string;
  relationship: string;
  tenure_months: number;
  invited_at?: string;
  completed_at?: string | null;
  consent_recorded: boolean;
};

type RefSlot = {
  profile: RefProfile;
  questions: RefQuestion[];
  responses: Array<{ question_id: string; answer: string; mode?: string; duration_sec?: number }>;
  submit_token: string;
  is_complete: boolean;
};

type ScoredReference = {
  reference_id: string;
  reference_name: string;
  relationship: string;
  overall: number;
  band: string;
  answers: RefScoredAnswer[];
  themes: string[];
  red_flags: string[];
  summary: string;
};

type RefCheckSummary = {
  overall_score: number;
  band: string;
  recommendation: string;
  strengths: string[];
  risks: string[];
  contradictions: string[];
  competency_scores: Record<string, number>;
  references: ScoredReference[];
  narrative: string;
  fairness_note: string;
  n_references: number;
  relationships_covered: string[];
};

type RefCheck = {
  id: string;
  candidate_id?: string;
  candidate_name: string;
  job_id?: string;
  job_title: string;
  extra_context: string;
  n_questions: number;
  references: RefSlot[];
  summary?: RefCheckSummary | null;
  created_at: string;
  completed_at?: string | null;
  status: string;
};

const RELATIONSHIPS = ["manager", "peer", "report", "client", "mentor", "other"] as const;
type Relationship = (typeof RELATIONSHIPS)[number];

const BAND_TONE: Record<string, "success" | "info" | "warn" | "danger" | "neutral"> = {
  strong_endorse: "success",
  endorse: "success",
  proceed_with_caution: "warn",
  lukewarm: "warn",
  do_not_endorse: "danger",
};

const REC_LABEL: Record<string, string> = {
  advance: "Advance",
  advance_with_caveats: "Advance with caveats",
  hold: "Hold",
  decline: "Decline",
};

const DIM_ORDER = ["endorsement", "specificity", "candor", "length", "concern"] as const;
const DIM_LABEL: Record<string, string> = {
  endorsement: "Endorsement",
  specificity: "Specificity",
  candor: "Candor",
  length: "Depth",
  concern: "Concern",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function ScoreBadge({ score, band }: { score: number; band?: string }) {
  const tone =
    score >= 75 ? "success" : score >= 55 ? "info" : score >= 35 ? "warn" : "danger";
  return (
    <Pill tone={tone}>
      {score}
      {band ? <span className="opacity-70 ml-1">· {band.replace(/_/g, " ")}</span> : null}
    </Pill>
  );
}

function DimBar({ label, value, danger }: { label: string; value: number; danger?: boolean }) {
  const v = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-2xs uppercase tracking-eyebrow text-muted">
        <span>{label}</span>
        <span className="font-mono tabular-nums text-ink">{v}</span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-sunken overflow-hidden">
        <div className={danger ? "h-full bg-danger-fg/80" : "h-full bg-ink/80"} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ReferenceCheckPage() {
  // Setup state
  const [candidateName, setCandidateName] = useState("");
  const [candidateId, setCandidateId] = useState("");
  const [jobId, setJobId] = useState("");
  const [jobTitle, setJobTitle] = useState("");
  const [extraContext, setExtraContext] = useState("");
  const [nQuestions, setNQuestions] = useState(6);

  // Active check
  const [check, setCheck] = useState<RefCheck | null>(null);
  const [activeRefId, setActiveRefId] = useState<string | null>(null);
  const [activeQuestionId, setActiveQuestionId] = useState<string | null>(null);
  const [perAnswerScores, setPerAnswerScores] = useState<Record<string, Record<string, RefScoredAnswer>>>({});
  // perAnswerScores[refId][questionId] = scored
  const [writtenDrafts, setWrittenDrafts] = useState<Record<string, Record<string, string>>>({});

  const [creating, setCreating] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Add-reference form
  const [addOpen, setAddOpen] = useState(false);
  const [refName, setRefName] = useState("");
  const [refEmail, setRefEmail] = useState("");
  const [refTitle, setRefTitle] = useState("");
  const [refCompany, setRefCompany] = useState("");
  const [refRelationship, setRefRelationship] = useState<Relationship>("manager");
  const [refTenure, setRefTenure] = useState(12);
  const [refConsent, setRefConsent] = useState(false);
  const [adding, setAdding] = useState(false);

  // Default per-question mode (recruiter-on-call default)
  const [defaultMode, setDefaultMode] = useState<InterviewMode>("audio");

  const jobsQ = useQuery({ queryKey: ["ref-jobs"], queryFn: () => apiFetch<Job[]>("/recruiting/jobs") });
  const candsQ = useQuery({ queryKey: ["ref-cands"], queryFn: () => apiFetch<Candidate[]>("/recruiting/candidates") });
  const historyQ = useQuery({ queryKey: ["ref-checks"], queryFn: () => apiFetch<{ items: RefCheck[] }>("/reference-checks") });

  useEffect(() => {
    const j = jobsQ.data?.find((x) => x.id === jobId);
    if (j) setJobTitle(j.title);
  }, [jobId, jobsQ.data]);
  useEffect(() => {
    const c = candsQ.data?.find((x) => x.id === candidateId);
    if (c) setCandidateName(c.full_name);
  }, [candidateId, candsQ.data]);

  const activeRef = useMemo(() => check?.references.find((r) => r.profile.id === activeRefId) ?? null, [check, activeRefId]);

  async function startCheck() {
    setError(null);
    if (!candidateName.trim()) {
      setError("Candidate name is required.");
      return;
    }
    setCreating(true);
    try {
      const c = await apiPost<RefCheck>("/reference-checks", {
        candidate_id: candidateId || null,
        candidate_name: candidateName,
        job_id: jobId || null,
        job_title: jobTitle || "Unknown Role",
        extra_context: extraContext,
        n_questions: nQuestions,
      });
      setCheck(c);
      setPerAnswerScores({});
      setWrittenDrafts({});
      setActiveRefId(null);
      setAddOpen(true);
    } catch (e: any) {
      setError(e?.message ?? "Could not create reference check");
    } finally {
      setCreating(false);
    }
  }

  async function addReference() {
    if (!check || !refName.trim()) return;
    setAdding(true);
    try {
      const slot = await apiPost<RefSlot>(`/reference-checks/${check.id}/references`, {
        name: refName,
        email: refEmail,
        title: refTitle,
        company: refCompany,
        relationship: refRelationship,
        tenure_months: refTenure,
        consent_recorded: refConsent,
      });
      // Re-fetch the whole check so the references list is fresh
      const fresh = await apiFetch<RefCheck>(`/reference-checks/${check.id}`);
      setCheck(fresh);
      setActiveRefId(slot.profile.id);
      setActiveQuestionId(slot.questions[0]?.id ?? null);
      setRefName(""); setRefEmail(""); setRefTitle(""); setRefCompany("");
      setRefConsent(false); setRefTenure(12); setRefRelationship("manager");
      setAddOpen(false);
    } catch (e: any) {
      setError(e?.message ?? "Could not add reference");
    } finally {
      setAdding(false);
    }
  }

  async function submitAnswer(refId: string, qid: string, a: AnswerSubmission) {
    if (!check) return;
    try {
      const res = await apiPost<{ scored: RefScoredAnswer }>(
        `/reference-checks/${check.id}/references/${refId}/respond`,
        {
          question_id: qid,
          answer: a.transcript,
          mode: a.mode,
          duration_sec: a.duration_sec,
          words_per_minute: a.words_per_minute,
          has_face: a.has_face,
          media_meta: a.media_meta,
        }
      );
      setPerAnswerScores((prev) => ({
        ...prev,
        [refId]: { ...(prev[refId] ?? {}), [qid]: res.scored },
      }));
      setWrittenDrafts((prev) => ({
        ...prev,
        [refId]: { ...(prev[refId] ?? {}), [qid]: a.transcript },
      }));
      // advance to next unscored question for this ref
      const slot = check.references.find((r) => r.profile.id === refId);
      if (slot) {
        const scoredMap = { ...(perAnswerScores[refId] ?? {}), [qid]: res.scored };
        const nxt = slot.questions.find((q) => q.id !== qid && !scoredMap[q.id]);
        setActiveQuestionId(nxt ? nxt.id : null);
      }
    } catch (e: any) {
      setError(e?.message ?? "Could not score that answer");
    }
  }

  async function submitWritten(refId: string, qid: string) {
    if (!check) return;
    const draft = (writtenDrafts[refId]?.[qid] ?? "").trim();
    if (!draft) return;
    await submitAnswer(refId, qid, {
      transcript: draft,
      mode: "written",
      duration_sec: 0,
      words_per_minute: 0,
      has_face: false,
      media_meta: { kind: "written" },
    });
  }

  async function completeReference(refId: string) {
    if (!check) return;
    try {
      await apiPost(`/reference-checks/${check.id}/references/${refId}/complete`, {});
      const fresh = await apiFetch<RefCheck>(`/reference-checks/${check.id}`);
      setCheck(fresh);
    } catch (e: any) {
      setError(e?.message ?? "Could not finalize reference");
    }
  }

  async function completeCheck() {
    if (!check) return;
    setCompleting(true);
    try {
      const updated = await apiPost<RefCheck>(`/reference-checks/${check.id}/complete`, {});
      setCheck(updated);
    } catch (e: any) {
      setError(e?.message ?? "Could not synthesize check");
    } finally {
      setCompleting(false);
    }
  }

  function copyInviteLink(token: string) {
    if (typeof window === "undefined") return;
    const url = `${window.location.origin}/app/reference-check/respond/${token}`;
    navigator.clipboard?.writeText(url).catch(() => undefined);
  }

  const history = historyQ.data?.items ?? [];

  // ---------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring · AI"
        title="AI Reference Checks"
        subtitle="Calibrated, relationship-aware reference interviews. Recruiter-led or invite-link, written or live voice/video. Multi-reference synthesis with explicit contradictions — always human-reviewed."
      />

      {/* Setup */}
      {!check && (
        <Surface>
          <SectionTitle eyebrow="Setup" title="Start a reference check" />
          <div className="mt-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <label className="block">
                <div className="mb-1 text-sm font-medium text-ink">Candidate (optional)</div>
                <select
                  className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
                  value={candidateId}
                  onChange={(e) => setCandidateId(e.target.value)}
                >
                  <option value="">— Free-form —</option>
                  {(candsQ.data ?? []).map((c) => (
                    <option key={c.id} value={c.id}>{c.full_name}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <div className="mb-1 text-sm font-medium text-ink">Job (optional)</div>
                <select
                  className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
                  value={jobId}
                  onChange={(e) => setJobId(e.target.value)}
                >
                  <option value="">— Free-form —</option>
                  {(jobsQ.data ?? []).map((j) => (
                    <option key={j.id} value={j.id}>{j.title}</option>
                  ))}
                </select>
              </label>
              <Input label="Candidate name" value={candidateName} onChange={(e) => setCandidateName(e.target.value)} />
              <Input label="Role title" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
              <Input
                label="Questions per reference"
                type="number" min={4} max={12}
                value={nQuestions}
                onChange={(e) => setNQuestions(Math.max(4, Math.min(12, Number(e.target.value) || 6)))}
              />
            </div>
            <Textarea
              label="Context from interviews (optional)"
              rows={4}
              value={extraContext}
              onChange={(e) => setExtraContext(e.target.value)}
              placeholder="Paste a few notes the references should be probed on — e.g. specific projects, stretch areas, or claims you want corroborated."
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={startCheck} disabled={creating}>
                {creating ? "Creating…" : "Create reference check"}
              </Button>
              {error && <span className="text-sm text-danger-fg">{error}</span>}
            </div>
            <div className="text-2xs uppercase tracking-eyebrow text-muted">
              Each reference gets relationship-tailored questions. You can run a call live (audio/video) or send an invite link they fill in themselves.
            </div>
          </div>
        </Surface>
      )}

      {/* Active check shell */}
      {check && !check.summary && (
        <>
          <Surface pad="sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="fp-eyebrow">Reference check in progress</div>
                <div className="text-md font-semibold text-ink">{check.candidate_name} · {check.job_title}</div>
                <div className="text-xs text-muted mt-0.5">
                  {check.references.length} reference{check.references.length === 1 ? "" : "s"} · {check.n_questions} questions per reference · default capture mode <span className="font-medium text-ink">{defaultMode}</span>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Action variant="subtle" onClick={() => { setCheck(null); setPerAnswerScores({}); setActiveRefId(null); }}>
                  Abandon
                </Action>
                <Action
                  variant="primary"
                  onClick={completeCheck}
                  disabled={completing || check.references.length === 0 || !check.references.some((r) => Object.keys(perAnswerScores[r.profile.id] ?? {}).length > 0)}
                >
                  {completing ? "Synthesising…" : "Synthesise references"}
                </Action>
              </div>
            </div>
          </Surface>

          <Surface pad="sm">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="fp-eyebrow">References</div>
                <div className="text-xs text-muted">Pick a reference to capture their answers. Each gets relationship-tailored questions.</div>
              </div>
              <div className="flex items-center gap-2">
                <div className="text-2xs uppercase tracking-eyebrow text-muted mr-1">Default mode</div>
                {(["audio", "video", "written"] as InterviewMode[]).map((m) => (
                  <Action key={m} size="sm" variant={defaultMode === m ? "primary" : "subtle"} onClick={() => setDefaultMode(m)}>
                    {m === "audio" ? "Audio call" : m === "video" ? "Video call" : "Written"}
                  </Action>
                ))}
                <Action variant="primary" size="sm" onClick={() => setAddOpen((v) => !v)}>
                  {addOpen ? <><IconClose /> Close</> : <>+ Add reference</>}
                </Action>
              </div>
            </div>

            {addOpen && (
              <div className="mt-4 rounded-md border border-line bg-canvas p-4 space-y-3">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Input label="Reference name" value={refName} onChange={(e) => setRefName(e.target.value)} />
                  <Input label="Email" type="email" value={refEmail} onChange={(e) => setRefEmail(e.target.value)} />
                  <Input label="Title" value={refTitle} onChange={(e) => setRefTitle(e.target.value)} />
                  <Input label="Company" value={refCompany} onChange={(e) => setRefCompany(e.target.value)} />
                  <label className="block">
                    <div className="mb-1 text-sm font-medium text-ink">Relationship</div>
                    <select
                      className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink"
                      value={refRelationship}
                      onChange={(e) => setRefRelationship(e.target.value as Relationship)}
                    >
                      {RELATIONSHIPS.map((r) => (
                        <option key={r} value={r}>{r}</option>
                      ))}
                    </select>
                  </label>
                  <Input
                    label="Tenure together (months)"
                    type="number" min={0} max={240}
                    value={refTenure}
                    onChange={(e) => setRefTenure(Math.max(0, Math.min(240, Number(e.target.value) || 0)))}
                  />
                </div>
                <label className="flex items-center gap-2 text-sm text-body">
                  <input type="checkbox" checked={refConsent} onChange={(e) => setRefConsent(e.target.checked)} />
                  Candidate has given consent for me to contact this reference.
                </label>
                <div className="flex items-center justify-end gap-2">
                  <Action variant="subtle" onClick={() => setAddOpen(false)}>Cancel</Action>
                  <Action variant="primary" onClick={addReference} disabled={!refName.trim() || adding || !refConsent}>
                    {adding ? "Adding…" : "Add reference"}
                  </Action>
                </div>
                {!refConsent && (
                  <div className="text-2xs uppercase tracking-eyebrow text-muted">
                    Consent attestation required before adding a reference.
                  </div>
                )}
              </div>
            )}

            {check.references.length === 0 ? (
              <div className="mt-4">
                <EmptyState
                  title="No references yet"
                  description="Add the candidate's first reference to generate relationship-tailored questions."
                />
              </div>
            ) : (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {check.references.map((slot) => {
                  const refScored = perAnswerScores[slot.profile.id] ?? {};
                  const answered = Object.keys(refScored).length;
                  const isActive = slot.profile.id === activeRefId;
                  return (
                    <button
                      key={slot.profile.id}
                      onClick={() => {
                        setActiveRefId(slot.profile.id);
                        const next = slot.questions.find((q) => !refScored[q.id]);
                        setActiveQuestionId(next ? next.id : slot.questions[0]?.id ?? null);
                      }}
                      className={`text-left rounded-md border p-3 transition-colors ${isActive ? "border-ink bg-surface" : "border-line bg-canvas hover:bg-sunken"}`}
                    >
                      <div className="flex items-start gap-3">
                        <Avatar name={slot.profile.name} size={36} />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-semibold text-ink truncate">{slot.profile.name}</div>
                          <div className="text-xs text-muted truncate">
                            {slot.profile.title || slot.profile.relationship}{slot.profile.company ? ` · ${slot.profile.company}` : ""}
                          </div>
                          <div className="mt-2 flex flex-wrap items-center gap-1.5">
                            <Pill tone="neutral">{slot.profile.relationship}</Pill>
                            <Pill tone={answered >= slot.questions.length ? "success" : answered > 0 ? "info" : "neutral"}>
                              {answered}/{slot.questions.length} answered
                            </Pill>
                            {slot.profile.tenure_months > 0 && <Pill tone="neutral">{slot.profile.tenure_months}mo</Pill>}
                          </div>
                          {slot.submit_token && (
                            <div
                              className="mt-2 text-2xs uppercase tracking-eyebrow text-muted hover:text-ink cursor-pointer"
                              onClick={(e) => { e.stopPropagation(); copyInviteLink(slot.submit_token); }}
                              title="Copy self-serve link"
                            >
                              <IconArrowUpRight /> Copy invite link
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </Surface>

          {/* Active reference capture */}
          {activeRef && (
            <Surface>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="fp-eyebrow">{activeRef.profile.relationship} · capturing answers</div>
                  <div className="text-md font-semibold text-ink">{activeRef.profile.name}</div>
                  <div className="text-xs text-muted">
                    {activeRef.profile.title}{activeRef.profile.company ? ` · ${activeRef.profile.company}` : ""}
                    {activeRef.profile.tenure_months ? ` · worked together ${activeRef.profile.tenure_months}mo` : ""}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Action variant="subtle" onClick={() => completeReference(activeRef.profile.id)}>
                    Mark reference complete
                  </Action>
                </div>
              </div>

              <div className="mt-4 space-y-4">
                {activeRef.questions.map((q, idx) => {
                  const scored = (perAnswerScores[activeRef.profile.id] ?? {})[q.id];
                  const isActive = activeQuestionId === q.id;
                  const draft = (writtenDrafts[activeRef.profile.id] ?? {})[q.id] ?? "";
                  return (
                    <Surface key={q.id} inset hairline pad="md">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="fp-eyebrow">Q{idx + 1} · {q.competency.replace(/_/g, " ")}</div>
                          <div className="text-sm font-semibold text-ink mt-0.5">{q.question}</div>
                          {q.rationale && <div className="text-xs text-muted mt-1">{q.rationale}</div>}
                        </div>
                        <div className="flex items-center gap-2">
                          {scored && <ScoreBadge score={scored.score} />}
                          {scored?.subscores?.concern && scored.subscores.concern >= 40 && (
                            <Pill tone="danger">concern</Pill>
                          )}
                        </div>
                      </div>

                      <div className="mt-3">
                        {scored && !isActive ? (
                          <div className="rounded-md border border-line bg-canvas p-3 space-y-2">
                            <div className="flex items-center justify-between">
                              <div className="text-2xs uppercase tracking-eyebrow text-muted">Captured answer</div>
                              <Action variant="subtle" size="sm" onClick={() => setActiveQuestionId(q.id)}>Re-capture</Action>
                            </div>
                            <div className="text-sm text-ink whitespace-pre-wrap leading-relaxed">
                              {scored.answer || <span className="text-muted">—</span>}
                            </div>
                          </div>
                        ) : (
                          <PerQuestionCapture
                            key={`${q.id}-${isActive ? "a" : "i"}`}
                            question={q}
                            defaultMode={defaultMode}
                            writtenValue={draft}
                            onWrittenChange={(v) =>
                              setWrittenDrafts((prev) => ({
                                ...prev,
                                [activeRef.profile.id]: { ...(prev[activeRef.profile.id] ?? {}), [q.id]: v },
                              }))
                            }
                            onSubmit={(a) => submitAnswer(activeRef.profile.id, q.id, a)}
                            onSubmitWritten={() => submitWritten(activeRef.profile.id, q.id)}
                          />
                        )}
                      </div>

                      {scored && (
                        <div className="mt-4 space-y-3 border-t border-line pt-3">
                          {scored.subscores && Object.keys(scored.subscores).length > 0 && (
                            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                              {DIM_ORDER.map((k) => (
                                <DimBar
                                  key={k}
                                  label={DIM_LABEL[k]}
                                  value={scored.subscores?.[k] ?? 0}
                                  danger={k === "concern"}
                                />
                              ))}
                            </div>
                          )}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div>
                              <div className="fp-eyebrow text-success-fg mb-1">Themes</div>
                              {scored.strengths.length === 0
                                ? <div className="text-xs text-muted">—</div>
                                : <ul className="text-xs text-body space-y-0.5">{scored.strengths.map((s, i) => <li key={i}>• {s}</li>)}</ul>}
                            </div>
                            <div>
                              <div className="fp-eyebrow text-danger-fg mb-1">Concerns</div>
                              {scored.concerns.length === 0
                                ? <div className="text-xs text-muted">—</div>
                                : <ul className="text-xs text-body space-y-0.5">{scored.concerns.map((s, i) => <li key={i}>• {s}</li>)}</ul>}
                            </div>
                          </div>
                          {scored.follow_up && (
                            <div className="rounded-md border border-line bg-canvas px-3 py-2 text-xs text-body">
                              <span className="fp-eyebrow mr-2">Suggested follow-up</span>
                              {scored.follow_up}
                            </div>
                          )}
                        </div>
                      )}
                    </Surface>
                  );
                })}
              </div>
            </Surface>
          )}
        </>
      )}

      {/* Final synthesis */}
      {check?.summary && (
        <div className="space-y-4">
          <Surface pad="lg">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="fp-eyebrow">Reference synthesis</div>
                <div className="text-xl font-semibold text-ink mt-1">{check.candidate_name} · {check.job_title}</div>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <Pill tone={BAND_TONE[check.summary.band] ?? "neutral"}>
                    {check.summary.band.replace(/_/g, " ")}
                  </Pill>
                  <Pill tone="neutral">
                    {REC_LABEL[check.summary.recommendation] ?? check.summary.recommendation}
                  </Pill>
                  <Pill tone="neutral">{check.summary.n_references} ref{check.summary.n_references === 1 ? "" : "s"}</Pill>
                  {check.summary.relationships_covered.map((r) => (
                    <Pill key={r} tone="info">{r}</Pill>
                  ))}
                </div>
              </div>
              <div className="text-right">
                <div className="text-4xl font-bold text-ink tabular-nums">{check.summary.overall_score}</div>
                <div className="fp-eyebrow">weighted endorsement</div>
              </div>
            </div>

            <div className="mt-4 text-sm text-body leading-relaxed">{check.summary.narrative}</div>

            {check.summary.competency_scores && Object.keys(check.summary.competency_scores).length > 0 && (
              <div className="mt-5">
                <div className="fp-eyebrow mb-2">Competency consensus</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {Object.entries(check.summary.competency_scores).map(([k, v]) => (
                    <div key={k} className="rounded-md border border-line bg-canvas p-3">
                      <div className="text-2xs uppercase tracking-eyebrow text-muted capitalize">{k.replace(/_/g, " ")}</div>
                      <div className="text-lg font-semibold text-ink mt-0.5 tabular-nums">{v}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <div className="fp-eyebrow text-success-fg mb-1">Strengths</div>
                {check.summary.strengths.length === 0 ? (
                  <div className="text-xs text-muted">—</div>
                ) : (
                  <ul className="text-sm text-body space-y-1">{check.summary.strengths.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                )}
              </div>
              <div>
                <div className="fp-eyebrow text-danger-fg mb-1">Risks</div>
                {check.summary.risks.length === 0 ? (
                  <div className="text-xs text-muted">—</div>
                ) : (
                  <ul className="text-sm text-body space-y-1">{check.summary.risks.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                )}
              </div>
            </div>

            {check.summary.contradictions.length > 0 && (
              <div className="mt-5 rounded-md border border-warn-line bg-warn-bg p-3">
                <div className="fp-eyebrow text-warn-fg mb-1">Contradictions across references</div>
                <ul className="text-xs text-warn-fg space-y-1">
                  {check.summary.contradictions.map((c, i) => <li key={i}>• {c}</li>)}
                </ul>
              </div>
            )}

            <div className="mt-5">
              <div className="fp-eyebrow mb-2">Per-reference roll-up</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {check.summary.references.map((r) => (
                  <div key={r.reference_id} className="rounded-md border border-line bg-canvas p-3">
                    <div className="flex items-center justify-between gap-2">
                      <div>
                        <div className="text-sm font-semibold text-ink">{r.reference_name}</div>
                        <div className="text-xs text-muted capitalize">{r.relationship}</div>
                      </div>
                      <ScoreBadge score={r.overall} band={r.band} />
                    </div>
                    <div className="mt-2 text-xs text-body">{r.summary}</div>
                    {r.themes.length > 0 && (
                      <div className="mt-2">
                        <div className="text-2xs uppercase tracking-eyebrow text-success-fg">Themes</div>
                        <ul className="text-2xs text-body space-y-0.5">{r.themes.slice(0, 3).map((t, i) => <li key={i}>• {t}</li>)}</ul>
                      </div>
                    )}
                    {r.red_flags.length > 0 && (
                      <div className="mt-2">
                        <div className="text-2xs uppercase tracking-eyebrow text-danger-fg">Concerns</div>
                        <ul className="text-2xs text-body space-y-0.5">{r.red_flags.slice(0, 3).map((t, i) => <li key={i}>• {t}</li>)}</ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-5 rounded-md border border-warn-line bg-warn-bg text-warn-fg text-xs px-3 py-2">
              ⚖ {check.summary.fairness_note}
            </div>
          </Surface>

          <Action
            variant="subtle"
            onClick={() => {
              setCheck(null);
              setPerAnswerScores({});
              setActiveRefId(null);
              setActiveQuestionId(null);
            }}
          >
            Start another reference check
          </Action>
        </div>
      )}

      {/* History */}
      <Surface pad="sm">
        <SectionTitle eyebrow="History" title="Past reference checks" />
        {history.length === 0 ? (
          <div className="text-sm text-muted py-6 text-center">No reference checks yet</div>
        ) : (
          <div className="divide-y divide-line mt-2">
            {history.map((c) => (
              <div key={c.id} className="py-2 flex items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-ink">{c.candidate_name} · {c.job_title}</div>
                  <div className="text-xs text-muted">
                    {new Date(c.created_at).toLocaleString()} · {c.references.length} ref{c.references.length === 1 ? "" : "s"} · {c.status}
                  </div>
                </div>
                {c.summary ? (
                  <ScoreBadge score={c.summary.overall_score} band={c.summary.band} />
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
// Per-question capture (mode toggle + VideoInterviewer)
// ---------------------------------------------------------------------------
function PerQuestionCapture({
  question,
  defaultMode,
  writtenValue,
  onWrittenChange,
  onSubmit,
  onSubmitWritten,
}: {
  question: RefQuestion;
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
              rows={5}
              onChange={(e) => onWrittenChange(e.target.value)}
              placeholder="Type the reference's response (or notes you took during the live call)…"
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
