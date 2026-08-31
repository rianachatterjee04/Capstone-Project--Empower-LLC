"use client";

/**
 * The candidate's side of the interview.
 *
 * WHAT THE CANDIDATE MUST NOT SEE
 * Any signal about how they are doing. That is now enforced at the API, not
 * here: `/next` and `/answer` serialise a candidate-safe payload built from an
 * allowlist, so the gap analysis, the competency, the probe depth and the
 * evidence count never reach this process at all.
 *
 * The earlier version of this page received all of that and ignored it in
 * React, which is not a boundary -- anyone with DevTools could read the
 * scoring strategy and game the rest of the interview. This page is now
 * simply not told.
 *
 * WHAT IT MUST SHOW
 * Consent, in plain words, before anything starts. Where they are. That a
 * follow-up is a follow-up rather than a new topic -- being asked "what didn't
 * go well?" is much less unnerving when you can see it is a deeper question
 * about what you just said. And an honest recording indicator: if nothing is
 * being captured, it says so rather than showing a decorative red dot.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch, apiPost, authHeaders } from "@/lib/api";
import { Surface, Stack, Pill, EmptyState } from "@/components/ds";
import { env } from "@/lib/env";
import {
  InterviewCapture,
  detectSupport,
  uploadPart,
  type CaptureState,
  type CaptureSupport,
} from "@/lib/interviewCapture";

type Question = {
  id: string;
  text: string;
  sequence: number;
  is_followup: boolean;
};

type NextResponse =
  | { finished: true; message?: string }
  | { finished: false; waiting: true }
  | { finished: false; question: Question };

// The API sends a boolean. It deliberately does not send WHICH kind of
// follow-up: "this is a deeper question about what you just said" helps a
// candidate; "this is FOLLOWUP_OWNERSHIP at depth 2" tells them what the
// system thinks is missing.

export default function LiveInterviewPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;

  const [phase, setPhase] =
    useState<"consent" | "check" | "live" | "saving" | "done">("consent");
  const [question, setQuestion] = useState<Question | null>(null);
  const [answer, setAnswer] = useState("");
  const [asked, setAsked] = useState(0);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [startedAt] = useState(() => Date.now());
  const box = useRef<HTMLTextAreaElement | null>(null);
  const answerStartedAt = useRef<number | null>(null);

  // --- real capture ------------------------------------------------------
  const [support, setSupport] = useState<CaptureSupport | null>(null);
  const [capture, setCapture] = useState<CaptureState>("IDLE");
  const [captureNote, setCaptureNote] = useState<string>("");
  const [partsUploaded, setPartsUploaded] = useState(0);
  const cap = useRef<InterviewCapture | null>(null);
  const video = useRef<HTMLVideoElement | null>(null);

  useEffect(() => {
    setSupport(detectSupport());
  }, []);

  // The recorder's own clock. Answer offsets come from HERE rather than from
  // page load, because the server verifies them against the media duration.
  const recorderNow = useCallback(
    () => cap.current?.now() ?? Date.now() - startedAt,
    [startedAt],
  );

  // A candidate closing the tab while a part is still uploading loses that
  // part. The browser's own prompt is the only thing that can stop them, and
  // it is only armed while something is genuinely in flight.
  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!cap.current?.pendingUploads) return;
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, []);

  const advance = useCallback(
    async (attempt: string | null) => {
      setBusy(true);
      try {
        const q = await apiFetch<NextResponse>(
          `/interview-v2/${id}/next${attempt ? `?attempt_id=${attempt}` : ""}`,
        );
        if ("finished" in q && q.finished) {
          // AWAIT THE FLUSH. `stop()` used to be fire-and-forget, so the
          // candidate's answer to the FINAL question was still uploading when
          // this screen changed — and closing the tab lost it silently. The
          // candidate is told what is happening rather than being shown a
          // finished page over an unfinished upload.
          setQuestion(null);
          setPhase("saving");
          try {
            await cap.current?.stop();
          } catch {
            /* a capture that never started has nothing to flush */
          }
          // SEAL: tell the server how many parts this browser produced.
          //
          // A part that never reached the server leaves no trace there, so
          // this is the only moment anyone can say "that was all of them".
          // Without it the recording stays CAPTURING and the recruiter is
          // told the media may be incomplete -- which is the honest answer,
          // and the reason this is sent rather than assumed.
          const produced = cap.current?.partsProduced ?? 0;
          const lost = cap.current?.lostParts ?? [];
          if (lost.length) {
            // Say it plainly. The alternative is a "done" screen over a
            // recording the server does not fully have.
            setCaptureNote(
              `${lost.length} of ${produced} recorded segment` +
                `${lost.length === 1 ? "" : "s"} could not be uploaded after ` +
                `retrying. Your answers were saved as text, and the recruiter ` +
                `will see the video marked as incomplete.`,
            );
          }
          if (produced > 0) {
            try {
              await apiPost(`/interview-v2/${id}/recording/seal`, {
                parts_expected: produced,
              });
            } catch (e: any) {
              setCaptureNote(
                `the recording was uploaded but could not be sealed: ` +
                  `${e?.message ?? e}. A recruiter will see it marked as ` +
                  `possibly incomplete.`,
              );
            }
          }
          setPhase("done");
        } else if ("question" in q) {
          setQuestion(q.question);
          setAnswer("");
          setAsked((n) => n + 1);
          setTimeout(() => box.current?.focus(), 60);
        }
      } catch (e: any) {
        setErr(e?.message ?? String(e));
      } finally {
        setBusy(false);
      }
    },
    [id],
  );

  const begin = useCallback(async () => {
    setBusy(true);
    setErr(null);
    try {
      const started = await apiPost<{ attempt_id: string }>(
        `/interview-v2/${id}/start`,
        {},
      );
      setAttemptId(started.attempt_id);

      // Start recording BEFORE the first question, so the recorder clock and
      // the interview share an origin. Capture failing does not stop the
      // interview -- it changes what we tell the candidate is happening.
      const c = new InterviewCapture({
        onState: (s, detail) => {
          setCapture(s);
          setCaptureNote(detail ?? "");
        },
        onPart: async (blob, partNumber, offsetMs, durationMs) => {
          // THE UPLOAD HAS TO CARRY CREDENTIALS.
          // This passed no headers, so every recorded part was POSTed
          // unauthenticated and refused. The failure was visible on this
          // page and invisible everywhere else, because reaching it needs a
          // working camera.
          //
          // A FAILURE HERE MUST PROPAGATE. Catching it here made every upload
          // look successful to the capture layer, which is what its retry and
          // its lost-part accounting are driven by -- a swallowed rejection
          // disabled both, silently. The blip case is handled by the retry;
          // a part that is genuinely lost is reported at seal time.
          await uploadPart(env.apiBaseUrl, String(id), blob, {
            partNumber,
            offsetMs,
            durationMs,
            attemptId: started.attempt_id,
            headers: await authHeaders(),
          });
          setPartsUploaded((n) => n + 1);
        },
        onTranscript: () => {},
      });
      cap.current = c;
      await c.start({ video: true, audio: true });
      if (video.current && (c as any).stream) {
        video.current.srcObject = (c as any).stream;
      }

      setPhase("live");
      await advance(started.attempt_id);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setBusy(false);
    }
  }, [id, advance]);

  const submit = useCallback(async () => {
    if (!question || answer.trim().length === 0) return;
    setBusy(true);
    try {
      // Offsets come from the RECORDER clock, not from page load. That is
      // what makes them checkable against the media's measured duration
      // rather than merely being timestamps of button presses.
      const elapsed = recorderNow();
      const started = answerStartedAt.current ?? Math.max(0, elapsed - 1000);

      const res = await apiPost<{ answer_id: string }>(
        `/interview-v2/${id}/answer`,
        {
          question_id: question.id,
          answer_text: answer,
          attempt_id: attemptId,
          recording_start_ms: Math.round(started),
          recording_end_ms: Math.round(elapsed),
        },
      );

      // Hand over whatever the browser transcribed while they were answering,
      // bound to this answer and to the current recording part.
      const heard = cap.current?.takeTranscript() ?? [];
      if (heard.length) {
        try {
          await apiPost(`/interview-v2/${id}/transcript`, {
            results: heard,
            attempt_id: attemptId,
            recording_part: 1,
            answer_id: res.answer_id,
          });
        } catch {
          /* the answer is stored; a transcript gap is reported by /alignment */
        }
      }

      answerStartedAt.current = recorderNow();
      await advance(attemptId);
    } catch (e: any) {
      setErr(e?.message ?? String(e));
      setBusy(false);
    }
    // recorderNow, not startedAt: the callback never reads startedAt directly,
    // it reads it through recorderNow, whose only dependency is startedAt. So
    // recorderNow already changes exactly when startedAt does. This is the
    // capture path, and a genuine exhaustive-deps warning in it should not have
    // to compete with a benign one for attention.
  }, [question, answer, id, attemptId, advance, recorderNow]);

  // ---- consent ----------------------------------------------------------
  if (phase === "consent")
    return (
      <main style={{ maxWidth: 640, margin: "48px auto", padding: "0 20px" }}>
        <Stack gap={4}>
          <h1 style={{ fontSize: 24, fontWeight: 650, margin: 0 }}>
            Before we start
          </h1>
          <Surface>
            <p style={{ marginTop: 0, fontSize: 14.5, lineHeight: 1.6 }}>
              This interview is conducted by an AI interviewer. It will ask you
              about your own experience and will follow up on what you say.
            </p>
            <ul style={{ fontSize: 14, lineHeight: 1.7, paddingLeft: 20 }}>
              <li>Your answers are recorded and transcribed.</li>
              <li>
                They are assessed against the competencies for this role.{" "}
                <strong>A human recruiter makes the hiring decision</strong> —
                this is not an automated hire or reject.
              </li>
              <li>
                The recruiter can see exactly which of your words supported each
                part of the assessment.
              </li>
              <li>
                You are not assessed on appearance, accent, how quickly you
                speak, or anything other than what you say about your work.
              </li>
              <li>You can stop at any time.</li>
            </ul>
            {err && (
              <div
                style={{
                  background: "#fdeaea", color: "#a52222", padding: "10px 14px",
                  borderRadius: 8, fontSize: 13.5, marginBottom: 12,
                }}
              >
                {err}
              </div>
            )}
            <button
              onClick={() => setPhase("check")}
              disabled={busy}
              style={{
                background: "#2f5bd7", color: "#fff", border: "none",
                borderRadius: 8, padding: "11px 20px", fontSize: 15,
                fontWeight: 600, cursor: "pointer",
              }}
            >
              I understand — continue
            </button>
          </Surface>
        </Stack>
      </main>
    );

  // ---- device check -----------------------------------------------------
  if (phase === "check")
    return (
      <main style={{ maxWidth: 640, margin: "48px auto", padding: "0 20px" }}>
        <Stack gap={4}>
          <h1 style={{ fontSize: 24, fontWeight: 650, margin: 0 }}>
            Camera and microphone
          </h1>
          <Surface>
            {support === null ? (
              <div style={{ fontSize: 13.5, color: "#646b76" }}>
                Checking your camera and microphone…
              </div>
            ) : support.getUserMedia && support.mediaRecorder ? (
              <div
                style={{
                  background: "#e6f4ec", border: "1px solid #16794a22",
                  borderRadius: 10, padding: 18, fontSize: 13.5,
                  color: "#16794a", marginBottom: 16,
                }}
              >
                <div style={{ fontWeight: 650, marginBottom: 6 }}>
                  This interview will be recorded
                </div>
                <span style={{ color: "#3a4a42" }}>
                  Your browser will ask for camera and microphone permission
                  when you start. Video and audio are recorded and stored.
                  {support.speechRecognition
                    ? " Your speech is also transcribed live in this browser."
                    : " This browser cannot transcribe live, so the recruiter"
                      + " will see the recording and your typed answers."}
                </span>
              </div>
            ) : (
              <div
                style={{
                  background: "#fdf3e0", border: "1px solid #8a5a0022",
                  borderRadius: 10, padding: 18, fontSize: 13.5,
                  color: "#8a5a00", marginBottom: 16,
                }}
              >
                <div style={{ fontWeight: 650, marginBottom: 6 }}>
                  This browser cannot record
                </div>
                <span style={{ color: "#4a4133" }}>
                  The interview will still run and your answers are still
                  assessed — there will simply be no recording. Nothing here
                  will pretend otherwise.
                </span>
              </div>
            )}

            <p style={{ fontSize: 13.5, color: "#646b76" }}>
              You will be asked roughly ten questions. Some of them will be
              follow-ups on your own answers, and those are marked as such.
              Take your time — there is no timer on any individual question.
            </p>
            {err && (
              <div
                style={{
                  background: "#fdeaea", color: "#a52222", padding: "10px 14px",
                  borderRadius: 8, fontSize: 13.5, marginBottom: 12,
                }}
              >
                {err}
              </div>
            )}
            <button
              onClick={begin}
              disabled={busy}
              style={{
                background: "#2f5bd7", color: "#fff", border: "none",
                borderRadius: 8, padding: "11px 20px", fontSize: 15,
                fontWeight: 600, cursor: busy ? "not-allowed" : "pointer",
                opacity: busy ? 0.6 : 1,
              }}
            >
              {busy ? "Starting…" : "Start the interview"}
            </button>
          </Surface>
        </Stack>
      </main>
    );

  // ---- finished ---------------------------------------------------------
  if (phase === "saving")
    return (
      <main style={{ maxWidth: 640, margin: "48px auto", padding: "0 20px" }}>
        <Surface>
          <EmptyState
            title="Saving your recording…"
            description={
              "Your answers are already submitted. This is the last part of " +
              "the recording being uploaded — it only takes a moment. Please " +
              "keep this tab open."
            }
          />
        </Surface>
      </main>
    );

  if (phase === "done")
    return (
      <main style={{ maxWidth: 640, margin: "48px auto", padding: "0 20px" }}>
        <Surface>
          <EmptyState
            title="That's everything — thank you."
            description={
              `You answered ${asked} question${asked === 1 ? "" : "s"}. A ` +
              `recruiter will review your answers alongside the evidence for ` +
              `each competency, and will be in touch. Nothing was decided ` +
              `automatically.`
            }
          />
        </Surface>
      </main>
    );

  // ---- live -------------------------------------------------------------
  const isFollowup = question?.is_followup ?? false;

  return (
    <main style={{ maxWidth: 720, margin: "36px auto", padding: "0 20px" }}>
      <div
        style={{
          display: "flex", justifyContent: "space-between",
          alignItems: "center", marginBottom: 16,
        }}
      >
        <span style={{ fontSize: 13, color: "#646b76" }}>
          Question {asked}
        </span>
        {/* The indicator reflects the RECORDER's actual state. A red dot over
            a recorder that is not running misleads a candidate about the very
            thing they consented to. */}
        {capture === "RECORDING" ? (
          <span style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span
              style={{
                width: 9, height: 9, borderRadius: "50%",
                background: "#c0392b", display: "inline-block",
              }}
            />
            <span style={{ fontSize: 12.5, color: "#646b76" }}>
              recording{partsUploaded > 0 ? ` · ${partsUploaded} saved` : ""}
            </span>
          </span>
        ) : (
          <Pill tone="warn">
            {capture === "PERMISSION_DENIED"
              ? "not recording — permission declined"
              : capture === "UNSUPPORTED"
                ? "not recording — unsupported browser"
                : capture === "DEVICE_LOST"
                  ? "recording stopped — camera or microphone went away"
                  : capture === "ERROR"
                    ? "recording stopped — something went wrong"
                    : "not recording"}
          </Pill>
        )}
      </div>

      <Surface>
        {capture === "RECORDING" && (
          <video
            ref={video}
            autoPlay
            muted
            playsInline
            style={{
              width: 168, borderRadius: 8, float: "right",
              marginLeft: 14, marginBottom: 10, background: "#000",
            }}
          />
        )}
        {captureNote && (
          <div
            style={{
              background: "#fdf3e0", color: "#8a5a00", padding: "8px 12px",
              borderRadius: 8, fontSize: 12.5, marginBottom: 12,
            }}
          >
            {captureNote}
          </div>
        )}
        {isFollowup && (
          <div style={{ marginBottom: 10 }}>
            <Pill tone="info">
              Following up on what you just said
            </Pill>
          </div>
        )}

        <p
          style={{
            fontSize: 18, lineHeight: 1.55, fontWeight: 550,
            marginTop: 0, marginBottom: 18,
          }}
        >
          {question?.text ?? "…"}
        </p>

        <textarea
          ref={box}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          placeholder="Take your time. Specifics help — what you did, what happened, what the numbers were."
          rows={9}
          style={{
            width: "100%", fontSize: 15, lineHeight: 1.6, padding: 12,
            borderRadius: 8, border: "1px solid #e3e6ea", fontFamily: "inherit",
            resize: "vertical",
          }}
        />

        {err && (
          <div
            style={{
              background: "#fdeaea", color: "#a52222", padding: "10px 14px",
              borderRadius: 8, fontSize: 13.5, marginTop: 12,
            }}
          >
            {err}
          </div>
        )}

        <div
          style={{
            display: "flex", justifyContent: "space-between",
            alignItems: "center", marginTop: 14,
          }}
        >
          <span style={{ fontSize: 12.5, color: "#646b76" }}>
            {answer.trim().split(/\s+/).filter(Boolean).length} words
          </span>
          <button
            onClick={submit}
            disabled={busy || answer.trim().length === 0}
            style={{
              background: "#2f5bd7", color: "#fff", border: "none",
              borderRadius: 8, padding: "10px 20px", fontSize: 15,
              fontWeight: 600,
              cursor: busy || !answer.trim() ? "not-allowed" : "pointer",
              opacity: busy || !answer.trim() ? 0.55 : 1,
            }}
          >
            {busy ? "…" : "Submit answer"}
          </button>
        </div>
      </Surface>

      <p
        style={{
          fontSize: 12.5, color: "#646b76", marginTop: 14, textAlign: "center",
        }}
      >
        You are not being scored on how you write. A recruiter reads your actual
        words.
      </p>
    </main>
  );
}
