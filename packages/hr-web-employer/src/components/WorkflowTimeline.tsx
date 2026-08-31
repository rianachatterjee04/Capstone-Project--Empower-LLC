"use client";
/**
 * WorkflowTimeline — a calm vertical timeline used for onboarding,
 * offboarding, performance cycles, comp cycles, and any sequenced flow.
 *
 * Each step renders:
 *   - a status dot (done · in_progress · pending · blocked)
 *   - title + description
 *   - owner role chip
 *   - optional due date
 *   - optional list of sub-tasks with the same status vocabulary
 *
 * No icons inside the dots — calm geometry only. Connecting line is a single
 * hairline. Active step has subtle background fill, finished steps muted.
 */
import React from "react";
import clsx from "clsx";
import { Pill } from "./ds";

export type StepStatus = "done" | "in_progress" | "pending" | "blocked";

export type WorkflowSubtask = {
  id?: string;
  label: string;
  status: StepStatus;
  owner?: string;
};

export type WorkflowStep = {
  id: string;
  title: string;
  description?: string;
  status: StepStatus;
  owner?: string;
  due?: string;
  ai_hint?: string;
  subtasks?: WorkflowSubtask[];
  /** Optional small CTA rendered on the right of the step header. */
  action?: React.ReactNode;
};

const DOT: Record<StepStatus, string> = {
  done: "bg-success-fg border-success-fg",
  in_progress: "bg-accent border-accent",
  pending: "bg-canvas border-line",
  blocked: "bg-danger-fg border-danger-fg",
};

const ROW_BG: Record<StepStatus, string> = {
  done: "",
  in_progress: "bg-canvas",
  pending: "",
  blocked: "bg-danger-bg/40",
};

const STATUS_TONE: Record<StepStatus, "success" | "info" | "neutral" | "danger"> = {
  done: "success",
  in_progress: "info",
  pending: "neutral",
  blocked: "danger",
};

function StatusDot({ status }: { status: StepStatus }) {
  return (
    <span
      className={clsx(
        "block h-3 w-3 rounded-full border-2 shrink-0 transition-colors duration-150 ease-calm",
        DOT[status],
      )}
      aria-label={status}
    />
  );
}

