"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { PIPELINE_STAGES as SHARED_STAGES, toStage } from "@/lib/pipelineStages";

import { PageHeader, Surface, SectionTitle, Pill, Action, LinkAction, EmptyState, Avatar, Divider } from "@/components/ds";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Job = { id: string; title: string; location?: string | null; status: string; description: string; created_at: string };
type Candidate = { id: string; full_name: string; email: string; status: string; ai_score?: number | null; ai_summary?: string | null; job_posting_id: string; created_at: string };

// One vocabulary, shared with the talent board and matched by the API.
// "other" is this page's own bucket for a status neither side recognises: it
// is DRAWN when non-empty, so a new status value looks like a bucket nobody
// expected instead of inflating the top of the funnel.
const FUNNEL_STAGES = [...SHARED_STAGES, "other"] as const;
type Stage = (typeof FUNNEL_STAGES)[number];

function bucket(status: string): Stage {
  return (toStage(status) as Stage) ?? "other";
}

const STAGE_TONE: Record<string, "info" | "warn" | "success" | "danger" | "neutral"> = {
  new: "info",
  screened: "info",
  interview: "warn",
  offer: "warn",
  hired: "success",
  rejected: "danger",
  other: "neutral",
};

function scoreTone(s?: number | null): "success" | "warn" | "danger" | "neutral" {
  if (s == null) return "neutral";
  if (s >= 75) return "success";
  if (s >= 55) return "warn";
  return "danger";
}

