"use client";
/**
 * ScorecardPanel — per-interviewer scorecard with AI-drafted ratings and
 * evidence chips.  Renders inline beside the transcript so the interviewer
 * can rate as they listen.
 */
import { useState } from "react";
import { Action, Pill } from "@/components/ds";
import { IconCheck, IconSparkle } from "@/components/icons";
import { apiPatch } from "@/lib/api";
import type { CompetencyScore, FairnessFlag, RATING_LABEL, Scorecard } from "./types";

const LABELS = ["No hire", "Lean no hire", "Lean hire", "Hire", "Strong hire"];

export function ScorecardPanel({
  interviewId,
  scorecard,
  competencies,
  onChange,
  onDraftFromTranscript,
  onSubmit,
}: {
  interviewId: string;
  scorecard: Scorecard | null;
  competencies: string[];
  onChange: () => void;
  onDraftFromTranscript: () => void;
  onSubmit: (overall: number, rec: string, conf: number) => void;
}) {
  const [overall, setOverall] = useState<number>(2);
  const [rec, setRec] = useState<string>("hire");
  const [conf, setConf] = useState<number>(3);

  // The route is PATCH /interviews/{id}/scorecard/{scorecard_id}. This sent
  // POST -- in a function called patchRow -- so it was rejected with 405 before
  // the handler ever ran, and every competency a recruiter typed was discarded.
  async function patchRow(competency: string, fields: Partial<CompetencyScore>) {
    if (!scorecard) return;
    await apiPatch(`/interviews/${interviewId}/scorecard/${scorecard.id}`, {
      competency,
      ...fields,
    });
    onChange();
  }

  if (!scorecard) {
    return <div className="text-sm text-muted">No scorecard yet.</div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <div className="fp-eyebrow">Scorecard</div>
          <div className="text-sm font-semibold text-ink">{scorecard.interviewer_name}</div>
        </div>
        <div className="flex items-center gap-2">
          <Action variant="subtle" size="sm" onClick={onDraftFromTranscript}>
            <IconSparkle /> AI draft from transcript
          </Action>
        </div>
      </div>

      <ul className="space-y-2">
        {(scorecard.competencies ?? []).map((c) => (
          <RowEditor key={c.competency} row={c} onSave={(fields) => patchRow(c.competency, fields)} />
        ))}
      </ul>

      {/* Submit block */}
      <div className="rounded-md border border-line bg-canvas p-3 space-y-2">
        <div className="fp-eyebrow">Overall</div>
        <div className="flex flex-wrap gap-1">
          {[0, 1, 2, 3, 4].map((r) => (
            <Action key={r} size="sm" variant={overall === r ? "primary" : "subtle"} onClick={() => setOverall(r)}>
              {LABELS[r]}
            </Action>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-2xs uppercase tracking-eyebrow text-muted">Recommendation</div>
          {["hire", "no_hire", "unsure"].map((x) => (
            <Action key={x} size="sm" variant={rec === x ? "primary" : "subtle"} onClick={() => setRec(x)}>{x.replace(/_/g, " ")}</Action>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-2xs uppercase tracking-eyebrow text-muted">Confidence</div>
          {[1, 2, 3, 4, 5].map((n) => (
            <Action key={n} size="sm" variant={conf === n ? "primary" : "subtle"} onClick={() => setConf(n)}>{n}</Action>
          ))}
        </div>
        <Action variant="primary" onClick={() => onSubmit(overall, rec, conf)}>
          <IconCheck /> Submit scorecard
        </Action>
        {scorecard.status === "submitted" && (
          <div className="text-2xs uppercase tracking-eyebrow text-success-fg">submitted</div>
        )}
      </div>
    </div>
  );
}

function RowEditor({ row, onSave }: { row: CompetencyScore; onSave: (fields: Partial<CompetencyScore>) => void }) {
  const [notes, setNotes] = useState(row.notes ?? "");
  const [rating, setRating] = useState<number | null>(row.rating ?? null);
  const flags = row.fairness_flags ?? [];
  return (
    <li className="rounded-md border border-line bg-canvas p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm font-medium text-ink">{row.competency.replace(/_/g, " ")}</div>
        <div className="flex items-center gap-2">
          {row.ai_suggested_rating !== null && row.ai_suggested_rating !== undefined && (
            <Pill tone="info">AI: {LABELS[row.ai_suggested_rating]}</Pill>
          )}
          {row.final_rating !== null && row.final_rating !== undefined && (
            <Pill tone={row.final_rating >= 3 ? "success" : row.final_rating >= 2 ? "warn" : "danger"}>
              {LABELS[row.final_rating]}
            </Pill>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {[0, 1, 2, 3, 4].map((r) => (
          <Action key={r} size="sm" variant={rating === r ? "primary" : "subtle"} onClick={() => { setRating(r); onSave({ rating: r }); }}>
            {LABELS[r]}
          </Action>
        ))}
      </div>
      <textarea
        rows={2}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={() => onSave({ notes })}
        placeholder="Evidence + observation (cite transcript)"
        className="mt-2 w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink"
      />
      {(row.evidence_snippets ?? []).length > 0 && (
        <div className="mt-1 text-2xs text-muted">
          Evidence: {row.evidence_snippets.slice(0, 2).map((s, i) => <span key={i} className="italic">"{s}" </span>)}
        </div>
      )}
      {flags.length > 0 && (
        <ul className="mt-2 space-y-1">
          {flags.map((f: FairnessFlag, i: number) => (
            <li key={i} className="rounded-md border border-warn-line bg-warn-bg text-warn-fg text-2xs px-2 py-1">
              ⚠ {f.title}: {f.detail}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
