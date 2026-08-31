"use client";
/**
 * ScoreExplanationPanel — explainable interview scoring + human-in-the-loop
 * recourse. Renders the per-rubric-dimension breakdown (score + evidence +
 * confidence), and lets a recruiter/candidate flag a score for human review;
 * an HR/manager reviewer can adjust it with a reason (audit-trailed).
 *
 * Compliance: LL144 (bias-audit + notice), Colorado AI Act (explanation +
 * appeal), EU AI Act Annex III (human oversight + record-keeping).
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost, apiPatch } from "@/lib/api";
import { Action, Pill, SectionTitle, Surface, EmptyState, Divider } from "@/components/ds";

type Evidence = { interviewer: string; quote: string };
type Dimension = {
  dimension: string;
  score: number;
  rating_label: string;
  weight: number;
  weighted_contribution: number;
  n_ratings: number;
  rating_spread: number;
  confidence: number;
  evidence: Evidence[];
  evidence_gap: boolean;
};
type Review = {
  id: string;
  dimension: string;
  status: "open" | "resolved";
  requested_by: string;
  requested_by_role: string;
  reason: string;
  original_rating: number | null;
  adjusted_rating: number | null;
  reviewer: string | null;
  review_reason: string | null;
  audit_trail: { ts: string; action: string; actor: string; detail: string }[];
};
type Explanation = {
  available: boolean;
  reason?: string;
  ai_disclosure: string;
  human_reviewable: boolean;
  panel_size?: number;
  weights_sum?: number;
  rubric: Dimension[];
  overall_score: number;
  overall_score_max?: number;
  overall_confidence?: number;
  compliance: { framework: string; obligation: string; satisfied_by: string }[];
  reviews: Review[];
  note?: string;
};

const scoreTone = (s: number) => (s >= 3 ? "success" : s >= 2 ? "warn" : "danger");

export function ScoreExplanationPanel({ interviewId }: { interviewId: string }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["score-explanation", interviewId],
    queryFn: () => apiFetch<Explanation>(`/interviews/${interviewId}/score-explanation`),
  });
  const [openDim, setOpenDim] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const data = q.data;

  async function requestReview(dimension: string, original: number | null) {
    if (!reason.trim()) return;
    setBusy(true);
    try {
      await apiPost(`/interviews/${interviewId}/score-review`, {
        dimension,
        reason,
        requested_by_role: "recruiter",
        original_rating: original,
      });
      setReason("");
      setOpenDim(null);
      await qc.invalidateQueries({ queryKey: ["score-explanation", interviewId] });
    } finally { setBusy(false); }
  }

  async function resolveReview(reviewId: string, adjusted: number) {
    setBusy(true);
    try {
      await apiPatch(`/interviews/${interviewId}/score-review/${reviewId}`, {
        adjusted_rating: adjusted,
        reason: "Reviewer adjustment after human check",
      });
      await qc.invalidateQueries({ queryKey: ["score-explanation", interviewId] });
    } finally { setBusy(false); }
  }

  return (
    <Surface>
      <SectionTitle
        eyebrow="Explainable scoring + recourse"
        title="Score explanation"
        description="Every dimension cites the evidence that drove it. AI-assisted scores are human-reviewable."
        trailing={<Pill tone="info">{data?.ai_disclosure ?? "AI-assisted, human-reviewable"}</Pill>}
      />

      {q.isLoading ? (
        <div className="mt-4 text-sm text-muted">Loading…</div>
      ) : !data?.available ? (
        <div className="mt-4">
          <EmptyState title="No submitted scorecards yet" description={data?.reason ?? "Submit a scorecard to generate the explainable breakdown."} />
        </div>
      ) : (
        <div className="mt-4 space-y-4">
          <div className="flex items-center gap-3">
            <div className="text-3xl font-bold tabular-nums text-ink">{data.overall_score.toFixed(2)}<span className="text-base text-muted"> / {data.overall_score_max ?? 4}</span></div>
            <div>
              <Pill tone={scoreTone(data.overall_score)}>{(data.overall_confidence! * 100).toFixed(0)}% confidence</Pill>
              <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">weighted sum of {data.rubric.length} dimensions (weights sum to {data.weights_sum})</div>
            </div>
          </div>

          <ul className="space-y-2">
            {data.rubric.map((d) => (
              <li key={d.dimension} className="rounded-md border border-line bg-canvas p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-ink capitalize">{d.dimension.replace(/_/g, " ")}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted">weight {d.weight}</span>
                    <Pill tone={scoreTone(d.score)}>{d.score.toFixed(2)} · {d.rating_label.replace(/_/g, " ")}</Pill>
                    <span className="text-2xs text-muted tabular-nums">{(d.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
                {d.evidence.length > 0 ? (
                  <ul className="mt-2 space-y-1">
                    {d.evidence.map((e, i) => (
                      <li key={i} className="text-xs text-body pl-2 border-l-2 border-line italic">“{e.quote}” <span className="text-muted not-italic">— {e.interviewer}</span></li>
                    ))}
                  </ul>
                ) : (
                  <div className="mt-1 text-2xs uppercase tracking-eyebrow text-warn-fg">Evidence gap — no transcript citation</div>
                )}
                <div className="mt-2 flex items-center gap-2">
                  <button onClick={() => setOpenDim(openDim === d.dimension ? null : d.dimension)} className="text-2xs uppercase tracking-eyebrow text-muted hover:text-ink">
                    {openDim === d.dimension ? "Cancel" : "Request human review"}
                  </button>
                </div>
                {openDim === d.dimension && (
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why should a human re-check this score?"
                      className="flex-1 min-w-[220px] h-8 rounded-md border border-line bg-surface px-3 text-sm text-ink outline-none" />
                    <Action variant="primary" size="sm" onClick={() => requestReview(d.dimension, d.score)} disabled={!reason.trim() || busy}>Submit review request</Action>
                  </div>
                )}
              </li>
            ))}
          </ul>

          {/* Recourse / review queue */}
          {data.reviews.length > 0 && (
            <div>
              <Divider className="my-2" />
              <div className="fp-eyebrow mb-2">Human review recourse ({data.reviews.length})</div>
              <ul className="space-y-2">
                {data.reviews.map((r) => (
                  <li key={r.id} className="rounded-md border border-line bg-canvas p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-ink capitalize">{r.dimension.replace(/_/g, " ")}</span>
                      <Pill tone={r.status === "resolved" ? "success" : "warn"}>{r.status}</Pill>
                    </div>
                    <div className="text-xs text-muted mt-1">Flagged by {r.requested_by_role}: “{r.reason}”</div>
                    {r.status === "resolved" ? (
                      <div className="text-xs text-body mt-1">Adjusted {r.original_rating ?? "—"} → <span className="font-semibold text-ink">{r.adjusted_rating}</span> by {r.reviewer}</div>
                    ) : (
                      <div className="mt-2 flex items-center gap-1.5">
                        <span className="text-2xs uppercase tracking-eyebrow text-muted">Reviewer adjust to:</span>
                        {[0, 1, 2, 3, 4].map((v) => (
                          <button key={v} onClick={() => resolveReview(r.id, v)} disabled={busy}
                            className="h-6 w-6 rounded border border-line text-xs text-body hover:bg-accent hover:text-accent-fg tabular-nums">{v}</button>
                        ))}
                      </div>
                    )}
                    <div className="mt-2 text-2xs text-muted">Audit trail: {r.audit_trail.map((a) => a.action).join(" → ")}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Compliance mapping */}
          <div>
            <Divider className="my-2" />
            <div className="fp-eyebrow mb-2">Compliance mapping</div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {data.compliance.map((c) => (
                <div key={c.framework} className="rounded-md border border-line bg-canvas p-2">
                  <div className="text-xs font-medium text-ink">{c.framework}</div>
                  <div className="text-2xs text-muted mt-0.5">{c.obligation}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Surface>
  );
}
