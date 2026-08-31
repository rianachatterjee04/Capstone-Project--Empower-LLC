"use client";
import { Pill, Surface } from "@/components/ds";
import type { PostSummary } from "./types";

const REC_TONE: Record<string, "success" | "warn" | "info" | "danger"> = {
  advance: "success", advance_with_caveats: "warn", hold: "info", decline: "danger",
};

export function PostInterviewSummary({ s }: { s: PostSummary }) {
  if (!s.ready) {
    return (
      <Surface pad="md">
        <div className="fp-eyebrow">Post-interview summary</div>
        <div className="mt-2 text-sm text-muted">{s.narrative}</div>
      </Surface>
    );
  }
  return (
    <Surface pad="lg">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="fp-eyebrow">Post-interview summary</div>
          <div className="text-xl font-semibold text-ink mt-1">{s.candidate_name}</div>
          <div className="text-sm text-muted">{s.job_title}</div>
        </div>
        <div className="text-right">
          <div className="text-4xl font-bold text-ink tabular-nums">{s.overall_score ?? 0}</div>
          <div className="fp-eyebrow">overall · {s.band}</div>
          {s.recommendation && (
            <div className="mt-1">
              <Pill tone={REC_TONE[s.recommendation] ?? "neutral"}>{s.recommendation.replace(/_/g, " ")}</Pill>
            </div>
          )}
        </div>
      </div>

      {s.narrative && <div className="mt-4 text-sm text-body leading-relaxed">{s.narrative}</div>}

      {s.competency_scores && Object.keys(s.competency_scores).length > 0 && (
        <div className="mt-5">
          <div className="fp-eyebrow mb-2">Per-competency rollup</div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(s.competency_scores).map(([k, v]) => (
              <div key={k} className="rounded-md border border-line bg-canvas p-3">
                <div className="text-2xs uppercase tracking-eyebrow text-muted">{k.replace(/_/g, " ")}</div>
                <div className="text-lg font-semibold text-ink tabular-nums">{v}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="fp-eyebrow text-success-fg mb-1">Strengths</div>
          <ul className="text-sm text-body space-y-1">{(s.strengths ?? []).map((x, i) => <li key={i}>• {x}</li>)}</ul>
        </div>
        <div>
          <div className="fp-eyebrow text-danger-fg mb-1">Concerns</div>
          <ul className="text-sm text-body space-y-1">{(s.concerns ?? []).map((x, i) => <li key={i}>• {x}</li>)}</ul>
        </div>
      </div>

      {s.panel_debrief && s.panel_debrief.length > 0 && (
        <div className="mt-5">
          <div className="fp-eyebrow mb-2">Panel debrief</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
            {s.panel_debrief.map((p, i) => (
              <div key={i} className="rounded-md border border-line bg-canvas p-3">
                <div className="text-sm font-medium text-ink">{p.interviewer_name}</div>
                <div className="text-xs text-muted">{p.rating_label} · confidence {p.confidence}</div>
                {p.headline_competency && <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">strongest: {p.headline_competency.replace(/_/g, " ")}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {s.next_actions && s.next_actions.length > 0 && (
        <div className="mt-5">
          <div className="fp-eyebrow mb-1">Next actions</div>
          <ul className="text-sm text-body space-y-0.5">{s.next_actions.map((x, i) => <li key={i}>• {x}</li>)}</ul>
        </div>
      )}

      {s.offer_risk_notes && s.offer_risk_notes.length > 0 && (
        <div className="mt-5 rounded-md border border-warn-line bg-warn-bg p-3 text-xs text-warn-fg">
          <div className="font-semibold mb-1">Offer risk notes</div>
          <ul>{s.offer_risk_notes.map((x, i) => <li key={i}>• {x}</li>)}</ul>
        </div>
      )}

      {s.candidate_feedback_draft && (
        <div className="mt-5 rounded-md border border-line bg-canvas p-3">
          <div className="fp-eyebrow mb-1">Candidate feedback draft</div>
          <div className="text-sm text-body italic">{s.candidate_feedback_draft}</div>
        </div>
      )}

      {s.fairness_note && (
        <div className="mt-5 rounded-md border border-warn-line bg-warn-bg p-3 text-xs text-warn-fg">⚖ {s.fairness_note}</div>
      )}
    </Surface>
  );
}
