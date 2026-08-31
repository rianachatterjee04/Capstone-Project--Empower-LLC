"use client";
/**
 * Self-serve reference response page.
 *
 * What the reference lands on after clicking the invite link. No login
 * required — the URL token is the credential. They see the candidate +
 * role they're vouching for, the relationship and tenure the recruiter
 * captured, and a calm, paced question flow.
 *
 * For each question they can:
 *   - read the question (or have it read aloud)
 *   - choose written / audio / video capture
 *   - submit, see live confirmation, and move on
 *
 * Nothing is uploaded except the transcript + duration metadata.
 */
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { apiFetch, apiPost } from "@/lib/api";
import { Action, Pill, Surface, PageHeader, EmptyState } from "@/components/ds";
import { IconCheck, IconSparkle } from "@/components/icons";
import { VideoInterviewer, AnswerSubmission, InterviewMode } from "@/components/VideoInterviewer";

type SelfServePayload = {
  check: { id: string; candidate_name: string; job_title: string };
  reference: {
    id: string;
    name: string;
    relationship: string;
    title?: string;
    company?: string;
    tenure_months: number;
  };
  questions: { id: string; competency: string; question: string; rationale?: string }[];
  responses_submitted: number;
};

type SubmitResp = {
  question: { id: string };
  scored: { question_id: string; score: number };
  remaining: number;
};

