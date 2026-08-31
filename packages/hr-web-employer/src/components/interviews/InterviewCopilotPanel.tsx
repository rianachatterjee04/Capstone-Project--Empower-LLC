"use client";
/**
 * Right-rail AI Copilot panel for the live interview room.
 *
 * Surfaces:
 *  - Live summary of the latest answer
 *  - Suggested follow-up questions (click to send into the question guide)
 *  - Scorecard mapping (which competencies this answer touched)
 *  - Missing evidence (which competencies still have no transcript proof)
 *  - Fairness flags on any free-text the interviewer types
 *
 * NOTE: nothing here generates answers for the candidate.  The Copilot only
 * assists the interviewer.
 */
import { useEffect, useState } from "react";
import { Action, Pill } from "@/components/ds";
import { IconSparkle } from "@/components/icons";
import { apiFetch, apiPost } from "@/lib/api";
import type { FairnessFlag, LiveContext } from "./types";

export function InterviewCopilotPanel({
  interviewId,
  refreshMs = 4000,
  onSuggestQuestion,
}: {
  interviewId: string;
  refreshMs?: number;
  onSuggestQuestion?: (q: { text: string; competency: string; rationale: string }) => void;
}) {
  const [ctx, setCtx] = useState<LiveContext | null>(null);
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState("");
  const [flags, setFlags] = useState<FairnessFlag[] | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function tick() {
      if (!alive) return;
      try {
        setLoading(true);
        const c = await apiFetch<LiveContext>(`/interview-ai/${interviewId}/live-context`);
        if (alive) setCtx(c);
      } catch { /* noop */ }
      finally {
        if (alive) {
          setLoading(false);
          timer = setTimeout(tick, refreshMs);
        }
      }
    }
    void tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [interviewId, refreshMs]);

  async function checkFairness() {
    if (!draft.trim()) return;
    const r = await apiPost<{ flags: FairnessFlag[]; summary: any }>(`/interview-ai/${interviewId}/assist`, {
      action: "check_question_fairness",
      text: draft,
    });
    setFlags(r.flags ?? []);
  }

  return (
    <div className="flex flex-col gap-4 h-full overflow-y-auto pr-1">
      {/* Live summary */}
      <Section title="Live summary" subtitle={ctx ? `${ctx.transcript_lines} lines captured` : "Waiting…"}>
        {ctx?.live_summary ? (
          <div className="text-sm text-body leading-relaxed">{ctx.live_summary}</div>
        ) : (
          <div className="text-xs text-muted italic">AI will summarise the candidate's answer in 1-2 sentences as the transcript fills in.</div>
        )}
      </Section>

      {/* Suggested follow-ups */}
      <Section title="Suggested follow-ups" subtitle="Click to add to the question guide">
        {ctx?.follow_up_questions && ctx.follow_up_questions.length > 0 ? (
          <ul className="space-y-2">
            {ctx.follow_up_questions.map((q, i) => (
              <li key={i} className="rounded-md border border-line bg-canvas p-2">
                <div className="text-sm text-ink">{q.text}</div>
                <div className="flex items-center justify-between mt-1">
                  <div className="text-2xs uppercase tracking-eyebrow text-muted">{q.competency} · {q.rationale}</div>
                  {onSuggestQuestion && (
                    <Action variant="subtle" size="sm" onClick={() => onSuggestQuestion(q)}>+ add</Action>
                  )}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-muted italic">No suggestions yet.</div>
        )}
      </Section>

      {/* Scorecard mapping */}
      <Section title="Scorecard mapping" subtitle="Which competencies just got signal">
        {ctx?.scorecard_mapping?.length ? (
          <ul className="space-y-1">
            {ctx.scorecard_mapping.map((m, i) => (
              <li key={i} className="flex items-center justify-between gap-2">
                <span className="text-sm text-ink truncate">{m.competency.replace(/_/g, " ")}</span>
                {m.evidence_detected ? (
                  <Pill tone="success">{m.matched_phrases.slice(0, 2).join(", ")}</Pill>
                ) : (
                  <Pill tone="neutral">no signal yet</Pill>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-xs text-muted italic">—</div>
        )}
      </Section>

      {/* Missing evidence */}
      {ctx?.missing_evidence?.length ? (
        <Section title="Missing evidence" subtitle="Cover these before time runs out">
          <ul className="space-y-1">
            {ctx.missing_evidence.map((i) => (
              <li key={i.id} className="rounded-md border border-warn-line bg-warn-bg p-2 text-xs text-warn-fg">
                <div className="font-medium">{i.title}</div>
                <div>{i.description}</div>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {/* Fairness check on a draft question */}
      <Section title="Fairness check" subtitle="Paste a question or note you're about to ask">
        <textarea
          rows={3}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder='e.g. "Are you planning a family soon?" — the AI will flag protected-class probes.'
          className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
        />
        <div className="mt-2 flex items-center gap-2">
          <Action variant="subtle" size="sm" onClick={checkFairness} disabled={!draft.trim()}>
            <IconSparkle /> Check
          </Action>
          {loading && <span className="text-2xs text-muted">refreshing…</span>}
        </div>
        {flags && (
          flags.length === 0 ? (
            <div className="mt-2 rounded-md border border-success-line bg-success-bg text-success-fg text-xs px-3 py-2">
              No fairness concerns detected.
            </div>
          ) : (
            <ul className="mt-2 space-y-1">
              {flags.map((f, i) => (
                <li key={i} className={`rounded-md border px-3 py-2 text-xs ${
                  f.severity === "block" ? "border-danger-line bg-danger-bg text-danger-fg" :
                  f.severity === "warn" ? "border-warn-line bg-warn-bg text-warn-fg" :
                  "border-info-line bg-info-bg text-info-fg"
                }`}>
                  <div className="font-semibold">{f.title}</div>
                  <div>{f.detail}</div>
                  {f.suggestion && <div className="mt-0.5 italic">{f.suggestion}</div>}
                </li>
              ))}
            </ul>
          )
        )}
      </Section>
    </div>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-surface p-3">
      <div className="flex items-baseline justify-between">
        <div className="fp-eyebrow">{title}</div>
        {subtitle && <div className="text-2xs text-muted">{subtitle}</div>}
      </div>
      <div className="mt-2">{children}</div>
    </div>
  );
}