export default function HiringOverviewPage() {
  const qc = useQueryClient();
  const jobsQ = useQuery({ queryKey: ["jobs"], queryFn: () => apiFetch<Job[]>("/recruiting/jobs") });
  const candsQ = useQuery({ queryKey: ["candidates"], queryFn: () => apiFetch<Candidate[]>("/recruiting/candidates") });
  const summaryQ = useQuery({ queryKey: ["hiring-cpo"], queryFn: () => apiFetch<{ counts?: any; recommendations?: any[] }>("/cpo/report") });

  const jobs = jobsQ.data ?? [];
  const cands = candsQ.data ?? [];

  const byStage = useMemo(() => {
    const m = new Map<Stage, number>();
    for (const s of FUNNEL_STAGES) m.set(s, 0);
    for (const c of cands) {
      m.set(bucket(c.status), (m.get(bucket(c.status)) ?? 0) + 1);
    }
    return m;
  }, [cands]);

  const openJobs = jobs.filter((j) => j.status !== "closed");
  const totalCands = cands.length;
  const avgScore = cands.filter((c) => c.ai_score != null).length
    ? Math.round(cands.filter((c) => c.ai_score != null).reduce((a, c) => a + (c.ai_score ?? 0), 0) / cands.filter((c) => c.ai_score != null).length)
    : null;
  const coverage = openJobs.length > 0 ? (totalCands / openJobs.length).toFixed(1) : "—";
  const offers = byStage.get("offer") ?? 0;
  const interview = byStage.get("interview") ?? 0;

  const anyScored = cands.some((c) => typeof c.ai_score === "number");

  // UNSCORED IS NOT A SCORE OF ZERO.
  // `(b.ai_score ?? 0) - (a.ai_score ?? 0)` sorted every unscreened candidate
  // to the bottom as though they had scored zero, which is the ranking mistake
  // the analytics page now warns about in words. Scored candidates rank among
  // themselves; unscored ones follow, in a stable order, ranked by nothing.
  const topCands = useMemo(
    () =>
      [...cands]
        .sort((a, b) => {
          const as = typeof a.ai_score === "number" ? a.ai_score : null;
          const bs = typeof b.ai_score === "number" ? b.ai_score : null;
          if (as === null && bs === null) return 0;
          if (as === null) return 1;
          if (bs === null) return -1;
          return bs - as;
        })
        .slice(0, 5),
    [cands]
  );

  const [running, setRunning] = useState(false);
  async function runRecruitingAgent() {
    setRunning(true);
    try {
      await apiPost("/agents/recruiting/run", {});
      await qc.invalidateQueries({ queryKey: ["jobs"] });
      await qc.invalidateQueries({ queryKey: ["candidates"] });
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Hiring"
        title="Hiring overview"
        subtitle="One scannable view of every open requisition, AI-ranked candidates, and the agentic recruiting loop."
        actions={
          <>
            <Action variant="subtle" onClick={runRecruitingAgent} disabled={running}>
              <IconSparkle /> {running ? "Running…" : "Run recruiting agent"}
            </Action>
            <LinkAction href="/app/talent" variant="primary">Open talent pipeline</LinkAction>
          </>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Stat label="Open requisitions" value={openJobs.length} tone={openJobs.length ? "info" : "neutral"} />
        <Stat label="Candidates" value={totalCands} />
        <Stat label="Pipeline coverage" value={`${coverage}×`} tone={openJobs.length && parseFloat(coverage) < 4 ? "warn" : "neutral"} />
        <Stat label="Avg AI score" value={avgScore ?? "—"} />
        <Stat label="At offer" value={offers} tone={offers ? "warn" : "neutral"} />
      </div>

      {/* Funnel */}
      <Surface>
        <SectionTitle eyebrow="Pipeline" title="Stage funnel" description={`${totalCands} candidates across ${openJobs.length} open roles`} />
        <div className="mt-4 grid grid-cols-2 md:grid-cols-6 gap-2">
          {FUNNEL_STAGES.filter((s) => s !== "other" || (byStage.get("other") ?? 0) > 0).map((s) => {
            const n = byStage.get(s) ?? 0;
            const pct = totalCands ? Math.round((n / totalCands) * 100) : 0;
            return (
              <div key={s} className="rounded-md border border-line bg-canvas p-3">
                <div className="fp-eyebrow capitalize">
                  {s === "other" ? "Unrecognised stage" : s}
                </div>
                <div className="mt-1 text-2xl font-semibold tabular-nums text-ink">{n}</div>
                <div className="mt-2 h-1 rounded-full bg-sunken overflow-hidden">
                  <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
                </div>
                <div className="mt-1 text-2xs uppercase tracking-eyebrow text-muted">{pct}%</div>
              </div>
            );
          })}
        </div>
      </Surface>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Top AI-ranked */}
        <Surface className="lg:col-span-2">
          {/* "AI ranked · Top candidates right now" sat above four candidates
              that all carry ai_score = null. Nothing had ranked them; they
              were simply listed. The heading now says which it is. */}
          <SectionTitle
            eyebrow={anyScored ? "AI ranked" : "Not yet screened"}
            title={anyScored ? "Top candidates right now" : "Candidates in the pipeline"}
            trailing={<Link href="/app/talent" className="text-xs underline text-muted hover:text-ink">Full pipeline →</Link>}
          />
          {topCands.length === 0 ? (
            <EmptyState
              title="No candidates yet"
              description="Add a candidate from Recruiting or sync via your ATS."
              action={<LinkAction href="/app/recruiting" size="sm" variant="primary">Open recruiting</LinkAction>}
            />
          ) : (
            <ul className="mt-3 divide-y divide-rule">
              {topCands.map((c) => {
                const job = jobs.find((j) => j.id === c.job_posting_id);
                return (
                  <li key={c.id} className="py-3 flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0 flex-1">
                      <Avatar name={c.full_name} size={32} />
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-semibold text-ink">{c.full_name}</span>
                          <Pill tone={STAGE_TONE[c.status] ?? "neutral"}>{c.status}</Pill>
                          {job && <span className="text-2xs uppercase tracking-eyebrow text-muted">{job.title}</span>}
                        </div>
                        {c.ai_summary && <div className="text-xs text-muted mt-0.5 line-clamp-2">{c.ai_summary}</div>}
                      </div>
                    </div>
                    <div className="shrink-0 flex items-center gap-2">
                      {c.ai_score != null && <Pill tone={scoreTone(c.ai_score)}>{c.ai_score}</Pill>}
                      <LinkAction href={`/app/interview-ai?candidateId=${c.id}&jobId=${c.job_posting_id}`} size="sm" variant="subtle">
                        <IconSparkle /> Interview
                      </LinkAction>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Surface>

        {/* Open requisitions */}
        <Surface>
          <SectionTitle
            eyebrow="Requisitions"
            title="Open roles"
            trailing={<Link href="/app/recruiting" className="text-xs underline text-muted hover:text-ink">All jobs →</Link>}
          />
          {openJobs.length === 0 ? (
            <EmptyState title="No open roles" description="Post a job to get the pipeline moving." action={<LinkAction href="/app/recruiting" size="sm" variant="primary">Post a job</LinkAction>} />
          ) : (
            <ul className="mt-3 space-y-1.5 max-h-[360px] overflow-auto -mx-1 px-1">
              {openJobs.map((j) => {
                const jobCands = cands.filter((c) => c.job_posting_id === j.id);
                return (
                  <li key={j.id}>
                    <Link href="/app/talent" className="flex items-center justify-between rounded-md border border-line bg-canvas hover:bg-sunken transition-colors duration-150 ease-calm px-3 py-2.5">
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-ink truncate">{j.title}</div>
                        <div className="text-2xs uppercase tracking-eyebrow text-muted">{j.location ?? "—"} · {j.status}</div>
                      </div>
                      <div className="shrink-0 flex items-center gap-2">
                        <span className="text-2xs uppercase tracking-eyebrow text-muted">{jobCands.length} cand</span>
                        <span className="text-muted"><IconArrowUpRight /></span>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </Surface>
      </div>

      {/* Workflow shortcuts */}
      <Surface inset hairline={false} className="bg-transparent p-0">
        <SectionTitle eyebrow="Hiring workflows" title="Move people through the funnel" />
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            { label: "Talent pipeline", href: "/app/talent", aiHinted: true, desc: "Kanban + AI ranking" },
            { label: "AI interviewer", href: "/app/interview-ai", aiHinted: true, desc: "Generate + score interviews" },
            { label: "Content studio", href: "/app/content-studio", aiHinted: true, desc: "JD + scorecard + balanced feedback" },
            { label: "Requisitions", href: "/app/recruiting", desc: "Post + manage open roles" },
            { label: "ATS syndication", href: "/app/ats", desc: "Multi-board posting" },
            { label: "ATS mapping + screening", href: "/app/ats-mapping", desc: "Field mapping" },
            { label: "People CRM", href: "/app/crm", aiHinted: true, desc: "Candidates · alumni · referrals" },
            { label: "Recruiting agent", href: "/app/agents?agent=recruiting", aiHinted: true, desc: "Runs + proposed actions" },
          ].map((q) => (
            <Link key={q.label} href={q.href} className="group rounded-lg border border-line bg-surface px-3.5 py-3 text-sm text-body hover:text-ink hover:bg-sunken transition-colors duration-150 ease-calm flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span>{q.label}</span>
                  {q.aiHinted && <span className="text-2xs uppercase tracking-eyebrow text-muted group-hover:text-ink">AI</span>}
                </div>
                <div className="text-2xs uppercase tracking-eyebrow text-muted mt-0.5 truncate">{q.desc}</div>
              </div>
              <span className="text-muted group-hover:text-ink shrink-0"><IconArrowUpRight /></span>
            </Link>
          ))}
        </div>
      </Surface>
    </div>
  );
}

function Stat({ label, value, tone = "neutral" }: { label: string; value: React.ReactNode; tone?: "neutral" | "info" | "warn" | "success" }) {
  const ring: Record<string, string> = {
    neutral: "",
    info: "ring-1 ring-info-line",
    warn: "ring-1 ring-warn-line",
    success: "ring-1 ring-success-line",
  };
  return (
    <div className={`rounded-md border border-line bg-surface p-4 ${ring[tone]}`}>
      <div className="fp-eyebrow">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight text-ink tabular-nums">{value}</div>
    </div>
  );
}
