"use client";
/**
 * Pulse — the employee side of engagement surveys. Answer whatever pulse /
 * eNPS surveys are currently open. Aggregate results are HR-only (k-anonymous),
 * so this surface is purely "have your say". Backend: /engagement.
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState } from "@/components/ds";

type Question = { id: string; text: string; kind: string; category: string | null; options: string[] };
type SurveyMeta = { id: string; title: string; type: string; status: string; anonymous: boolean; response_count: number };
type Survey = SurveyMeta & { questions: Question[] };

export default function PulsePage() {
  const listQ = useQuery({ queryKey: ["engagement-surveys"], queryFn: () => apiFetch<{ items: SurveyMeta[] }>("/engagement/surveys"), refetchInterval: 90_000 });
  const open = (listQ.data?.items ?? []).filter((s) => s.status === "open");

  const [surveyId, setSurveyId] = useState<string>("");
  useEffect(() => {
    if (!surveyId && open.length) setSurveyId(open[0].id);
  }, [open, surveyId]);

  const surveyQ = useQuery({
    queryKey: ["engagement-survey", surveyId],
    queryFn: () => apiFetch<Survey>(`/engagement/surveys/${surveyId}`),
    enabled: !!surveyId,
  });
  const survey = surveyQ.data;

  const [answers, setAnswers] = useState<Record<string, number | string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [err, setErr] = useState<string | null>(null);

  // reset answers when switching surveys
  useEffect(() => { setAnswers({}); setErr(null); }, [surveyId]);

  async function submit() {
    if (!surveyId || Object.keys(answers).length === 0) return;
    setSubmitting(true);
    setErr(null);
    try {
      await apiPost(`/engagement/surveys/${surveyId}/responses`, { answers });
      setDone((d) => ({ ...d, [surveyId]: true }));
      setAnswers({});
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Growth"
        title="Pulse"
        subtitle="Quick, honest check-ins. Your individual answers stay confidential — only aggregate trends are shared with HR."
      />

      {listQ.isLoading ? (
        <Surface><EmptyState title="Loading…" /></Surface>
      ) : open.length === 0 ? (
        <Surface><EmptyState title="No open surveys" description="When a pulse or engagement survey opens, you'll be able to answer it here." /></Surface>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-5">
          {/* Open surveys */}
          <Surface pad="sm">
            <div className="fp-eyebrow mb-2">Open surveys</div>
            <div className="space-y-1.5">
              {open.map((s) => (
                <button key={s.id} onClick={() => setSurveyId(s.id)}
                  className={`w-full text-left rounded-md px-3 py-2 border text-sm ${surveyId === s.id ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>
                  <div className="font-medium">{s.title}</div>
                  <div className="text-xs opacity-80 flex items-center gap-1.5">
                    {s.type}{s.anonymous ? " · anonymous" : ""}{done[s.id] ? " · done" : ""}
                  </div>
                </button>
              ))}
            </div>
          </Surface>

          {/* Questionnaire */}
          <div>
            {!survey ? (
              <Surface><EmptyState title="Loading survey…" /></Surface>
            ) : done[survey.id] ? (
              <Surface>
                <SectionTitle eyebrow="Thank you" title="Your response was recorded" />
                <p className="mt-3 text-sm text-muted">Thanks for taking the time. {survey.anonymous ? "Your answers are anonymous." : ""} Results roll up to HR once enough people respond.</p>
              </Surface>
            ) : (
              <Surface>
                <div className="flex items-center justify-between gap-3">
                  <SectionTitle eyebrow={survey.type} title={survey.title} />
                  {survey.anonymous && <Pill tone="info">anonymous</Pill>}
                </div>
                <div className="mt-4 space-y-5">
                  {survey.questions.map((qn, i) => (
                    <div key={qn.id}>
                      <div className="text-sm font-medium text-ink">{i + 1}. {qn.text}</div>
                      <div className="mt-2">
                        <QuestionInput q={qn} value={answers[qn.id]} onChange={(v) => setAnswers((a) => ({ ...a, [qn.id]: v }))} />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="mt-5 flex items-center gap-3">
                  <Action variant="primary" onClick={submit} disabled={submitting || Object.keys(answers).length === 0}>
                    {submitting ? "Submitting…" : "Submit response"}
                  </Action>
                  {err && <span className="text-sm text-danger-fg">{err}</span>}
                </div>
              </Surface>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function QuestionInput({ q, value, onChange }: { q: Question; value: number | string | undefined; onChange: (v: number | string) => void }) {
  if (q.kind === "open") {
    return (
      <textarea rows={3} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)}
        placeholder="Your answer (optional)"
        className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink outline-none focus:bg-surface" />
    );
  }
  if (q.kind === "multi") {
    return (
      <div className="flex flex-wrap gap-1.5">
        {q.options.map((o) => (
          <button key={o} onClick={() => onChange(o)}
            className={`text-sm rounded-md px-3 py-1.5 border ${value === o ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>
            {o}
          </button>
        ))}
      </div>
    );
  }
  // scale_1_5, enps_0_10, nps → numeric scale buttons
  const isEnps = q.kind === "enps_0_10" || q.kind === "nps";
  const scale = isEnps ? Array.from({ length: 11 }, (_, i) => i) : [1, 2, 3, 4, 5];
  return (
    <div className="flex flex-wrap gap-1.5">
      {scale.map((n) => (
        <button key={n} onClick={() => onChange(n)}
          className={`h-9 w-9 rounded-md border text-sm font-medium tabular-nums ${value === n ? "bg-accent text-accent-fg border-accent" : "bg-surface border-line text-body hover:bg-sunken"}`}>
          {n}
        </button>
      ))}
      <span className="self-center ml-1 text-xs text-muted">{isEnps ? "0 = not likely · 10 = very likely" : "1 = disagree · 5 = agree"}</span>
    </div>
  );
}
