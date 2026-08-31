"use client";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, MetricStat, LinkAction, EmptyState, Divider, Avatar } from "@/components/ds";
import { WorkflowTimeline, type StepStatus, type WorkflowStep } from "@/components/WorkflowTimeline";
import { IconArrowUpRight, IconSparkle } from "@/components/icons";

type Employee = {
  id: string;
  legal_name: string;
  email: string;
  job_title?: string | null;
  department?: string | null;
  status: string;
};

/** Real review row from GET /reviews — includes the true milestone timestamps. */
type Review = {
  id: string;
  employee_id: string;
  cycle: string;
  status: string;
  ai_decision?: string | null;
  self_submitted_at?: string | null;
  manager_submitted_at?: string | null;
  finalized_at?: string | null;
};

type Cycle = { name: string; status: string; opened_at?: string | null; closed_at?: string | null };

type Reviewee = {
  employee: Employee;
  review: Review;
  self: StepStatus;
  manager: StepStatus;
  finalize: StepStatus;
  progress: number;
  statusLabel: string;
};

/**
 * Derive an employee's REAL position in the cycle from the milestone timestamps
 * that the /reviews router actually writes (submit_self, submit_manager,
 * finalize). No fabrication — an employee with no review simply isn't in the
 * cohort, and a draft review shows "self in progress".
 */
function deriveReviewee(review: Review, employee: Employee): Reviewee {
  const hasSelf = !!review.self_submitted_at;
  const hasMgr = !!review.manager_submitted_at || ["manager_submitted", "finalized"].includes(review.status);
  const hasFinal = !!review.finalized_at || review.status === "finalized";

  const self: StepStatus = hasSelf || hasMgr || hasFinal ? "done" : "in_progress";
  const manager: StepStatus = hasMgr || hasFinal ? "done" : hasSelf ? "in_progress" : "pending";
  const finalize: StepStatus = hasFinal ? "done" : hasMgr ? "in_progress" : "pending";

  const progress = hasFinal ? 1 : hasMgr ? 0.66 : hasSelf ? 0.4 : 0.12;
  const statusLabel = hasFinal ? "Finalized" : hasMgr ? "Manager review" : hasSelf ? "Self submitted" : "Draft";

  return { employee, review, self, manager, finalize, progress, statusLabel };
}

const STAGES = [
  { key: "self", label: "Self" },
  { key: "manager", label: "Manager" },
  { key: "finalize", label: "Finalized" },
] as const;

function progressTone(p: number): "success" | "warn" | "info" | "danger" {
  if (p >= 1) return "success";
  if (p >= 0.6) return "info";
  if (p >= 0.3) return "warn";
  return "danger";
}

function buildTimeline(r: Reviewee): WorkflowStep[] {
  const decision = r.review.ai_decision;
  return [
    {
      id: "self-review",
      title: "Self review",
      owner: r.employee.legal_name,
      description: "Employee reflects on goals, impact, and growth areas.",
      status: r.self,
      ai_hint: "Bias + vagueness detector reviews the draft inline.",
    },
    {
      id: "manager-review",
      title: "Manager review",
      owner: "Manager",
      description: "Manager writes the review using the self assessment.",
      status: r.manager,
      ai_hint: "Coach surfaces vague language and proposes balanced rewrites.",
    },
    {
      id: "finalize",
      title: decision ? `Finalize · ${decision}` : "Finalize & decision",
      owner: "HR / admin",
      description: "AI discrepancy flags are computed, then the review is finalized and calibrated.",
      status: r.finalize,
    },
  ];
}

