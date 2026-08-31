"use client";
/**
 * Live Interview Room — the headline Copilot surface.
 *
 * Layout:
 *   Top:    candidate context
 *   Left:   live transcript (consent-gated)
 *   Center: question guide + scorecard
 *   Right:  AI Copilot panel (live summary, follow-ups, fairness, mapping)
 *
 * Ethical posture: consent banner is always visible. Recording cannot start
 * until both parties grant. The Copilot does NOT generate answers for the
 * candidate — only assistance for the interviewer.
 */
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch, apiPatch, apiPost, detailMessage } from "@/lib/api";
import { Action, Pill, Surface } from "@/components/ds";
import { IconCheck, IconClose, IconSparkle } from "@/components/icons";
import { CandidateContextCard } from "@/components/interviews/CandidateContextCard";
import { InterviewCopilotPanel } from "@/components/interviews/InterviewCopilotPanel";
import { LiveTranscript } from "@/components/interviews/LiveTranscript";
import { QuestionGuide } from "@/components/interviews/QuestionGuide";
import { ScorecardPanel } from "@/components/interviews/ScorecardPanel";
import { PostInterviewSummary } from "@/components/interviews/PostInterviewSummary";
import type { ConsentRecord, Interview, InterviewQuestion, PostSummary, Scorecard } from "@/components/interviews/types";

type LiveCandidate = { id: string; ai_score: number | null; ai_summary: string | null };

