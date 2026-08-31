"use client";
/**
 * Recruiter Cockpit — mission control for the agentic recruiting layer.
 *
 * What lives here:
 *  - Today's priorities (AI-stitched from bottlenecks + CX risks)
 *  - Recruiter productivity stats (open reqs, in-flight, time-to-screen)
 *  - Hiring bottlenecks per requisition with severity bands
 *  - Pipeline funnel per requisition with conversion rates
 *  - Talent pools (auto-bucketed by skill signature)
 *  - Candidate experience risks (stalled / ghosted)
 *  - AI sourcing for a chosen requisition (passive pool match)
 *  - AI outreach drafting modal
 *  - Scorecard rollup tool (composite of AI screen + interview + reference)
 *
 * Design: Linear / Notion calm. Whitespace, single accent, no neon.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch, apiPost } from "@/lib/api";
import {
  Action,
  Avatar,
  EmptyState,
  PageHeader,
  Pill,
  SectionTitle,
  Surface,
} from "@/components/ds";
import {
  IconArrowUpRight,
  IconCheck,
  IconClose,
  IconSparkle,
} from "@/components/icons";

// ---------------------------------------------------------------------------
// Types (mirror backend payloads)
// ---------------------------------------------------------------------------
type Job = { id: string; title: string; description?: string };
type Candidate = { id: string; full_name: string; email: string; resume_text?: string; job_posting_id?: string };

type Productivity = {
  open_reqs: number;
  candidates_in_flight: number;
  candidates_added_7d: number;
  interviews_done_30d: number;
  avg_time_to_first_screen_days: number;
  avg_time_to_offer_days: number;
  bottlenecks_critical: number;
  silent_candidates_3d: number;
  notes: string[];
};

type Bottleneck = {
  job_id: string; job_title: string; stage: string; stage_label: string;
  candidates_in_stage: number; avg_days_in_stage: number; target_days: number;
  severity: "ok" | "watch" | "alert" | "critical"; note: string;
};

type CxSignal = {
  candidate_id: string; candidate_name: string; stage: string;
  days_in_stage: number; last_touch_days: number;
  risk: "ok" | "delay" | "stalled" | "ghosted"; note: string;
};

type Today = {
  productivity: Productivity;
  bottlenecks: Bottleneck[];
  candidate_experience: CxSignal[];
  today_priorities: {
    kind: string;
    severity: "critical" | "alert" | "watch" | "ok";
    title: string;
    detail: string;
    job_id?: string;
    candidate_id?: string;
  }[];
};

type Funnel = {
  job_id: string; job_title: string;
  counts: Record<string, number>;
  conversion: Record<string, number>;
  time_to_first_screen_days: number;
  time_to_offer_days: number;
  open_days: number;
};

type SourcingMatch = {
  candidate_id: string; candidate_name: string;
  current_job_id?: string; current_status: string;
  overall_score: number;
  skill_overlap: string[]; adjacent_skills: string[];
  evidence_snippets: string[];
  why_match: string; last_seen_days: number;
};

type TalentPool = {
  id: string; name: string; description: string;
  candidate_ids: string[]; skill_signature: string[]; avg_score: number;
};

type OutreachDraft = {
  candidate_id: string; candidate_name: string; job_title: string;
  channel: string; tone: string;
  subject: string; body: string; follow_up_body: string;
  rationale: string; is_llm_generated: boolean;
};

type Scorecard = {
  candidate_id: string; candidate_name: string;
  ai_screen_score: number | null;
  interview_overall: number | null;
  interview_dimensions: Record<string, number>;
  reference_overall: number | null;
  reference_band: string | null;
  composite_score: number;
  recommendation: string;
  strengths: string[]; risks: string[]; next_actions: string[];
};

const SEVERITY_TONE: Record<string, "success" | "info" | "warn" | "danger" | "neutral"> = {
  ok: "success", watch: "info", alert: "warn", critical: "danger",
};
const RISK_TONE: Record<string, "success" | "info" | "warn" | "danger"> = {
  ok: "success", delay: "info", stalled: "warn", ghosted: "danger",
};
const STAGE_LABEL: Record<string, string> = {
  applied: "Applied", ai_screened: "AI Screened", recruiter_review: "Review",
  interview: "Interview", offer: "Offer", hired: "Hired", rejected: "Rejected",
};
const STAGE_ORDER = ["applied", "ai_screened", "recruiter_review", "interview", "offer", "hired"];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function RecruiterCockpitPage() {
  // Drawers
  const [outreachFor, setOutreachFor] = useState<{
    candidate?: SourcingMatch | { candidate_id: string; candidate_name: string };
    job?: Job;
  } | null>(null);
  const [sourcingJobId, setSourcingJobId] = useState<string>("");
  const [scorecardOpen, setScorecardOpen] = useState(false);

  // Data
  const todayQ = useQuery({ queryKey: ["cockpit-today"], queryFn: () => apiFetch<Today>("/recruiting-cockpit/today") });
  const funnelQ = useQuery({ queryKey: ["cockpit-funnel"], queryFn: () => apiFetch<{ items: Funnel[] }>("/recruiting-cockpit/funnel") });
  const poolsQ = useQuery({ queryKey: ["cockpit-pools"], queryFn: () => apiFetch<{ items: TalentPool[] }>("/recruiting-cockpit/talent-pools") });
  const cxQ = useQuery({ queryKey: ["cockpit-cx"], queryFn: () => apiFetch<{ items: CxSignal[] }>("/recruiting-cockpit/candidate-experience") });
  const jobsQ = useQuery({ queryKey: ["cockpit-jobs"], queryFn: () => apiFetch<Job[]>("/recruiting/jobs") });
  const sourcingQ = useQuery({
    queryKey: ["cockpit-sourcing", sourcingJobId],
    queryFn: () => apiFetch<{ items: SourcingMatch[] }>(`/recruiting-cockpit/sourcing/${sourcingJobId}`),
    enabled: Boolean(sourcingJobId),
  });

  const today = todayQ.data;
  const funnels = funnelQ.data?.items ?? [];
  const pools = poolsQ.data?.items ?? [];
  const cx = cxQ.data?.items ?? [];
  const jobs = jobsQ.data ?? [];
  const sourcing = sourcingQ.data?.items ?? [];
  const sourcingJob = jobs.find((j) => j.id === sourcingJobId);

  // ---------------------------------------------------------------------
  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring · Mission control"
        title="Recruiter Cockpit"
        subtitle="AI-stitched priorities, bottleneck detection, sourcing recommendations, outreach drafting, and scorecard rollup — calibrated so the recruiter spends time on humans, not dashboards."
        actions={
          <>
            <Link href="/app/talent" className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-150 h-9 px-3 text-sm bg-surface text-ink border border-line hover:bg-sunken">
              Pipeline kanban
            </Link>
            <Link href="/app/interview-ai" className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-150 h-9 px-3 text-sm bg-surface text-ink border border-line hover:bg-sunken">
              AI Interviewer
            </Link>
            <Link href="/app/reference-check" className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-150 h-9 px-3 text-sm bg-surface text-ink border border-line hover:bg-sunken">
              Reference checks
            </Link>
            <Action variant="primary" onClick={() => setScorecardOpen(true)}>
              <IconSparkle /> Score a candidate
            </Action>
          </>
        }
      />

      {/* HERO: Productivity + Today's Priorities */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Surface pad="md" className="lg:col-span-1">
          <div className="fp-eyebrow">Today</div>
          <div className="mt-1 text-2xl font-semibold text-ink">Your hiring day at a glance</div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <Stat label="Open reqs" value={today?.productivity.open_reqs ?? "—"} />
            <Stat label="In flight" value={today?.productivity.candidates_in_flight ?? "—"} />
            <Stat label="Added 7d" value={today?.productivity.candidates_added_7d ?? "—"} />
            <Stat label="Interviews 30d" value={today?.productivity.interviews_done_30d ?? "—"} />
            <Stat label="Time-to-screen" value={today ? `${today.productivity.avg_time_to_first_screen_days}d` : "—"} />
            <Stat label="Time-to-offer" value={today ? `${today.productivity.avg_time_to_offer_days}d` : "—"} />
          </div>
          {today?.productivity.notes && today.productivity.notes.length > 0 && (
            <div className="mt-4 space-y-1.5">
              {today.productivity.notes.map((n, i) => (
                <div key={i} className="text-xs text-body bg-canvas rounded-md border border-line px-3 py-2">
                  {n}
                </div>
              ))}
            </div>
          )}
        </Surface>

        <Surface pad="md" className="lg:col-span-2">
          <div className="flex items-center justify-between">
            <div>
              <div className="fp-eyebrow">Today's priorities</div>
              <div className="text-md font-semibold text-ink">What to clear first</div>
            </div>
            {today && today.today_priorities.length > 0 && (
              <Pill tone="warn">{today.today_priorities.length} actions</Pill>
            )}
          </div>
          {!today || today.today_priorities.length === 0 ? (
            <div className="mt-4">
              <EmptyState
                title="Pipeline pacing healthy"
                description="No bottlenecks or candidate-experience risks need recruiter action today."
              />
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-line">
              {today.today_priorities.map((p, i) => (
                <li key={i} className="py-3 flex items-start gap-3">
                  <Pill tone={SEVERITY_TONE[p.severity] ?? "neutral"}>
                    {p.severity}
                  </Pill>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-ink">{p.title}</div>
                    <div className="text-xs text-muted mt-0.5">{p.detail}</div>
                  </div>
                  <Pill tone="neutral">{p.kind.replace(/_/g, " ")}</Pill>
                </li>
              ))}
            </ul>
          )}
        </Surface>
      </div>

      {/* Bottlenecks */}
      <Surface>
        <SectionTitle
          eyebrow="Pipeline health"
          title="Hiring bottlenecks"
          description="Where candidates are stalling across your open requisitions. Targets are tunable per stage."
        />
        {todayQ.isLoading ? (
          <div className="mt-4 text-sm text-muted">Detecting…</div>
        ) : !today || today.bottlenecks.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="No active requisitions" description="Add a job and candidates to see bottleneck detection." />
          </div>
        ) : (
          <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {today.bottlenecks.map((b, i) => (
              <div key={i} className="rounded-md border border-line bg-canvas p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-ink truncate">{b.job_title}</div>
                    <div className="text-xs text-muted">{b.stage_label}</div>
                  </div>
                  <Pill tone={SEVERITY_TONE[b.severity] ?? "neutral"}>{b.severity}</Pill>
                </div>
                <div className="mt-3 flex items-end justify-between">
                  <div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">Candidates</div>
                    <div className="text-xl font-semibold text-ink tabular-nums">{b.candidates_in_stage}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">Avg dwell</div>
                    <div className="text-sm font-medium text-ink tabular-nums">
                      {b.avg_days_in_stage}d <span className="text-muted">/ {b.target_days}d</span>
                    </div>
                  </div>
                </div>
                <div className="mt-3 text-xs text-body">{b.note}</div>
                <div className="mt-3 flex items-center gap-2">
                  <Action variant="subtle" size="sm" onClick={() => setSourcingJobId(b.job_id)}>
                    <IconSparkle /> Source more
                  </Action>
                  <Link
                    href={`/app/talent?jobId=${b.job_id}`}
                    className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium h-7 px-2.5 text-xs bg-surface text-ink border border-line hover:bg-sunken"
                  >
                    Open pipeline <IconArrowUpRight />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </Surface>

      {/* AI Sourcing */}
      <Surface>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <div className="fp-eyebrow">AI Sourcing</div>
            <div className="text-md font-semibold text-ink">Passive matches for a requisition</div>
            <div className="text-xs text-muted mt-0.5">
              Semantic + skill match against your full candidate pool — surfaces hidden talent already in your CRM.
            </div>
          </div>
          <label className="block min-w-[260px]">
            <div className="mb-1 text-2xs uppercase tracking-eyebrow text-muted">Requisition</div>
            <select
              className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
              value={sourcingJobId}
              onChange={(e) => setSourcingJobId(e.target.value)}
            >
              <option value="">— Pick a job —</option>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>{j.title}</option>
              ))}
            </select>
          </label>
        </div>

        {!sourcingJobId ? (
          <div className="mt-5">
            <EmptyState
              title="Pick a requisition to source for"
              description="The AI will rank everyone in your candidate pool (across all reqs) against the job description."
            />
          </div>
        ) : sourcingQ.isLoading ? (
          <div className="mt-5 text-sm text-muted">Ranking the pool…</div>
        ) : sourcing.length === 0 ? (
          <div className="mt-5">
            <EmptyState
              title="No passive matches yet"
              description="Add more candidates to the pool, or relax the matching criteria."
            />
          </div>
        ) : (
          <div className="mt-5 space-y-3">
            {sourcing.map((m) => (
              <div key={m.candidate_id} className="rounded-md border border-line bg-canvas p-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3 min-w-0">
                    <Avatar name={m.candidate_name} size={36} />
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-ink">{m.candidate_name}</div>
                      <div className="text-xs text-muted">
                        {STAGE_LABEL[m.current_status] ?? m.current_status} · last seen {m.last_seen_days}d ago
                      </div>
                      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                        {m.skill_overlap.slice(0, 4).map((s) => (
                          <Pill key={s} tone="success">{s}</Pill>
                        ))}
                        {m.adjacent_skills.slice(0, 3).map((s) => (
                          <Pill key={s} tone="info">+{s}</Pill>
                        ))}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-semibold text-ink tabular-nums">
                      {Math.round(m.overall_score * 100)}
                    </div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">match</div>
                  </div>
                </div>
                <div className="mt-2 text-xs text-body">{m.why_match}</div>
                {m.evidence_snippets.length > 0 && (
                  <ul className="mt-2 text-2xs text-muted space-y-0.5">
                    {m.evidence_snippets.slice(0, 2).map((e, i) => <li key={i}>• {e}</li>)}
                  </ul>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Action
                    variant="primary"
                    size="sm"
                    onClick={() => setOutreachFor({
                      candidate: m,
                      job: sourcingJob,
                    })}
                  >
                    <IconSparkle /> Draft outreach
                  </Action>
                  <Link
                    href={`/app/interview-ai?candidateId=${m.candidate_id}&jobId=${sourcingJobId}`}
                    className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium h-7 px-2.5 text-xs bg-surface text-ink border border-line hover:bg-sunken"
                  >
                    Schedule AI interview <IconArrowUpRight />
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </Surface>

      {/* Funnel per req */}
      <Surface>
        <SectionTitle
          eyebrow="Funnel"
          title="Conversion by requisition"
          description="How candidates flow through each stage. Conversion is the share who reached this stage or beyond."
        />
        {funnelQ.isLoading ? (
          <div className="mt-4 text-sm text-muted">Computing…</div>
        ) : funnels.length === 0 ? (
          <div className="mt-4">
            <EmptyState title="No requisitions" description="Open a job to populate the funnel." />
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            {funnels.map((f) => (
              <div key={f.job_id} className="rounded-md border border-line bg-canvas p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-ink">{f.job_title}</div>
                    <div className="text-xs text-muted">
                      Open {f.open_days}d · time-to-first-screen {f.time_to_first_screen_days}d · time-to-offer {f.time_to_offer_days}d
                    </div>
                  </div>
                  <Link
                    href={`/app/talent?jobId=${f.job_id}`}
                    className="inline-flex items-center justify-center gap-1.5 rounded-md font-medium h-7 px-2.5 text-xs bg-surface text-ink border border-line hover:bg-sunken"
                  >
                    Open <IconArrowUpRight />
                  </Link>
                </div>
                <div className="mt-3 grid grid-cols-6 gap-2">
                  {STAGE_ORDER.map((s) => (
                    <FunnelBar key={s} label={STAGE_LABEL[s] ?? s} count={f.counts[s] ?? 0} max={Math.max(...Object.values(f.counts), 1)} />
                  ))}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-2xs uppercase tracking-eyebrow text-muted">
                  {Object.entries(f.conversion).map(([edge, v]) => (
                    <span key={edge}>
                      <span className="text-muted">{edge.replace(/_/g, " ")}:</span>{" "}
                      <span className="text-ink font-mono tabular-nums">{Math.round(v * 100)}%</span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Surface>

      {/* Candidate Experience + Talent Pools */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Surface>
          <SectionTitle
            eyebrow="Candidate experience"
            title="Who's at risk of ghosting"
            description="Candidates with no recruiter action — protect the funnel and the brand."
          />
          {cxQ.isLoading ? (
            <div className="mt-4 text-sm text-muted">Scanning…</div>
          ) : cx.length === 0 ? (
            <div className="mt-4">
              <EmptyState title="All candidates have been touched recently" description="No CX risk signals right now." />
            </div>
          ) : (
            <ul className="mt-4 divide-y divide-line">
              {cx.map((s) => (
                <li key={s.candidate_id} className="py-3 flex items-start gap-3">
                  <Pill tone={RISK_TONE[s.risk] ?? "neutral"}>{s.risk}</Pill>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-ink">{s.candidate_name}</div>
                    <div className="text-xs text-muted">{s.note}</div>
                  </div>
                  <Action
                    variant="subtle"
                    size="sm"
                    onClick={() => setOutreachFor({
                      candidate: { candidate_id: s.candidate_id, candidate_name: s.candidate_name },
                    })}
                  >
                    Re-engage
                  </Action>
                </li>
              ))}
            </ul>
          )}
        </Surface>

        <Surface>
          <SectionTitle
            eyebrow="Talent pools"
            title="Auto-bucketed by skill signature"
            description="Pre-warmed pools so you can nurture clusters instead of individuals."
          />
          {poolsQ.isLoading ? (
            <div className="mt-4 text-sm text-muted">Bucketing…</div>
          ) : pools.length === 0 ? (
            <div className="mt-4">
              <EmptyState title="No pools yet" description="Add resumes to your candidate pool to auto-cluster." />
            </div>
          ) : (
            <div className="mt-4 space-y-2">
              {pools.map((p) => (
                <div key={p.id} className="rounded-md border border-line bg-canvas p-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-ink">{p.name}</div>
                    <div className="text-xs text-muted">{p.description}</div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {p.skill_signature.slice(0, 5).map((s) => (
                        <Pill key={s} tone="neutral">{s}</Pill>
                      ))}
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-lg font-semibold text-ink tabular-nums">{p.candidate_ids.length}</div>
                    <div className="text-2xs uppercase tracking-eyebrow text-muted">avg {p.avg_score}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Surface>
      </div>

      {/* Outreach drawer */}
      {outreachFor && (
        <OutreachDrawer
          candidate={outreachFor.candidate}
          job={outreachFor.job}
          jobs={jobs}
          onClose={() => setOutreachFor(null)}
        />
      )}

      {/* Scorecard drawer */}
      {scorecardOpen && (
        <ScorecardDrawer onClose={() => setScorecardOpen(false)} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Components
// ---------------------------------------------------------------------------
function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-md border border-line bg-canvas px-3 py-2">
      <div className="text-2xs uppercase tracking-eyebrow text-muted">{label}</div>
      <div className="text-lg font-semibold text-ink tabular-nums">{value}</div>
    </div>
  );
}

function FunnelBar({ label, count, max }: { label: string; count: number; max: number }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="rounded-md border border-line bg-surface p-2">
      <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">{label}</div>
      <div className="text-md font-semibold text-ink tabular-nums">{count}</div>
      <div className="mt-1 h-1 w-full rounded-full bg-sunken overflow-hidden">
        <div className="h-full bg-ink/80" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Outreach drawer
// ---------------------------------------------------------------------------
function OutreachDrawer({
  candidate,
  job: initialJob,
  jobs,
  onClose,
}: {
  candidate: { candidate_id: string; candidate_name: string } | undefined;
  job?: Job;
  jobs: Job[];
  onClose: () => void;
}) {
  const [tone, setTone] = useState<"warm" | "direct" | "warm_referral">("warm");
  const [channel, setChannel] = useState<"email" | "linkedin" | "slack">("email");
  const [jobId, setJobId] = useState<string>(initialJob?.id ?? "");
  const [drafting, setDrafting] = useState(false);
  const [draft, setDraft] = useState<OutreachDraft | null>(null);
  const [copied, setCopied] = useState<"" | "subject" | "body" | "follow_up">("");
  const selectedJob = useMemo(() => jobs.find((j) => j.id === jobId), [jobs, jobId]);

  async function generate() {
    if (!candidate) return;
    setDrafting(true);
    setDraft(null);
    try {
      const d = await apiPost<OutreachDraft>("/recruiting-cockpit/outreach/draft", {
        candidate_id: candidate.candidate_id,
        candidate_name: candidate.candidate_name,
        job_id: jobId || null,
        job_title: selectedJob?.title ?? "the role",
        tone,
        channel,
      });
      setDraft(d);
    } finally {
      setDrafting(false);
    }
  }

  function copy(field: "subject" | "body" | "follow_up", value: string) {
    if (typeof window === "undefined") return;
    navigator.clipboard?.writeText(value).catch(() => undefined);
    setCopied(field);
    setTimeout(() => setCopied(""), 1500);
  }

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-ink/30 backdrop-blur-sm" onClick={onClose} />
      <div className="w-full max-w-xl h-full bg-surface border-l border-line shadow-lift overflow-y-auto">
        <div className="px-5 py-4 border-b border-line flex items-center justify-between gap-3 sticky top-0 bg-surface z-10">
          <div>
            <div className="fp-eyebrow">AI outreach</div>
            <div className="text-md font-semibold text-ink">{candidate?.candidate_name ?? "Candidate"}</div>
          </div>
          <Action variant="subtle" onClick={onClose}><IconClose /> Close</Action>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="block">
              <div className="mb-1 text-2xs uppercase tracking-eyebrow text-muted">Requisition</div>
              <select
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
              >
                <option value="">— Pick a job —</option>
                {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
              </select>
            </label>
            <label className="block">
              <div className="mb-1 text-2xs uppercase tracking-eyebrow text-muted">Channel</div>
              <div className="flex flex-wrap gap-2">
                {(["email", "linkedin", "slack"] as const).map((c) => (
                  <Action key={c} size="sm" variant={channel === c ? "primary" : "subtle"} onClick={() => setChannel(c)}>
                    {c}
                  </Action>
                ))}
              </div>
            </label>
            <label className="block md:col-span-2">
              <div className="mb-1 text-2xs uppercase tracking-eyebrow text-muted">Tone</div>
              <div className="flex flex-wrap gap-2">
                {(["warm", "direct", "warm_referral"] as const).map((t) => (
                  <Action key={t} size="sm" variant={tone === t ? "primary" : "subtle"} onClick={() => setTone(t)}>
                    {t.replace(/_/g, " ")}
                  </Action>
                ))}
              </div>
            </label>
          </div>

          <Action variant="primary" onClick={generate} disabled={drafting}>
            <IconSparkle /> {drafting ? "Drafting…" : draft ? "Re-draft" : "Generate"}
          </Action>

          {draft && (
            <div className="space-y-4">
              <div>
                <div className="flex items-center justify-between">
                  <div className="fp-eyebrow">Subject</div>
                  <Action variant="subtle" size="sm" onClick={() => copy("subject", draft.subject)}>
                    <IconCheck /> {copied === "subject" ? "Copied" : "Copy"}
                  </Action>
                </div>
                <div className="mt-1 rounded-md border border-line bg-canvas p-3 text-sm text-ink">{draft.subject}</div>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <div className="fp-eyebrow">Body</div>
                  <Action variant="subtle" size="sm" onClick={() => copy("body", draft.body)}>
                    <IconCheck /> {copied === "body" ? "Copied" : "Copy"}
                  </Action>
                </div>
                <div className="mt-1 rounded-md border border-line bg-canvas p-3 text-sm text-body whitespace-pre-wrap leading-relaxed">{draft.body}</div>
              </div>
              <div>
                <div className="flex items-center justify-between">
                  <div className="fp-eyebrow">Follow-up</div>
                  <Action variant="subtle" size="sm" onClick={() => copy("follow_up", draft.follow_up_body)}>
                    <IconCheck /> {copied === "follow_up" ? "Copied" : "Copy"}
                  </Action>
                </div>
                <div className="mt-1 rounded-md border border-line bg-canvas p-3 text-sm text-body whitespace-pre-wrap leading-relaxed">{draft.follow_up_body}</div>
              </div>
              <div className="rounded-md border border-line bg-canvas p-3 text-2xs uppercase tracking-eyebrow text-muted">
                <div>{draft.is_llm_generated ? "LLM-drafted" : "Local template (no LLM key configured)"}</div>
                <div className="text-body normal-case tracking-normal text-xs mt-1">{draft.rationale}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scorecard rollup drawer
// ---------------------------------------------------------------------------
function ScorecardDrawer({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [aiScreen, setAiScreen] = useState<number | "">("");
  const [interview, setInterview] = useState<number | "">("");
  const [reference, setReference] = useState<number | "">("");
  const [refBand, setRefBand] = useState<string>("endorse");
  const [tech, setTech] = useState<number | "">("");
  const [comm, setComm] = useState<number | "">("");
  const [expr, setExpr] = useState<number | "">("");
  const [struc, setStruc] = useState<number | "">("");
  const [own, setOwn] = useState<number | "">("");

  const [sc, setSc] = useState<Scorecard | null>(null);
  const [busy, setBusy] = useState(false);

  async function compute() {
    if (!name.trim()) return;
    setBusy(true);
    try {
      const payload: any = {
        candidate_name: name,
        ai_screen_score: aiScreen === "" ? null : Number(aiScreen),
        interview_overall: interview === "" ? null : Number(interview),
        reference_overall: reference === "" ? null : Number(reference),
        reference_band: refBand,
        interview_dimensions: {
          technical: tech === "" ? 0 : Number(tech),
          communication: comm === "" ? 0 : Number(comm),
          expression: expr === "" ? 0 : Number(expr),
          structure: struc === "" ? 0 : Number(struc),
          ownership: own === "" ? 0 : Number(own),
        },
      };
      const r = await apiPost<Scorecard>("/recruiting-cockpit/scorecard", payload);
      setSc(r);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="fixed inset-0 z-40 flex">
      <div className="flex-1 bg-ink/30 backdrop-blur-sm" onClick={onClose} />
      <div className="w-full max-w-xl h-full bg-surface border-l border-line shadow-lift overflow-y-auto">
        <div className="px-5 py-4 border-b border-line flex items-center justify-between gap-3 sticky top-0 bg-surface z-10">
          <div>
            <div className="fp-eyebrow">Scorecard rollup</div>
            <div className="text-md font-semibold text-ink">Composite a candidate decision</div>
          </div>
          <Action variant="subtle" onClick={onClose}><IconClose /> Close</Action>
        </div>
        <div className="p-5 space-y-4">
          <label className="block">
            <div className="mb-1 text-2xs uppercase tracking-eyebrow text-muted">Candidate name</div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
            />
          </label>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <NumInput label="AI screen" value={aiScreen} onChange={setAiScreen} />
            <NumInput label="Interview overall" value={interview} onChange={setInterview} />
            <NumInput label="Reference overall" value={reference} onChange={setReference} />
          </div>
          <label className="block">
            <div className="mb-1 text-2xs uppercase tracking-eyebrow text-muted">Reference band</div>
            <select
              value={refBand}
              onChange={(e) => setRefBand(e.target.value)}
              className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink"
            >
              {["strong_endorse", "endorse", "proceed_with_caution", "lukewarm", "do_not_endorse"].map((b) => (
                <option key={b} value={b}>{b.replace(/_/g, " ")}</option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <NumInput label="Technical" value={tech} onChange={setTech} />
            <NumInput label="Comms" value={comm} onChange={setComm} />
            <NumInput label="Expression" value={expr} onChange={setExpr} />
            <NumInput label="Structure" value={struc} onChange={setStruc} />
            <NumInput label="Ownership" value={own} onChange={setOwn} />
          </div>
          <Action variant="primary" onClick={compute} disabled={!name.trim() || busy}>
            <IconSparkle /> {busy ? "Rolling up…" : sc ? "Re-compute" : "Compute composite"}
          </Action>

          {sc && (
            <div className="space-y-3">
              <div className="rounded-md border border-line bg-canvas p-4 flex items-center justify-between">
                <div>
                  <div className="fp-eyebrow">Composite</div>
                  <div className="text-3xl font-bold text-ink tabular-nums">{sc.composite_score}</div>
                </div>
                <Pill tone={
                  sc.recommendation === "advance" ? "success" :
                  sc.recommendation === "advance_with_caveats" ? "warn" :
                  sc.recommendation === "hold" ? "info" : "danger"
                }>
                  {sc.recommendation.replace(/_/g, " ")}
                </Pill>
              </div>
              {sc.strengths.length > 0 && (
                <div>
                  <div className="fp-eyebrow text-success-fg mb-1">Strengths</div>
                  <ul className="text-sm text-body space-y-0.5">{sc.strengths.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                </div>
              )}
              {sc.risks.length > 0 && (
                <div>
                  <div className="fp-eyebrow text-danger-fg mb-1">Risks</div>
                  <ul className="text-sm text-body space-y-0.5">{sc.risks.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                </div>
              )}
              {sc.next_actions.length > 0 && (
                <div>
                  <div className="fp-eyebrow mb-1">Next actions</div>
                  <ul className="text-sm text-body space-y-0.5">{sc.next_actions.map((s, i) => <li key={i}>• {s}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function NumInput({ label, value, onChange }: { label: string; value: number | ""; onChange: (v: number | "") => void }) {
  return (
    <label className="block">
      <div className="mb-1 text-2xs uppercase tracking-eyebrow text-muted">{label}</div>
      <input
        type="number" min={0} max={100}
        value={value}
        onChange={(e) => onChange(e.target.value === "" ? "" : Math.max(0, Math.min(100, Number(e.target.value))))}
        className="w-full rounded-md border border-line bg-canvas px-3 py-2 text-sm text-ink tabular-nums"
      />
    </label>
  );
}