export function WorkflowTimeline({
  steps,
  className,
}: {
  steps: WorkflowStep[];
  className?: string;
}) {
  return (
    <ol className={clsx("relative", className)}>
      {steps.map((step, idx) => {
        const isLast = idx === steps.length - 1;
        return (
          <li key={step.id} className="relative pl-8 pb-5 last:pb-0">
            {/* Connecting hairline */}
            {!isLast && (
              <span
                aria-hidden
                className="absolute left-[5px] top-3 bottom-0 w-px bg-line"
              />
            )}
            {/* Dot */}
            <span className="absolute left-0 top-1">
              <StatusDot status={step.status} />
            </span>

            <div className={clsx("rounded-md border border-line p-3.5", ROW_BG[step.status])}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-ink">{step.title}</span>
                    <Pill tone={STATUS_TONE[step.status]}>{step.status.replace("_", " ")}</Pill>
                    {step.owner && (
                      <span className="text-2xs uppercase tracking-eyebrow text-muted">
                        {step.owner}
                      </span>
                    )}
                    {step.due && (
                      <span className="text-2xs uppercase tracking-eyebrow text-muted">
                        due {step.due}
                      </span>
                    )}
                  </div>
                  {step.description && (
                    <div className="text-xs text-body mt-1">{step.description}</div>
                  )}
                  {step.ai_hint && (
                    <div className="text-xs text-muted mt-1 italic">
                      AI · {step.ai_hint}
                    </div>
                  )}
                </div>
                {step.action && <div className="shrink-0">{step.action}</div>}
              </div>

              {step.subtasks && step.subtasks.length > 0 && (
                <ul className="mt-3 space-y-1.5 border-t border-rule pt-2">
                  {step.subtasks.map((t, i) => (
                    <li key={t.id ?? `${step.id}-${i}`} className="flex items-center gap-2 text-xs">
                      <StatusDot status={t.status} />
                      <span
                        className={clsx(
                          "flex-1",
                          t.status === "done" ? "text-muted line-through decoration-rule" : "text-body",
                        )}
                      >
                        {t.label}
                      </span>
                      {t.owner && (
                        <span className="text-2xs uppercase tracking-eyebrow text-muted">{t.owner}</span>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------------------------------------------------------------------
 * Helpers — common workflow templates so pages stay terse.
 * ------------------------------------------------------------------------- */

/**
 * Compute step status from progress percentage of subtasks.
 */
export function stepFromSubtasks(
  base: Omit<WorkflowStep, "status">,
  subtasks: WorkflowSubtask[],
): WorkflowStep {
  if (subtasks.length === 0) return { ...base, status: "pending" };
  const allDone = subtasks.every((s) => s.status === "done");
  const anyDone = subtasks.some((s) => s.status === "done");
  const anyBlocked = subtasks.some((s) => s.status === "blocked");
  if (anyBlocked) return { ...base, status: "blocked", subtasks };
  if (allDone) return { ...base, status: "done", subtasks };
  if (anyDone) return { ...base, status: "in_progress", subtasks };
  return { ...base, status: "pending", subtasks };
}

/**
 * Canonical onboarding journey. Pages can override / extend.
 */
export function defaultOnboardingTemplate(employeeName: string, role: string): WorkflowStep[] {
  return [
    stepFromSubtasks(
      { id: "pre-day-1", title: "Pre-Day 1", owner: "HR + IT", description: `Set ${employeeName} up before their first day.` },
      [
        { label: "Send offer for e-signature", status: "done", owner: "HR" },
        { label: "Collect I-9 + W-4", status: "done", owner: "HR" },
        { label: "Order equipment", status: "in_progress", owner: "IT" },
        { label: "Assign workspace + accounts", status: "pending", owner: "IT" },
      ],
    ),
    stepFromSubtasks(
      { id: "day-1", title: "Day 1", owner: "Manager", description: "Welcome, manager 1:1, buddy intro, calendar walk-through." },
      [
        { label: "Manager kick-off 1:1", status: "pending", owner: "Manager" },
        { label: "Buddy introduction", status: "pending", owner: "Buddy" },
        { label: "Security + acceptable use training", status: "pending", owner: "New hire", },
      ],
    ),
    stepFromSubtasks(
      { id: "first-week", title: "First week", owner: "Manager", description: "Context, calendar setup, shadow meetings." },
      [
        { label: "Shadow customer / ops meetings", status: "pending", owner: "New hire" },
        { label: "Read role-specific docs", status: "pending", owner: "New hire" },
      ],
    ),
    stepFromSubtasks(
      { id: "first-30", title: "First 30 days", owner: "Manager + HR", description: "Complete onboarding learning path; ship a small but visible piece of work." },
      [
        { label: `Complete ${role} learning path`, status: "pending", owner: "New hire" },
        { label: "Ship visible first piece of work", status: "pending", owner: "New hire" },
        { label: "Stakeholder map", status: "pending", owner: "Manager" },
      ],
    ),
    stepFromSubtasks(
      { id: "first-90", title: "First 90 days", owner: "Manager + HR", description: "Independent delivery, first formal performance check-in." },
      [
        { label: "Independent project delivery", status: "pending", owner: "New hire" },
        { label: "First formal performance check-in", status: "pending", owner: "Manager" },
      ],
    ),
  ];
}

/**
 * Canonical performance review cycle: self → peer → manager → calibration →
 * approval → delivery. Pages can override individual statuses.
 */
export function defaultPerformanceCycleTemplate(
  employeeName: string,
  options: {
    self?: StepStatus;
    peer?: StepStatus;
    manager?: StepStatus;
    calibration?: StepStatus;
    approval?: StepStatus;
    delivery?: StepStatus;
    cycleLabel?: string;
  } = {},
): WorkflowStep[] {
  const cycle = options.cycleLabel ?? "Q2 cycle";
  return [
    {
      id: "self-review",
      title: "Self review",
      owner: employeeName,
      description: `${employeeName} reflects on goals, impact, and growth areas.`,
      status: options.self ?? "in_progress",
      ai_hint: "Bias + vagueness detector reviews the draft inline.",
    },
    {
      id: "peer-review",
      title: "Peer feedback",
      owner: "2–3 peers",
      description: "Selected peers submit structured feedback.",
      status: options.peer ?? "pending",
    },
    {
      id: "manager-review",
      title: "Manager review",
      owner: "Manager",
      description: "Manager writes the review using self + peer signal.",
      status: options.manager ?? "pending",
      ai_hint: "Coach surfaces vague language and proposes balanced rewrites.",
    },
    {
      id: "calibration",
      title: "Calibration",
      owner: "HR + leadership",
      description: "Cross-team calibration to remove rater drift.",
      status: options.calibration ?? "pending",
    },
    {
      id: "approval",
      title: "Final approval",
      owner: "HR / admin",
      description: "Sign-off before delivery.",
      status: options.approval ?? "pending",
    },
    {
      id: "delivery",
      title: "Delivery & conversation",
      owner: "Manager",
      description: `Manager shares results with ${employeeName} in a 1:1.`,
      status: options.delivery ?? "pending",
    },
  ];
}

/**
 * Canonical compensation review cycle: performance signal → AI recommendation
 * → manager proposal → HR calibration → finance approval → communicate.
 */
export function defaultCompReviewTemplate(
  employeeName: string,
  options: {
    perfSignal?: StepStatus;
    aiRec?: StepStatus;
    managerProposal?: StepStatus;
    hrCalibration?: StepStatus;
    financeApproval?: StepStatus;
    communicate?: StepStatus;
    cycleLabel?: string;
  } = {},
): WorkflowStep[] {
  return [
    {
      id: "perf-signal",
      title: "Performance signal",
      owner: "Manager",
      description: "Latest review rating and recent impact are surfaced.",
      status: options.perfSignal ?? "done",
    },
    {
      id: "ai-rec",
      title: "AI recommendation",
      owner: "Comp AI",
      description: "Merit + promotion range with explainable rationale and pay-equity flags.",
      status: options.aiRec ?? "in_progress",
      ai_hint: "Confidence + equity flags shown alongside the range.",
    },
    {
      id: "manager-proposal",
      title: "Manager proposal",
      owner: "Manager",
      description: `Manager selects the proposed package for ${employeeName} within band.`,
      status: options.managerProposal ?? "pending",
    },
    {
      id: "hr-calibration",
      title: "HR calibration",
      owner: "HRBP",
      description: "Cross-team check for compa-ratio drift and equity.",
      status: options.hrCalibration ?? "pending",
    },
    {
      id: "finance-approval",
      title: "Finance approval",
      owner: "CFO / Finance",
      description: "Budget envelope confirmed; ledger entry queued.",
      status: options.financeApproval ?? "pending",
    },
    {
      id: "communicate",
      title: "Communicate",
      owner: "Manager",
      description: "Compensation letter delivered; effective date set.",
      status: options.communicate ?? "pending",
    },
  ];
}

/**
 * Canonical offboarding journey.
 */
export function defaultOffboardingTemplate(employeeName: string): WorkflowStep[] {
  return [
    stepFromSubtasks(
      { id: "notice", title: "Notice & confirmation", owner: "HR + Manager" },
      [
        { label: `Confirm last day with ${employeeName}`, status: "done", owner: "HR" },
        { label: "Manager acknowledgement", status: "done", owner: "Manager" },
        { label: "Inform the team", status: "in_progress", owner: "Manager" },
      ],
    ),
    stepFromSubtasks(
      { id: "knowledge", title: "Knowledge transfer", owner: "Manager" },
      [
        { label: "Documented project handoffs", status: "in_progress", owner: "Outgoing" },
        { label: "Successor named for each workstream", status: "pending", owner: "Manager" },
        { label: "Stakeholder introductions", status: "pending", owner: "Outgoing" },
      ],
    ),
    stepFromSubtasks(
      { id: "exit-interview", title: "Exit interview", owner: "HR", description: "Capture feedback to improve retention." },
      [
        { label: "Schedule 30-min exit interview", status: "pending", owner: "HR" },
        { label: "Capture themes for HR review", status: "pending", owner: "HR" },
      ],
    ),
    stepFromSubtasks(
      { id: "access", title: "Access & assets", owner: "IT + Security", description: "Revoke access; collect equipment." },
      [
        { label: "Revoke SSO + email at end of last day", status: "pending", owner: "IT" },
        { label: "Recover laptop + peripherals", status: "pending", owner: "IT" },
        { label: "Recover badges + physical keys", status: "pending", owner: "Office" },
      ],
    ),
    stepFromSubtasks(
      { id: "payroll", title: "Payroll & benefits", owner: "HR + Payroll" },
      [
        { label: "Final paycheque calculation", status: "pending", owner: "Payroll" },
        { label: "Process PTO payout", status: "pending", owner: "Payroll" },
        { label: "COBRA / continuation election", status: "pending", owner: "Benefits" },
        { label: "Stock vesting & true-up", status: "pending", owner: "Finance" },
      ],
    ),
    stepFromSubtasks(
      { id: "retention", title: "Records & retention", owner: "HR + Legal" },
      [
        { label: "Archive employment file per policy", status: "pending", owner: "HR" },
        { label: "Audit trail of access revocation", status: "pending", owner: "Security" },
      ],
    ),
  ];
}
