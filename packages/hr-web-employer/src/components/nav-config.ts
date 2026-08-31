/**
 * Foundry People navigation map — CAPABILITY-FIRST.
 *
 * Design goal: EVERY major capability is one click away and clearly named.
 * The previous map buried built features (e.g. the AI Interviewer was the 7th
 * item inside a 12-item "Hiring" list, and performance was labelled only
 * "Review cycle"), so owners reported "I can't find it even though it's built".
 *
 * This map fixes that:
 *   - Groups mirror how HR leaders think: People · Recruiting · Performance ·
 *     Compensation · Equity & Stock · Learning · Analytics · Compliance · AI.
 *   - The flagship AI features (AI Interviewer, Resume AI screening, AI review
 *     drafting, comp AI, attrition, ombudsman) are surfaced at the TOP of their
 *     group and flagged `aiHinted` so the sidebar badges them.
 *   - Nothing is deleted — every route still points at an existing page.
 *
 * `aiHinted` renders an "AI" badge in the sidebar so AI-powered surfaces are
 * discoverable at a glance.
 */
import type { AppRole } from "@/lib/auth";

export type NavSection = {
  id: string;
  label: string;
  href: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  roles: AppRole[];
  /** Sub-routes shown as contextual nav once the user is inside this section. */
  children?: { label: string; href: string; aiHinted?: boolean; roles?: AppRole[] }[];
};

import {
  IconHome,
  IconPeople,
  IconHiring,
  IconPerformance,
  IconCompliance,
  IconAIOps,
  IconAnalytics,
  IconPayroll,
  IconBenefits,
} from "./icons";

const ADMIN: AppRole[] = ["owner", "admin", "hr"];
const ADMIN_MGR: AppRole[] = ["owner", "admin", "hr", "manager"];
const ALL: AppRole[] = ["owner", "admin", "hr", "manager", "employee"];