export default function LiveInterviewRoom() {
  const sp = useSearchParams();
  const id = sp.get("id");
  const [postSummary, setPostSummary] = useState<PostSummary | null>(null);

  const ivQ = useQuery({ queryKey: ["live-iv", id], queryFn: () => apiFetch<Interview>(`/interviews/${id}`), enabled: Boolean(id) });
  const consentQ = useQuery({
    queryKey: ["live-consent", id],
    queryFn: () => apiFetch<ConsentRecord>(`/interviews/${id}/consent`),
    enabled: Boolean(id),
    refetchInterval: 6000,
  });
  const qQ = useQuery({ queryKey: ["live-q", id], queryFn: () => apiFetch<{ items: InterviewQuestion[] }>(`/interviews/${id}/questions`), enabled: Boolean(id) });
  const scQ = useQuery({
    queryKey: ["live-sc", id],
    queryFn: () => apiFetch<{ items: Scorecard[] }>(`/interviews/${id}/scorecard`),
    enabled: Boolean(id),
    refetchInterval: 4000,
  });

  const iv = ivQ.data;
  const candQ = useQuery({
    queryKey: ["live-cand", iv?.candidate_id],
    enabled: !!iv?.candidate_id,
    queryFn: () => apiFetch<LiveCandidate[]>(`/recruiting/candidates`),
  });
  const candidate = candQ.data?.find((c) => c.id === iv?.candidate_id);
  const consent = consentQ.data;
  const canCapture =
    consent?.candidate_consent_status === "granted" &&
    consent?.interviewer_consent_status === "granted";

  const focusCompetencies = useMemo(
    () => iv?.interview_plan?.focus_areas ?? ["communication", "technical_depth", "ownership", "collaboration"],
    [iv?.interview_plan?.focus_areas],
  );
  const scorecard = (scQ.data?.items ?? []).find((s) => s.status !== "submitted") ?? null;

  async function ensureScorecard() {
    if (!id) return;
    if (scorecard) return;
    await apiPost(`/interviews/${id}/scorecard`, {
      interviewer_name: "Interviewer",
      competencies: focusCompetencies,
    });
    scQ.refetch();
  }

  useEffect(() => { void ensureScorecard(); }, [id, focusCompetencies.join("|")]); // eslint-disable-line

  if (!id) {
    return <div className="p-6">Missing interview id. Use <code>/app/interviews/live?id=...</code></div>;
  }
  // `!iv` was true both while loading AND after the request failed, so a real
  // interview id whose record the API cannot find showed "Loading…" for ever.
  // That is the worst kind of broken screen: it looks like it is about to work.
  //
  // It happens for a genuine reason worth naming. Interviews live in two
  // stores: interview-v2 writes rows to Postgres, while this route is served by
  // interview_copilot_service, which keeps its state in the API process. An
  // interview that exists in the database is unknown here after a restart, so
  // the API answers 404 and the page must say so rather than spin.
  if (ivQ.isError) {
    const missing = detailMessage(ivQ.error).includes("not found");
    return (
      <div className="p-6 space-y-2">
        <div className="text-sm font-medium">This interview could not be opened.</div>
        <p className="text-sm text-muted">
          {missing
            ? "The interview copilot has no record of it. Copilot interviews are held in the API process and are lost when it restarts, so an interview created before the last restart cannot be resumed here."
            : detailMessage(ivQ.error)}
        </p>
        <p className="text-xs text-muted">Interview id: <code>{id}</code></p>
      </div>
    );
  }
  if (!iv) return <div className="p-6 text-sm text-muted">Loading…</div>;

  async function patchConsent(side: "candidate" | "interviewer", status: "granted" | "denied") {
    await apiPost(`/interviews/${id}/consent`, {
      [`${side}_consent_status`]: status,
    });
    consentQ.refetch();
  }

  async function draftFromTranscript() {
    if (!scorecard) return;
    const r = await apiPost<{ drafted: any[] }>(`/interviews/${id}/scorecard/${scorecard.id}/draft`, {
      competencies: (scorecard.competencies ?? []).map((c) => c.competency),
    });
    // Apply AI drafts to each row
    for (const d of r.drafted) {
      // PATCH, not POST: the same 405 that was silently dropping every manual
      // edit was dropping every AI-drafted row here too.
      await apiPatch(`/interviews/${id}/scorecard/${scorecard.id}`, {
        competency: d.competency,
        notes: d.note,
        evidence_snippets: d.evidence_snippets,
      });
    }
    scQ.refetch();
  }

  async function submitScorecard(overall: number, rec: string, conf: number) {
    if (!scorecard) return;
    await apiPost(`/interviews/${id}/scorecard/${scorecard.id}/submit`, {
      overall_rating: overall,
      overall_recommendation: rec,
      interviewer_confidence: conf,
    });
    scQ.refetch();
  }

  async function pullSummary() {
    const s = await apiPost<PostSummary>(`/interviews/${id}/post-summary`, {});
    setPostSummary(s);
  }

  return (
    <div className="space-y-4 h-full flex flex-col">
      {/* Consent banner — always visible */}
      <ConsentBanner consent={consent} onPatch={patchConsent} />

      {/* matchScore={78} was hard-coded here too — the same invented number as
          the prep page, in the room where the interviewer is actually looking
          at the person. It reads the linked candidate or says it has none. */}
      <CandidateContextCard
        interview={iv}
        candidateSummary={candidate?.ai_summary || undefined}
        matchScore={typeof candidate?.ai_score === "number" ? candidate.ai_score : undefined}
        profileState={
          !iv.candidate_id
            ? "no-candidate"
            : candQ.isLoading
              ? "loading"
              : !candidate
                ? "missing"
                : candidate.ai_summary || typeof candidate.ai_score === "number"
                  ? "ready"
                  : "not-screened"
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-[640px]">
        {/* Left: live transcript */}
        <div className="lg:col-span-4 flex flex-col min-h-[400px]">
          <Surface pad="sm" className="flex flex-col h-full min-h-0">
            <div className="fp-eyebrow mb-2">Live transcript</div>
            <LiveTranscript interviewId={id} canCapture={canCapture} />
          </Surface>
        </div>

        {/* Center: questions + scorecard */}
        <div className="lg:col-span-4 space-y-4">
          <Surface pad="md">
            <QuestionGuide
              questions={qQ.data?.items ?? []}
              onMarkAsked={async (q) => { await apiPost(`/interviews/${id}/questions/${q.id}/asked`, {}); qQ.refetch(); }}
            />
          </Surface>
          <Surface pad="md">
            <ScorecardPanel
              interviewId={id}
              scorecard={scorecard}
              competencies={focusCompetencies}
              onChange={() => scQ.refetch()}
              onDraftFromTranscript={draftFromTranscript}
              onSubmit={submitScorecard}
            />
          </Surface>
        </div>

        {/* Right: AI Copilot panel */}
        <div className="lg:col-span-4">
          <Surface pad="sm" className="h-full">
            <div className="fp-eyebrow mb-2 flex items-center gap-2">
              <IconSparkle /> AI Copilot
            </div>
            <InterviewCopilotPanel interviewId={id} />
          </Surface>
        </div>
      </div>

      {/* Bottom action bar */}
      <div className="flex items-center justify-between gap-3 pt-2 border-t border-line">
        <div className="text-2xs uppercase tracking-eyebrow text-muted">
          Copilot active · {canCapture ? "transcript capturing" : "consent required"}
        </div>
        <div className="flex items-center gap-2">
          <Action variant="subtle" onClick={pullSummary}>Generate post-summary</Action>
          <Link
            href={`/app/interviews/${id}`}
            className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium h-9 px-3 text-sm bg-surface text-ink border border-line hover:bg-sunken"
          >
            Back to prep
          </Link>
        </div>
      </div>

      {postSummary && (
        <PostInterviewSummary s={postSummary} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function ConsentBanner({ consent, onPatch }: {
  consent: ConsentRecord | undefined;
  onPatch: (side: "candidate" | "interviewer", status: "granted" | "denied") => void;
}) {
  const both = consent?.candidate_consent_status === "granted" && consent?.interviewer_consent_status === "granted";
  return (
    <div className={`rounded-md border p-3 ${
      both ? "border-success-line bg-success-bg" : "border-warn-line bg-warn-bg"
    }`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="fp-eyebrow">Consent</div>
          <div className={`text-sm font-medium ${both ? "text-success-fg" : "text-warn-fg"}`}>
            {both
              ? "Both parties have granted consent — AI Copilot is active and transcript capture is enabled."
              : "Capture is blocked until BOTH the candidate and interviewer record consent."}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ConsentChip label="Candidate" status={consent?.candidate_consent_status} onGrant={() => onPatch("candidate", "granted")} onDeny={() => onPatch("candidate", "denied")} />
          <ConsentChip label="Interviewer" status={consent?.interviewer_consent_status} onGrant={() => onPatch("interviewer", "granted")} onDeny={() => onPatch("interviewer", "denied")} />
        </div>
      </div>
    </div>
  );
}

function ConsentChip({ label, status, onGrant, onDeny }: { label: string; status?: string; onGrant: () => void; onDeny: () => void }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-xs text-ink">{label}:</span>
      <Pill tone={status === "granted" ? "success" : status === "denied" ? "danger" : "warn"}>{status ?? "not_collected"}</Pill>
      {status !== "granted" && (
        <Action variant="subtle" size="sm" onClick={onGrant}><IconCheck /> grant</Action>
      )}
      {status === "granted" && (
        <Action variant="subtle" size="sm" onClick={onDeny}><IconClose /> revoke</Action>
      )}
    </div>
  );
}
