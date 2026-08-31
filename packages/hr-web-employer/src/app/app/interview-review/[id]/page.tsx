"use client";

/**
 * Recruiter playback: the score, the words behind it, and the jump.
 *
 * THE ONE INTERACTION THAT MATTERS
 * Click any assessment, strength or contradiction and the player seeks to the
 * moment the candidate said it, and the transcript scrolls to that line. That
 * is the product: an assessment you can check in four seconds instead of
 * watching twenty-five minutes.
 *
 * WHAT THIS PAGE REFUSES TO DO
 * Show a competency as weak when it was never established. INSUFFICIENT_EVIDENCE
 * and NOT_PROBED render in their own neutral treatment, separated from real
 * scores, because a recruiter skimming a column of numbers will otherwise read
 * an absence as a low opinion of the candidate.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch, apiObjectUrl } from "@/lib/api";
import { locateSeek, timelineEndMs } from "@/lib/timeline";
import { env } from "@/lib/env";
import {
  Surface,
  Stack,
  PageHeader,
  SectionTitle,
  Pill,
  MetricStat,
  Divider,
  EmptyState,
} from "@/components/ds";

// ---------------------------------------------------------------------------
// Types — mirror app/api/routers/interview_v2.py::playback
// ---------------------------------------------------------------------------

type EvidenceLink = { evidence_id: string; role: string };

type Assessment = {
  id: string;
  competency_key: string;
  label: string;
  state: "SCORED" | "INSUFFICIENT_EVIDENCE" | "NOT_PROBED";
  score: number | null;
  confidence: number | null;
  rationale: string;
  missing_evidence: string | null;
  evidence: EvidenceLink[];
};

type Evidence = {
  id: string;
  competency_key: string;
  polarity: "SUPPORTS" | "CONTRADICTS" | "NEUTRAL";
  kind: string;
  quote: string;
  rationale: string;
  strength: number;
  start_ms: number | null;
  end_ms: number | null;
  answer_id: string;
};

type Turn = {
  question_id: string;
  sequence: number;
  kind: string;
  probe_depth: number;
  question: string;
  intent: string | null;
  competency_id: string | null;
  answer: {
    id: string;
    text: string;
    start_ms: number | null;
    end_ms: number | null;
    substantive: boolean;
  } | null;
};

type SummaryItem = {
  text: string;
  competency_key: string | null;
  evidence_ids: string[];
  quote: string | null;
  start_ms: number | null;
};

type Verification = {
  verdict: string;
  established: string | null;
  rationale: string;
  confidence: number | null;
  claim: string;
  source_excerpt: string;
  source_kind: string;
  claim_type: string;
};

type Playback = {
  interview: {
    id: string;
    status: string;
    mode: string;
    candidate: { id: string; name: string } | null;
    job: { id: string; title: string } | null;
  };
  scorecard: {
    overall_state: string;
    overall_score: number | null;
    overall_confidence: number | null;
    completeness: "COMPLETE" | "INCOMPLETE";
    uncovered_required: string[];
    decision_authority: string;
    rubric: string;
  } | null;
  assessments: Assessment[];
  evidence: Evidence[];
  conversation: Turn[];
  plan: {
    key: string;
    label: string;
    why: string;
    hook: string | null;
    required: boolean;
    weight: number;
  }[];
  claim_verifications: Verification[];
  debrief: {
    headline: string;
    overall_assessment: string;
    strengths: SummaryItem[];
    weaknesses: SummaryItem[];
    also_assessed?: SummaryItem[];
    contradictions: SummaryItem[];
    unresolved_questions: SummaryItem[];
    recommended_followup: SummaryItem[];
  } | null;
  transcript: {
    id: string;
    speaker: string;
    sequence: number;
    start_ms: number;
    end_ms: number;
    text: string;
    source: string;
    revision: number;
    asr_adapter: string | null;
    asr_confidence: number | null;
  }[];
  /** How the transcript was obtained. The grade is the WEAKEST segment's. */
  transcript_provenance?: {
    authority: "NONE" | "CLIENT_REPORTED" | "SERVER_DERIVED" | "UNKNOWN";
    adapters: string[];
    detail: string;
  };
  /** Whether the media held is the WHOLE recording. See media.assess_completeness. */
  recording_completeness?: {
    state: "NOT_CAPTURED" | "CAPTURING" | "SEALED" | "INCOMPLETE";
    parts_held: number;
    parts_expected: number | null;
    missing_parts: number[];
    duplicate_parts: number[];
    zero_byte_parts: number[];
    detail: string;
  };
  recordings: {
    id: string;
    media_kind: string;
    part: number;
    storage_kind: string;
    /** A URL to fetch. The server used to ship its own filesystem path here. */
    href: string;
    duration_ms: number | null;
    timeline_offset_ms: number;
  }[];
};

