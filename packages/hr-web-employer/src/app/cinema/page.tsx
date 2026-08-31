"use client";
/**
 * /cinema — full-bleed cinematic walkthrough of Foundry People.
 *
 * Lives OUTSIDE the /app shell on purpose: no sidebar, no topbar, no chrome.
 * Designed for projector / stakeholder demos. Keyboard nav: ← → / Space /
 * 1-9 / Esc returns to the app.
 *
 * Each chapter has:
 *   - eyebrow chapter number
 *   - large title + 1-2 line subtitle
 *   - visual content (cards, stats, or mockup)
 *   - "Try it live" CTA → real surface (opens in same tab)
 *
 * Style: dark-mode cinematic. Single graphite accent. No gradients used as
 * theme — only as one subtle vignette behind the hero.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";

type Chapter = {
  id: string;
  number: string;
  eyebrow: string;
  title: string;
  subtitle: string;
  ctaLabel?: string;
  ctaHref?: string;
  visual: React.ReactNode;
};

// ---------------------------------------------------------------------------
// Chapters — comprehensive lifecycle coverage across 9 acts.
//
//   Act I  · Vision                    (2 chapters)
//   Act II · Daily operating layer     (3 chapters)
//   Act III · Hire                     (6 chapters)
//   Act IV · Onboard                   (2 chapters)
//   Act V  · Run the team              (5 chapters)
//   Act VI · Protect                   (3 chapters)
//   Act VII · Money                    (2 chapters)
//   Act VIII · Move people through org (3 chapters)
//   Act IX · AI Ops + close            (4 chapters)
//
// 30 chapters total. Each has a deep-link CTA into the real surface.
// ---------------------------------------------------------------------------
const CHAPTERS: Chapter[] = [
  // ============= ACT I · Vision =============
  {
    id: "title",
    number: "00",
    eyebrow: "Foundry People",
    title: "The AI Workforce Operating System",
    subtitle:
      "Not another HRIS. An operational brain that hires, runs, calibrates and protects the people side of the business — calm, premium, AI-native.",
    visual: <TitleHero />,
  },
  {
    id: "shift",
    number: "01",
    eyebrow: "Act I · Vision",
    title: "From forms-and-tables to operational intelligence",
    subtitle:
      "Workday, Rippling and BambooHR digitised paperwork. Foundry People runs the workflow itself — proactively, with calibrated AI in every loop.",
    visual: <ShiftGrid />,
  },

  // ============= ACT II · Daily operating layer =============
  {
    id: "command",
    number: "02",
    eyebrow: "Act II · Daily operating layer",
    title: "Workforce Command Center",
    subtitle:
      "Today's priorities, AI recommendations, workforce health — calm. Not dashboard spam.",
    ctaLabel: "Open the briefing",
    ctaHref: "/app",
    visual: <CommandMock />,
  },
  {
    id: "manager-os",
    number: "03",
    eyebrow: "Act II · Daily operating layer",
    title: "Manager OS — every manager gets a CPO",
    subtitle:
      "Daily AI briefing per manager: team health, burnout flags, overdue 1:1s, PTO conflicts, hiring recommendations, learning gaps. Proactive suggestions, not passive dashboards.",
    ctaLabel: "Open Manager OS",
    ctaHref: "/app/manager",
    visual: <ManagerOsMock />,
  },
  {
    id: "exec-brief",
    number: "04",
    eyebrow: "Act II · Daily operating layer",
    title: "Executive Brief — the morning read the CEO actually opens",
    subtitle:
      "Hiring velocity, attrition risk, comp compression, learning adoption — synthesised into a 60-second narrative. Drill-downs one click away.",
    ctaLabel: "Open Executive Brief",
    ctaHref: "/app/brief",
    visual: <ExecBriefMock />,
  },

  // ============= ACT III · Hire =============
  {
    id: "cockpit",
    number: "05",
    eyebrow: "Act III · Hire",
    title: "Recruiter Cockpit — mission control for hiring",
    subtitle:
      "AI surfaces today's priorities, detects bottlenecks per requisition, and ranks the passive pool against open roles. The recruiter starts here every morning.",
    ctaLabel: "Open the cockpit",
    ctaHref: "/app/recruiter-cockpit",
    visual: <CockpitMock />,
  },
  {
    id: "sourcing",
    number: "06",
    eyebrow: "Act III · Hire",
    title: "AI Sourcing — surface hidden talent already in your CRM",
    subtitle:
      "Semantic + skill match across every candidate you've ever touched. Adjacent-skill inference. Evidence snippets. Internal mobility flags.",
    ctaLabel: "Try AI sourcing",
    ctaHref: "/app/recruiter-cockpit",
    visual: <SourcingMock />,
  },
  {
    id: "outreach",
    number: "07",
    eyebrow: "Act III · Hire",
    title: "AI Outreach — drafted in your voice, in seconds",
    subtitle:
      "Calibrated tone (warm · direct · warm referral). Channel-aware. Splices in the candidate's strongest matching skills. First-touch + follow-up in one click.",
    ctaLabel: "Draft an email",
    ctaHref: "/app/recruiter-cockpit",
    visual: <OutreachMock />,
  },
  {
    id: "interview",
    number: "08",
    eyebrow: "Act III · Hire",
    title: "AI Interview — multimodal, calibrated, refusal-aware",
    subtitle:
      "AI reads the question aloud. Records video + live transcript in-browser. Scores on technical · communication · expression · structure · ownership. Refusals floor to zero.",
    ctaLabel: "Run an interview",
    ctaHref: "/app/interview-ai",
    visual: <InterviewMock />,
  },
  {
    id: "reference",
    number: "09",
    eyebrow: "Act III · Hire",
    title: "AI Reference Checks — multi-reference synthesis",
    subtitle:
      "Relationship-aware questions. Endorsement · specificity · candor · concern scoring. Surfaces contradictions across references — calls out the soft endorsement explicitly.",
    ctaLabel: "Start a reference check",
    ctaHref: "/app/reference-check",
    visual: <ReferenceMock />,
  },
  {
    id: "referrals",
    number: "10a",
    eyebrow: "Act III · Hire",
    title: "Referral Intelligence — AI matches employee networks to open reqs",
    subtitle:
      "Every employee carries an implicit network and skill signature. The system ranks open reqs against each employee so they know exactly where their referral lands. Reward tracking + leaderboard built in.",
    ctaLabel: "Open Referrals",
    ctaHref: "/app/referrals",
    visual: <ReferralsMock />,
  },
  {
    id: "copilot",
    number: "10a-2",
    eyebrow: "Act III · Hire",
    title: "Interview Copilot — real-time AI assist for human interviewers",
    subtitle:
      "Cluely-class real-time AI assistance — but ethical, consent-based, and connected to the rest of Foundry People. Live transcript, suggested follow-ups, fairness flags, evidence chips, AI-drafted scorecards. No hidden overlays, no cheating mode.",
    ctaLabel: "Open Copilot",
    ctaHref: "/app/interviews",
    visual: <CopilotMock />,
  },
  {
    id: "loop",
    number: "10b",
    eyebrow: "Act III · Hire",
    title: "Interview Loop Orchestration — panel debrief, calibrated",
    subtitle:
      "Solo AI Interview + 5 humans on a panel + 1 calibrated debrief. Surfaces dissent, flags variance, computes a composite — no more drift between interviewers.",
    ctaLabel: "Open Interview Loop",
    ctaHref: "/app/interview-loop",
    visual: <InterviewLoopMock />,
  },
  {
    id: "scorecard",
    number: "10",
    eyebrow: "Act III · Hire",
    title: "Scorecard Rollup — one composite, one recommendation",
    subtitle:
      "AI screen + interview overall + 5 interview dimensions + reference overall + band → composite, recommendation chain, next actions. The hiring loop is closed.",
    ctaLabel: "Roll up a candidate",
    ctaHref: "/app/recruiter-cockpit",
    visual: <ScorecardMock />,
  },

  // ============= ACT IV · Onboard =============
  {
    id: "onboarding",
    number: "11",
    eyebrow: "Act IV · Onboard",
    title: "AI Onboarding — 30/60/90 generated for every new hire",
    subtitle:
      "Role-based onboarding plans. IT setup, payroll, benefits enrollment, compliance training, manager intros — orchestrated. AI onboarding assistant answers the new hire's questions.",
    ctaLabel: "Open Onboarding",
    ctaHref: "/app/onboarding",
    visual: <OnboardingMock />,
  },
  {
    id: "documents",
    number: "12",
    eyebrow: "Act IV · Onboard",
    title: "Documents & Verification — signed, stored, audited",
    subtitle:
      "I-9, offer letters, NDAs, equipment receipts. Background + identity verification flows. Every signature, view, and edit captured in an AuditEvent.",
    ctaLabel: "Open Documents",
    ctaHref: "/app/documents",
    visual: <DocsMock />,
  },

  // ============= ACT V · Run the team =============
  {
    id: "performance",
    number: "13",
    eyebrow: "Act V · Run the team",
    title: "Performance Review — AI summary + bias detection",
    subtitle:
      "Self review · manager review · peer feedback. AI summarises reviewer language, flags vague feedback, detects bias patterns, and surfaces calibration outliers.",
    ctaLabel: "Open Performance",
    ctaHref: "/app/performance",
    visual: <PerformanceMock />,
  },
  {
    id: "comp",
    number: "14",
    eyebrow: "Act V · Run the team",
    title: "Compensation Review — AI with pay-equity overlay",
    subtitle:
      "Salary band intelligence. Pay equity scatter. Compression detection. Merit pool allocator. Recommends ranges; flags inconsistencies before they ship.",
    ctaLabel: "Open Comp Review",
    ctaHref: "/app/comp",
    visual: <CompMock />,
  },
  {
    id: "calibration",
    number: "14a",
    eyebrow: "Act V · Run the team",
    title: "9-Box Calibration — performance × potential, debiased",
    subtitle:
      "Every manager places their reports on the 3×3 grid. The system flags centrality bias, leniency bias, halo effects, and language bias before the cycle locks. Surfaces promotion-ready candidates + retention risks.",
    ctaLabel: "Open Calibration",
    ctaHref: "/app/calibration",
    visual: <CalibrationMock />,
  },
  {
    id: "goals",
    number: "15",
    eyebrow: "Act V · Run the team",
    title: "Goals & OKRs ↔ Tasks ↔ Outcomes",
    subtitle:
      "Objectives roll down into key results, key results into tasks, tasks back into review evidence. The whole loop is wired — no more goals-as-paperwork.",
    ctaLabel: "Open Goals",
    ctaHref: "/app/goals",
    visual: <GoalsMock />,
  },
  {
    id: "recognition-pulse",
    number: "16",
    eyebrow: "Act V · Run the team",
    title: "Recognition · Pulse · Wellness",
    subtitle:
      "Lightweight peer recognition that actually gets used. eNPS pulse cycles with sentiment trends. Wellness signals that feed Workforce Risk before burnout shows up in a 1:1.",
    ctaLabel: "Open Pulse",
    ctaHref: "/app/pulse",
    visual: <PulseMock />,
  },
  {
    id: "learning",
    number: "17",
    eyebrow: "Act V · Run the team",
    title: "Learning + Company Memory — Sana-style, but deeper",
    subtitle:
      "Conversational learning. Role-based plans. RAG over SOPs, policies, onboarding docs, meeting notes. Manager asks anything, gets a calibrated answer with sources.",
    ctaLabel: "Open Learning",
    ctaHref: "/app/learning",
    visual: <LearningMock />,
  },

  // ============= ACT VI · Protect =============
  {
    id: "ombudsman",
    number: "18",
    eyebrow: "Act VI · Protect",
    title: "Ombudsman — anonymous reporting, investigated with care",
    subtitle:
      "Anonymous intake. Restricted case access. AI summarises and risk-categorises without de-anonymising. Retaliation warnings on every workflow. Investigation audit trails.",
    ctaLabel: "Open Ombudsman",
    ctaHref: "/app/ombudsman",
    visual: <OmbudsmanMock />,
  },
  {
    id: "risk",
    number: "19",
    eyebrow: "Act VI · Protect",
    title: "Workforce Risk Engine — burnout, attrition, compliance",
    subtitle:
      "Continuous monitoring across PTO, performance drift, engagement, manager responsiveness, payroll anomalies. Calibrated severity. Intervention recommendations.",
    ctaLabel: "Open Risk",
    ctaHref: "/app/risk",
    visual: <RiskMock />,
  },
  {
    id: "compliance",
    number: "20",
    eyebrow: "Act VI · Protect",
    title: "Compliance · Cases · Policies · Audit",
    subtitle:
      "Case management. Policy library with execution tracking. Escalation workflows. Every state change captured in an AuditEvent — defensible by design.",
    ctaLabel: "Open Compliance",
    ctaHref: "/app/compliance",
    visual: <ComplianceMock />,
  },

  // ============= ACT VII · Money =============
  {
    id: "benefits",
    number: "21",
    eyebrow: "Act VII · Money",
    title: "Benefits + Open Enrollment + Life Events",
    subtitle:
      "Plan comparisons side-by-side. Open enrollment workflows. Life event flows (birth, marriage, move) that trigger the right downstream tasks. Benefits AI assistant for employee questions.",
    ctaLabel: "Open Benefits",
    ctaHref: "/app/benefits",
    visual: <BenefitsMock />,
  },
  {
    id: "finance",
    number: "22",
    eyebrow: "Act VII · Money",
    title: "Workforce Finance — payroll-ready, CFO-modelable",
    subtitle:
      "Pay profiles, deductions, payroll previews, GL/QuickBooks/ADP sync stubs. CFO modeling for headcount scenarios, comp band shifts, hiring plan vs. burn.",
    ctaLabel: "Open Workforce Finance",
    ctaHref: "/app/finance",
    visual: <FinanceMock />,
  },

  // ============= ACT VIII · Move people through the org =============
  {
    id: "marketplace",
    number: "23",
    eyebrow: "Act VIII · Move",
    title: "Internal Talent Marketplace",
    subtitle:
      "Employees see recommended career paths, skill gaps, internal openings, promotion readiness. Managers see hidden talent, succession candidates, future leaders.",
    ctaLabel: "Open Talent Marketplace",
    ctaHref: "/app/marketplace",
    visual: <MarketplaceMock />,
  },
  {
    id: "skills",
    number: "23a",
    eyebrow: "Act VIII · Move",
    title: "Skills Graph — clusters, adjacencies, supply vs demand",
    subtitle:
      "Skills as a navigable graph. Clusters group what goes together; adjacencies show pivot paths; supply (employees) vs demand (open reqs) surfaces where to hire, retrain, or unlock internal mobility.",
    ctaLabel: "Open Skills Graph",
    ctaHref: "/app/skills",
    visual: <SkillsGraphMock />,
  },
  {
    id: "org",
    number: "24",
    eyebrow: "Act VIII · Move",
    title: "Org Design + Org Graph — workforce topology",
    subtitle:
      "Manager span analysis. Skill distribution. Succession heatmaps. AI overlays for burnout, attrition, overloaded teams, hiring hotspots. Drag-to-restructure.",
    ctaLabel: "Open Org Graph",
    ctaHref: "/app/org-graph",
    visual: <OrgMock />,
  },
  {
    id: "offboarding",
    number: "25",
    eyebrow: "Act VIII · Move",
    title: "Offboarding & Exit — graceful, knowledge-preserving",
    subtitle:
      "Exit checklist: knowledge transfer, equipment, access removal, benefits termination. AI exit interviews with sentiment + risk analysis. Patterns surface for management.",
    ctaLabel: "Open Offboarding",
    ctaHref: "/app/offboarding",
    visual: <OffboardingMock />,
  },

  // ============= ACT IX · AI Ops + close =============
  {
    id: "agents",
    number: "26",
    eyebrow: "Act IX · AI Ops",
    title: "AI Agents + Agent Store",
    subtitle:
      "Agents orchestrate workflows: pulse cycles, comp prep, attrition outreach, compliance sweeps. Marketplace of pre-built agents you can install or fork.",
    ctaLabel: "Open Agents",
    ctaHref: "/app/agents",
    visual: <AgentsMock />,
  },
  {
    id: "automations",
    number: "26a",
    eyebrow: "Act IX · AI Ops",
    title: "Workflow Automations — when X, then Y",
    subtitle:
      "The user-facing way to wire any event (burnout flag, new hire, hiring bottleneck, ombudsman case) to a chain of actions. Library of pre-built automations + a builder for your own. Every run audit-trailed.",
    ctaLabel: "Open Automations",
    ctaHref: "/app/automations",
    visual: <AutomationsMock />,
  },
  {
    id: "analytics",
    number: "27",
    eyebrow: "Act IX · AI Ops",
    title: "Narrative Analytics — insights, not chart soup",
    subtitle:
      "AI writes the narrative the dashboard would have made you assemble manually. Hiring velocity, attrition, learning adoption, manager effectiveness — in plain English.",
    ctaLabel: "Open Analytics",
    ctaHref: "/app/analytics",
    visual: <AnalyticsMock />,
  },
  {
    id: "stack",
    number: "28",
    eyebrow: "Act IX · AI Ops",
    title: "Production-minded by default",
    subtitle:
      "FastAPI + Postgres + SQLAlchemy on the backend, 245+ routes. Next.js 14 App Router + TS + Tailwind on the front, 60+ surfaces. JWT + RBAC. Embeddings + LLM provider-agnostic.",
    visual: <StackMock />,
  },
  {
    id: "close",
    number: "29",
    eyebrow: "Why this exists",
    title: "Built for SMBs that want to operate like the best",
    subtitle:
      "Linear-calm UX. Cinematic surfaces. Agentic loops. The AI Chief People Officer the SMB market doesn't have yet — without the ERP ugliness of the ones that try.",
    ctaLabel: "Enter the app",
    ctaHref: "/app",
    visual: <CloseHero />,
  },
];

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function CinemaPage() {
  const [idx, setIdx] = useState(0);
  const [showHelp, setShowHelp] = useState(false);

  const ch = CHAPTERS[idx];
  const total = CHAPTERS.length;

  const next = useCallback(() => setIdx((i) => Math.min(total - 1, i + 1)), [total]);
  const prev = useCallback(() => setIdx((i) => Math.max(0, i - 1)), []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight" || e.key === " " || e.key === "PageDown") {
        e.preventDefault();
        next();
      } else if (e.key === "ArrowLeft" || e.key === "PageUp") {
        e.preventDefault();
        prev();
      } else if (e.key === "Home") {
        e.preventDefault();
        setIdx(0);
      } else if (e.key === "End") {
        e.preventDefault();
        setIdx(total - 1);
      } else if (e.key === "?" || e.key === "/") {
        e.preventDefault();
        setShowHelp((v) => !v);
      } else if (e.key >= "1" && e.key <= "9") {
        const n = Number(e.key) - 1;
        if (n < total) setIdx(n);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev, total]);

  return (
    <div className="min-h-screen bg-[#0B0C10] text-[#E8E8EC] flex flex-col overflow-hidden">
      {/* Subtle gradient vignette behind content */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(120,120,140,0.08), transparent 70%)",
        }}
      />

      {/* Top bar */}
      <header className="relative z-10 px-8 py-5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Logo />
          <div>
            <div className="text-xs uppercase tracking-[0.15em] text-white/40">Cinema</div>
            <div className="text-sm font-medium text-white/80">Foundry People — guided tour</div>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-white/40">
          <button
            onClick={() => setShowHelp((v) => !v)}
            className="hover:text-white/80 transition-colors"
            title="Keyboard help (?)"
          >
            ⌘ Shortcuts
          </button>
          <Link href="/app" className="hover:text-white/80 transition-colors">
            Exit to app
          </Link>
        </div>
      </header>

      {/* Slide */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-8 py-6">
        <article key={ch.id} className="w-full max-w-6xl mx-auto cinema-fade">
          <div className="text-xs uppercase tracking-[0.18em] text-white/40 mb-3">
            Chapter {ch.number} · {ch.eyebrow}
          </div>
          <h1 className="text-4xl md:text-5xl lg:text-6xl font-semibold tracking-tight leading-[1.05]">
            {ch.title}
          </h1>
          <p className="mt-4 text-base md:text-lg text-white/60 max-w-3xl leading-relaxed">
            {ch.subtitle}
          </p>

          <div className="mt-8">{ch.visual}</div>

          {ch.ctaHref && (
            <div className="mt-8 flex items-center gap-3">
              <Link
                href={ch.ctaHref}
                className="inline-flex items-center gap-2 rounded-md bg-white text-[#0B0C10] px-4 py-2 text-sm font-medium hover:bg-white/90 transition-colors"
              >
                {ch.ctaLabel ?? "Open"} →
              </Link>
              <span className="text-xs text-white/40">Live in a new tab · ⏎</span>
            </div>
          )}
        </article>
      </main>

      {/* Bottom controls */}
      <footer className="relative z-10 px-8 py-5 flex items-center justify-between text-xs text-white/40">
        <div className="flex items-center gap-1.5 flex-1 max-w-md">
          {CHAPTERS.map((c, i) => (
            <button
              key={c.id}
              onClick={() => setIdx(i)}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i === idx ? "bg-white" : i < idx ? "bg-white/30" : "bg-white/10"
              }`}
              title={`${c.number} · ${c.title}`}
            />
          ))}
        </div>
        <div className="flex items-center gap-4">
          <span>
            {String(idx + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
          </span>
          <button onClick={prev} disabled={idx === 0} className="hover:text-white/80 disabled:opacity-30">
            ← Prev
          </button>
          <button onClick={next} disabled={idx === total - 1} className="hover:text-white/80 disabled:opacity-30">
            Next →
          </button>
        </div>
      </footer>

      {/* Keyboard help overlay */}
      {showHelp && (
        <div
          className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-8"
          onClick={() => setShowHelp(false)}
        >
          <div className="bg-[#15161B] border border-white/10 rounded-lg p-6 w-full max-w-md">
            <div className="text-sm font-semibold text-white mb-3">Keyboard shortcuts</div>
            <ul className="space-y-2 text-sm text-white/70">
              <li className="flex justify-between"><span>Next slide</span><kbd>→ / Space</kbd></li>
              <li className="flex justify-between"><span>Previous</span><kbd>←</kbd></li>
              <li className="flex justify-between"><span>Jump to slide</span><kbd>1–9</kbd></li>
              <li className="flex justify-between"><span>First / Last</span><kbd>Home / End</kbd></li>
              <li className="flex justify-between"><span>Toggle this help</span><kbd>?</kbd></li>
              <li className="flex justify-between"><span>Exit to app</span><kbd>Click "Exit to app"</kbd></li>
            </ul>
            <div className="mt-4 text-xs text-white/40">Click anywhere to dismiss.</div>
          </div>
        </div>
      )}

      <style jsx global>{`
        .cinema-fade {
          animation: cinemaFade 380ms cubic-bezier(0.2, 0.7, 0.2, 1);
        }
        @keyframes cinemaFade {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        kbd {
          background: rgba(255,255,255,0.08);
          padding: 2px 6px;
          border-radius: 4px;
          font-family: ui-monospace, monospace;
          font-size: 11px;
        }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Visual primitives (lightweight, no external deps)
// ---------------------------------------------------------------------------
function Logo() {
  return (
    <div
      aria-hidden
      className="h-8 w-8 rounded-md bg-gradient-to-br from-white to-white/40 flex items-center justify-center text-[#0B0C10] font-bold text-sm"
    >
      F
    </div>
  );
}

function SlateCard({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`rounded-lg bg-white/[0.03] border border-white/10 backdrop-blur-sm ${className}`}>
      {children}
    </div>
  );
}

function Eyebrow({ children }: { children: React.ReactNode }) {
  return <div className="text-[10px] uppercase tracking-[0.18em] text-white/40">{children}</div>;
}

function StatChip({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <SlateCard className="p-3">
      <Eyebrow>{label}</Eyebrow>
      <div className="mt-1 text-xl font-semibold tabular-nums text-white">{value}</div>
      {hint && <div className="text-[11px] text-white/40 mt-0.5">{hint}</div>}
    </SlateCard>
  );
}

function Tag({ children, accent }: { children: React.ReactNode; accent?: "green" | "amber" | "red" | "blue" }) {
  const colors: Record<string, string> = {
    green: "bg-emerald-400/15 text-emerald-300 border-emerald-300/20",
    amber: "bg-amber-400/15 text-amber-300 border-amber-300/20",
    red:   "bg-rose-400/15 text-rose-300 border-rose-300/20",
    blue:  "bg-sky-400/15 text-sky-300 border-sky-300/20",
  };
  const c = accent ? colors[accent] : "bg-white/5 text-white/60 border-white/10";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${c}`}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Slide visuals
// ---------------------------------------------------------------------------
function TitleHero() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 max-w-3xl">
      <StatChip label="Domain" value="People" hint="end-to-end" />
      <StatChip label="Mode" value="Agentic" hint="AI in every loop" />
      <StatChip label="UX" value="Calm" hint="Linear / Notion" />
      <StatChip label="Built for" value="SMB→Mid" hint="not the F500" />
    </div>
  );
}

function ShiftGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl">
      <SlateCard className="p-5">
        <Eyebrow>Old enterprise HR</Eyebrow>
        <ul className="mt-3 space-y-1.5 text-sm text-white/60">
          <li>• Static dashboards</li>
          <li>• Forms-and-tables</li>
          <li>• ERP-grade clutter</li>
          <li>• Chatbot bolted on the side</li>
          <li>• Click here to submit</li>
        </ul>
      </SlateCard>
      <SlateCard className="p-5 border-white/20">
        <Eyebrow>Foundry People</Eyebrow>
        <ul className="mt-3 space-y-1.5 text-sm text-white">
          <li>• Operational intelligence</li>
          <li>• Agentic workflows</li>
          <li>• Calm cinematic UX</li>
          <li>• AI embedded in every surface</li>
          <li>• Proactive — not reactive</li>
        </ul>
      </SlateCard>
    </div>
  );
}

function CommandMock() {
  return (
    <SlateCard className="p-5 max-w-4xl">
      <Eyebrow>Today · Workforce briefing</Eyebrow>
      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatChip label="Open reqs" value="14" />
        <StatChip label="In flight" value="83" hint="across 14 reqs" />
        <StatChip label="Approvals" value="6" hint="action needed" />
        <StatChip label="Risk score" value="34" hint="moderate" />
      </div>
      <ul className="mt-4 space-y-2 text-sm">
        <li className="flex items-center gap-3"><Tag accent="red">critical</Tag><span className="text-white">Clear Interview stall on Senior Python Engineer</span><span className="text-white/40">— 11 candidates · 8d dwell · 4× target</span></li>
        <li className="flex items-center gap-3"><Tag accent="amber">alert</Tag><span className="text-white">Re-engage Marcus Patel</span><span className="text-white/40">— 21d in Applied · likely ghosted</span></li>
        <li className="flex items-center gap-3"><Tag accent="blue">watch</Tag><span className="text-white">PTO conflict on Atlas team</span><span className="text-white/40">— 3 overlapping</span></li>
      </ul>
    </SlateCard>
  );
}

function CockpitMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 max-w-5xl">
      <SlateCard className="p-4 lg:col-span-1">
        <Eyebrow>Recruiter productivity</Eyebrow>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <StatChip label="Open reqs" value="4" />
          <StatChip label="In flight" value="3" />
          <StatChip label="Added 7d" value="9" />
          <StatChip label="TTS" value="2.3d" hint="industry 2d" />
        </div>
      </SlateCard>
      <SlateCard className="p-4 lg:col-span-2">
        <Eyebrow>Today's priorities</Eyebrow>
        <ul className="mt-3 space-y-2 text-sm">
          <li className="flex items-start gap-3"><Tag accent="red">critical</Tag><span className="text-white">Clear Recruiter Review stall on Sr Designer · 5 candidates · 9d dwell</span></li>
          <li className="flex items-start gap-3"><Tag accent="amber">alert</Tag><span className="text-white">Re-engage 3 candidates stalled in Applied 14d+</span></li>
          <li className="flex items-start gap-3"><Tag accent="blue">watch</Tag><span className="text-white">Time-to-screen creeping above industry median — speed up first touch</span></li>
        </ul>
      </SlateCard>
    </div>
  );
}

function SourcingMock() {
  const matches = [
    { name: "Atiman R.", score: 84, overlap: ["fastapi", "postgres", "asyncio"], adjacent: ["llm", "embeddings"], note: "5y backend · validation pipelines" },
    { name: "Sarah K.",  score: 71, overlap: ["python", "fastapi"], adjacent: ["kubernetes", "ci/cd"], note: "Platform background" },
    { name: "Jordan P.", score: 68, overlap: ["postgres", "python"], adjacent: ["react", "next.js"], note: "Full-stack with backend lean" },
  ];
  return (
    <SlateCard className="p-5 max-w-4xl">
      <div className="flex items-center justify-between">
        <Eyebrow>AI Sourcing · Senior Python Engineer</Eyebrow>
        <span className="text-[11px] text-white/40">3 of 47 passive candidates · ranked</span>
      </div>
      <div className="mt-4 space-y-3">
        {matches.map((m) => (
          <div key={m.name} className="rounded-md border border-white/10 bg-white/[0.02] p-3 flex items-start gap-3">
            <div className="h-9 w-9 rounded-full bg-white/10 flex items-center justify-center text-xs font-semibold text-white/70">
              {m.name.split(" ").map((s) => s[0]).join("")}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-white">{m.name}</div>
              <div className="text-[11px] text-white/40">{m.note}</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {m.overlap.map((s) => <Tag key={s} accent="green">{s}</Tag>)}
                {m.adjacent.map((s) => <Tag key={s} accent="blue">+{s}</Tag>)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-xl font-semibold tabular-nums text-white">{m.score}</div>
              <div className="text-[10px] uppercase tracking-[0.15em] text-white/40">match</div>
            </div>
          </div>
        ))}
      </div>
    </SlateCard>
  );
}

function OutreachMock() {
  return (
    <SlateCard className="p-5 max-w-3xl">
      <div className="flex items-center justify-between">
        <Eyebrow>AI Outreach draft · warm · email</Eyebrow>
        <span className="text-[11px] text-white/40">Splicing 3 overlapping skills</span>
      </div>
      <div className="mt-3 rounded-md bg-black/30 border border-white/10 p-4 text-sm leading-relaxed text-white/80 font-mono whitespace-pre-wrap">
{`Subject: Atiman — quick thought on a Senior Python Engineer role

Hi Atiman — I came across your profile and wanted to reach out directly.

We're hiring a Senior Python Engineer at Foundry People. Your work on
fastapi, postgres, asyncio is exactly the kind of profile we're looking for.

I'd love 15 minutes to share what the team is working on and hear what
you're thinking about for what's next. No expectation — just a low-pressure
conversation.

— Sarah Chen, Foundry People`}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        <Tag accent="green">Tone: warm</Tag>
        <Tag accent="blue">Channel: email</Tag>
        <Tag>Skill splice: fastapi + postgres + asyncio</Tag>
      </div>
    </SlateCard>
  );
}

function InterviewMock() {
  const dims = [
    { label: "Technical", v: 71 },
    { label: "Communication", v: 78 },
    { label: "Expression", v: 92, danger: false },
    { label: "Structure", v: 65 },
    { label: "Ownership", v: 88 },
  ];
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl">
      <SlateCard className="p-5 aspect-video flex items-center justify-center">
        <div className="text-center">
          <div className="text-[10px] uppercase tracking-[0.18em] text-rose-300 mb-2">● REC · 01:24</div>
          <div className="h-32 w-32 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-white/30 text-xs mx-auto">camera</div>
          <div className="mt-3 text-xs text-white/40">Live transcript on · WPM 142 · face detected</div>
        </div>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>Multi-dim scoring</Eyebrow>
        <div className="mt-3 space-y-3">
          {dims.map((d) => (
            <div key={d.label}>
              <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.15em] text-white/40">
                <span>{d.label}</span>
                <span className="font-mono tabular-nums text-white">{d.v}</span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
                <div className="h-full bg-white/80" style={{ width: `${d.v}%` }} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 text-[11px] text-white/40">
          Refusal-aware. "I don't know" → ~0 instead of inflated baseline.
        </div>
      </SlateCard>
    </div>
  );
}

function ReferenceMock() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-4xl">
      <SlateCard className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-white">Sarah Chen</div>
            <div className="text-[11px] text-white/40">manager · 18mo</div>
          </div>
          <Tag accent="green">strong endorse · 78</Tag>
        </div>
        <div className="mt-3 text-xs text-white/60 italic">
          "Top 5% of engineers I've managed. Owned the validation pipeline end-to-end. Cut bad-entry reach-through to near zero in Q3…"
        </div>
      </SlateCard>
      <SlateCard className="p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-white">Marcus Patel</div>
            <div className="text-[11px] text-white/40">peer · 14mo</div>
          </div>
          <Tag accent="amber">lukewarm · 42</Tag>
        </div>
        <div className="mt-3 text-xs text-white/60 italic">
          "He's pretty good. I think he does fine work most of the time. Maybe could be more decisive…"
        </div>
      </SlateCard>
      <SlateCard className="p-4 md:col-span-2 border-amber-300/20 bg-amber-400/[0.04]">
        <Eyebrow>⚠ Contradiction detected</Eyebrow>
        <div className="mt-1 text-sm text-amber-100">
          References disagree on <span className="font-semibold">collaboration</span>: scores range 7–62 across 2 references.
        </div>
        <div className="mt-1 text-[11px] text-amber-200/70">
          Recommendation: schedule a brief follow-up to probe the specific reservation before final decision.
        </div>
      </SlateCard>
    </div>
  );
}

function ScorecardMock() {
  return (
    <SlateCard className="p-5 max-w-3xl">
      <div className="flex items-end justify-between">
        <div>
          <Eyebrow>Composite</Eyebrow>
          <div className="mt-1 text-5xl font-bold text-white tabular-nums">71</div>
        </div>
        <Tag accent="green">advance</Tag>
      </div>
      <div className="mt-5 grid grid-cols-3 gap-2">
        <StatChip label="AI screen" value="78" />
        <StatChip label="Interview" value="71" hint="multi-dim" />
        <StatChip label="Reference" value="65" hint="endorse" />
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div>
          <Eyebrow>Strengths</Eyebrow>
          <ul className="mt-1 text-xs text-white/70 space-y-0.5">
            <li>• Confident, on-camera communication</li>
            <li>• Strong reference signal (65/100)</li>
          </ul>
        </div>
        <div>
          <Eyebrow>Next actions</Eyebrow>
          <ul className="mt-1 text-xs text-white/70 space-y-0.5">
            <li>• Schedule onsite / final round</li>
            <li>• Add tech screener on edge-case design</li>
          </ul>
        </div>
      </div>
    </SlateCard>
  );
}

function FunnelMock() {
  const stages = [
    { label: "Applied", v: 47, w: 100 },
    { label: "AI Screened", v: 24, w: 51 },
    { label: "Review", v: 14, w: 30 },
    { label: "Interview", v: 6, w: 13 },
    { label: "Offer", v: 2, w: 4 },
    { label: "Hired", v: 1, w: 2 },
  ];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
      <SlateCard className="p-5">
        <Eyebrow>Pipeline · Senior Python Engineer · open 27d</Eyebrow>
        <div className="mt-4 space-y-2">
          {stages.map((s) => (
            <div key={s.label}>
              <div className="flex items-center justify-between text-[11px] text-white/50">
                <span>{s.label}</span>
                <span className="tabular-nums text-white">{s.v}</span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
                <div className="h-full bg-white/80" style={{ width: `${s.w}%` }} />
              </div>
            </div>
          ))}
        </div>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>Bottlenecks detected</Eyebrow>
        <div className="mt-3 space-y-2 text-sm">
          <div className="rounded-md border border-rose-300/30 bg-rose-400/[0.05] p-3">
            <div className="flex items-center justify-between"><span className="text-white font-medium">Interview stall</span><Tag accent="red">critical · 4×</Tag></div>
            <div className="text-[11px] text-white/50 mt-1">11 candidates · 8d dwell · target 7d</div>
          </div>
          <div className="rounded-md border border-amber-300/30 bg-amber-400/[0.05] p-3">
            <div className="flex items-center justify-between"><span className="text-white font-medium">Review backlog</span><Tag accent="amber">alert · 2.5×</Tag></div>
            <div className="text-[11px] text-white/50 mt-1">5 candidates · 5d dwell · target 2d</div>
          </div>
        </div>
      </SlateCard>
    </div>
  );
}

function PerformanceMock() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-5xl">
      <SlateCard className="p-4">
        <Eyebrow>Review cycle Q2</Eyebrow>
        <div className="mt-2 text-2xl font-semibold text-white tabular-nums">86% complete</div>
        <ul className="mt-3 space-y-1 text-xs text-white/60">
          <li>• 42 self · 38 manager</li>
          <li>• AI bias check passed</li>
          <li>• 3 flagged for calibration</li>
        </ul>
      </SlateCard>
      <SlateCard className="p-4">
        <Eyebrow>Comp planning</Eyebrow>
        <div className="mt-2 text-2xl font-semibold text-white tabular-nums">$642k / $720k</div>
        <ul className="mt-3 space-y-1 text-xs text-white/60">
          <li>• Pay equity overlay live</li>
          <li>• 4 compression flags</li>
          <li>• Industry P50 anchored</li>
        </ul>
      </SlateCard>
      <SlateCard className="p-4">
        <Eyebrow>Goals & OKRs</Eyebrow>
        <div className="mt-2 text-2xl font-semibold text-white tabular-nums">62% on-track</div>
        <ul className="mt-3 space-y-1 text-xs text-white/60">
          <li>• 18 objectives · 54 KRs</li>
          <li>• Linked to 132 tasks</li>
          <li>• 7 stale &gt; 14d</li>
        </ul>
      </SlateCard>
    </div>
  );
}

function AiOpsMock() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-5xl">
      <SlateCard className="p-4">
        <Eyebrow>Workforce risk</Eyebrow>
        <ul className="mt-3 space-y-1.5 text-sm">
          <li className="flex items-center gap-2"><Tag accent="red">crit</Tag><span className="text-white/80">Burnout · Atlas team</span></li>
          <li className="flex items-center gap-2"><Tag accent="amber">alert</Tag><span className="text-white/80">Attrition risk · Sr ICs</span></li>
          <li className="flex items-center gap-2"><Tag accent="blue">watch</Tag><span className="text-white/80">PTO overload Q3</span></li>
        </ul>
      </SlateCard>
      <SlateCard className="p-4">
        <Eyebrow>Company memory · RAG</Eyebrow>
        <ul className="mt-3 space-y-1.5 text-xs text-white/60">
          <li>• 142 SOPs ingested</li>
          <li>• 38 policies</li>
          <li>• 220 onboarding docs</li>
          <li>• Vector search live</li>
        </ul>
      </SlateCard>
      <SlateCard className="p-4">
        <Eyebrow>Executive brief</Eyebrow>
        <div className="mt-2 text-xs text-white/70 italic leading-relaxed">
          "Hiring velocity up 12% vs Q1. Engineering attrition risk concentrated in 2 ICs — both flagged for manager 1:1 this week. Comp compression on 4 PM roles — recommend Q3 adjustment…"
        </div>
      </SlateCard>
    </div>
  );
}

function ManagerOsMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-5xl">
      <SlateCard className="p-4">
        <Eyebrow>This morning</Eyebrow>
        <div className="mt-2 text-md font-semibold text-white">Atlas team · 8 reports</div>
        <ul className="mt-3 space-y-1.5 text-xs text-white/60">
          <li>• 2 overdue 1:1s this week</li>
          <li>• PTO conflict on June 12 (3 overlap)</li>
          <li>• Utilization 87% — above target</li>
        </ul>
      </SlateCard>
      <SlateCard className="p-4">
        <Eyebrow>AI recommendations</Eyebrow>
        <ul className="mt-3 space-y-2 text-sm">
          <li className="flex items-start gap-2"><Tag accent="amber">action</Tag><span className="text-white/85">Schedule 1:1 with Priya — burnout signal detected</span></li>
          <li className="flex items-start gap-2"><Tag accent="blue">consider</Tag><span className="text-white/85">Promotion candidate detected: Mia (8 mo over level)</span></li>
          <li className="flex items-start gap-2"><Tag accent="green">good</Tag><span className="text-white/85">Team eNPS +12 vs last cycle</span></li>
        </ul>
      </SlateCard>
      <SlateCard className="p-4">
        <Eyebrow>Hiring you can act on</Eyebrow>
        <div className="mt-2 text-xs text-white/60">2 reqs open · 14 candidates · 1 offer pending</div>
        <ul className="mt-3 space-y-1.5 text-xs text-white/70">
          <li>• Sr Designer · ready for onsite (3)</li>
          <li>• Sr PM · stalled at recruiter review</li>
        </ul>
      </SlateCard>
    </div>
  );
}

function ExecBriefMock() {
  return (
    <SlateCard className="p-6 max-w-3xl">
      <Eyebrow>Executive brief · Wednesday, May 23</Eyebrow>
      <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatChip label="Hiring velocity" value="+12%" hint="vs Q1" />
        <StatChip label="Attrition risk" value="2 ICs" hint="flagged" />
        <StatChip label="Comp compression" value="4 roles" hint="PM ladder" />
        <StatChip label="Learning adoption" value="74%" hint="+9 wow" />
      </div>
      <div className="mt-5 text-sm text-white/80 leading-relaxed font-serif italic">
        "Hiring velocity is up 12% vs Q1, driven by the engineering org closing 5 senior offers. Attrition risk is concentrated in two senior ICs — both flagged for manager 1:1 this week. Comp compression on four PM roles recommends a Q3 adjustment. Learning adoption climbed to 74% on the back of the new manager-coaching module…"
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Tag accent="green">on track</Tag>
        <Tag accent="amber">2 action items</Tag>
        <span className="text-[11px] text-white/40">Generated 06:30 · 60s read</span>
      </div>
    </SlateCard>
  );
}

function OnboardingMock() {
  const tracks = [
    { day: "Day 1",    label: "Workspace",  items: ["Laptop shipped & set up", "SSO + access provisioned", "Email + Slack live"], status: "done" },
    { day: "Day 7",    label: "Foundation", items: ["Manager 1:1 cadence", "Buddy assigned", "Codebase tour scheduled"], status: "done" },
    { day: "Day 30",   label: "Ramp",       items: ["First PR merged", "Owns 1 small feature", "All compliance trainings"], status: "active" },
    { day: "Day 60",   label: "Scope",      items: ["Owns 1 medium project", "Independent on the stack", "Peer feedback round 1"], status: "pending" },
    { day: "Day 90",   label: "Trusted",    items: ["Owns a recurring surface", "Mentors next new hire", "Confirmed against ladder"], status: "pending" },
  ];
  const tone: Record<string, "green" | "amber" | "blue"> = { done: "green", active: "amber", pending: "blue" };
  return (
    <SlateCard className="p-5 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <Eyebrow>30 / 60 / 90 · Sr Backend Engineer</Eyebrow>
          <div className="mt-1 text-sm font-semibold text-white">Atiman Rao · started May 6 · manager: Sarah Chen</div>
        </div>
        <Tag accent="green">on track · day 17</Tag>
      </div>
      <div className="mt-4 grid grid-cols-1 md:grid-cols-5 gap-3">
        {tracks.map((t) => (
          <div key={t.day} className={`rounded-md border p-3 ${t.status === "active" ? "border-amber-300/40 bg-amber-400/[0.05]" : "border-white/10 bg-white/[0.02]"}`}>
            <div className="flex items-center justify-between">
              <div className="text-[10px] uppercase tracking-[0.15em] text-white/40">{t.day}</div>
              <Tag accent={tone[t.status]}>{t.status}</Tag>
            </div>
            <div className="mt-1 text-sm font-semibold text-white">{t.label}</div>
            <ul className="mt-2 space-y-0.5 text-[11px] text-white/60">
              {t.items.map((i) => <li key={i}>• {i}</li>)}
            </ul>
          </div>
        ))}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-white/40">
        <Tag>IT setup ✓</Tag><Tag>Payroll ✓</Tag><Tag>Benefits enrolled</Tag><Tag>3/4 trainings</Tag>
        <span className="ml-auto">AI onboarding assistant answered 14 employee questions this week</span>
      </div>
    </SlateCard>
  );
}

function DocsMock() {
  const rows = [
    { name: "Offer letter", who: "Atiman Rao", status: "signed", date: "May 1" },
    { name: "I-9 verification", who: "Atiman Rao", status: "verified", date: "May 5" },
    { name: "NDA + IP assignment", who: "Atiman Rao", status: "signed", date: "May 5" },
    { name: "Equipment receipt", who: "Atiman Rao", status: "pending", date: "—" },
    { name: "Background check", who: "Atiman Rao", status: "complete", date: "May 3" },
  ];
  const tone: Record<string, "green" | "amber" | "blue"> = { signed: "green", verified: "green", complete: "green", pending: "amber" };
  return (
    <SlateCard className="p-5 max-w-3xl">
      <Eyebrow>Documents · audited end-to-end</Eyebrow>
      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="text-[10px] uppercase tracking-[0.15em] text-white/40">
            <th className="text-left font-normal pb-2">Document</th>
            <th className="text-left font-normal pb-2">Owner</th>
            <th className="text-left font-normal pb-2">Status</th>
            <th className="text-right font-normal pb-2">Date</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} className="border-t border-white/5">
              <td className="py-2 text-white">{r.name}</td>
              <td className="py-2 text-white/60">{r.who}</td>
              <td className="py-2"><Tag accent={tone[r.status]}>{r.status}</Tag></td>
              <td className="py-2 text-right text-white/60 tabular-nums">{r.date}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-3 text-[11px] text-white/40">Every view + edit logged in AuditEvent · retention policies honored</div>
    </SlateCard>
  );
}

function CompMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
      <SlateCard className="p-5">
        <Eyebrow>Pay equity overlay · IC ladder</Eyebrow>
        <div className="mt-3 relative h-44 rounded-md bg-white/[0.02] border border-white/10 p-3">
          {/* faux scatter */}
          {[
            { x: 18, y: 65, c: "white" },
            { x: 27, y: 58, c: "white" },
            { x: 35, y: 70, c: "white" },
            { x: 42, y: 50, c: "rose" },
            { x: 52, y: 38, c: "rose" },
            { x: 60, y: 42, c: "white" },
            { x: 70, y: 30, c: "white" },
            { x: 82, y: 22, c: "white" },
            { x: 50, y: 28, c: "amber" },
          ].map((p, i) => (
            <div
              key={i}
              className={`absolute h-2.5 w-2.5 rounded-full ${
                p.c === "rose" ? "bg-rose-300" : p.c === "amber" ? "bg-amber-300" : "bg-white/80"
              }`}
              style={{ left: `${p.x}%`, bottom: `${p.y}%` }}
            />
          ))}
          <div className="absolute inset-0 border-l border-b border-white/10 pointer-events-none" />
          <div className="absolute bottom-1 left-3 text-[10px] text-white/40">tenure →</div>
          <div className="absolute top-1 left-3 text-[10px] text-white/40">↑ comp</div>
        </div>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
          <Tag accent="red">2 flagged underpaid</Tag>
          <Tag accent="amber">1 outlier</Tag>
          <Tag accent="green">band P50 anchored</Tag>
        </div>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>Merit pool · Q3</Eyebrow>
        <div className="mt-3 text-2xl font-semibold text-white tabular-nums">$642k <span className="text-base text-white/40">/ $720k</span></div>
        <div className="mt-3 space-y-2">
          {[
            { label: "Engineering", v: 78, amt: "$280k" },
            { label: "Product",     v: 65, amt: "$120k" },
            { label: "Design",      v: 88, amt: "$92k" },
            { label: "Go-to-market", v: 70, amt: "$150k" },
          ].map((r) => (
            <div key={r.label}>
              <div className="flex items-center justify-between text-xs text-white/70">
                <span>{r.label}</span>
                <span className="tabular-nums text-white">{r.amt}</span>
              </div>
              <div className="mt-1 h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
                <div className="h-full bg-white/80" style={{ width: `${r.v}%` }} />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 rounded-md border border-amber-300/30 bg-amber-400/[0.05] p-3 text-xs text-amber-100">
          <span className="font-semibold">AI recommendation:</span> reallocate $18k from GTM into compression fixes on the PM ladder.
        </div>
      </SlateCard>
    </div>
  );
}

function GoalsMock() {
  return (
    <SlateCard className="p-5 max-w-4xl">
      <div className="flex items-center justify-between">
        <Eyebrow>Q2 · Reach 10k weekly active users</Eyebrow>
        <Tag accent="green">on track · 64%</Tag>
      </div>
      <div className="mt-4 space-y-3">
        {[
          { kr: "Ship onboarding v2 to 100% of new signups", v: 90, owner: "Mia · Eng", tasks: 12 },
          { kr: "Reduce activation friction by 30%",          v: 55, owner: "Atiman · Eng", tasks: 8 },
          { kr: "Launch invite-a-teammate flow",              v: 70, owner: "Priya · PM", tasks: 9 },
          { kr: "Lift week-2 retention from 24% to 38%",      v: 41, owner: "Mia · Eng", tasks: 14 },
        ].map((k) => (
          <div key={k.kr} className="rounded-md border border-white/10 bg-white/[0.02] p-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm text-white">{k.kr}</div>
              <span className="text-xs text-white/40 tabular-nums">{k.v}%</span>
            </div>
            <div className="mt-2 h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
              <div className={`h-full ${k.v >= 60 ? "bg-emerald-300" : k.v >= 40 ? "bg-amber-300" : "bg-rose-300"}`} style={{ width: `${k.v}%` }} />
            </div>
            <div className="mt-1.5 flex items-center justify-between text-[11px] text-white/40">
              <span>{k.owner}</span>
              <span>{k.tasks} tasks linked</span>
            </div>
          </div>
        ))}
      </div>
    </SlateCard>
  );
}

function PulseMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
      <SlateCard className="p-5">
        <Eyebrow>Pulse · eNPS trend</Eyebrow>
        <div className="mt-3 flex items-end gap-1.5 h-32">
          {[28, 31, 26, 34, 30, 38, 42, 44, 41, 47, 49, 52].map((v, i) => (
            <div key={i} className="flex-1 rounded-t-sm bg-emerald-300/70" style={{ height: `${(v / 60) * 100}%` }} />
          ))}
        </div>
        <div className="mt-2 flex items-center justify-between text-xs text-white/60">
          <span>eNPS +52 · ↑ 8 vs last cycle</span>
          <Tag accent="green">healthy</Tag>
        </div>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>Recognition this week</Eyebrow>
        <div className="mt-3 space-y-2">
          {[
            { from: "Sarah", to: "Mia", note: "Crushed the migration cut-over Friday." },
            { from: "Atiman", to: "Priya", note: "Saved the demo with the policy fix." },
            { from: "Jordan", to: "Sarah", note: "Best 1:1 review I've ever had." },
          ].map((r, i) => (
            <div key={i} className="rounded-md border border-white/10 bg-white/[0.02] p-3 text-sm">
              <div className="text-white">{r.from} → <span className="font-semibold">{r.to}</span></div>
              <div className="text-xs text-white/60 italic mt-0.5">"{r.note}"</div>
            </div>
          ))}
        </div>
      </SlateCard>
    </div>
  );
}

function LearningMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
      <SlateCard className="p-5">
        <Eyebrow>Role-based learning · Sr Backend Engineer</Eyebrow>
        <ul className="mt-3 space-y-2">
          {[
            { t: "Async Python in production", done: true },
            { t: "FastAPI patterns & pitfalls", done: true },
            { t: "Postgres performance & EXPLAIN", done: false },
            { t: "Designing for on-call sanity", done: false },
            { t: "Mentorship & feedback (manager track)", done: false },
          ].map((c) => (
            <li key={c.t} className="flex items-center justify-between text-sm">
              <span className={c.done ? "text-white/40 line-through" : "text-white"}>{c.t}</span>
              <Tag accent={c.done ? "green" : "blue"}>{c.done ? "done" : "queued"}</Tag>
            </li>
          ))}
        </ul>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>Company Memory · ask anything</Eyebrow>
        <div className="mt-3 rounded-md bg-black/30 border border-white/10 p-3 text-sm text-white/80 leading-relaxed">
          <div className="text-[11px] uppercase tracking-[0.15em] text-white/40">You</div>
          <div className="mt-1">What's our policy on parental leave?</div>
          <div className="mt-3 text-[11px] uppercase tracking-[0.15em] text-emerald-300/80">AI</div>
          <div className="mt-1 text-white/70">
            Foundry People offers 16 weeks of fully-paid parental leave for the primary caregiver and 6 weeks for the secondary, regardless of gender. Eligible from day one. Returns include a phased ramp option…
          </div>
          <div className="mt-2 text-[10px] text-white/40">
            Sources: policies/parental-leave-v3.md · onboarding/benefits-summary.pdf
          </div>
        </div>
      </SlateCard>
    </div>
  );
}

function OmbudsmanMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
      <SlateCard className="p-5 border-rose-300/20">
        <div className="flex items-center justify-between">
          <Eyebrow>Case #OM-204 · anonymous</Eyebrow>
          <Tag accent="red">restricted</Tag>
        </div>
        <div className="mt-3 text-sm text-white/80 leading-relaxed">
          Reporter raised concerns about pattern of behavior from a senior IC in 1:1s — characterised as dismissive and undermining toward junior reports.
        </div>
        <div className="mt-3 grid grid-cols-2 gap-2">
          <StatChip label="Intake" value="May 15" />
          <StatChip label="Severity" value="Medium" />
          <StatChip label="Assigned" value="Compliance" />
          <StatChip label="Retaliation watch" value="Active" />
        </div>
        <div className="mt-3 rounded-md border border-amber-300/30 bg-amber-400/[0.05] p-3 text-[11px] text-amber-100">
          ⚖ Confidentiality enforced. Only assigned investigators can view reporter identity (where shared). Every access logged.
        </div>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>AI investigation assist</Eyebrow>
        <ul className="mt-3 space-y-2 text-sm text-white/85">
          <li>• Summarised intake into 3 specific incidents</li>
          <li>• Risk-categorised: behavioural pattern (not policy violation yet)</li>
          <li>• Suggested interview list (manager, 2 peers, HRBP)</li>
          <li>• Drafted protective workflow if reporter re-identifies</li>
        </ul>
        <div className="mt-4 text-[11px] text-white/40">
          AI never de-anonymises. Reporter identity stays in a separately-permissioned table; the AI only sees redacted text.
        </div>
      </SlateCard>
    </div>
  );
}

function RiskMock() {
  const teams = [
    { name: "Atlas (Eng)", burnout: 72, attrition: 41, util: 87, tone: "red" },
    { name: "Helios (Eng)", burnout: 38, attrition: 22, util: 71, tone: "green" },
    { name: "Aurora (PM)", burnout: 54, attrition: 35, util: 78, tone: "amber" },
    { name: "Nova (Design)", burnout: 22, attrition: 18, util: 64, tone: "green" },
    { name: "Vega (GTM)", burnout: 61, attrition: 48, util: 82, tone: "amber" },
  ];
  return (
    <SlateCard className="p-5 max-w-5xl">
      <Eyebrow>Workforce risk · radar across 5 teams</Eyebrow>
      <table className="mt-4 w-full text-sm">
        <thead>
          <tr className="text-[10px] uppercase tracking-[0.15em] text-white/40">
            <th className="text-left font-normal pb-2">Team</th>
            <th className="text-right font-normal pb-2">Burnout</th>
            <th className="text-right font-normal pb-2">Attrition</th>
            <th className="text-right font-normal pb-2">Utilization</th>
            <th className="text-right font-normal pb-2">Severity</th>
          </tr>
        </thead>
        <tbody>
          {teams.map((t) => (
            <tr key={t.name} className="border-t border-white/5">
              <td className="py-2 text-white">{t.name}</td>
              <td className="py-2 text-right tabular-nums text-white/85">{t.burnout}</td>
              <td className="py-2 text-right tabular-nums text-white/85">{t.attrition}</td>
              <td className="py-2 text-right tabular-nums text-white/85">{t.util}%</td>
              <td className="py-2 text-right">
                <Tag accent={t.tone as "red" | "amber" | "green"}>{t.tone === "red" ? "critical" : t.tone === "amber" ? "alert" : "ok"}</Tag>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 rounded-md border border-rose-300/30 bg-rose-400/[0.05] p-3 text-xs text-rose-100">
        <span className="font-semibold">Intervention recommended:</span> Atlas team burnout score 72 has held for 3 weeks. Suggest 1:1 sweep + capacity reallocation before the next promo cycle.
      </div>
    </SlateCard>
  );
}

function ComplianceMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-5xl">
      <SlateCard className="p-4">
        <Eyebrow>Active cases</Eyebrow>
        <div className="mt-2 text-2xl font-semibold text-white tabular-nums">7</div>
        <ul className="mt-3 space-y-1 text-xs text-white/60">
          <li>• 2 open investigations</li>
          <li>• 4 in resolution</li>
          <li>• 1 awaiting reporter input</li>
        </ul>
      </SlateCard>
      <SlateCard className="p-4">
        <Eyebrow>Policy execution</Eyebrow>
        <div className="mt-2 text-2xl font-semibold text-white tabular-nums">94%</div>
        <ul className="mt-3 space-y-1 text-xs text-white/60">
          <li>• 38 active policies</li>
          <li>• 3 overdue acknowledgments</li>
          <li>• Q3 refresh queued</li>
        </ul>
      </SlateCard>
      <SlateCard className="p-4">
        <Eyebrow>Audit trail · 30d</Eyebrow>
        <div className="mt-2 text-2xl font-semibold text-white tabular-nums">12,840</div>
        <ul className="mt-3 space-y-1 text-xs text-white/60">
          <li>• Every state change captured</li>
          <li>• Searchable, exportable</li>
          <li>• SOC2 evidence-ready</li>
        </ul>
      </SlateCard>
    </div>
  );
}

function BenefitsMock() {
  const plans = [
    { name: "Anchor PPO", premium: "$420", deductible: "$1,000", oop: "$4,000", best: "Specialist visits" },
    { name: "Anchor HDHP", premium: "$210", deductible: "$3,000", oop: "$6,500", best: "Healthy + HSA savers" },
    { name: "Anchor HMO", premium: "$310", deductible: "$500", oop: "$3,000", best: "Lowest out-of-pocket" },
  ];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-5xl">
      {plans.map((p, i) => (
        <SlateCard key={p.name} className={`p-5 ${i === 1 ? "border-white/30" : ""}`}>
          <div className="flex items-center justify-between">
            <Eyebrow>Plan</Eyebrow>
            {i === 1 && <Tag accent="green">AI pick for you</Tag>}
          </div>
          <div className="mt-1 text-md font-semibold text-white">{p.name}</div>
          <div className="mt-4 text-2xl font-semibold text-white tabular-nums">{p.premium}<span className="text-sm text-white/40">/mo</span></div>
          <ul className="mt-3 space-y-1 text-xs text-white/60">
            <li>Deductible · <span className="text-white tabular-nums">{p.deductible}</span></li>
            <li>OOP max · <span className="text-white tabular-nums">{p.oop}</span></li>
            <li>Best for · <span className="text-white">{p.best}</span></li>
          </ul>
        </SlateCard>
      ))}
      <SlateCard className="p-4 lg:col-span-3">
        <div className="flex items-center justify-between">
          <Eyebrow>Open enrollment · 38 of 64 enrolled</Eyebrow>
          <Tag accent="amber">closes June 1</Tag>
        </div>
        <div className="mt-2 h-1.5 w-full rounded-full bg-white/5 overflow-hidden">
          <div className="h-full bg-white/80" style={{ width: "59%" }} />
        </div>
        <div className="mt-2 text-[11px] text-white/40">Life events (birth, marriage, move) auto-trigger qualified change flows.</div>
      </SlateCard>
    </div>
  );
}

function FinanceMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-5xl">
      <SlateCard className="p-5 lg:col-span-2">
        <Eyebrow>Payroll preview · pay period ending May 31</Eyebrow>
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          <StatChip label="Headcount" value="64" />
          <StatChip label="Gross" value="$842k" />
          <StatChip label="Taxes + ER" value="$184k" />
          <StatChip label="Net to bank" value="$586k" />
        </div>
        <div className="mt-3 rounded-md border border-emerald-300/30 bg-emerald-400/[0.05] p-3 text-xs text-emerald-100">
          ✓ Reconciles against last period within $1.2k variance. No anomalies detected.
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-white/40">
          <Tag>GL export ready</Tag>
          <Tag>QuickBooks sync stub</Tag>
          <Tag>ADP sync stub</Tag>
          <Tag>Guideline / Human Interest</Tag>
        </div>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>CFO modeling · 6mo hiring plan</Eyebrow>
        <ul className="mt-3 space-y-1 text-xs text-white/70">
          <li>Scenario A · plan: +12 hires · burn +$184k/mo</li>
          <li>Scenario B · trim: +8 hires · burn +$112k/mo</li>
          <li>Scenario C · pause: 0 hires · burn flat</li>
        </ul>
        <div className="mt-3 rounded-md border border-white/10 p-2 text-[11px] text-white/50">
          AI: Scenario B preserves runway through Q4 while still closing the engineering velocity gap.
        </div>
      </SlateCard>
    </div>
  );
}

function MarketplaceMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 max-w-5xl">
      <SlateCard className="p-5">
        <Eyebrow>Recommended for you · Mia</Eyebrow>
        <ul className="mt-3 space-y-2">
          {[
            { role: "Tech Lead · Atlas team", fit: 84, why: "Strongest match on backend depth + mentorship signal." },
            { role: "Founding Engineer · Vega", fit: 71, why: "Adjacent stack + early-stage appetite from your survey." },
            { role: "Eng Manager track", fit: 66, why: "Promotion readiness signal up 18% vs last cycle." },
          ].map((r) => (
            <li key={r.role} className="rounded-md border border-white/10 bg-white/[0.02] p-3 flex items-start justify-between gap-3">
              <div>
                <div className="text-sm font-medium text-white">{r.role}</div>
                <div className="text-[11px] text-white/50 mt-0.5">{r.why}</div>
              </div>
              <div className="text-right">
                <div className="text-xl font-semibold text-white tabular-nums">{r.fit}</div>
                <div className="text-[10px] uppercase tracking-[0.15em] text-white/40">fit</div>
              </div>
            </li>
          ))}
        </ul>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>Manager view · hidden talent</Eyebrow>
        <ul className="mt-3 space-y-2 text-sm">
          <li className="flex items-start gap-2"><Tag accent="green">succession</Tag><span className="text-white/85">Priya — ready for Eng Manager next cycle</span></li>
          <li className="flex items-start gap-2"><Tag accent="blue">stretch</Tag><span className="text-white/85">Atiman — capacity for staff-level scope</span></li>
          <li className="flex items-start gap-2"><Tag accent="amber">underutilised</Tag><span className="text-white/85">Jordan — adjacent skills not currently leveraged</span></li>
        </ul>
      </SlateCard>
    </div>
  );
}

function OrgMock() {
  return (
    <SlateCard className="p-5 max-w-5xl">
      <div className="flex items-center justify-between">
        <Eyebrow>Org graph · manager span analysis</Eyebrow>
        <Tag accent="amber">2 spans overloaded</Tag>
      </div>
      <div className="mt-4 grid grid-cols-1 md:grid-cols-4 gap-2 text-xs">
        {[
          { mgr: "Sarah Chen · VP Eng", span: 11, tone: "red", note: "Above 8 target" },
          { mgr: "James Lin · Eng Mgr", span: 7, tone: "green", note: "Healthy" },
          { mgr: "Priya N · PM Lead", span: 9, tone: "amber", note: "Watch" },
          { mgr: "Alex M · Design Lead", span: 5, tone: "green", note: "Healthy" },
          { mgr: "Dana C · GTM Lead", span: 12, tone: "red", note: "Restructure recommended" },
          { mgr: "Sam K · Ops Lead", span: 4, tone: "green", note: "Healthy" },
          { mgr: "Robin T · Data Lead", span: 6, tone: "green", note: "Healthy" },
          { mgr: "Quinn P · CX Lead", span: 8, tone: "green", note: "At target" },
        ].map((r) => (
          <div key={r.mgr} className="rounded-md border border-white/10 bg-white/[0.02] p-3">
            <div className="text-[11px] text-white/50 truncate">{r.mgr}</div>
            <div className="mt-1 flex items-baseline justify-between">
              <div className="text-xl font-semibold text-white tabular-nums">{r.span}</div>
              <Tag accent={r.tone as "red" | "amber" | "green"}>{r.note}</Tag>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
        <SlateCard className="p-3"><Eyebrow>Skill distribution</Eyebrow><div className="mt-1 text-white/70">Backend-heavy. Frontend gap on Atlas team.</div></SlateCard>
        <SlateCard className="p-3"><Eyebrow>Succession heatmap</Eyebrow><div className="mt-1 text-white/70">2 ready-now for Eng Manager. 0 for VP Eng.</div></SlateCard>
        <SlateCard className="p-3"><Eyebrow>Hiring hotspots</Eyebrow><div className="mt-1 text-white/70">Atlas team needs 2 senior ICs; PM ladder needs 1 IC4.</div></SlateCard>
      </div>
    </SlateCard>
  );
}

function OffboardingMock() {
  const items = [
    { name: "Exit interview booked", done: true },
    { name: "Knowledge transfer doc started", done: true },
    { name: "On-call rotation handed over", done: true },
    { name: "Access removal queued for last day", done: false },
    { name: "Equipment shipping label sent", done: false },
    { name: "Benefits termination + COBRA letter", done: false },
    { name: "Final paycheck + PTO payout reconciled", done: false },
  ];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 max-w-5xl">
      <SlateCard className="p-5 lg:col-span-2">
        <Eyebrow>Offboarding checklist · Jordan P · last day June 7</Eyebrow>
        <ul className="mt-3 space-y-1.5">
          {items.map((i) => (
            <li key={i.name} className="flex items-center gap-2 text-sm">
              <span className={`h-4 w-4 rounded border flex items-center justify-center text-[10px] ${i.done ? "border-emerald-300/60 bg-emerald-300/20 text-emerald-200" : "border-white/15"}`}>
                {i.done ? "✓" : ""}
              </span>
              <span className={i.done ? "text-white/40 line-through" : "text-white/85"}>{i.name}</span>
            </li>
          ))}
        </ul>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>AI exit interview · sentiment</Eyebrow>
        <div className="mt-3 text-3xl font-semibold text-white tabular-nums">+0.34</div>
        <div className="text-[11px] text-white/40">Net positive · would refer</div>
        <ul className="mt-3 space-y-1 text-xs text-white/70">
          <li>+ Praised mentorship culture</li>
          <li>+ Recommended ramp-up onboarding</li>
          <li>– Frustrated by comp band ceiling</li>
          <li>– Wanted more cross-team mobility</li>
        </ul>
        <div className="mt-3 rounded-md border border-amber-300/30 bg-amber-400/[0.05] p-2 text-[11px] text-amber-100">
          Pattern: 3 of last 5 exits cited comp band ceiling. Surface to comp review.
        </div>
      </SlateCard>
    </div>
  );
}

function AgentsMock() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-5xl">
      {[
        { name: "Pulse cycle agent", run: "Daily 06:00", note: "Runs eNPS, sentiments, sends digest", tone: "green" as const },
        { name: "Comp prep agent", run: "Weekly Mon", note: "Pre-builds comp scenarios for Friday review", tone: "blue" as const },
        { name: "Attrition outreach", run: "On signal", note: "Drafts manager talk track on attrition flag", tone: "amber" as const },
        { name: "Compliance sweep", run: "Monthly 1st", note: "Audits policy acknowledgments, drafts nudges", tone: "blue" as const },
        { name: "Onboarding orchestrator", run: "Per new hire", note: "30/60/90 plan + IT + benefits + intros", tone: "green" as const },
        { name: "Ombudsman intake", run: "On report", note: "Risk-categorises + drafts investigation plan", tone: "amber" as const },
      ].map((a) => (
        <SlateCard key={a.name} className="p-4">
          <div className="flex items-center justify-between">
            <Eyebrow>{a.run}</Eyebrow>
            <Tag accent={a.tone}>active</Tag>
          </div>
          <div className="mt-1 text-sm font-semibold text-white">{a.name}</div>
          <div className="mt-1 text-xs text-white/60">{a.note}</div>
        </SlateCard>
      ))}
    </div>
  );
}

function AnalyticsMock() {
  return (
    <SlateCard className="p-6 max-w-3xl">
      <Eyebrow>Narrative insight · Engineering org · week of May 19</Eyebrow>
      <div className="mt-4 text-sm text-white/85 leading-relaxed font-serif italic">
        "Engineering shipped 38% more closed PRs vs last week, driven primarily by Atlas team's migration push. Attrition risk has dropped from 2 signals to 1 after Priya's manager skip-level. Recognition density climbed 22% — most of it directed at the senior IC ladder, which historically correlates with sustained retention. One watch: time-on-ramp for the 4 May new hires is trending 1.4× the team median; an onboarding orchestrator sweep is recommended."
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Tag accent="green">PRs +38%</Tag>
        <Tag accent="green">Recognition +22%</Tag>
        <Tag accent="amber">Ramp 1.4× median</Tag>
        <Tag>3 follow-ups suggested</Tag>
      </div>
    </SlateCard>
  );
}

function ReferralsMock() {
  const matches = [
    { role: "Senior Python Engineer", score: 92, skills: ["python", "fastapi", "postgres"], net: ["ex-Stripe"], reward: 5000 },
    { role: "Founding ML Engineer",   score: 78, skills: ["python", "llm"],                 net: ["ex-Coinbase"],   reward: 7500 },
    { role: "Sr Frontend Engineer",   score: 51, skills: ["typescript"],                    net: ["Berkeley CS"],   reward: 4000 },
  ];
  return (
    <SlateCard className="p-5 max-w-4xl">
      <Eyebrow>Your network · matches for you · Atiman Rao</Eyebrow>
      <div className="mt-4 space-y-3">
        {matches.map((m) => (
          <div key={m.role} className="rounded-md border border-white/10 bg-white/[0.02] p-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white">{m.role}</div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {m.skills.map((s) => <Tag key={s} accent="green">{s}</Tag>)}
                {m.net.map((s) => <Tag key={s} accent="blue">network · {s}</Tag>)}
              </div>
            </div>
            <div className="text-right shrink-0">
              <div className="text-2xl font-semibold tabular-nums text-white">{m.score}</div>
              <div className="text-[10px] uppercase tracking-[0.15em] text-white/40">match</div>
              <div className="mt-1 text-sm font-medium text-emerald-300">${m.reward.toLocaleString()}</div>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3 text-[11px] text-white/40">Skill overlap + ex-employer + alma mater signals weighted into one match score.</div>
    </SlateCard>
  );
}

function CopilotMock() {
  return (
    <div className="grid grid-cols-12 gap-3 max-w-5xl">
      {/* Consent banner */}
      <SlateCard className="col-span-12 p-3 border-emerald-300/30 bg-emerald-400/[0.04]">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="text-xs text-emerald-100">
            <span className="font-semibold">Consent granted</span> — both parties recorded consent before transcript began. AI assistance is for the interviewer only.
          </div>
          <div className="flex gap-2">
            <Tag accent="green">candidate · granted</Tag>
            <Tag accent="green">interviewer · granted</Tag>
          </div>
        </div>
      </SlateCard>

      {/* Three-column live room */}
      <SlateCard className="col-span-12 md:col-span-4 p-3">
        <Eyebrow>● Live transcript</Eyebrow>
        <div className="mt-2 space-y-1 text-xs text-white/80">
          <div><span className="text-white/40 uppercase tracking-[0.15em] mr-2">candidate</span>I led the migration from Django to async FastAPI…</div>
          <div><span className="text-white/40 uppercase tracking-[0.15em] mr-2">candidate</span>It dropped p95 latency by about 40% in three months.</div>
          <div><span className="text-white/40 uppercase tracking-[0.15em] mr-2">interviewer</span>What surprised you most about the cut-over?</div>
          <div className="text-white/30 italic">Listening…</div>
        </div>
      </SlateCard>

      <SlateCard className="col-span-12 md:col-span-4 p-3">
        <Eyebrow>Question guide · 5/9 asked</Eyebrow>
        <ul className="mt-2 space-y-1 text-xs">
          <li className="text-white/40 line-through">Walk me through a complex decision</li>
          <li className="text-white/40 line-through">Tell me about a system you owned end-to-end</li>
          <li className="text-white">Describe a real disagreement with a peer</li>
          <li className="text-white">What would you do differently next time?</li>
        </ul>
        <div className="mt-3"><Eyebrow>Scorecard mapping</Eyebrow></div>
        <ul className="mt-1 space-y-1 text-xs text-white/70">
          <li className="flex items-center justify-between"><span>technical depth</span><Tag accent="green">architecture, trade-off</Tag></li>
          <li className="flex items-center justify-between"><span>ownership</span><Tag accent="green">"I led", end-to-end</Tag></li>
          <li className="flex items-center justify-between"><span>communication</span><Tag>no signal yet</Tag></li>
        </ul>
      </SlateCard>

      <SlateCard className="col-span-12 md:col-span-4 p-3 border-white/20">
        <Eyebrow>AI Copilot · suggestions</Eyebrow>
        <div className="mt-2 rounded-md border border-white/10 bg-white/[0.02] p-2 text-xs">
          <div className="text-white/80 italic">"Candidate cited p95 + 40% — solid numerical specificity. Communication competency still has no transcript signal."</div>
        </div>
        <div className="mt-3 space-y-2 text-xs">
          <div className="rounded-md border border-white/10 bg-white/[0.02] p-2">
            <div className="text-white">Can you put a number on the team size and cost?</div>
            <div className="text-[10px] text-white/40">technical_depth · no quantitative scope yet</div>
          </div>
          <div className="rounded-md border border-white/10 bg-white/[0.02] p-2">
            <div className="text-white">How did you communicate the cut-over to non-engineers?</div>
            <div className="text-[10px] text-white/40">communication · probe to close the gap</div>
          </div>
        </div>
        <div className="mt-3 rounded-md border border-amber-300/30 bg-amber-400/[0.05] p-2 text-[10px] text-amber-100">
          ⚠ Fairness flag: question about "family status" detected in interviewer draft. Suggested rephrase ready.
        </div>
      </SlateCard>
    </div>
  );
}

function InterviewLoopMock() {
  const panel = [
    { name: "Sarah Chen",    role: "Recruiter screen", rating: 3, label: "hire" },
    { name: "James Lin",      role: "Tech screen",      rating: 3, label: "hire" },
    { name: "Priya N",        role: "System design",    rating: 4, label: "strong hire" },
    { name: "Dana C",         role: "Coding",           rating: 3, label: "hire" },
    { name: "Quinn P",        role: "Values + fit",     rating: 1, label: "lean no hire" },
  ];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-5xl">
      <SlateCard className="p-5 lg:col-span-2">
        <Eyebrow>Panel · 5 interviewers</Eyebrow>
        <ul className="mt-3 space-y-2">
          {panel.map((p) => (
            <li key={p.name} className="flex items-center justify-between rounded-md border border-white/10 bg-white/[0.02] px-3 py-2">
              <div>
                <div className="text-sm font-medium text-white">{p.name}</div>
                <div className="text-[11px] text-white/40">{p.role}</div>
              </div>
              <Tag accent={p.rating >= 3 ? "green" : p.rating >= 2 ? "amber" : "red"}>{p.label}</Tag>
            </li>
          ))}
        </ul>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>Calibrated debrief</Eyebrow>
        <div className="mt-2 text-3xl font-bold text-white tabular-nums">71</div>
        <Tag accent="amber">advance with caveats</Tag>
        <div className="mt-3 rounded-md border border-amber-300/30 bg-amber-400/[0.05] p-3 text-[11px] text-amber-100">
          <span className="font-semibold">Dissent:</span> Quinn P. rated lean-no-hire (3 below median). Schedule a longer debrief to probe the specific concern before deciding.
        </div>
        <ul className="mt-3 space-y-1 text-[11px] text-white/60">
          <li>+ Consensus: strong system-design depth</li>
          <li>– Consensus: weak on the values question</li>
        </ul>
      </SlateCard>
    </div>
  );
}

function CalibrationMock() {
  // 3x3 grid, top-right = stars
  const grid: Record<string, string[]> = {
    "1-3": [],          "2-3": ["Jordan"],  "3-3": ["Atiman", "Mia"],
    "1-2": [],          "2-2": ["Marcus", "Robin"], "3-2": ["Priya"],
    "1-1": [],          "2-1": [],          "3-1": ["Dana"],
  };
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-5xl">
      <SlateCard className="p-5 lg:col-span-2">
        <Eyebrow>9-box · performance × potential</Eyebrow>
        <div className="mt-4 grid grid-cols-3 gap-2">
          {[3, 2, 1].map((pot) => (
            [1, 2, 3].map((perf) => {
              const key = `${perf}-${pot}`;
              const items = grid[key] ?? [];
              const hot = perf === 3 && pot >= 2;
              return (
                <div key={key} className={`min-h-[88px] rounded-md border bg-white/[0.02] p-2 ${hot ? "border-white/40" : "border-white/10"}`}>
                  <div className="text-[10px] uppercase tracking-[0.15em] text-white/40">{key}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {items.map((n) => <Tag key={n} accent={hot ? "green" : "blue"}>{n}</Tag>)}
                  </div>
                </div>
              );
            })
          )).flat()}
        </div>
      </SlateCard>
      <SlateCard className="p-5">
        <Eyebrow>Manager bias flags</Eyebrow>
        <ul className="mt-3 space-y-2 text-[11px] text-white/80">
          <li className="flex items-start gap-2"><Tag accent="amber">leniency</Tag>James Lin · avg perf 2.8 across 6 reports</li>
          <li className="flex items-start gap-2"><Tag accent="red">centrality</Tag>Dana C · all 5 reports placed in same row</li>
          <li className="flex items-start gap-2"><Tag accent="amber">language</Tag>2 rationale fields contain gender-coded phrases</li>
        </ul>
      </SlateCard>
    </div>
  );
}

function SkillsGraphMock() {
  const clusters = [
    { name: "Python backend", sup: 8, dem: 12, health: "amber" as const },
    { name: "Frontend / React", sup: 6, dem: 4, health: "green" as const },
    { name: "AI / ML", sup: 2, dem: 7, health: "red" as const },
    { name: "Platform / DevOps", sup: 5, dem: 3, health: "green" as const },
    { name: "Data engineering", sup: 4, dem: 5, health: "amber" as const },
    { name: "Design", sup: 3, dem: 1, health: "green" as const },
  ];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 max-w-5xl">
      {clusters.map((c) => (
        <SlateCard key={c.name} className="p-4">
          <div className="flex items-start justify-between">
            <div>
              <Eyebrow>Cluster</Eyebrow>
              <div className="text-sm font-semibold text-white mt-1">{c.name}</div>
            </div>
            <Tag accent={c.health === "red" ? "red" : c.health === "amber" ? "amber" : "green"}>
              {c.health === "red" ? "critical" : c.health === "amber" ? "watch" : "ok"}
            </Tag>
          </div>
          <div className="mt-3 flex items-end justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.15em] text-white/40">Supply</div>
              <div className="text-lg font-semibold text-white tabular-nums">{c.sup}</div>
            </div>
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-[0.15em] text-white/40">Demand</div>
              <div className="text-lg font-semibold text-white tabular-nums">{c.dem}</div>
            </div>
            <div className="text-right">
              <div className="text-[10px] uppercase tracking-[0.15em] text-white/40">Gap</div>
              <div className={`text-lg font-semibold tabular-nums ${c.dem - c.sup > 0 ? "text-amber-300" : "text-emerald-300"}`}>
                {c.dem - c.sup > 0 ? `+${c.dem - c.sup}` : c.dem - c.sup}
              </div>
            </div>
          </div>
        </SlateCard>
      ))}
    </div>
  );
}

function AutomationsMock() {
  const autos = [
    { name: "Burnout → manager talk track + 1:1", trigger: "risk.burnout", actions: 3, status: "active" as const },
    { name: "New hire day 1 → onboarding orchestrator", trigger: "onboarding.day_1", actions: 3, status: "active" as const },
    { name: "Hiring bottleneck → recruiter sweep", trigger: "hiring.bottleneck", actions: 2, status: "active" as const },
    { name: "Pay compression → comp prep agent", trigger: "comp.compression", actions: 2, status: "queued" as const },
    { name: "Weekly Monday → Executive Brief email", trigger: "schedule.weekly", actions: 2, status: "active" as const },
    { name: "Monthly → compliance ack sweep", trigger: "schedule.monthly", actions: 3, status: "active" as const },
  ];
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 max-w-5xl">
      {autos.map((a) => (
        <SlateCard key={a.name} className="p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white">{a.name}</div>
              <div className="mt-1 flex flex-wrap gap-1">
                <Tag accent="blue">trigger · {a.trigger}</Tag>
                <Tag>{a.actions} actions</Tag>
              </div>
            </div>
            <Tag accent={a.status === "active" ? "green" : "amber"}>{a.status}</Tag>
          </div>
        </SlateCard>
      ))}
    </div>
  );
}

function StackMock() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 max-w-4xl">
      {[
        { title: "Backend", body: "FastAPI · async SQLAlchemy · Postgres · JWT + RBAC" },
        { title: "Frontend", body: "Next.js 14 App Router · TS · Tailwind · React Query" },
        { title: "AI layer", body: "Embeddings abstraction · LLM provider-agnostic · RAG-ready" },
        { title: "Real-time", body: "Realtime bootstrap · audit events · decision inbox" },
      ].map((c) => (
        <SlateCard key={c.title} className="p-4">
          <Eyebrow>{c.title}</Eyebrow>
          <div className="mt-2 text-xs text-white/70 leading-relaxed">{c.body}</div>
        </SlateCard>
      ))}
    </div>
  );
}

function CloseHero() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 max-w-3xl">
      <StatChip label="60+" value="surfaces" hint="employer + employee" />
      <StatChip label="245+" value="API routes" hint="FastAPI" />
      <StatChip label="9" value="primary nav" hint="≤ 9 to reduce load" />
      <StatChip label="100%" value="AI-embedded" hint="not a chatbot tab" />
    </div>
  );
}
