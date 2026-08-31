// AI-Economy Workforce — Mixed Org, Skills, Productivity & Onboarding
//
// Deterministic mock data + helpers for four HR surfaces built around a
// workforce that blends humans with AI labor:
//
//   1. "Workforce Roster" — a single roster of humans, contractors, AI agents,
//      and bots, each with cost, permissions, capabilities, and a lifecycle /
//      approval state plus an audit trail count.
//
//   2. "AI Skill Matrix" — per-employee proficiency (0-100) across eight
//      AI-native skills, with a certified flag, plus a skillGaps() roll-up.
//
//   3. "AI Productivity" — per-employee leverage: hours saved, automations
//      built, tasks eliminated, dollar savings, and the ratio of automated to
//      worked hours.
//
//   4. "Onboarding Runs" — provisioning of a new hire across a fixed tool set,
//      with per-tool status, security verifications, an overall status, and a
//      time-to-productive estimate.
//
// All values are fixed at authoring time. Every derived figure flows purely
// from these rows through the exported helpers — there is NO Math.random() (or
// any other nondeterminism) evaluated at module load, so identical inputs
// always yield identical outputs and snapshots stay stable.

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

export type Trend = "up" | "down" | "flat";

/** Clamp a number into the inclusive [0, 100] band and round to an integer. */
export function clamp100(n: number): number {
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

/**
 * Color helper for a 0-100 score.
 *   >= 85  green  #16A34A
 *   70-84  teal   #0F766E
 *   55-69  amber  #D97706
 *   < 55   red    #DC2626
 */
export function scoreColor(n: number): string {
  const v = clamp100(n);
  if (v >= 85) return "#16A34A";
  if (v >= 70) return "#0F766E";
  if (v >= 55) return "#D97706";
  return "#DC2626";
}

function mean(values: ReadonlyArray<number>): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

// ===========================================================================
// 1. WORKFORCE ROSTER (humans + contractors + agents + bots)
// ===========================================================================

export type WorkforceKind = "human" | "contractor" | "agent" | "bot";

export type LifecycleStatus = "active" | "pending_approval" | "retired";

export type ApprovalStatus = "approved" | "pending" | "rejected" | "n/a";

export interface WorkforceMember {
  id: string;
  kind: WorkforceKind;
  name: string;
  /** Role or title, e.g. "Payroll Specialist" or "Invoice Reconciliation Agent". */
  role: string;
  department: string;
  /** Human owner accountable for an agent/bot. Undefined for humans/contractors. */
  owner?: string;
  /** Model provider backing an agent. Undefined for humans/contractors/bots. */
  modelProvider?: string;
  /** Fully-loaded monthly cost (salary share, contract rate, or compute spend). */
  monthlyCostUsd: number;
  /** Granted permission scopes. */
  permissions: ReadonlyArray<string>;
  /** What this member can do. */
  capabilities: ReadonlyArray<string>;
  lifecycleStatus: LifecycleStatus;
  approvalStatus: ApprovalStatus;
  /** Number of audit-log entries recorded for this member. */
  auditCount: number;
  /** ISO-8601 timestamp of last activity. */
  lastActive: string;
}

export const WORKFORCE_MEMBERS: ReadonlyArray<WorkforceMember> = [
  {
    id: "wf_h01",
    kind: "human",
    name: "Ava Restrepo",
    role: "Payroll Specialist",
    department: "Payroll Ops",
    monthlyCostUsd: 7100,
    permissions: ["payroll:read", "payroll:edit", "reports:read"],
    capabilities: ["Payroll processing", "Deduction review", "Employee support"],
    lifecycleStatus: "active",
    approvalStatus: "n/a",
    auditCount: 318,
    lastActive: "2026-06-27T16:40:00Z",
  },
  {
    id: "wf_h02",
    kind: "human",
    name: "Daniel Okoro",
    role: "Payroll Lead",
    department: "Payroll Ops",
    monthlyCostUsd: 9800,
    permissions: ["payroll:read", "payroll:edit", "payroll:approve", "reports:read"],
    capabilities: ["Run approval", "Variance reconciliation", "Agent oversight"],
    lifecycleStatus: "active",
    approvalStatus: "n/a",
    auditCount: 642,
    lastActive: "2026-06-27T18:05:00Z",
  },
  {
    id: "wf_h03",
    kind: "human",
    name: "Priya Nandakumar",
    role: "Lead HR Business Partner",
    department: "HR Business Partners",
    monthlyCostUsd: 10400,
    permissions: ["people:read", "people:edit", "comp:read", "reports:read"],
    capabilities: ["Workforce planning", "Manager coaching", "Policy authoring"],
    lifecycleStatus: "active",
    approvalStatus: "n/a",
    auditCount: 471,
    lastActive: "2026-06-27T14:22:00Z",
  },
  {
    id: "wf_c01",
    kind: "contractor",
    name: "Sofia Marchetti",
    role: "People Analytics Contractor",
    department: "People Analytics",
    monthlyCostUsd: 12000,
    permissions: ["analytics:read", "reports:read"],
    capabilities: ["Attrition modeling", "Comp benchmarking", "Dashboarding"],
    lifecycleStatus: "active",
    approvalStatus: "approved",
    auditCount: 188,
    lastActive: "2026-06-26T20:10:00Z",
  },
  {
    id: "wf_c02",
    kind: "contractor",
    name: "Jonas Berg",
    role: "Technical Recruiter (Contract)",
    department: "Talent Acquisition",
    monthlyCostUsd: 8600,
    permissions: ["ats:read", "ats:edit"],
    capabilities: ["Sourcing", "Screening", "Interview coordination"],
    lifecycleStatus: "active",
    approvalStatus: "approved",
    auditCount: 97,
    lastActive: "2026-06-25T17:48:00Z",
  },
  {
    id: "wf_a01",
    kind: "agent",
    name: "Payroll Reconciliation Agent",
    role: "Invoice & Payroll Reconciliation Agent",
    department: "Payroll Ops",
    owner: "Daniel Okoro",
    modelProvider: "Anthropic Claude Opus 4",
    monthlyCostUsd: 1340,
    permissions: ["payroll:read", "reports:read", "ledger:read"],
    capabilities: [
      "Variance detection",
      "Overtime audit",
      "Anomaly flagging",
      "Draft register prep",
    ],
    lifecycleStatus: "active",
    approvalStatus: "approved",
    auditCount: 2841,
    lastActive: "2026-06-27T08:12:00Z",
  },
  {
    id: "wf_a02",
    kind: "agent",
    name: "Talent Sourcing Agent",
    role: "Candidate Sourcing & Outreach Agent",
    department: "Talent Acquisition",
    owner: "Jonas Berg",
    modelProvider: "Anthropic Claude Sonnet 4",
    monthlyCostUsd: 720,
    permissions: ["ats:read", "ats:edit", "email:send"],
    capabilities: ["Resume screening", "Outreach drafting", "Pipeline triage"],
    lifecycleStatus: "active",
    approvalStatus: "approved",
    auditCount: 1559,
    lastActive: "2026-06-27T11:33:00Z",
  },
  {
    id: "wf_a03",
    kind: "agent",
    name: "Comp Benchmarking Agent",
    role: "Compensation Benchmarking Agent",
    department: "People Analytics",
    owner: "Sofia Marchetti",
    modelProvider: "Anthropic Claude Opus 4",
    monthlyCostUsd: 980,
    permissions: ["analytics:read", "comp:read"],
    capabilities: ["Market data sync", "Band modeling", "Pay-equity scan"],
    lifecycleStatus: "pending_approval",
    approvalStatus: "pending",
    auditCount: 64,
    lastActive: "2026-06-24T09:50:00Z",
  },
  {
    id: "wf_a04",
    kind: "agent",
    name: "Policy Q&A Agent",
    role: "Employee Policy Assistant Agent",
    department: "HR Business Partners",
    owner: "Priya Nandakumar",
    modelProvider: "Anthropic Claude Haiku 3.5",
    monthlyCostUsd: 410,
    permissions: ["policy:read", "kb:read"],
    capabilities: ["Policy lookup", "Benefits Q&A", "Citation grounding"],
    lifecycleStatus: "active",
    approvalStatus: "approved",
    auditCount: 4203,
    lastActive: "2026-06-27T17:58:00Z",
  },
  {
    id: "wf_b01",
    kind: "bot",
    name: "Onboarding Provisioner",
    role: "Account Provisioning Bot",
    department: "IT Operations",
    owner: "Priya Nandakumar",
    monthlyCostUsd: 120,
    permissions: ["identity:provision", "saas:admin"],
    capabilities: ["Account creation", "Group assignment", "MFA enrollment"],
    lifecycleStatus: "active",
    approvalStatus: "approved",
    auditCount: 1022,
    lastActive: "2026-06-27T07:15:00Z",
  },
  {
    id: "wf_b02",
    kind: "bot",
    name: "Timesheet Reminder Bot",
    role: "Notification Bot",
    department: "Payroll Ops",
    owner: "Ava Restrepo",
    monthlyCostUsd: 35,
    permissions: ["slack:post"],
    capabilities: ["Scheduled reminders", "Deadline nudges"],
    lifecycleStatus: "retired",
    approvalStatus: "approved",
    auditCount: 5310,
    lastActive: "2026-04-30T12:00:00Z",
  },
];

// --- Roster lookups & rollups ----------------------------------------------

export function getWorkforceMember(id: string): WorkforceMember | undefined {
  return WORKFORCE_MEMBERS.find((m) => m.id === id);
}

export function membersByKind(
  kind: WorkforceKind
): ReadonlyArray<WorkforceMember> {
  return WORKFORCE_MEMBERS.filter((m) => m.kind === kind);
}

export function pendingApprovals(): ReadonlyArray<WorkforceMember> {
  return WORKFORCE_MEMBERS.filter(
    (m) => m.lifecycleStatus === "pending_approval" || m.approvalStatus === "pending"
  );
}

/** Headcount, monthly cost, and audit volume rolled up by kind. */
export const WORKFORCE_SUMMARY = (() => {
  const kinds: ReadonlyArray<WorkforceKind> = ["human", "contractor", "agent", "bot"];
  const byKind = kinds.map((kind) => {
    const members = membersByKind(kind);
    return {
      kind,
      count: members.length,
      monthlyCostUsd: round2(members.reduce((s, m) => s + m.monthlyCostUsd, 0)),
    };
  });
  return {
    headcount: WORKFORCE_MEMBERS.length,
    activeCount: WORKFORCE_MEMBERS.filter((m) => m.lifecycleStatus === "active")
      .length,
    pendingApprovalCount: pendingApprovals().length,
    monthlyCostUsd: round2(
      WORKFORCE_MEMBERS.reduce((s, m) => s + m.monthlyCostUsd, 0)
    ),
    aiMonthlyCostUsd: round2(
      WORKFORCE_MEMBERS.filter((m) => m.kind === "agent" || m.kind === "bot").reduce(
        (s, m) => s + m.monthlyCostUsd,
        0
      )
    ),
    byKind,
  };
})();

// ===========================================================================
// 2. AI SKILL MATRIX
// ===========================================================================

/** The eight AI-native skills tracked across the org. */
export const AI_SKILLS = [
  "Prompt Engineering",
  "Cursor",
  "Claude Code",
  "Databricks",
  "Copilot",
  "MCP",
  "Agent Design",
  "Model Evaluation",
] as const;

export type AiSkill = (typeof AI_SKILLS)[number];

export interface SkillRating {
  /** Proficiency, 0-100. */
  proficiency: number;
  /** Whether the person holds a certification for this skill. */
  certified: boolean;
}

export interface EmployeeSkills {
  /** References a WorkforceMember.id (humans + contractors). */
  memberId: string;
  name: string;
  ratings: Readonly<Record<AiSkill, SkillRating>>;
}

/** Helper to build a fully-typed skill row from compact tuples. */
function skillRow(
  memberId: string,
  name: string,
  values: Readonly<Record<AiSkill, [number, boolean]>>
): EmployeeSkills {
  const ratings = {} as Record<AiSkill, SkillRating>;
  for (const skill of AI_SKILLS) {
    const [proficiency, certified] = values[skill];
    ratings[skill] = { proficiency: clamp100(proficiency), certified };
  }
  return { memberId, name, ratings };
}

export const SKILL_MATRIX: ReadonlyArray<EmployeeSkills> = [
  skillRow("wf_h01", "Ava Restrepo", {
    "Prompt Engineering": [72, true],
    Cursor: [40, false],
    "Claude Code": [48, false],
    Databricks: [55, false],
    Copilot: [60, false],
    MCP: [30, false],
    "Agent Design": [35, false],
    "Model Evaluation": [58, false],
  }),
  skillRow("wf_h02", "Daniel Okoro", {
    "Prompt Engineering": [90, true],
    Cursor: [78, true],
    "Claude Code": [85, true],
    Databricks: [70, false],
    Copilot: [80, true],
    MCP: [74, false],
    "Agent Design": [82, true],
    "Model Evaluation": [88, true],
  }),
  skillRow("wf_h03", "Priya Nandakumar", {
    "Prompt Engineering": [84, true],
    Cursor: [55, false],
    "Claude Code": [60, false],
    Databricks: [48, false],
    Copilot: [66, false],
    MCP: [52, false],
    "Agent Design": [70, true],
    "Model Evaluation": [76, true],
  }),
  skillRow("wf_c01", "Sofia Marchetti", {
    "Prompt Engineering": [80, true],
    Cursor: [72, false],
    "Claude Code": [68, false],
    Databricks: [92, true],
    Copilot: [70, false],
    MCP: [58, false],
    "Agent Design": [64, false],
    "Model Evaluation": [86, true],
  }),
  skillRow("wf_c02", "Jonas Berg", {
    "Prompt Engineering": [54, false],
    Cursor: [38, false],
    "Claude Code": [42, false],
    Databricks: [30, false],
    Copilot: [50, false],
    MCP: [24, false],
    "Agent Design": [33, false],
    "Model Evaluation": [40, false],
  }),
];

// --- Skill helpers ----------------------------------------------------------

export function getSkills(memberId: string): EmployeeSkills | undefined {
  return SKILL_MATRIX.find((r) => r.memberId === memberId);
}

/** Mean proficiency across all eight skills for one person, 0-100. */
export function skillAverage(row: EmployeeSkills): number {
  return clamp100(
    mean(AI_SKILLS.map((s) => row.ratings[s].proficiency))
  );
}

export interface SkillGap {
  skill: AiSkill;
  /** Mean proficiency across the team for this skill, 0-100. */
  avgProficiency: number;
  /** How many people are below the proficiency target. */
  belowTarget: number;
  /** How many people hold a certification for this skill. */
  certifiedCount: number;
  /** Names of people most in need of upskilling (below target, lowest first). */
  needsUpskilling: ReadonlyArray<string>;
}

/**
 * Identify org-wide skill gaps. A person is "below target" for a skill when
 * their proficiency is under `target` (default 60). Returns one entry per
 * skill, sorted by widest gap (lowest average proficiency) first.
 */
export function skillGaps(target = 60): ReadonlyArray<SkillGap> {
  return AI_SKILLS.map((skill) => {
    const below = SKILL_MATRIX.filter(
      (r) => r.ratings[skill].proficiency < target
    ).sort(
      (a, b) =>
        a.ratings[skill].proficiency - b.ratings[skill].proficiency ||
        a.memberId.localeCompare(b.memberId)
    );
    return {
      skill,
      avgProficiency: clamp100(
        mean(SKILL_MATRIX.map((r) => r.ratings[skill].proficiency))
      ),
      belowTarget: below.length,
      certifiedCount: SKILL_MATRIX.filter((r) => r.ratings[skill].certified)
        .length,
      needsUpskilling: below.map((r) => r.name),
    };
  }).sort(
    (a, b) => a.avgProficiency - b.avgProficiency || a.skill.localeCompare(b.skill)
  );
}

// ===========================================================================
// 3. AI PRODUCTIVITY
// ===========================================================================

export interface Productivity {
  /** References a WorkforceMember.id. */
  memberId: string;
  name: string;
  /** Hours of manual work saved in the trailing 30 days. */
  hoursSaved: number;
  /** New automations/workflows authored in the period. */
  automationsCreated: number;
  /** Recurring manual tasks fully eliminated. */
  tasksEliminated: number;
  /** Estimated dollar value of time + tasks saved. */
  costSavingsUsd: number;
  /** Ratio of automated hours to hours personally worked (0-1+). */
  hoursAutomatedVsWorked: number;
  trend: Trend;
}

export const PRODUCTIVITY: ReadonlyArray<Productivity> = [
  {
    memberId: "wf_h01",
    name: "Ava Restrepo",
    hoursSaved: 34,
    automationsCreated: 2,
    tasksEliminated: 5,
    costSavingsUsd: 2380,
    hoursAutomatedVsWorked: 0.21,
    trend: "up",
  },
  {
    memberId: "wf_h02",
    name: "Daniel Okoro",
    hoursSaved: 71,
    automationsCreated: 6,
    tasksEliminated: 12,
    costSavingsUsd: 6960,
    hoursAutomatedVsWorked: 0.44,
    trend: "up",
  },
  {
    memberId: "wf_h03",
    name: "Priya Nandakumar",
    hoursSaved: 52,
    automationsCreated: 4,
    tasksEliminated: 8,
    costSavingsUsd: 5410,
    hoursAutomatedVsWorked: 0.33,
    trend: "flat",
  },
  {
    memberId: "wf_c01",
    name: "Sofia Marchetti",
    hoursSaved: 63,
    automationsCreated: 5,
    tasksEliminated: 9,
    costSavingsUsd: 5040,
    hoursAutomatedVsWorked: 0.39,
    trend: "up",
  },
  {
    memberId: "wf_c02",
    name: "Jonas Berg",
    hoursSaved: 18,
    automationsCreated: 1,
    tasksEliminated: 2,
    costSavingsUsd: 1080,
    hoursAutomatedVsWorked: 0.12,
    trend: "down",
  },
];

export function getProductivity(memberId: string): Productivity | undefined {
  return PRODUCTIVITY.find((p) => p.memberId === memberId);
}

/** Org-wide productivity totals and the leader by hours saved. */
export const PRODUCTIVITY_SUMMARY = (() => {
  const sorted = [...PRODUCTIVITY].sort(
    (a, b) => b.hoursSaved - a.hoursSaved || a.memberId.localeCompare(b.memberId)
  );
  return {
    totalHoursSaved: PRODUCTIVITY.reduce((s, p) => s + p.hoursSaved, 0),
    totalAutomations: PRODUCTIVITY.reduce((s, p) => s + p.automationsCreated, 0),
    totalTasksEliminated: PRODUCTIVITY.reduce((s, p) => s + p.tasksEliminated, 0),
    totalCostSavingsUsd: round2(
      PRODUCTIVITY.reduce((s, p) => s + p.costSavingsUsd, 0)
    ),
    avgHoursAutomatedVsWorked: round2(
      mean(PRODUCTIVITY.map((p) => p.hoursAutomatedVsWorked))
    ),
    topPerformerId: sorted[0]?.memberId,
  };
})();

// ===========================================================================
// 4. ONBOARDING RUNS
// ===========================================================================

/** The fixed tool set every new hire is provisioned across. */
export const ONBOARDING_TOOLS = [
  "Slack",
  "GitHub",
  "Jira",
  "Cursor",
  "Claude",
  "OpenAI",
  "Google",
  "AWS",
  "Databricks",
  "Snowflake",
] as const;

export type OnboardingTool = (typeof ONBOARDING_TOOLS)[number];

export type ProvisionStatus =
  | "provisioned"
  | "in_progress"
  | "pending"
  | "failed"
  | "skipped";

export interface ToolProvision {
  tool: OnboardingTool;
  status: ProvisionStatus;
}

export interface OnboardingVerifications {
  /** Multi-factor auth enrolled. */
  mfa: boolean;
  /** Required security/role training completed. */
  training: boolean;
  /** Acceptable-use & data policies signed. */
  policiesSigned: boolean;
  /** Access scoped to least privilege (no broad admin grants). */
  leastPrivilege: boolean;
}

export type OnboardingStatus =
  | "complete"
  | "in_progress"
  | "blocked"
  | "not_started";

export interface OnboardingRun {
  id: string;
  newHire: string;
  role: string;
  department: string;
  startDate: string;
  tools: ReadonlyArray<ToolProvision>;
  verifications: OnboardingVerifications;
  /** Overall status, derived via computeOnboardingStatus. */
  status: OnboardingStatus;
  /** Estimated days from start to fully productive. */
  timeToProductiveDays: number;
}

/** Compact helper: provision every tool to one status, then override some. */
function provisionAll(
  base: ProvisionStatus,
  overrides: Partial<Record<OnboardingTool, ProvisionStatus>> = {}
): ReadonlyArray<ToolProvision> {
  return ONBOARDING_TOOLS.map((tool) => ({
    tool,
    status: overrides[tool] ?? base,
  }));
}

/**
 * Derive an overall onboarding status from tool provisioning + verifications.
 *   - any failed tool OR any missing verification on an otherwise-done run -> blocked
 *   - all tools provisioned/skipped AND all verifications true -> complete
 *   - nothing started -> not_started
 *   - otherwise -> in_progress
 */
export function computeOnboardingStatus(
  tools: ReadonlyArray<ToolProvision>,
  verifications: OnboardingVerifications
): OnboardingStatus {
  const hasFailed = tools.some((t) => t.status === "failed");
  const allDone = tools.every(
    (t) => t.status === "provisioned" || t.status === "skipped"
  );
  const allVerified =
    verifications.mfa &&
    verifications.training &&
    verifications.policiesSigned &&
    verifications.leastPrivilege;
  const noneStarted = tools.every((t) => t.status === "pending");

  if (hasFailed) return "blocked";
  if (allDone && allVerified) return "complete";
  if (allDone && !allVerified) return "blocked";
  if (noneStarted) return "not_started";
  return "in_progress";
}

interface OnboardingRunRow {
  id: string;
  newHire: string;
  role: string;
  department: string;
  startDate: string;
  tools: ReadonlyArray<ToolProvision>;
  verifications: OnboardingVerifications;
  timeToProductiveDays: number;
}

const ONBOARDING_ROWS: ReadonlyArray<OnboardingRunRow> = [
  {
    id: "onb_01",
    newHire: "Marcus Feld",
    role: "Data Engineer",
    department: "People Analytics",
    startDate: "2026-06-08",
    tools: provisionAll("provisioned"),
    verifications: {
      mfa: true,
      training: true,
      policiesSigned: true,
      leastPrivilege: true,
    },
    timeToProductiveDays: 4,
  },
  {
    id: "onb_02",
    newHire: "Lena Sørensen",
    role: "Payroll Analyst",
    department: "Payroll Ops",
    startDate: "2026-06-22",
    tools: provisionAll("provisioned", {
      Databricks: "in_progress",
      Snowflake: "pending",
      OpenAI: "skipped",
    }),
    verifications: {
      mfa: true,
      training: false,
      policiesSigned: true,
      leastPrivilege: true,
    },
    timeToProductiveDays: 7,
  },
  {
    id: "onb_03",
    newHire: "Wei Zhang",
    role: "AI Platform Engineer",
    department: "IT Operations",
    startDate: "2026-06-25",
    tools: provisionAll("provisioned", {
      AWS: "failed",
      Snowflake: "in_progress",
    }),
    verifications: {
      mfa: true,
      training: true,
      policiesSigned: false,
      leastPrivilege: false,
    },
    timeToProductiveDays: 9,
  },
  {
    id: "onb_04",
    newHire: "Ifeoma Balogun",
    role: "Recruiting Coordinator",
    department: "Talent Acquisition",
    startDate: "2026-06-27",
    tools: provisionAll("pending"),
    verifications: {
      mfa: false,
      training: false,
      policiesSigned: false,
      leastPrivilege: false,
    },
    timeToProductiveDays: 12,
  },
];

export const ONBOARDING_RUNS: ReadonlyArray<OnboardingRun> = ONBOARDING_ROWS.map(
  (row) => ({
    ...row,
    status: computeOnboardingStatus(row.tools, row.verifications),
  })
);

// --- Onboarding helpers -----------------------------------------------------

export function getOnboardingRun(id: string): OnboardingRun | undefined {
  return ONBOARDING_RUNS.find((r) => r.id === id);
}

/** Fraction of the tool set fully provisioned (or skipped) for a run, 0-100. */
export function onboardingProgress(run: OnboardingRun): number {
  const done = run.tools.filter(
    (t) => t.status === "provisioned" || t.status === "skipped"
  ).length;
  return clamp100((done / run.tools.length) * 100);
}

/** Runs that need attention: blocked, or with any failed tool provision. */
export function onboardingNeedsAttention(): ReadonlyArray<OnboardingRun> {
  return ONBOARDING_RUNS.filter(
    (r) => r.status === "blocked" || r.tools.some((t) => t.status === "failed")
  );
}
