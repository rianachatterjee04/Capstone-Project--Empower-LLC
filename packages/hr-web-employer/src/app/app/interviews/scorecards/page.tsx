"use client";
/**
 * Scorecards index — every scorecard across every interview, with
 * AI-suggested vs final-rating spreads, evidence-gap flags, calibration.
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch } from "@/lib/api";
import { EmptyState, PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import type { Interview, Scorecard } from "@/components/interviews/types";

const RATING_LABEL = ["No hire", "Lean no hire", "Lean hire", "Hire", "Strong hire"];

export default function ScorecardsIndexPage() {
  const ivQ = useQuery({ queryKey: ["sc-index-iv"], queryFn: () => apiFetch<{ items: Interview[] }>("/interviews") });
  const interviews = ivQ.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring · Scorecards"
        title="All scorecards"
        subtitle="Per-interview scorecards with AI-suggested ratings, evidence chips, and panel calibration. Every rating is evidence-grounded; the AI flags ratings without transcript citation."
      />

      {interviews.length === 0 ? (
        <Surface>
          <EmptyState title="No scorecards yet" description="Create your first interview to start collecting scorecards." />
        </Surface>
      ) : (
        <div className="space-y-4">
          {interviews.map((iv) => (
            <ScorecardCard key={iv.id} interview={iv} />
          ))}
        </div>
      )}
    </div>
  );
}

function ScorecardCard({ interview }: { interview: Interview }) {
  const scQ = useQuery({
    queryKey: ["sc-detail", interview.id],
    queryFn: () => apiFetch<{ items: Scorecard[] }>(`/interviews/${interview.id}/scorecard`),
  });
  const items = scQ.data?.items ?? [];
  const submitted = items.filter((s) => s.status === "submitted");
  const drafts = items.filter((s) => s.status === "draft");
  const evidence_gaps = submitted.reduce(
    (n, s) => n + s.competencies.filter((c) => c.final_rating !== null && (c.evidence_snippets?.length ?? 0) === 0).length,
    0,
  );
  return (
    <Surface>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="fp-eyebrow">{interview.interview_type}</div>
          <Link href={`/app/interviews/${interview.id}`} className="text-sm font-semibold text-ink hover:opacity-80">
            {interview.candidate_name} · {interview.job_title}
          </Link>
          <div className="text-xs text-muted">{submitted.length}/{items.length} scorecards submitted</div>
        </div>
        <div className="flex items-center gap-2">
          {evidence_gaps > 0 && <Pill tone="warn">{evidence_gaps} evidence gap{evidence_gaps > 1 ? "s" : ""}</Pill>}
          {drafts.length > 0 && <Pill tone="info">{drafts.length} draft</Pill>}
        </div>
      </div>

      {items.length > 0 && (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {items.map((s) => (
            <div key={s.id} className="rounded-md border border-line bg-canvas p-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-medium text-ink">{s.interviewer_name}</div>
                <Pill tone={s.status === "submitted" ? "success" : "neutral"}>{s.status}</Pill>
              </div>
              {s.overall_rating !== null && s.overall_rating !== undefined && (
                <div className="mt-1 text-xs text-muted">
                  Overall: <span className="text-ink font-medium">{RATING_LABEL[s.overall_rating]}</span>{" "}
                  · confidence {s.interviewer_confidence ?? "—"}
                </div>
              )}
              <ul className="mt-2 text-xs text-body space-y-0.5">
                {s.competencies.slice(0, 4).map((c) => (
                  <li key={c.competency} className="flex items-center justify-between">
                    <span className="truncate">{c.competency.replace(/_/g, " ")}</span>
                    {c.final_rating !== null && c.final_rating !== undefined ? (
                      <span className="text-ink tabular-nums">{c.final_rating}</span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </Surface>
  );
}