export default function SelfServeRespondPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token ?? "";

  const [data, setData] = useState<SelfServePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [activeId, setActiveId] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [answered, setAnswered] = useState<Record<string, number>>({}); // qid → score
  const [defaultMode, setDefaultMode] = useState<InterviewMode>("audio");
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) return;
    let cancel = false;
    (async () => {
      try {
        const d = await apiFetch<SelfServePayload>(`/reference-checks/respond/${token}`);
        if (cancel) return;
        setData(d);
        const next = d.questions.find((_, i) => i >= d.responses_submitted);
        setActiveId(next?.id ?? d.questions[0]?.id ?? null);
      } catch (e: any) {
        if (!cancel) setError(e?.message ?? "This link is invalid or expired.");
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, [token]);

  const total = data?.questions.length ?? 0;
  const answeredCount = Object.keys(answered).length + (data?.responses_submitted ?? 0);

  async function submit(qid: string, a: AnswerSubmission) {
    try {
      const res = await apiPost<SubmitResp>(`/reference-checks/respond/${token}`, {
        question_id: qid,
        answer: a.transcript,
        mode: a.mode,
        duration_sec: a.duration_sec,
        words_per_minute: a.words_per_minute,
        has_face: a.has_face,
        media_meta: a.media_meta,
      });
      setAnswered((prev) => ({ ...prev, [qid]: res.scored.score }));
      if (data) {
        const next = data.questions.find((q) => q.id !== qid && !(answered[q.id] !== undefined));
        if (next) {
          setActiveId(next.id);
        } else {
          setDone(true);
          setActiveId(null);
        }
      }
    } catch (e: any) {
      setError(e?.message ?? "Could not submit. Please try again.");
    }
  }

  function submitWritten(qid: string) {
    const v = (drafts[qid] ?? "").trim();
    if (!v) return;
    return submit(qid, {
      transcript: v,
      mode: "written",
      duration_sec: 0,
      words_per_minute: 0,
      has_face: false,
      media_meta: { kind: "written" },
    });
  }

  if (loading) {
    return (
      <div className="space-y-4">
        <PageHeader eyebrow="Reference response" title="Loading…" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-4">
        <PageHeader eyebrow="Reference response" title="We can't load this reference" />
        <Surface>
          <EmptyState
            title="Link not available"
            description={error ?? "This invite link may have expired or already been used."}
          />
        </Surface>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={`${data.reference.relationship.toUpperCase()} REFERENCE FOR`}
        title={data.check.candidate_name}
        subtitle={`Role under consideration: ${data.check.job_title}. Thank you for taking 10 minutes — your candor matters. You may answer by typing, speaking, or video. Recordings stay in your browser; only the transcript + duration is sent.`}
      />

      <Surface pad="sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="fp-eyebrow">Your relationship to {data.check.candidate_name}</div>
            <div className="text-sm font-medium text-ink">
              {data.reference.name}
              {data.reference.title ? ` · ${data.reference.title}` : ""}
              {data.reference.company ? ` · ${data.reference.company}` : ""}
            </div>
            <div className="text-xs text-muted">
              {data.reference.relationship} · worked together {data.reference.tenure_months}mo
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="text-2xs uppercase tracking-eyebrow text-muted mr-1">Default answer mode</div>
            {(["audio", "video", "written"] as InterviewMode[]).map((m) => (
              <Action key={m} size="sm" variant={defaultMode === m ? "primary" : "subtle"} onClick={() => setDefaultMode(m)}>
                {m === "audio" ? "Voice" : m === "video" ? "Video" : "Text"}
              </Action>
            ))}
          </div>
        </div>
        <div className="mt-3">
          <div className="h-1.5 w-full rounded-full bg-sunken overflow-hidden">
            <div className="h-full bg-ink/80" style={{ width: `${total > 0 ? (answeredCount / total) * 100 : 0}%` }} />
          </div>
          <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1.5">
            {answeredCount} of {total} answered
          </div>
        </div>
      </Surface>

      {done ? (
        <Surface>
          <EmptyState
            title="Thank you — your reference has been submitted."
            description={`Your responses are confidential and will be reviewed alongside the other references for ${data.check.candidate_name}.`}
          />
        </Surface>
      ) : (
        <div className="space-y-4">
          {data.questions.map((q, idx) => {
            const isAnswered = answered[q.id] !== undefined;
            const isActive = activeId === q.id;
            return (
              <Surface key={q.id} pad="md">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="fp-eyebrow">Q{idx + 1} · {q.competency.replace(/_/g, " ")}</div>
                    <div className="text-sm font-semibold text-ink mt-0.5">{q.question}</div>
                    {q.rationale && <div className="text-xs text-muted mt-1">{q.rationale}</div>}
                  </div>
                  <div className="flex items-center gap-2">
                    {isAnswered && <Pill tone="success">submitted</Pill>}
                    {!isAnswered && !isActive && (
                      <Action variant="subtle" size="sm" onClick={() => setActiveId(q.id)}>Answer this one</Action>
                    )}
                  </div>
                </div>

                {isAnswered && (
                  <div className="mt-3 rounded-md border border-line bg-canvas p-3 text-xs text-muted">
                    Thank you — your answer has been captured.
                  </div>
                )}

                {!isAnswered && isActive && (
                  <div className="mt-3">
                    <PerQuestionCapture
                      question={q}
                      defaultMode={defaultMode}
                      writtenValue={drafts[q.id] ?? ""}
                      onWrittenChange={(v) => setDrafts((p) => ({ ...p, [q.id]: v }))}
                      onSubmit={(a) => submit(q.id, a)}
                      onSubmitWritten={() => submitWritten(q.id)}
                    />
                  </div>
                )}
              </Surface>
            );
          })}
        </div>
      )}

      <div className="text-2xs uppercase tracking-eyebrow text-muted text-center">
        Foundry People · AI-assisted reference check · responses are reviewed by a human recruiter
      </div>
    </div>
  );
}

function PerQuestionCapture({
  question,
  defaultMode,
  writtenValue,
  onWrittenChange,
  onSubmit,
  onSubmitWritten,
}: {
  question: { question: string; rationale?: string };
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
          <Action key={m} variant={mode === m ? "primary" : "subtle"} size="sm" onClick={() => setMode(m)}>
            {m === "video" ? "Video" : m === "audio" ? "Voice" : "Text"}
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
              placeholder="Share a concrete example. Specific is better than safe."
              className="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:bg-surface"
            />
          </div>
          <div className="flex items-center justify-end">
            <Action variant="primary" onClick={onSubmitWritten} disabled={!writtenValue.trim()}>
              <IconCheck /> Submit answer
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
