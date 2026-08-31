"use client";
/**
 * Interview detail / prep workspace.
 *  - Candidate context card
 *  - AI-generated interview plan (focus areas, agenda, verify, concerns)
 *  - Question guide
 *  - Consent state + jump-to-live link
 *  - Post-interview summary (when ready)
 */
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Action, EmptyState, PageHeader, Pill, SectionTitle, Surface } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";
import { CandidateContextCard } from "@/components/interviews/CandidateContextCard";
import { QuestionGuide } from "@/components/interviews/QuestionGuide";
import { PostInterviewSummary } from "@/components/interviews/PostInterviewSummary";
import { InterviewInsights } from "@/components/interviews/InterviewInsights";
import { ScoreExplanationPanel } from "@/components/interviews/ScoreExplanationPanel";
import type { Interview, InterviewInsight, InterviewQuestion, PostSummary } from "@/components/interviews/types";

type Candidate = {
  id: string;
  full_name: string;
  ai_score: number | null;
  ai_summary: string | null;
  resume_text: string | null;
};

export default function InterviewDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [generating, setGenerating] = useState(false);
  const [showSummary, setShowSummary] = useState(false);
  const [summary, setSummary] = useState<PostSummary | null>(null);

  const ivQ = useQuery({ queryKey: ["iv", id], queryFn: () => apiFetch<Interview>(`/interviews/${id}`) });
  const qQ = useQuery({ queryKey: ["iv-q", id], queryFn: () => apiFetch<{ items: InterviewQuestion[] }>(`/interviews/${id}/questions`) });
  const insQ = useQuery({ queryKey: ["iv-ins", id], queryFn: () => apiFetch<{ items: InterviewInsight[] }>(`/interview-ai/${id}/insights`) });
  const iv = ivQ.data;

  // THE CANDIDATE CONTEXT WAS INVENTED.
  //
  // This page hard-coded "5 years building async Python backends", the skills
  // python/fastapi/postgres/asyncio, the gaps llm/embeddings, and an AI MATCH
  // of 78 — as literals, for every interview. A Senior Accountant was shown a
  // backend engineer's profile and a confident-looking score that was a
  // constant. An "AI match" is a claim about a person; a constant presented as
  // one is the worst thing that can be on this screen.
  //
  // Worse, generatePlanAndQuestions fed the same invented strings to the plan
  // and question generators, so the AI output a buyer would judge us on was
  // derived from a profile belonging to nobody.
  //
  // Real candidates carry ai_summary and ai_score. Both are null until
  // screening runs, and "not screened" is its own state — not a zero, and not
  // an excuse to make one up.
  const candQ = useQuery({
    queryKey: ["iv-cand", iv?.candidate_id],
    enabled: !!iv?.candidate_id,
    queryFn: () => apiFetch<Candidate[]>(`/recruiting/candidates`),
  });
  const candidate = candQ.data?.find((c) => c.id === iv?.candidate_id);
  const candidateSummary = candidate?.ai_summary || undefined;
  const matchScore = typeof candidate?.ai_score === "number" ? candidate.ai_score : undefined;

  async function generatePlanAndQuestions() {
    if (!iv) return;
    setGenerating(true);
    try {
      // Whatever we actually hold about this candidate, and nothing else. The
      // endpoints default every field and read job title and interview type
      // from the interview server-side, so an unscreened candidate yields a
      // plan built on the role — which is honest — rather than one built on
      // someone else's resume.
      const summary = candidateSummary || candidate?.resume_text?.slice(0, 600) || "";
      await apiPost(`/interviews/${id}/generate-plan`, {
        job_description: "",
        candidate_summary: summary,
        extracted_skills: [],
        skill_gaps: [],
      });
      await apiPost(`/interviews/${id}/generate-questions`, {
        candidate_summary: summary,
        skill_gaps: [],
        n_questions: 8,
      });
      ivQ.refetch();
      qQ.refetch();
    } finally { setGenerating(false); }
  }

  async function pullSummary() {
    const s = await apiPost<PostSummary>(`/interviews/${id}/post-summary`, {});
    setSummary(s);
    setShowSummary(true);
  }

  if (!iv) return <div className="text-sm text-muted">Loading…</div>;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring · Interview prep"
        title={iv.candidate_name}
        subtitle={`${iv.job_title} · ${iv.interview_type} interview`}
        actions={
          <>
            <Action variant="subtle" onClick={pullSummary}>
              Post-interview summary
            </Action>
            <Link
              href={`/app/interviews/live?id=${id}`}
              className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium h-9 px-3 text-sm bg-accent text-accent-fg hover:opacity-90"
            >
              <IconSparkle /> Enter live room <IconArrowUpRight />
            </Link>
          </>
        }
      />

      <CandidateContextCard
        interview={iv}
        candidateSummary={candidateSummary}
        matchScore={matchScore}
        profileState={
          !iv.candidate_id
            ? "no-candidate"
            : candQ.isLoading
              ? "loading"
              : !candidate
                ? "missing"
                : candidateSummary || matchScore !== undefined
                  ? "ready"
                  : "not-screened"
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Surface className="lg:col-span-2">
          <SectionTitle
            eyebrow="Interview plan + questions"
            title={iv.interview_plan ? "AI-generated plan + question set" : "Generate the plan"}
            description={iv.interview_plan ? `Generated by ${iv.interview_plan.generated_by}` : "Click to draft a calibrated interview plan and per-competency question set."}
            trailing={!iv.interview_plan && (
              <Action variant="primary" size="sm" onClick={generatePlanAndQuestions} disabled={generating}>
                <IconSparkle /> {generating ? "Drafting…" : "Generate plan + questions"}
              </Action>
            )}
          />

          {iv.interview_plan ? (
            <div className="mt-4 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Block title="Verify">{(iv.interview_plan.verify ?? []).map((s, i) => <li key={i}>• {s}</li>)}</Block>
                <Block title="Probe concerns">{(iv.interview_plan.concerns_to_explore ?? []).map((s, i) => <li key={i}>• {s}</li>)}</Block>
                <Block title="Positive signals to confirm">{(iv.interview_plan.positive_signals_to_confirm ?? []).map((s, i) => <li key={i}>• {s}</li>)}</Block>
                <Block title="Agenda">{(iv.interview_plan.agenda ?? []).map((s, i) => <li key={i}>• {s.minutes}m — {s.topic}</li>)}</Block>
              </div>
              {iv.interview_plan.candidate_specific_notes && (
                <div className="rounded-md border border-line bg-canvas p-3 text-sm text-body italic">
                  {iv.interview_plan.candidate_specific_notes}
                </div>
              )}
              <div className="pt-2 border-t border-line">
                <QuestionGuide
                  questions={qQ.data?.items ?? []}
                  onMarkAsked={async (q) => { await apiPost(`/interviews/${id}/questions/${q.id}/asked`, {}); qQ.refetch(); }}
                />
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <EmptyState
                title="No plan yet"
                description="The AI uses the candidate summary + extracted skills + skill gaps to build a focused plan."
              />
            </div>
          )}
        </Surface>

        <Surface>
          <SectionTitle eyebrow="Insights" title="What the Copilot has flagged" />
          <div className="mt-3">
            <InterviewInsights items={insQ.data?.items ?? []} />
          </div>
        </Surface>
      </div>

      <ScoreExplanationPanel interviewId={id} />

      {showSummary && summary && (
        <PostInterviewSummary s={summary} />
      )}
    </div>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-canvas p-3">
      <div className="fp-eyebrow mb-1">{title}</div>
      <ul className="text-xs text-body space-y-0.5">{children}</ul>
    </div>
  );
}