// ---------------------------------------------------------------------------

const fmtTime = (ms: number | null | undefined): string => {
  if (ms === null || ms === undefined) return "—";
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
};

const SCORE_TONE = (score: number | null): string => {
  if (score === null) return "var(--muted, #6b7280)";
  if (score >= 3) return "#16794a";
  if (score >= 2) return "#2f5bd7";
  return "#8a5a00";
};

/**
 * What each transcript authority means, in the reader's words.
 *
 * The page used to test for SERVER_DERIVED and CLIENT_REPORTED and fall through
 * to "origin not recorded" for anything else. The seeded demo interview reports
 * DEMO_FIXTURE, so the most important case landed in the fallback and the page
 * said its origin was NOT recorded when it was recorded precisely — as a
 * fixture. The sentence beside it was right; the headline contradicted it.
 *
 * A value missing from this map still falls back, which is the honest answer
 * for an authority we genuinely do not recognise.
 */
const TRANSCRIPT_ORIGIN: Record<string, string> = {
  SERVER_DERIVED: "Transcript: from the recording",
  CLIENT_REPORTED: "Transcript: reported by the candidate's browser",
  DEMO_FIXTURE: "Transcript: seeded for this demonstration",
  // NONE means there are no transcript segments at all. "Origin not recorded"
  // would suggest a transcript exists whose source we lost track of.
  NONE: "Transcript: none recorded",
  UNKNOWN: "Transcript: origin not recorded",
};

