"use client";
import { Action, Pill } from "@/components/ds";
import { IconCheck } from "@/components/icons";
import type { InterviewQuestion } from "./types";

/**
 * Renders the structured question list with "Mark asked" affordance and
 * progress indicator.  Used in both the prep page and the live room.
 */
export function QuestionGuide({
  questions,
  onMarkAsked,
}: {
  questions: InterviewQuestion[];
  onMarkAsked?: (q: InterviewQuestion) => void;
}) {
  const asked = questions.filter((q) => q.asked).length;
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="fp-eyebrow">Question guide</div>
          <div className="text-sm font-semibold text-ink">{asked} / {questions.length} asked</div>
        </div>
        <div className="h-1.5 w-32 rounded-full bg-sunken overflow-hidden">
          <div className="h-full bg-ink/80" style={{ width: `${(asked / Math.max(questions.length, 1)) * 100}%` }} />
        </div>
      </div>
      <ul className="space-y-2">
        {questions.map((q, i) => (
          <li
            key={q.id}
            className={`rounded-md border border-line p-3 ${q.asked ? "bg-sunken/50 opacity-70" : "bg-canvas"}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="text-2xs uppercase tracking-eyebrow text-muted">
                  Q{i + 1} · {q.competency.replace(/_/g, " ")}
                  {q.required && <span className="ml-2">· required</span>}
                  {q.generated_by_ai && <span className="ml-2">· AI</span>}
                </div>
                <div className={`text-sm mt-0.5 ${q.asked ? "line-through text-muted" : "text-ink"}`}>
                  {q.text}
                </div>
                {q.rationale && (
                  <div className="text-2xs text-muted mt-1">{q.rationale}</div>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {q.asked ? (
                  <Pill tone="success"><IconCheck /> asked</Pill>
                ) : onMarkAsked ? (
                  <Action variant="subtle" size="sm" onClick={() => onMarkAsked(q)}>Mark asked</Action>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