export const NAV: NavSection[] = [
  // ---------------------------------------------------------------- HOME
  {
    id: "home",
    label: "Home",
    href: "/app",
    icon: IconHome,
    roles: ALL,
    children: [
      // Action-feed home: the things that need attention today, one click away.
      { label: "Dashboard", href: "/app" },
      { label: "Work hub", href: "/app/work" },
      { label: "Command center", href: "/app/command-center", aiHinted: true, roles: ADMIN_MGR },
      { label: "Inbox", href: "/app/inbox" },
      { label: "Approvals", href: "/app/approvals" },
      { label: "Notifications", href: "/app/notifications" },
      { label: "Activity", href: "/app/activity" },
      { label: "Calendar", href: "/app/calendar" },
      { label: "Manager OS", href: "/app/manager", aiHinted: true, roles: ADMIN_MGR },
      { label: "Executive brief", href: "/app/brief", aiHinted: true, roles: ADMIN },
      { label: "Setup", href: "/app/setup", aiHinted: true, roles: ADMIN },
    ],
  },

  // ---------------------------------------------------------------- PEOPLE
  {
    id: "people",
    label: "People",
    href: "/app/people",
    icon: IconPeople,
    roles: ALL,
    children: [
      { label: "Directory", href: "/app/people" },
      { label: "Org chart", href: "/app/org" },
      { label: "Org graph", href: "/app/org-graph", aiHinted: true },
      { label: "Org design", href: "/app/org-design", aiHinted: true },
      { label: "Team workspaces", href: "/app/teams", aiHinted: true },
      { label: "Onboarding", href: "/app/onboarding" },
      { label: "AI onboarding & provisioning", href: "/app/ai-onboarding", aiHinted: true },
      { label: "Offboarding", href: "/app/offboarding" },
      { label: "Checklists", href: "/app/checklists" },
      { label: "Time off (PTO)", href: "/app/pto" },
      { label: "Documents", href: "/app/documents" },
      // Digital twin is no longer a separate destination — it is the "Twin"
      // tab on each person's unified profile (/app/people/[id]). The directory
      // above is the way in.
      { label: "People CRM", href: "/app/crm", aiHinted: true },
    ],
  },

  // ------------------------------------------------ WORKFORCE INTELLIGENCE
  // The OS for the entire workforce — humans + AI agents + contractors + bots
  // in one graph, priced against one P&L. Our answer to Mercor (which stops at
  // hiring): the Workforce Graph + Workforce Financial Intelligence.
  {
    id: "workforce-intel",
    label: "Workforce Intelligence",
    href: "/app/workforce-graph",
    icon: IconAIOps,
    roles: ADMIN_MGR,
    children: [
      { label: "Workforce graph", href: "/app/workforce-graph", aiHinted: true },
      { label: "Workforce financial intelligence", href: "/app/workforce-finance-intel", aiHinted: true },
    ],
  },

  // ---------------------------------------------------------------- GROWTH
  {
    id: "commercial",
    label: "Growth",
    href: "/app/commercial",
    icon: IconAnalytics,
    roles: ADMIN_MGR,
  },

  // ------------------------------------------------------------- TRUCKING/3PL
  // The trucking board had a complete API and no route. Every capability being
  // one click away is this file's stated design goal, and a surface with no
  // entry here is a surface nobody finds.
  {
    id: "trucking",
    label: "Trucking & 3PL",
    href: "/app/trucking",
    icon: IconPayroll,
    roles: ADMIN_MGR,
  },

  // ---------------------------------------------------------------- RECRUITING
  {
    id: "recruiting",
    label: "Recruiting",
    href: "/app/hiring",
    icon: IconHiring,
    roles: ADMIN_MGR,
    children: [
      { label: "Hiring overview", href: "/app/hiring" },
      { label: "Requisitions & pipeline", href: "/app/talent", aiHinted: true },
      { label: "AI Interviewer", href: "/app/interview-ai", aiHinted: true },
      { label: "AI interviews & recordings", href: "/app/ai-interviews", aiHinted: true },
      { label: "Adaptive interview monitor", href: "/app/interview-monitor", aiHinted: true },
      { label: "Resume AI screening", href: "/app/recruiter-cockpit", aiHinted: true },
      { label: "Interview scorecards", href: "/app/interviews/scorecards", aiHinted: true },
      { label: "Candidate integrity", href: "/app/candidate-integrity", aiHinted: true },
      { label: "Interview loop", href: "/app/interview-loop", aiHinted: true },
      { label: "Jobs & requisitions", href: "/app/recruiting" },
      { label: "Referrals", href: "/app/referrals", aiHinted: true },
      { label: "Reference checks", href: "/app/reference-check", aiHinted: true },
      { label: "JD content studio", href: "/app/content-studio", aiHinted: true },
      { label: "ATS syndication", href: "/app/ats" },
      { label: "ATS field mapping", href: "/app/ats-mapping" },
    ],
  },

  // ---------------------------------------------------------------- PERFORMANCE
  {
    id: "performance",
    label: "Performance",
    href: "/app/performance",
    icon: IconPerformance,
    roles: ALL,
    children: [
      { label: "Performance reviews", href: "/app/performance", aiHinted: true },
      { label: "Goals & OKRs", href: "/app/goals" },
      { label: "1:1s", href: "/app/one-on-ones", aiHinted: true },
      { label: "Engagement & eNPS", href: "/app/engagement", aiHinted: true },
      { label: "AI coaching", href: "/app/ai-coaching", aiHinted: true },
      { label: "AI skills matrix", href: "/app/ai-skills-matrix", aiHinted: true },
      { label: "AI productivity analytics", href: "/app/ai-productivity", aiHinted: true },
      { label: "Grow (career ladders)", href: "/app/grow", aiHinted: true },
      { label: "9-box calibration", href: "/app/calibration", aiHinted: true },
      { label: "Recognition", href: "/app/recognition" },
      { label: "Succession & talent marketplace", href: "/app/marketplace", aiHinted: true },
      { label: "Attrition & flight risk", href: "/app/risk", aiHinted: true },
    ],
  },

  // ---------------------------------------------------------------- COMPENSATION
  {
    id: "compensation",
    label: "Compensation",
    href: "/app/comp",
    icon: IconPayroll,
    roles: ADMIN_MGR,
    children: [
      { label: "Comp review cycle", href: "/app/comp", aiHinted: true },
      { label: "Pay equity", href: "/app/pay-equity", aiHinted: true },
      { label: "Bonuses", href: "/app/bonuses" },
      { label: "Market & bands", href: "/app/market" },
      { label: "Payroll dashboard", href: "/app/payroll" },
      { label: "Payroll employees", href: "/app/payroll/employees" },
      { label: "Payroll risk review", href: "/app/payroll-risk", aiHinted: true },
      { label: "Tax remittances (EFTPS)", href: "/app/payroll/remittances" },
      { label: "Tax rates & config", href: "/app/payroll/tax-config" },
      { label: "Year-end (W-2 · 1099-NEC · 940)", href: "/app/payroll/year-end" },
      { label: "Workforce finance", href: "/app/finance", aiHinted: true },
      { label: "CFO modeling", href: "/app/cfo" },
      { label: "Benefits", href: "/app/benefits", roles: ADMIN },
    ],
  },

  // ---------------------------------------------------------------- LEARNING
  {
    id: "learning",
    label: "Learning",
    href: "/app/learning",
    icon: IconPerformance,
    roles: ALL,
    children: [
      { label: "Learning paths", href: "/app/learning", aiHinted: true },
      { label: "Skills graph", href: "/app/skills", aiHinted: true },
      // Internal mobility lives at /app/marketplace — surfaced once, under
      // Performance as "Succession & talent marketplace".
    ],
  },

  // ---------------------------------------------------------------- ANALYTICS
  {
    id: "analytics",
    label: "People Analytics",
    href: "/app/analytics",
    icon: IconAnalytics,
    roles: ADMIN_MGR,
    children: [
      { label: "People analytics", href: "/app/analytics", aiHinted: true },
      { label: "HR dashboard", href: "/app/hr" },
      { label: "Reports", href: "/app/reports" },
      { label: "Predictive insights", href: "/app/insights", aiHinted: true },
      // Attrition & flight risk (/app/risk) is surfaced once, under Performance.
      { label: "Compliance dashboard", href: "/app/compliance" },
    ],
  },

  // ---------------------------------------------------------------- COMPLIANCE
  {
    id: "compliance",
    label: "Compliance",
    href: "/app/compliance",
    icon: IconCompliance,
    roles: ALL,
    children: [
      { label: "Ombudsman (confidential)", href: "/app/ombudsman", aiHinted: true },
      { label: "Cases", href: "/app/cases" },
      { label: "Investigations", href: "/app/investigations" },
      { label: "Governance decisions", href: "/app/governance", aiHinted: true },
      { label: "Policies", href: "/app/policies" },
      { label: "Escalations", href: "/app/escalations" },
      { label: "Verification", href: "/app/verification" },
      { label: "Audit views", href: "/app/audit" },
      { label: "Policy execution", href: "/app/policies-exec" },
    ],
  },

  // ---------------------------------------------------------------- AI & AUTOMATION
  {
    id: "ai",
    label: "AI & Automation",
    href: "/app/agents",
    icon: IconAIOps,
    roles: ADMIN_MGR,
    children: [
      { label: "AI assistant / helpdesk", href: "/app/assistant", aiHinted: true },
      { label: "Agents", href: "/app/agents", aiHinted: true },
      { label: "Agent store", href: "/app/agent-store", aiHinted: true },
      { label: "Automations", href: "/app/automations", aiHinted: true },
      { label: "Exec copilot", href: "/app/exec-copilot", aiHinted: true },
      { label: "Workforce AI proficiency", href: "/app/workforce-ai", aiHinted: true },
      { label: "Human + AI workforce", href: "/app/workforce-registry", aiHinted: true },
      { label: "Payroll agent trust", href: "/app/payroll-trust", aiHinted: true },
      { label: "Company memory", href: "/app/memory", aiHinted: true },
      { label: "Integrations", href: "/app/integrations" },
      { label: "Settings", href: "/app/settings", roles: ADMIN },
    ],
  },
];