export default function InterviewReviewPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [data, setData] = useState<Playback | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cursorMs, setCursorMs] = useState<number>(0);
  const [activeEvidence, setActiveEvidence] = useState<string | null>(null);
  // The <video> element cannot send an Authorization header, so the part is
  // fetched with one and handed to the player as a blob. See `apiObjectUrl`.
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const [mediaError, setMediaError] = useState<string | null>(null);
  const [seekProblem, setSeekProblem] = useState<string | null>(null);
  const [loadedPart, setLoadedPart] = useState<number | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const player = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    if (!id) return;
    // env.apiBaseUrl already ends in "/api", so the path must NOT repeat it.
    // The majority convention in this app is a bare "/resource" path;
    // the handful of pages using "/api/..." produce a doubled prefix.
    apiFetch<Playback>(`/interview-v2/${id}/playback`)
      .then(setData)
      .catch((e) => setErr(e?.message ?? String(e)));
  }, [id]);

  const evidenceById = useMemo(() => {
    const m = new Map<string, Evidence>();
    (data?.evidence ?? []).forEach((e) => m.set(e.id, e));
    return m;
  }, [data]);

  /** The click that makes this page worth paying for. */
  // ONE TIMELINE, SEVERAL FILES.
  //
  // A reconnect makes a new part, so a 72-second interview is three 24-second
  // WebM files with `timeline_offset_ms` saying where each sits. The player
  // loaded `recordings[0]` and nothing else, so every piece of evidence after
  // the first part was unreachable -- and the "past the end of the recording"
  // guard fired on it, reporting the length of ONE PART as the length of the
  // interview. Honest about the wrong number.
  const parts = useMemo(
    () =>
      [...(data?.recordings ?? [])].sort(
        (a, b) => a.timeline_offset_ms - b.timeline_offset_ms,
      ),
    [data],
  );

  // The timeline arithmetic lives in @/lib/timeline so it can be tested: a bad
  // offset does not throw, it plays a different moment.
  const timelineMs = useMemo(() => timelineEndMs(parts), [parts]);

  /** Load a part, replacing whatever is loaded. Returns once it is playable. */
  const loadPart = useCallback(async (part: (typeof parts)[number]) => {
    const url = await apiObjectUrl(part.href);
    setMediaUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return url;
    });
    setLoadedPart(part.part);
    return url;
  }, []);

  useEffect(() => {
    if (!parts.length) return;
    let cancelled = false;
    (async () => {
      try {
        await loadPart(parts[0]);
      } catch (e: any) {
        if (!cancelled) {
          setMediaError(e?.message ?? "the recording could not be loaded");
        }
      }
    })();
    return () => { cancelled = true; };
  }, [parts, loadPart]);

  const jumpTo = useCallback(
    (ms: number | null, evidenceId?: string) => {
      if (ms === null || ms === undefined) return;
      setCursorMs(ms);
      if (evidenceId) setActiveEvidence(evidenceId);

      // SEEK THE ACTUAL MEDIA, OR SAY WHY NOT.
      //
      // An evidence timecode comes from the answer boundary the application
      // recorded. The media's duration comes from the recorder. Those are two
      // clocks, and a timecode past the end of the media means they have
      // diverged -- a partial upload, a recorder that stopped, or a part that
      // never arrived.
      //
      // Clamping silently to the end would be the worst option: the recruiter
      // would watch the wrong moment believing it was the right one. So the
      // seek is refused and named.
      setSeekProblem(null);
      const el0 = player.current;
      if (el0 && parts.length) {
        const target = locateSeek(parts, ms);
        if (!target) {
          setSeekProblem(
            `That evidence is timed at ${fmtTime(ms)}, and the recording ` +
              `covers ${fmtTime(0)}–${fmtTime(timelineMs)} across ` +
              `${parts.length} part${parts.length === 1 ? "" : "s"}. The ` +
              `answer boundary and the media disagree, so the player was not ` +
              `moved rather than being sent somewhere wrong.`,
          );
          return;
        }
        const { part, withinSeconds: within } = target;
        const seekNow = () => {
          try {
            const el = player.current;
            if (!el) return;
            el.currentTime = within;
            void el.play();
          } catch {
            /* the element may not be ready yet */
          }
        };
        if (part.part === loadedPart) {
          seekNow();
        } else {
          // A different part has to be fetched first; seek once it can play.
          void loadPart(part)
            .then(() => {
              const el = player.current;
              if (!el) return;
              const go = () => {
                el.removeEventListener("loadedmetadata", go);
                seekNow();
              };
              el.addEventListener("loadedmetadata", go);
            })
            .catch((e: any) =>
              setSeekProblem(
                `Part ${part.part} of the recording could not be loaded: ` +
                  `${e?.message ?? "unknown error"}`,
              ),
            );
        }
      }

      const el = document.getElementById(`turn-${ms}`);
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
    },
    [parts, timelineMs, loadedPart, loadPart],
  );

  // EVERY SEEK TARGET IS A REAL CONTROL.
  //
  // These were bare <div onClick>. They worked with a mouse and with nothing
  // else: no tab stop, no Enter or Space, no focus ring, and a screen reader
  // announced a paragraph of text rather than something you can activate. The
  // page's whole instruction is "Click a competency to jump to the evidence
  // behind it", so the one interaction it is built around was unreachable
  // without a pointer.
  //
  // Spread onto the existing element rather than swapping the tag for a
  // <button>, which would inherit button typography and reset the layout of
  // five different blocks.
  const seekable = useCallback(
    (ms: number | null | undefined, evidenceId?: string, label?: string) => ({
      role: "button" as const,
      tabIndex: 0,
      "aria-label": label,
      onClick: () => jumpTo(ms ?? null, evidenceId),
      onKeyDown: (e: React.KeyboardEvent) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          jumpTo(ms ?? null, evidenceId);
        }
      },
    }),
    [jumpTo],
  );

  if (err)
    return (
      <Surface>
        <EmptyState title="Could not load this interview" description={err} />
      </Surface>
    );

  if (!data)
    return (
      <Surface>
        <EmptyState title="Loading the interview…" description="Fetching evidence, assessments and transcript." />
      </Surface>
    );

  const { interview, scorecard, assessments, debrief } = data;
  const scored = assessments.filter((a) => a.state === "SCORED");
  const unestablished = assessments.filter((a) => a.state !== "SCORED");

  return (
    <Stack gap={5}>
      <PageHeader
        title={`${interview.candidate?.name ?? "Candidate"} — ${interview.job?.title ?? "role"}`}
        subtitle={
          debrief?.headline ??
          "This interview has not been finalised, so there is no assessment yet."
        }
        actions={
          scorecard ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <Pill tone={scorecard.completeness === "COMPLETE" ? "success" : "warn"}>
                {scorecard.completeness === "COMPLETE"
                  ? "All required competencies covered"
                  : `${scorecard.uncovered_required.length} required not covered`}
              </Pill>
              <Pill tone="neutral">Recruiter decision support</Pill>
            </div>
          ) : null
        }
      />

      {/* --- headline numbers ------------------------------------------- */}
      {scorecard && (
        <Surface>
          <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
            <MetricStat
              label="Overall"
              value={
                scorecard.overall_score !== null
                  ? `${scorecard.overall_score}/4`
                  : "Not established"
              }
              hint={`confidence ${scorecard.overall_confidence ?? "—"}`}
            />
            <MetricStat
              label="Competencies established"
              value={`${scored.length} of ${assessments.length}`}
              hint={
                unestablished.length
                  ? `${unestablished.length} not established by this interview`
                  : "every planned competency produced evidence"
              }
            />
            <MetricStat
              label="Rubric"
              value={scorecard.rubric}
              hint="versioned; the same rubric scores every candidate for this role"
            />
          </div>
          <Divider />
          <p style={{ margin: 0, fontSize: 13.5, color: "var(--muted, #646b76)" }}>
            {debrief?.overall_assessment}
          </p>
        </Surface>
      )}

      <div
        style={{
          display: "grid",
          gap: 16,
          gridTemplateColumns: "minmax(320px, 1fr) minmax(380px, 1.15fr)",
          alignItems: "start",
        }}
      >
        {/* ============ LEFT: scorecard + debrief ======================== */}
        <Stack gap={4}>
          <Surface>
            <SectionTitle title="Competency scorecard" />
            <p style={{ fontSize: 12.5, color: "var(--muted, #646b76)", marginTop: 0 }}>
              Click a competency to jump to the evidence behind it.
            </p>

            {scored.map((a) => {
              const evs = a.evidence
                .map((l) => evidenceById.get(l.evidence_id))
                .filter(Boolean) as Evidence[];
              const best = evs.sort((x, y) => y.strength - x.strength)[0];
              return (
                <div
                  key={a.id}
                  {...seekable(best?.start_ms, best?.id,
                    `Play the recording at the evidence for ${a.competency_key}`)}
                  style={{
                    cursor: best ? "pointer" : "default",
                    padding: "10px 0",
                    borderBottom: "1px solid var(--border, #e3e6ea)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                    <strong style={{ fontSize: 14 }}>{a.label}</strong>
                    <span
                      style={{
                        fontVariantNumeric: "tabular-nums",
                        fontWeight: 650,
                        color: SCORE_TONE(a.score),
                      }}
                    >
                      {a.score}/4
                    </span>
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--muted, #646b76)", marginTop: 2 }}>
                    {a.rationale}
                  </div>
                  {best && (
                    <div style={{ fontSize: 12, marginTop: 6, color: "#2f5bd7" }}>
                      ▸ “{best.quote.slice(0, 90)}…” at {fmtTime(best.start_ms)}
                    </div>
                  )}
                </div>
              );
            })}

            {unestablished.length > 0 && (
              <>
                <SectionTitle title="Not established by this interview" />
                <p style={{ fontSize: 12.5, color: "var(--muted, #646b76)", marginTop: 0 }}>
                  These are <strong>not</strong> low scores. The interview did not
                  produce enough for a judgement either way, so a human round
                  should cover them.
                </p>
                {unestablished.map((a) => (
                  <div
                    key={a.id}
                    style={{
                      padding: "8px 0",
                      borderBottom: "1px solid var(--border, #e3e6ea)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
                      <strong style={{ fontSize: 14 }}>{a.label}</strong>
                      <Pill tone="neutral">{a.state.replace(/_/g, " ").toLowerCase()}</Pill>
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--muted, #646b76)", marginTop: 2 }}>
                      {a.missing_evidence ?? a.rationale}
                    </div>
                  </div>
                ))}
              </>
            )}
          </Surface>

          {debrief && (
            <Surface>
              <SectionTitle title="Recruiter debrief" />

              {debrief.strengths.length > 0 && (
                <>
                  <div style={{ fontSize: 12, fontWeight: 650, marginTop: 8 }}>
                    Strongest evidence
                  </div>
                  {debrief.strengths.map((s, i) => (
                    <div
                      key={i}
                      {...seekable(s.start_ms, s.evidence_ids[0],
                        "Play the recording at this strength")}
                      style={{ cursor: "pointer", padding: "8px 0", fontSize: 13.5 }}
                    >
                      {s.text}
                      {s.quote && (
                        <div style={{ fontSize: 12, color: "#2f5bd7", marginTop: 3 }}>
                          ▸ “{s.quote.slice(0, 100)}…” at {fmtTime(s.start_ms)}
                        </div>
                      )}
                    </div>
                  ))}
                </>
              )}

              {/* THIS SECTION WAS TYPED AND NEVER RENDERED.
                  `debrief.weaknesses` was in the interface, came back on
                  every response, and appeared nowhere on the page. A debrief
                  that shows only strengths is not a debrief -- it is a
                  case for the candidate, and the recruiter it is written for
                  has no way to see what the interview did NOT establish.

                  Each item now carries the strongest evidence for that
                  competency, so a weak assessment seeks the recording at the
                  moment the candidate spoke to it. A recruiter should be able
                  to disagree with a low score by listening to it. */}
              {debrief.weaknesses.length > 0 && (
                <>
                  <div style={{ fontSize: 12, fontWeight: 650, marginTop: 12 }}>
                    Thin on evidence
                  </div>
                  <div style={{ fontSize: 11.5, color: "#6b7280", marginBottom: 2 }}>
                    A low score here means the interview did not establish it.
                    Play the clip and judge it yourself.
                  </div>
                  {debrief.weaknesses.map((w, i) => (
                    <div
                      key={i}
                      {...seekable(w.start_ms, w.evidence_ids[0],
                        "Play the recording at this gap")}
                      style={{
                        cursor: w.start_ms !== null ? "pointer" : "default",
                        padding: "8px 0",
                        fontSize: 13.5,
                      }}
                    >
                      {w.text}
                      {w.quote && (
                        <div style={{ fontSize: 12, color: "#2f5bd7", marginTop: 3 }}>
                          ▸ “{w.quote.slice(0, 100)}…” at {fmtTime(w.start_ms)}
                        </div>
                      )}
                    </div>
                  ))}
                </>
              )}

              {(debrief.also_assessed?.length ?? 0) > 0 && (
                <>
                  <div style={{ fontSize: 12, fontWeight: 650, marginTop: 12 }}>
                    Also at the bar
                  </div>
                  <div style={{ fontSize: 13, color: "#444", marginTop: 2 }}>
                    {debrief.also_assessed!.map((a, i) => (
                      <span
                        key={i}
                        {...seekable(a.start_ms, a.evidence_ids[0],
                        "Play the recording at this moment")}
                        style={{
                          cursor: a.start_ms !== null ? "pointer" : "default",
                          marginRight: 10,
                        }}
                      >
                        {a.text}
                        {i < debrief.also_assessed!.length - 1 ? " · " : ""}
                      </span>
                    ))}
                  </div>
                </>
              )}

              {debrief.contradictions.length > 0 && (
                <>
                  <div style={{ fontSize: 12, fontWeight: 650, marginTop: 12 }}>
                    To clarify with the candidate
                  </div>
                  {debrief.contradictions.map((c, i) => (
                    <div
                      key={i}
                      {...seekable(c.start_ms, c.evidence_ids[0],
                        "Play the recording at this contradiction")}
                      style={{
                        cursor: c.start_ms ? "pointer" : "default",
                        padding: "8px 0",
                        fontSize: 13.5,
                      }}
                    >
                      {c.text}
                    </div>
                  ))}
                </>
              )}

              {debrief.unresolved_questions.length > 0 && (
                <>
                  <div style={{ fontSize: 12, fontWeight: 650, marginTop: 12 }}>
                    What this interview did not establish
                  </div>
                  {debrief.unresolved_questions.map((u, i) => (
                    <div key={i} style={{ padding: "6px 0", fontSize: 13.5 }}>
                      {u.text}
                    </div>
                  ))}
                </>
              )}

              {debrief.recommended_followup.length > 0 && (
                <>
                  <div style={{ fontSize: 12, fontWeight: 650, marginTop: 12 }}>
                    Recommended for the human round
                  </div>
                  {debrief.recommended_followup.map((r, i) => (
                    <div key={i} style={{ padding: "6px 0", fontSize: 13.5 }}>
                      {r.text}
                    </div>
                  ))}
                </>
              )}
            </Surface>
          )}

          {data.claim_verifications.length > 0 && (
            <Surface>
              <SectionTitle title="Resume claims, checked" />
              {data.claim_verifications.map((v, i) => (
                <div
                  key={i}
                  style={{
                    padding: "10px 0",
                    borderBottom: "1px solid var(--border, #e3e6ea)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                    <span style={{ fontSize: 13.5 }}>“{v.source_excerpt}”</span>
                    <Pill
                      tone={
                        v.verdict === "SUPPORTED"
                          ? "success"
                          : v.verdict === "CONTRADICTED"
                            ? "danger"
                            : "warn"
                      }
                    >
                      {v.verdict.replace(/_/g, " ").toLowerCase()}
                    </Pill>
                  </div>
                  {v.established && (
                    <div style={{ fontSize: 13, marginTop: 4 }}>
                      Interview established: <strong>{v.established}</strong>
                    </div>
                  )}
                  <div style={{ fontSize: 12.5, color: "var(--muted, #646b76)", marginTop: 3 }}>
                    {v.rationale}
                  </div>
                </div>
              ))}
            </Surface>
          )}
        </Stack>

        {/* ============ RIGHT: player + conversation ===================== */}
        <Stack gap={4}>
          <Surface>
            <SectionTitle title="Recording" />
            {data.recordings.length === 0 ? (
              <div
                style={{
                  background: "var(--bg, #f6f7f9)",
                  border: "1px dashed var(--border, #e3e6ea)",
                  borderRadius: 10, padding: 24, textAlign: "center",
                  fontSize: 13, color: "var(--muted, #646b76)",
                }}
              >
                <div style={{ fontWeight: 650, marginBottom: 4 }}>
                  No recording was captured for this interview
                </div>
                The evidence below still carries timecodes from the answer
                boundaries, but there is no media to seek into. Media capture
                is per-interview and depends on the candidate&apos;s consent
                and browser.
              </div>
            ) : (
              <>
                {/* The real thing. Clicking evidence seeks this element. */}
                <video
                  ref={player}
                  controls
                  playsInline
                  src={mediaUrl ?? undefined}
                  style={{
                    width: "100%", borderRadius: 8, background: "#000",
                    maxHeight: 320,
                  }}
                  onTimeUpdate={(e) =>
                    setCursorMs(Math.floor(e.currentTarget.currentTime * 1000))
                  }
                />
                {/* A RECRUITER MUST NEVER SEE A PLAYER OVER AN INCOMPLETE
                    RECORDING WITHOUT BEING TOLD. A row existing is not the
                    same as the recording being whole, and an assessment
                    defended by media that is missing the answer it rests on
                    is the failure this banner exists to prevent. */}
                {data.recording_completeness &&
                  data.recording_completeness.state !== "SEALED" && (
                    <div
                      style={{
                        fontSize: 12, marginTop: 8, borderRadius: 6,
                        padding: "8px 10px",
                        background:
                          data.recording_completeness.state === "INCOMPLETE"
                            ? "#fef2f2" : "#fffbeb",
                        border:
                          data.recording_completeness.state === "INCOMPLETE"
                            ? "1px solid #fecaca" : "1px solid #fde68a",
                        color:
                          data.recording_completeness.state === "INCOMPLETE"
                            ? "#991b1b" : "#92400e",
                      }}
                    >
                      <strong>
                        {data.recording_completeness.state === "INCOMPLETE"
                          ? "This recording is not whole"
                          : "This recording was never sealed"}
                      </strong>
                      <div style={{ marginTop: 3 }}>
                        {data.recording_completeness.detail}
                      </div>
                    </div>
                  )}
                {seekProblem && (
                  <div
                    style={{
                      fontSize: 12, color: "#92400e", marginTop: 8,
                      background: "#fffbeb", border: "1px solid #fde68a",
                      borderRadius: 6, padding: "8px 10px",
                    }}
                  >
                    {seekProblem}
                  </div>
                )}
                {mediaError && (
                  <div style={{ fontSize: 12, color: "#b91c1c", marginTop: 6 }}>
                    The recording exists but could not be loaded: {mediaError}
                  </div>
                )}
                {!mediaUrl && !mediaError && (
                  <div style={{ fontSize: 12, color: "#6b7280", marginTop: 6 }}>
                    Loading the recording…
                  </div>
                )}
                <div
                  style={{
                    display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10,
                    fontSize: 12.5, alignItems: "center",
                  }}
                >
                  {data.recordings.map((r) => (
                    <Pill
                      key={r.id}
                      tone={r.storage_kind === "OBJECT_STORE" ? "success" : "info"}
                    >
                      part {r.part} · {r.media_kind.toLowerCase()} ·{" "}
                      {fmtTime(r.duration_ms)} · {r.storage_kind}
                    </Pill>
                  ))}
                </div>
                {data.recordings.length > 1 && (
                  <div
                    style={{
                      fontSize: 12, color: "var(--muted, #646b76)", marginTop: 8,
                    }}
                  >
                    This interview reconnected, so it is stored as{" "}
                    {data.recordings.length} parts on one timeline.
                  </div>
                )}
              </>
            )}

            <div
              style={{
                marginTop: 12,
                fontVariantNumeric: "tabular-nums",
                fontSize: 13,
              }}
            >
              Playhead: <strong>{fmtTime(cursorMs)}</strong>
              {activeEvidence && (
                <span style={{ color: "var(--muted, #646b76)" }}>
                  {" "}
                  — showing evidence {activeEvidence.slice(0, 8)}
                </span>
              )}
            </div>
          </Surface>

          <Surface>
            <SectionTitle title="The conversation" />
            <p style={{ fontSize: 12.5, color: "var(--muted, #646b76)", marginTop: 0 }}>
              Follow-ups are marked with why they were asked. A question the AI
              generated in response to an answer shows its probe depth.
            </p>
            {/* WHERE THE WORDS CAME FROM.
                Assessments cite these lines as evidence. A transcript the
                candidate's own browser produced and a transcript the server
                read off the recording are not the same evidence, and the
                difference belongs in front of whoever is relying on it. */}
            {data.transcript_provenance &&
              data.transcript_provenance.authority !== "NONE" && (
                <div
                  style={{
                    display: "flex", gap: 8, alignItems: "flex-start",
                    fontSize: 12, lineHeight: 1.5, marginBottom: 12,
                    padding: "8px 10px", borderRadius: 6,
                    border: "1px solid var(--border, #e3e6ea)",
                    background:
                      data.transcript_provenance.authority === "SERVER_DERIVED"
                        ? "var(--surface-2, #f7f8fa)"
                        : "var(--warn-bg, #fff8e6)",
                  }}
                >
                  <strong style={{ whiteSpace: "nowrap" }}>
                    {TRANSCRIPT_ORIGIN[data.transcript_provenance.authority] ??
                      "Transcript: origin not recorded"}
                  </strong>
                  <span style={{ color: "var(--muted, #646b76)" }}>
                    {data.transcript_provenance.detail}
                  </span>
                </div>
              )}
            <div ref={transcriptRef} style={{ maxHeight: 640, overflowY: "auto" }}>
              {data.conversation.map((t) => {
                const isActive =
                  t.answer?.start_ms !== null &&
                  t.answer?.start_ms !== undefined &&
                  t.answer.start_ms === cursorMs;
                return (
                  <div
                    key={t.question_id}
                    id={`turn-${t.answer?.start_ms ?? -1}`}
                    style={{
                      padding: "12px 10px",
                      marginBottom: 6,
                      borderRadius: 8,
                      background: isActive ? "var(--accent-soft, #eaf0fd)" : "transparent",
                      borderLeft: isActive
                        ? "3px solid #2f5bd7"
                        : "3px solid transparent",
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        gap: 8,
                        alignItems: "center",
                        marginBottom: 4,
                      }}
                    >
                      <Pill tone={t.probe_depth > 0 ? "info" : "neutral"}>
                        {t.probe_depth > 0
                          ? `follow-up · depth ${t.probe_depth}`
                          : "planned"}
                      </Pill>
                      <span style={{ fontSize: 11.5, color: "var(--muted, #646b76)" }}>
                        {t.kind.replace(/_/g, " ").toLowerCase()}
                        {t.answer?.start_ms !== null && t.answer?.start_ms !== undefined
                          ? ` · ${fmtTime(t.answer.start_ms)}`
                          : ""}
                      </span>
                    </div>
                    <div style={{ fontSize: 13.5, fontWeight: 600 }}>{t.question}</div>
                    {t.intent && (
                      <div style={{ fontSize: 11.5, color: "var(--muted, #646b76)", marginTop: 2 }}>
                        asked to: {t.intent}
                      </div>
                    )}
                    {t.answer ? (
                      <div
                        style={{
                          fontSize: 13,
                          marginTop: 8,
                          paddingLeft: 10,
                          borderLeft: "2px solid var(--border, #e3e6ea)",
                        }}
                      >
                        {t.answer.text}
                      </div>
                    ) : (
                      <div
                        style={{ fontSize: 12.5, marginTop: 6, color: "var(--muted, #646b76)" }}
                      >
                        (no answer recorded)
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </Surface>
        </Stack>
      </div>
    </Stack>
  );
}
