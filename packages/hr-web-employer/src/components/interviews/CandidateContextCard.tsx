"use client";
import { Pill, Surface } from "@/components/ds";
import type { Interview, InterviewPlan } from "./types";

/**
 * Compact "who am I interviewing" header.  Renders the candidate name,
 * role, type, plan summary if generated, and consent state at a glance.
 */
/**
 * `profileState` says WHY the candidate context is thin, so the card can be
 * silent about a person we know nothing about instead of filling the space.
 * The four states are genuinely different facts: no candidate is linked to the
 * interview at all; the record is still loading; it is linked but missing; or
 * it exists and has not been screened. Only "ready" carries an assessment.
 */
export type CandidateProfileState =
  | "ready"
  | "loading"
  | "not-screened"
  | "missing"
  | "no-candidate";

const PROFILE_NOTE: Record<Exclude<CandidateProfileState, "ready">, string> = {
  loading: "Loading the candidate record…",
  "not-screened": "Not screened yet — no AI summary or match score for this candidate.",
  missing: "The candidate record linked to this interview could not be loaded.",
  "no-candidate": "No candidate record is linked to this interview, so there is no resume, summary or match score to show.",
};

export function CandidateContextCard({
  interview,
  candidateSummary,
  extractedSkills,
  skillGaps,
  matchScore,
  profileState = "ready",
}: {
  interview: Interview;
  candidateSummary?: string;
  extractedSkills?: string[];
  skillGaps?: string[];
  matchScore?: number;
  profileState?: CandidateProfileState;
}) {
  const plan: InterviewPlan | null | undefined = interview.interview_plan;
  return (
    <Surface pad="md">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="fp-eyebrow">{interview.interview_type} interview</div>
          <div className="text-xl font-semibold text-ink truncate">{interview.candidate_name}</div>
          <div className="text-sm text-muted">for <span className="text-ink">{interview.job_title}</span></div>
          {interview.scheduled_at && (
            <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">
              {new Date(interview.scheduled_at).toLocaleString()} · {interview.duration_minutes}m
            </div>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {matchScore !== undefined && (
            <div className="text-right">
              <div className="text-2xl font-bold text-ink tabular-nums">{matchScore}</div>
              <div className="text-2xs uppercase tracking-eyebrow text-muted">AI match</div>
            </div>
          )}
          <Pill tone={interview.consent_status === "granted" ? "success" : interview.consent_status === "denied" ? "danger" : "warn"}>
            consent · {interview.consent_status.replace(/_/g, " ")}
          </Pill>
          {interview.recording_enabled && <Pill tone="info">recording on</Pill>}
        </div>
      </div>

      {candidateSummary && (
        <div className="mt-3 text-sm text-body leading-relaxed line-clamp-3">{candidateSummary}</div>
      )}

      {profileState !== "ready" && (
        <div className="mt-3 text-sm text-muted">{PROFILE_NOTE[profileState]}</div>
      )}

      {(extractedSkills?.length || skillGaps?.length) ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {extractedSkills?.slice(0, 6).map((s) => (
            <Pill key={s} tone="success">{s}</Pill>
          ))}
          {skillGaps?.slice(0, 4).map((s) => (
            <Pill key={s} tone="warn">gap · {s}</Pill>
          ))}
        </div>
      ) : null}

      {plan && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <div className="fp-eyebrow mb-1">Focus areas</div>
            <div className="flex flex-wrap gap-1">
              {(plan.focus_areas ?? []).slice(0, 6).map((s) => <Pill key={s} tone="neutral">{s}</Pill>)}
            </div>
          </div>
          <div>
            <div className="fp-eyebrow mb-1">Verify</div>
            <ul className="text-xs text-body space-y-0.5">{(plan.verify ?? []).slice(0, 3).map((s, i) => <li key={i}>• {s}</li>)}</ul>
          </div>
          <div>
            <div className="fp-eyebrow mb-1">Concerns to probe</div>
            <ul className="text-xs text-body space-y-0.5">{(plan.concerns_to_explore ?? []).slice(0, 3).map((s, i) => <li key={i}>• {s}</li>)}</ul>
          </div>
        </div>
      )}
    </Surface>
  );
}