export default function PerformancePage() {
  const empQ = useQuery({
    queryKey: ["employees"],
    queryFn: () => apiFetch<Employee[]>("/employees"),
  });
  const reviewsQ = useQuery({
    queryKey: ["reviews-all"],
    queryFn: () => apiFetch<{ reviews: Review[] }>("/reviews"),
  });
  const cyclesQ = useQuery({
    queryKey: ["review-cycles"],
    queryFn: () => apiFetch<{ cycles: Cycle[] }>("/reviews/cycles"),
  });

  const employees = useMemo(() => empQ.data ?? [], [empQ.data]);
  const reviews = useMemo(() => reviewsQ.data?.reviews ?? [], [reviewsQ.data]);
  const cycles = cyclesQ.data?.cycles ?? [];

  const empById = useMemo(
    () => Object.fromEntries(employees.map((e) => [e.id, e])),
    [employees],
  );

  // Which cycle are we showing? Prefer an actually-open cycle; else the most
  // recent cycle that has reviews.
  const openCycle = cycles.find((c) => c.status === "open");
  const currentCycle =
    openCycle?.name ?? (reviews.length ? reviews[0].cycle : null);

  const reviewees = useMemo(() => {
    if (!currentCycle) return [];
    return reviews
      .filter((r) => r.cycle === currentCycle)
      .map((r) => {
        const e = empById[r.employee_id];
        if (!e) return null;
        return deriveReviewee(r, e);
      })
      .filter(Boolean) as Reviewee[];
  }, [reviews, empById, currentCycle]);

  const [selectedId, setSelectedId] = useState<string>("");
  const selected = useMemo(
    () => reviewees.find((r) => r.employee.id === selectedId) ?? reviewees[0],
    [reviewees, selectedId],
  );

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const s of STAGES) counts[s.key] = 0;
    for (const r of reviewees) {
      for (const s of STAGES) {
        if ((r[s.key as keyof Reviewee] as StepStatus) === "done") counts[s.key] += 1;
      }
    }
    return counts;
  }, [reviewees]);

  const total = reviewees.length;
  const completed = reviewees.filter((r) => r.progress >= 1).length;
  const inFlight = reviewees.filter((r) => r.progress > 0 && r.progress < 1).length;
  const notInCycle = Math.max(0, employees.length - total);

  const loading = empQ.isLoading || reviewsQ.isLoading;
  const cycleOpen = !!openCycle;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Performance"
        title={currentCycle ? `${currentCycle} review` : "Performance reviews"}
        subtitle="Self review → manager review → finalize. Every step has an owner, AI coaching, and an audit trail — status below reflects live per-employee review state."
        actions={
          <>
            <LinkAction href="/app/agents?agent=performance" variant="subtle">
              Open performance agent
            </LinkAction>
            <LinkAction href="/app/comp" variant="primary">
              <IconSparkle /> Compensation review
            </LinkAction>
          </>
        }
      />

      {/* Cycle status banner */}
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {currentCycle ? (
          <Pill tone={cycleOpen ? "success" : "neutral"}>
            {currentCycle} · {cycleOpen ? "open" : "not open"}
          </Pill>
        ) : null}
        {currentCycle && <span className="text-muted">{total} in cohort · {notInCycle} not yet in this cycle</span>}
      </div>

      {loading ? (
        <Surface><div className="text-sm text-muted">Loading review state…</div></Surface>
      ) : reviewees.length === 0 ? (
        <Surface>
          <EmptyState
            title="No review cycle is running yet"
            description={
              cycleOpen
                ? `The cycle "${currentCycle}" is open, but no per-employee reviews have been created yet. Create reviews to populate live status here.`
                : "Open a cycle and create reviews to track each employee's real progress through self review, manager review, and finalize. This page shows live status only — it never fabricates a funnel."
            }
          />
        </Surface>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricStat label="In cohort" value={total} />
            <MetricStat label="In flight" value={inFlight} tone={inFlight ? "info" : "neutral"} />
            <MetricStat label="Not in cycle" value={notInCycle} tone={notInCycle ? "warn" : "neutral"} />
            <MetricStat label="Finalized" value={completed} tone="success" />
          </div>

          {/* Stage funnel — real counts */}
          <Surface>
            <SectionTitle
              eyebrow="Cycle funnel"
              title="Where the cohort is"
              description="Live counts across the three tracked review milestones."
            />
            <div className="mt-4 grid grid-cols-3 gap-2">
              {STAGES.map((s) => {
                const done = stageCounts[s.key];
                const ratio = total ? done / total : 0;
                return (
                  <div key={s.key} className="rounded-md border border-line bg-canvas p-3">
                    <div className="fp-eyebrow">{s.label}</div>
                    <div className="mt-1 text-lg font-semibold tabular-nums text-ink">{done} / {total}</div>
                    <div className="mt-2 h-1.5 rounded-full bg-sunken overflow-hidden">
                      <div className="h-full bg-accent" style={{ width: `${Math.round(ratio * 100)}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </Surface>

          {/* Cohort list + timeline */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <Surface>
              <SectionTitle eyebrow="Cohort" title="Reviewees" description="Pick someone to see their cycle." />
              <ul className="mt-3 divide-y divide-rule">
                {reviewees.map((r) => {
                  const active = (selectedId || reviewees[0].employee.id) === r.employee.id;
                  return (
                    <li key={r.employee.id}>
                      <button
                        onClick={() => setSelectedId(r.employee.id)}
                        className={[
                          "w-full text-left -mx-2 px-2 py-2.5 rounded-md flex items-center gap-3",
                          "transition-colors duration-150 ease-calm",
                          active ? "bg-canvas" : "hover:bg-sunken/60",
                        ].join(" ")}
                      >
                        <Avatar name={r.employee.legal_name} size={26} />
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-ink truncate">{r.employee.legal_name}</div>
                          <div className="text-2xs uppercase tracking-eyebrow text-muted truncate">
                            {r.statusLabel}
                          </div>
                          <div className="mt-1 h-1 rounded-full bg-sunken overflow-hidden">
                            <div className="h-full bg-accent" style={{ width: `${Math.round(r.progress * 100)}%` }} />
                          </div>
                        </div>
                        <Pill tone={progressTone(r.progress)}>{Math.round(r.progress * 100)}%</Pill>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </Surface>

            <Surface className="lg:col-span-2">
              <SectionTitle
                eyebrow={selected?.review.cycle ?? currentCycle ?? "Cycle"}
                title={selected ? `${selected.employee.legal_name} · cycle` : "Cycle"}
                trailing={
                  selected ? (
                    <Link href={`/app/people/${selected.employee.id}?tab=twin`} className="text-xs underline text-muted hover:text-ink flex items-center gap-1">
                      Digital twin <IconArrowUpRight />
                    </Link>
                  ) : null
                }
              />
              {!selected ? (
                <EmptyState title="—" description="Pick a reviewee from the cohort list." />
              ) : (
                <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-5">
                  <div className="lg:col-span-2">
                    <WorkflowTimeline steps={buildTimeline(selected)} />
                  </div>
                  <div>
                    <div className="fp-eyebrow mb-2">Coaching</div>
                    <div className="rounded-lg border border-line bg-canvas p-3 space-y-2 text-sm">
                      <p className="text-body">
                        The performance agent watches for vague or biased language and proposes balanced rewrites before review delivery.
                      </p>
                      <Divider />
                      <LinkAction href="/app/content-studio" size="sm" variant="subtle" className="w-full">
                        <IconSparkle /> Open balanced-feedback rewriter
                      </LinkAction>
                      <LinkAction href="/app/comp" size="sm" variant="primary" className="w-full">
                        Continue to compensation
                      </LinkAction>
                    </div>
                  </div>
                </div>
              )}
            </Surface>
          </div>

          <p className="text-xs text-muted">
            Every status above is read from the live <code className="text-body">performance_reviews</code> table
            (self, manager, and finalize milestones). Employees without a review in this cycle are counted as
            &ldquo;not in cycle&rdquo; rather than shown with an invented status.
          </p>
        </>
      )}
    </div>
  );
}
