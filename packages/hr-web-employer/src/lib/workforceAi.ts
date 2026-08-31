// Workforce AI Proficiency + Payroll Agent Trust
//
// Deterministic mock data and scoring for two HR surfaces:
//
//   1. "Workforce AI Proficiency" — how effectively each employee works *with*
//      AI, scored across the 4 D's popularized by CubeBench:
//        - Delegation:  picking the right tasks to hand to AI
//        - Description: writing clear, well-scoped prompts / specs
//        - Discernment: judging and correcting AI output
//        - Diligence:   verifying, citing, and owning the result
//
//   2. "Payroll Agent Trust" — how much we can trust the payroll automation
//      agent, scored across accuracy, policy compliance, approval coverage,
//      sensitive-data handling, and anomaly recovery.
//
// All data below is fixed at authoring time. Scores are derived purely from
// these rows via the exported helpers — there is NO Math.random() (or any
// other nondeterminism) evaluated at module load, so the same inputs always
// produce the same outputs and snapshots stay stable.

// ---------------------------------------------------------------------------
// Shared scoring primitives
// ---------------------------------------------------------------------------

export type Trend = "up" | "down" | "flat";

export type Severity = "low" | "medium" | "high" | "critical";

/** Clamp a number into the inclusive [0, 100] band and round to an integer. */
export function clamp100(n: number): number {
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

/**
 * Weighted average of sub-dimension scores. Weights need not sum to 1; they
 * are normalized. Returns a clamped 0-100 integer.
 */
export function weightedScore(
  parts: ReadonlyArray<{ value: number; weight: number }>
): number {
  let weighted = 0;
  let totalWeight = 0;
  for (const { value, weight } of parts) {
    weighted += value * weight;
    totalWeight += weight;
  }
  if (totalWeight <= 0) return 0;
  return clamp100(weighted / totalWeight);
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

export type ScoreBand = "strong" | "solid" | "developing" | "at-risk";

export function scoreBand(n: number): ScoreBand {
  const v = clamp100(n);
  if (v >= 85) return "strong";
  if (v >= 70) return "solid";
  if (v >= 55) return "developing";
  return "at-risk";
}

// ===========================================================================
// 1. WORKFORCE AI PROFICIENCY
// ===========================================================================

export interface Employee {
  id: string;
  name: string;
  team: string;
  role: string;
}

/** The 4 D's, scored 0-100. */
export interface FourDs {
  /** Choosing which work to route to AI vs. keep human. */
  delegation: number;
  /** Quality of prompting / task specification. */
  description: number;
  /** Judging, fact-checking, and correcting AI output. */
  discernment: number;
  /** Verifying, sourcing, and owning the final deliverable. */
  diligence: number;
}

export interface EmployeeAiProficiency {
  employeeId: string;
  /** The four sub-dimensions. */
  scores: FourDs;
  /** Weighted overall (see FOUR_D_WEIGHTS); derived, also cached here. */
  overall: number;
  /** Trailing 30-day AI spend attributable to this employee, USD. */
  aiCostUsd: number;
  /** AI sessions in the trailing 30 days. */
  sessions: number;
  /** Direction of overall score vs. the prior period. */
  trend: Trend;
}

export interface TeamProficiency {
  team: string;
  headcount: number;
  /** Mean of the 4 D's across the team. */
  scores: FourDs;
  /** Weighted overall for the team. */
  overall: number;
  aiCostUsd: number;
  sessions: number;
  trend: Trend;
}

export interface AiSession {
  id: string;
  employeeId: string;
  task: string;
  model: string;
  tokens: number;
  costUsd: number;
  /** Reviewer-assigned output quality, 0-100. */
  quality: number;
  /** ISO-8601 timestamp. */
  at: string;
}

export interface CoachingSuggestion {
  id: string;
  employeeId: string;
  /** Which of the 4 D's this targets. */
  dimension: keyof FourDs;
  title: string;
  detail: string;
  priority: Severity;
}

export interface ManagerNote {
  id: string;
  employeeId: string;
  author: string;
  note: string;
  at: string;
}

/**
 * Relative importance of each D when rolling up to an overall proficiency
 * score. Discernment and diligence are weighted highest because unverified AI
 * output is where org risk concentrates.
 */
export const FOUR_D_WEIGHTS: Readonly<Record<keyof FourDs, number>> = {
  delegation: 0.2,
  description: 0.25,
  discernment: 0.3,
  diligence: 0.25,
};

// --- Employees -------------------------------------------------------------

export const EMPLOYEES: ReadonlyArray<Employee> = [
  { id: "emp_01", name: "Ava Restrepo", team: "Payroll Ops", role: "Payroll Specialist" },
  { id: "emp_02", name: "Daniel Okoro", team: "Payroll Ops", role: "Payroll Lead" },
  { id: "emp_03", name: "Mei-Lin Chu", team: "People Analytics", role: "Analyst" },
  { id: "emp_04", name: "Sofia Marchetti", team: "People Analytics", role: "Senior Analyst" },
  { id: "emp_05", name: "Tarek Haddad", team: "HR Business Partners", role: "HRBP" },
  { id: "emp_06", name: "Priya Nandakumar", team: "HR Business Partners", role: "Lead HRBP" },
  { id: "emp_07", name: "Jonas Berg", team: "Talent Acquisition", role: "Recruiter" },
  { id: "emp_08", name: "Renata Alves", team: "Talent Acquisition", role: "Sourcing Lead" },
];

// --- Per-employee proficiency (raw 4 D's; overall is derived) --------------

interface ProficiencyRow {
  employeeId: string;
  scores: FourDs;
  aiCostUsd: number;
  sessions: number;
  trend: Trend;
}

const PROFICIENCY_ROWS: ReadonlyArray<ProficiencyRow> = [
  {
    employeeId: "emp_01",
    scores: { delegation: 78, description: 71, discernment: 64, diligence: 82 },
    aiCostUsd: 142.5,
    sessions: 96,
    trend: "up",
  },
  {
    employeeId: "emp_02",
    scores: { delegation: 91, description: 88, discernment: 90, diligence: 93 },
    aiCostUsd: 268.4,
    sessions: 154,
    trend: "up",
  },
  {
    employeeId: "emp_03",
    scores: { delegation: 62, description: 58, discernment: 49, diligence: 55 },
    aiCostUsd: 73.2,
    sessions: 41,
    trend: "down",
  },
  {
    employeeId: "emp_04",
    scores: { delegation: 84, description: 86, discernment: 81, diligence: 88 },
    aiCostUsd: 311.0,
    sessions: 188,
    trend: "flat",
  },
  {
    employeeId: "emp_05",
    scores: { delegation: 69, description: 64, discernment: 58, diligence: 60 },
    aiCostUsd: 58.9,
    sessions: 33,
    trend: "up",
  },
  {
    employeeId: "emp_06",
    scores: { delegation: 88, description: 90, discernment: 85, diligence: 87 },
    aiCostUsd: 197.6,
    sessions: 121,
    trend: "up",
  },
  {
    employeeId: "emp_07",
    scores: { delegation: 53, description: 47, discernment: 44, diligence: 51 },
    aiCostUsd: 64.7,
    sessions: 29,
    trend: "down",
  },
  {
    employeeId: "emp_08",
    scores: { delegation: 76, description: 79, discernment: 72, diligence: 74 },
    aiCostUsd: 129.3,
    sessions: 88,
    trend: "flat",
  },
];

// --- Derived overall proficiency -------------------------------------------

/** Weighted overall AI-proficiency score for a single employee's 4 D's. */
export function fourDsOverall(scores: FourDs): number {
  return weightedScore([
    { value: scores.delegation, weight: FOUR_D_WEIGHTS.delegation },
    { value: scores.description, weight: FOUR_D_WEIGHTS.description },
    { value: scores.discernment, weight: FOUR_D_WEIGHTS.discernment },
    { value: scores.diligence, weight: FOUR_D_WEIGHTS.diligence },
  ]);
}

/**
 * Overall proficiency for an employee. Accepts either an `EmployeeAiProficiency`
 * record or a bare `FourDs` object.
 */
export function overallProficiency(
  emp: EmployeeAiProficiency | FourDs
): number {
  const scores = "scores" in emp ? emp.scores : emp;
  return fourDsOverall(scores);
}

export const EMPLOYEE_PROFICIENCY: ReadonlyArray<EmployeeAiProficiency> =
  PROFICIENCY_ROWS.map((row) => ({
    employeeId: row.employeeId,
    scores: row.scores,
    overall: fourDsOverall(row.scores),
    aiCostUsd: row.aiCostUsd,
    sessions: row.sessions,
    trend: row.trend,
  }));

// --- Team rollups ----------------------------------------------------------

function mean(values: ReadonlyArray<number>): number {
  if (values.length === 0) return 0;
  return values.reduce((a, b) => a + b, 0) / values.length;
}

function rollupTrend(trends: ReadonlyArray<Trend>): Trend {
  const up = trends.filter((t) => t === "up").length;
  const down = trends.filter((t) => t === "down").length;
  if (up > down) return "up";
  if (down > up) return "down";
  return "flat";
}

function buildTeamProficiency(): ReadonlyArray<TeamProficiency> {
  const teams = Array.from(new Set(EMPLOYEES.map((e) => e.team)));
  return teams.map((team) => {
    const ids = new Set(
      EMPLOYEES.filter((e) => e.team === team).map((e) => e.id)
    );
    const members = EMPLOYEE_PROFICIENCY.filter((p) => ids.has(p.employeeId));
    const scores: FourDs = {
      delegation: clamp100(mean(members.map((m) => m.scores.delegation))),
      description: clamp100(mean(members.map((m) => m.scores.description))),
      discernment: clamp100(mean(members.map((m) => m.scores.discernment))),
      diligence: clamp100(mean(members.map((m) => m.scores.diligence))),
    };
    return {
      team,
      headcount: members.length,
      scores,
      overall: fourDsOverall(scores),
      aiCostUsd:
        Math.round(members.reduce((s, m) => s + m.aiCostUsd, 0) * 100) / 100,
      sessions: members.reduce((s, m) => s + m.sessions, 0),
      trend: rollupTrend(members.map((m) => m.trend)),
    };
  });
}

export const TEAM_PROFICIENCY: ReadonlyArray<TeamProficiency> =
  buildTeamProficiency();

// --- AI sessions -----------------------------------------------------------

export const AI_SESSIONS: ReadonlyArray<AiSession> = [
  {
    id: "ses_1001",
    employeeId: "emp_02",
    task: "Reconcile Q2 payroll variance report",
    model: "claude-opus-4",
    tokens: 48210,
    costUsd: 9.64,
    quality: 94,
    at: "2026-06-22T09:14:00Z",
  },
  {
    id: "ses_1002",
    employeeId: "emp_01",
    task: "Draft deduction-change confirmation emails",
    model: "claude-sonnet-4",
    tokens: 12380,
    costUsd: 1.11,
    quality: 81,
    at: "2026-06-22T11:02:00Z",
  },
  {
    id: "ses_1003",
    employeeId: "emp_03",
    task: "Summarize attrition cohort analysis",
    model: "claude-haiku-3.5",
    tokens: 9050,
    costUsd: 0.36,
    quality: 52,
    at: "2026-06-23T08:48:00Z",
  },
  {
    id: "ses_1004",
    employeeId: "emp_04",
    task: "Build comp-band benchmarking model",
    model: "claude-opus-4",
    tokens: 61740,
    costUsd: 12.35,
    quality: 89,
    at: "2026-06-23T14:30:00Z",
  },
  {
    id: "ses_1005",
    employeeId: "emp_06",
    task: "Generate manager talking points for RIF",
    model: "claude-sonnet-4",
    tokens: 18920,
    costUsd: 1.7,
    quality: 86,
    at: "2026-06-24T10:05:00Z",
  },
  {
    id: "ses_1006",
    employeeId: "emp_07",
    task: "Screen inbound resumes for backend role",
    model: "claude-haiku-3.5",
    tokens: 7600,
    costUsd: 0.3,
    quality: 44,
    at: "2026-06-24T13:41:00Z",
  },
  {
    id: "ses_1007",
    employeeId: "emp_08",
    task: "Write sourcing outreach sequence",
    model: "claude-sonnet-4",
    tokens: 14100,
    costUsd: 1.27,
    quality: 73,
    at: "2026-06-25T09:20:00Z",
  },
  {
    id: "ses_1008",
    employeeId: "emp_05",
    task: "Interpret engagement survey free-text",
    model: "claude-sonnet-4",
    tokens: 22480,
    costUsd: 2.02,
    quality: 60,
    at: "2026-06-25T15:55:00Z",
  },
  {
    id: "ses_1009",
    employeeId: "emp_02",
    task: "Audit overtime calculations vs. policy",
    model: "claude-opus-4",
    tokens: 39870,
    costUsd: 7.97,
    quality: 92,
    at: "2026-06-26T08:10:00Z",
  },
  {
    id: "ses_1010",
    employeeId: "emp_04",
    task: "Forecast headcount cost for FY27 plan",
    model: "claude-opus-4",
    tokens: 55300,
    costUsd: 11.06,
    quality: 84,
    at: "2026-06-26T16:22:00Z",
  },
];

// --- Coaching suggestions --------------------------------------------------

export const COACHING_SUGGESTIONS: ReadonlyArray<CoachingSuggestion> = [
  {
    id: "coach_01",
    employeeId: "emp_03",
    dimension: "discernment",
    title: "Verify AI-summarized figures before sharing",
    detail:
      "Two attrition summaries this month restated headline numbers incorrectly. Add a habit of spot-checking AI output against the source table before circulating.",
    priority: "high",
  },
  {
    id: "coach_02",
    employeeId: "emp_07",
    dimension: "description",
    title: "Tighten resume-screening prompts",
    detail:
      "Screening prompts omit must-have criteria, so the model returns low-precision shortlists. Use the role rubric template to specify required skills explicitly.",
    priority: "high",
  },
  {
    id: "coach_03",
    employeeId: "emp_07",
    dimension: "diligence",
    title: "Document why each candidate was passed",
    detail:
      "Add a one-line rationale per rejected candidate so decisions are auditable and bias-reviewable.",
    priority: "medium",
  },
  {
    id: "coach_04",
    employeeId: "emp_01",
    dimension: "discernment",
    title: "Cross-check deduction changes against policy",
    detail:
      "Before sending confirmation emails, reconcile the AI-proposed deduction against the benefits policy of record.",
    priority: "medium",
  },
  {
    id: "coach_05",
    employeeId: "emp_05",
    dimension: "delegation",
    title: "Route sensitive survey text through review",
    detail:
      "Free-text engagement responses can contain PII and complaints. Delegate first-pass theming to AI, but flag sensitive items for human escalation.",
    priority: "low",
  },
];

// --- Manager notes ---------------------------------------------------------

export const MANAGER_NOTES: ReadonlyArray<ManagerNote> = [
  {
    id: "note_01",
    employeeId: "emp_02",
    author: "Priya Nandakumar",
    note: "Daniel's payroll variance reconciliation with Opus saved roughly a day of manual work and caught a real rounding bug.",
    at: "2026-06-22T17:30:00Z",
  },
  {
    id: "note_02",
    employeeId: "emp_03",
    author: "Sofia Marchetti",
    note: "Paired with Mei-Lin on discernment; she now re-derives any AI-stated metric before it leaves the team.",
    at: "2026-06-23T12:15:00Z",
  },
  {
    id: "note_03",
    employeeId: "emp_07",
    author: "Renata Alves",
    note: "Jonas is over-trusting first-pass shortlists. Enrolled him in the prompting clinic next week.",
    at: "2026-06-24T18:00:00Z",
  },
  {
    id: "note_04",
    employeeId: "emp_06",
    author: "Tarek Haddad",
    note: "Priya's RIF talking points were balanced and policy-aware; reused as a team template.",
    at: "2026-06-24T20:40:00Z",
  },
];

// --- Leaderboards ----------------------------------------------------------

const RANKED_BY_OVERALL = [...EMPLOYEE_PROFICIENCY].sort(
  (a, b) => b.overall - a.overall || a.employeeId.localeCompare(b.employeeId)
);

/** Highest overall proficiency first. */
export const TOP_PERFORMERS: ReadonlyArray<EmployeeAiProficiency> =
  RANKED_BY_OVERALL.slice(0, 3);

/** Anyone below the "solid" threshold (70), lowest first. */
export const NEEDS_SUPPORT: ReadonlyArray<EmployeeAiProficiency> =
  RANKED_BY_OVERALL.filter((p) => p.overall < 70).sort(
    (a, b) => a.overall - b.overall || a.employeeId.localeCompare(b.employeeId)
  );

// --- Lookups ---------------------------------------------------------------

export function getEmployee(id: string): Employee | undefined {
  return EMPLOYEES.find((e) => e.id === id);
}

export function getProficiency(
  employeeId: string
): EmployeeAiProficiency | undefined {
  return EMPLOYEE_PROFICIENCY.find((p) => p.employeeId === employeeId);
}

export function sessionsForEmployee(
  employeeId: string
): ReadonlyArray<AiSession> {
  return AI_SESSIONS.filter((s) => s.employeeId === employeeId);
}

export function coachingForEmployee(
  employeeId: string
): ReadonlyArray<CoachingSuggestion> {
  return COACHING_SUGGESTIONS.filter((c) => c.employeeId === employeeId);
}

export function notesForEmployee(
  employeeId: string
): ReadonlyArray<ManagerNote> {
  return MANAGER_NOTES.filter((n) => n.employeeId === employeeId);
}

// ===========================================================================
// 2. PAYROLL AGENT TRUST
// ===========================================================================

export type PayrollRunStatus =
  | "draft"
  | "in_review"
  | "approved"
  | "paid"
  | "blocked";

export interface PayrollRun {
  id: string;
  /** Pay period, e.g. "2026-06 (1st half)". */
  period: string;
  grossUsd: number;
  /** Number of employees in the run. */
  employees: number;
  status: PayrollRunStatus;
  /** Whether the payroll agent assisted in preparing this run. */
  aiAssisted: boolean;
  /** Count of anomalies surfaced on this run. */
  anomalyCount: number;
  /** Derived trust score for this run (also computed via payrollTrustScore). */
  trustScore: number;
}

export interface PayrollAlert {
  id: string;
  title: string;
  severity: Severity;
  /** ISO-8601 timestamp. */
  detectedAt: string;
  runId: string;
  /** Human-readable evidence describing why this alert fired. */
  evidence: string;
}

/** Trust sub-dimensions, each scored 0-100. */
export interface PayrollTrustDimensions {
  /** Are computed amounts correct vs. ground truth? */
  accuracy: number;
  /** Do actions respect comp/benefits/tax policy? */
  policyCompliance: number;
  /** Were required human approvals obtained before action? */
  approvalCoverage: number;
  /** Was PII / sensitive comp data handled correctly? */
  sensitiveDataHandling: number;
  /** When something went wrong, how well did it recover/roll back? */
  anomalyRecovery: number;
}

export interface PayrollTrustScore {
  runId: string;
  dimensions: PayrollTrustDimensions;
  /** Weighted overall trust score, 0-100. */
  overall: number;
  band: ScoreBand;
}

export interface PayrollEvidenceItem {
  id: string;
  runId: string;
  /** ISO-8601 timestamp of the action. */
  at: string;
  /** Who/what performed it. */
  actor: string;
  /** The payroll action taken. */
  action: string;
  /** Whether a human approved this action. */
  approved: boolean;
  /** Optional supporting reference (ticket, policy id, etc.). */
  reference?: string;
}

/**
 * Weights for rolling payroll trust sub-dimensions into an overall score.
 * Accuracy and policy compliance dominate; approval coverage is a strong
 * secondary signal for an *agent* acting on money movement.
 */
export const PAYROLL_TRUST_WEIGHTS: Readonly<
  Record<keyof PayrollTrustDimensions, number>
> = {
  accuracy: 0.3,
  policyCompliance: 0.25,
  approvalCoverage: 0.2,
  sensitiveDataHandling: 0.15,
  anomalyRecovery: 0.1,
};

// --- Per-run trust sub-dimensions (raw) ------------------------------------

interface RunTrustRow {
  runId: string;
  dimensions: PayrollTrustDimensions;
}

const RUN_TRUST_ROWS: ReadonlyArray<RunTrustRow> = [
  {
    runId: "run_2026_05_a",
    dimensions: {
      accuracy: 97,
      policyCompliance: 95,
      approvalCoverage: 98,
      sensitiveDataHandling: 96,
      anomalyRecovery: 90,
    },
  },
  {
    runId: "run_2026_05_b",
    dimensions: {
      accuracy: 93,
      policyCompliance: 88,
      approvalCoverage: 91,
      sensitiveDataHandling: 94,
      anomalyRecovery: 82,
    },
  },
  {
    runId: "run_2026_06_a",
    dimensions: {
      accuracy: 71,
      policyCompliance: 58,
      approvalCoverage: 49,
      sensitiveDataHandling: 80,
      anomalyRecovery: 64,
    },
  },
  {
    runId: "run_2026_06_b",
    dimensions: {
      accuracy: 86,
      policyCompliance: 79,
      approvalCoverage: 74,
      sensitiveDataHandling: 88,
      anomalyRecovery: 77,
    },
  },
];

const RUN_TRUST_BY_ID = new Map(RUN_TRUST_ROWS.map((r) => [r.runId, r.dimensions]));

/** Weighted overall payroll trust from a set of sub-dimensions. */
export function trustDimensionsOverall(
  dimensions: PayrollTrustDimensions
): number {
  return weightedScore([
    { value: dimensions.accuracy, weight: PAYROLL_TRUST_WEIGHTS.accuracy },
    {
      value: dimensions.policyCompliance,
      weight: PAYROLL_TRUST_WEIGHTS.policyCompliance,
    },
    {
      value: dimensions.approvalCoverage,
      weight: PAYROLL_TRUST_WEIGHTS.approvalCoverage,
    },
    {
      value: dimensions.sensitiveDataHandling,
      weight: PAYROLL_TRUST_WEIGHTS.sensitiveDataHandling,
    },
    {
      value: dimensions.anomalyRecovery,
      weight: PAYROLL_TRUST_WEIGHTS.anomalyRecovery,
    },
  ]);
}

/**
 * Trust score for a payroll run. Accepts either a `PayrollRun` (looks up its
 * recorded sub-dimensions) or a `PayrollTrustDimensions` object directly.
 * Returns the 0-100 overall.
 */
export function payrollTrustScore(
  run: PayrollRun | PayrollTrustDimensions
): number {
  if ("dimensions" in run || "id" in run) {
    const dims = RUN_TRUST_BY_ID.get((run as PayrollRun).id);
    if (dims) return trustDimensionsOverall(dims);
    // Fall back to the trustScore already stamped on the run.
    return clamp100((run as PayrollRun).trustScore);
  }
  return trustDimensionsOverall(run as PayrollTrustDimensions);
}

export const PAYROLL_TRUST_SCORES: ReadonlyArray<PayrollTrustScore> =
  RUN_TRUST_ROWS.map((row) => {
    const overall = trustDimensionsOverall(row.dimensions);
    return {
      runId: row.runId,
      dimensions: row.dimensions,
      overall,
      band: scoreBand(overall),
    };
  });

const TRUST_SCORE_BY_RUN = new Map(
  PAYROLL_TRUST_SCORES.map((t) => [t.runId, t.overall])
);

// --- Payroll runs ----------------------------------------------------------

interface PayrollRunRow {
  id: string;
  period: string;
  grossUsd: number;
  employees: number;
  status: PayrollRunStatus;
  aiAssisted: boolean;
  anomalyCount: number;
}

const PAYROLL_RUN_ROWS: ReadonlyArray<PayrollRunRow> = [
  {
    id: "run_2026_05_a",
    period: "2026-05 (1st half)",
    grossUsd: 1842300,
    employees: 412,
    status: "paid",
    aiAssisted: true,
    anomalyCount: 1,
  },
  {
    id: "run_2026_05_b",
    period: "2026-05 (2nd half)",
    grossUsd: 1857940,
    employees: 414,
    status: "paid",
    aiAssisted: true,
    anomalyCount: 2,
  },
  {
    id: "run_2026_06_a",
    period: "2026-06 (1st half)",
    grossUsd: 2104880,
    employees: 419,
    status: "blocked",
    aiAssisted: true,
    anomalyCount: 4,
  },
  {
    id: "run_2026_06_b",
    period: "2026-06 (2nd half)",
    grossUsd: 1889120,
    employees: 421,
    status: "in_review",
    aiAssisted: true,
    anomalyCount: 2,
  },
];

export const PAYROLL_RUNS: ReadonlyArray<PayrollRun> = PAYROLL_RUN_ROWS.map(
  (row) => ({
    ...row,
    trustScore: TRUST_SCORE_BY_RUN.get(row.id) ?? 0,
  })
);

// --- Payroll alerts --------------------------------------------------------

export const PAYROLL_ALERTS: ReadonlyArray<PayrollAlert> = [
  {
    id: "alert_01",
    title: "Payroll Agent changed deduction without approval",
    severity: "critical",
    detectedAt: "2026-06-26T07:42:00Z",
    runId: "run_2026_06_a",
    evidence:
      "Agent reduced the 401(k) deduction for 3 employees from 6% to 4% citing a 'plan update', but no benefits-policy change ticket exists and no approver signed off. Action proceeded to the draft register before review.",
  },
  {
    id: "alert_02",
    title: "Overtime calculation needs review",
    severity: "high",
    detectedAt: "2026-06-26T08:05:00Z",
    runId: "run_2026_06_a",
    evidence:
      "11 hourly employees show overtime computed at 1.0x instead of 1.5x for hours beyond 40/week. Estimated underpayment $4,120 across the cohort.",
  },
  {
    id: "alert_03",
    title: "Contractor classification risk detected",
    severity: "high",
    detectedAt: "2026-06-25T16:18:00Z",
    runId: "run_2026_06_b",
    evidence:
      "2 workers paid as 1099 contractors have full-time hours, a fixed schedule, and company-issued equipment — patterns that trip the IRS common-law worker test and suggest possible misclassification.",
  },
  {
    id: "alert_04",
    title: "Payroll run has unusual variance from prior period",
    severity: "medium",
    detectedAt: "2026-06-26T07:55:00Z",
    runId: "run_2026_06_a",
    evidence:
      "Gross pay is up 13.3% vs. the prior half ($2,104,880 vs. $1,857,940) with only a +5 headcount change. Variance is concentrated in a single cost center and exceeds the 5% review threshold.",
  },
  {
    id: "alert_05",
    title: "Payroll run has unusual variance from prior period",
    severity: "low",
    detectedAt: "2026-06-12T09:30:00Z",
    runId: "run_2026_05_b",
    evidence:
      "Gross pay moved +0.8% vs. prior half, within tolerance; logged for trail completeness only.",
  },
];

// --- Payroll evidence (audit trail) ----------------------------------------

export const PAYROLL_EVIDENCE: ReadonlyArray<PayrollEvidenceItem> = [
  {
    id: "ev_01",
    runId: "run_2026_06_a",
    at: "2026-06-25T22:10:00Z",
    actor: "Payroll Agent",
    action: "Imported time & attendance data for 419 employees",
    approved: true,
    reference: "import:tna-2026-06a",
  },
  {
    id: "ev_02",
    runId: "run_2026_06_a",
    at: "2026-06-25T22:41:00Z",
    actor: "Payroll Agent",
    action: "Computed gross pay and statutory deductions",
    approved: true,
    reference: "calc:gross-2026-06a",
  },
  {
    id: "ev_03",
    runId: "run_2026_06_a",
    at: "2026-06-25T23:02:00Z",
    actor: "Payroll Agent",
    action: "Lowered 401(k) deduction 6% -> 4% for 3 employees",
    approved: false,
    reference: "delta:deduction-401k",
  },
  {
    id: "ev_04",
    runId: "run_2026_06_a",
    at: "2026-06-26T07:42:00Z",
    actor: "Anomaly Monitor",
    action: "Flagged unapproved deduction change; blocked run",
    approved: true,
    reference: "alert_01",
  },
  {
    id: "ev_05",
    runId: "run_2026_06_a",
    at: "2026-06-26T09:15:00Z",
    actor: "Daniel Okoro",
    action: "Reverted deduction change pending policy verification",
    approved: true,
    reference: "alert_01",
  },
  {
    id: "ev_06",
    runId: "run_2026_06_b",
    at: "2026-06-25T08:55:00Z",
    actor: "Payroll Agent",
    action: "Classified 2 new workers as 1099 contractors",
    approved: false,
    reference: "delta:classification",
  },
  {
    id: "ev_07",
    runId: "run_2026_06_b",
    at: "2026-06-25T16:18:00Z",
    actor: "Compliance Monitor",
    action: "Raised contractor classification risk for HRBP review",
    approved: true,
    reference: "alert_03",
  },
  {
    id: "ev_08",
    runId: "run_2026_05_a",
    at: "2026-05-10T21:30:00Z",
    actor: "Payroll Agent",
    action: "Prepared and submitted run for approval",
    approved: true,
    reference: "submit:2026-05a",
  },
  {
    id: "ev_09",
    runId: "run_2026_05_a",
    at: "2026-05-11T10:05:00Z",
    actor: "Priya Nandakumar",
    action: "Approved run and released payment",
    approved: true,
    reference: "approve:2026-05a",
  },
];

// --- Org-level payroll trust rollup ----------------------------------------

/** Mean trust across all scored runs, with the worst run called out. */
export const PAYROLL_TRUST_SUMMARY = (() => {
  const overall = clamp100(mean(PAYROLL_TRUST_SCORES.map((t) => t.overall)));
  const sorted = [...PAYROLL_TRUST_SCORES].sort((a, b) => a.overall - b.overall);
  return {
    overall,
    band: scoreBand(overall),
    color: scoreColor(overall),
    lowestRunId: sorted[0]?.runId,
    highestRunId: sorted[sorted.length - 1]?.runId,
    openCriticalAlerts: PAYROLL_ALERTS.filter((a) => a.severity === "critical")
      .length,
  };
})();

// --- Lookups ---------------------------------------------------------------

export function getPayrollRun(id: string): PayrollRun | undefined {
  return PAYROLL_RUNS.find((r) => r.id === id);
}

export function getRunTrust(runId: string): PayrollTrustScore | undefined {
  return PAYROLL_TRUST_SCORES.find((t) => t.runId === runId);
}

export function alertsForRun(runId: string): ReadonlyArray<PayrollAlert> {
  return PAYROLL_ALERTS.filter((a) => a.runId === runId);
}

export function evidenceForRun(
  runId: string
): ReadonlyArray<PayrollEvidenceItem> {
  return PAYROLL_EVIDENCE.filter((e) => e.runId === runId).sort((a, b) =>
    a.at.localeCompare(b.at)
  );
}
