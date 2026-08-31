"""AI Chief People Officer (CPO) service.

This is the brain that turns Foundry People from "HR software" into a workforce
operating system. The CPO continuously synthesises signals from hiring,
attrition, payroll, PTO, performance, comp, compliance, recruiting funnel and
learning into three views:

1. PRIORITIES — concrete things that need action today, ranked.
2. RECOMMENDATIONS — proactive suggestions ("X team likely understaffed in 45d").
3. WORKFORCE HEALTH — trend deltas the CEO/owner cares about.

The CPO never makes a decision on its own. It surfaces, ranks, and routes.
Every recommendation carries a `confidence` and a list of `requires_approval_by`
roles so the human stays in the loop.

For the demo this aggregates from live DB tables where available, falls back to
the synthetic attrition demo seed when not, and uses LLM-free heuristics so the
out-of-box experience is rich.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Candidate, Case, Employee, JobPosting, PTORequest
from app.services.attrition_service import AttritionFeatures, predict_batch


# ---------------------------------------------------------------------------
@dataclass
class Priority:
    id: str
    kind: str                # hiring | onboarding | comp | risk | compliance | payroll
    title: str
    detail: str
    urgency: str             # urgent | today | this_week
    cta_label: str
    cta_href: str
    impact: str = "medium"   # low | medium | high
    icon: str = "•"

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class Recommendation:
    id: str
    headline: str
    rationale: str
    confidence: str          # low | medium | high
    requires_approval_by: list[str]
    suggested_action: str
    horizon_days: int = 0
    # True when this recommendation is about one of the illustrative people the
    # attrition model scores, rather than someone in the reader's organisation.
    # The PRIORITY above already said the model runs on sample data; the
    # recommendation did not, and the recommendation is the one that tells a
    # manager to go and have a conversation with a named person.
    is_sample: bool = False

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class HealthMetric:
    key: str
    label: str
    value: float | int
    unit: str = ""
    trend: str = "flat"       # up | down | flat
    delta_pct: float = 0.0
    band: str = "ok"          # ok | watch | alert
    note: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class CPOReport:
    generated_at: str
    org_id: str
    priorities: list[Priority]
    recommendations: list[Recommendation]
    health: list[HealthMetric]
    headline: str
    summary: str

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "org_id": self.org_id,
            "priorities": [p.to_dict() for p in self.priorities],
            "recommendations": [r.to_dict() for r in self.recommendations],
            "health": [h.to_dict() for h in self.health],
            "headline": self.headline,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
async def _safe_count(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        res = await db.execute(text(sql), params)
        row = res.first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _band_for_pending(n: int) -> str:
    if n >= 6:
        return "alert"
    if n >= 3:
        return "watch"
    return "ok"


async def build_report(db: AsyncSession, org_id: str) -> CPOReport:
    """Aggregate signals into a single CPO report."""
    org_param = {"org_id": org_id}

    # ---- Hiring + recruiting funnel
    open_jobs = await _safe_count(
        db, "select count(*) from public.job_postings where org_id=:org_id and status<>'closed'", org_param,
    )
    candidates_total = await _safe_count(
        db, "select count(*) from public.candidates where org_id=:org_id", org_param,
    )
    candidates_screened = await _safe_count(
        db,
        "select count(*) from public.candidates where org_id=:org_id and status='screened'",
        org_param,
    )
    candidates_interview = await _safe_count(
        db,
        "select count(*) from public.candidates where org_id=:org_id and status='interview'",
        org_param,
    )
    candidates_offer = await _safe_count(
        db,
        "select count(*) from public.candidates where org_id=:org_id and status='offer'",
        org_param,
    )
    candidates_hired = await _safe_count(
        db,
        "select count(*) from public.candidates where org_id=:org_id and status='hired'",
        org_param,
    )

    # ---- People
    employees_total = await _safe_count(
        db, "select count(*) from public.employees where org_id=:org_id", org_param,
    )
    employees_invited = await _safe_count(
        db,
        "select count(*) from public.employees where org_id=:org_id and status='invited'",
        org_param,
    )

    # ---- PTO
    pto_pending = await _safe_count(
        db,
        "select count(*) from public.pto_requests where org_id=:org_id and status='pending'",
        org_param,
    )

    # ---- Cases / compliance signals
    cases_high = await _safe_count(
        db,
        "select count(*) from public.cases where org_id=:org_id and severity='high' and status not in ('closed')",
        org_param,
    )
    cases_open = await _safe_count(
        db,
        "select count(*) from public.cases where org_id=:org_id and status not in ('closed')",
        org_param,
    )

    # ---- Onboarding
    onboarding_open = await _safe_count(
        db,
        "select count(*) from public.onboarding_packets where org_id=:org_id and status<>'complete'",
        org_param,
    )

    # ---- Attrition, from a SAMPLE cohort (until a production model is wired)
    #
    # The executive brief's first line read "1 high flight-risk employee need
    # attention this week" and its narrative said "Top retention concern: Avery
    # Chen." Avery Chen is one of the three invented people below, and the
    # organisation reading it has one employee. This is the most-read line in
    # the product; naming somebody's top retention risk is a claim about a
    # person, and it was about a person who does not exist.
    sample_employees = [
        AttritionFeatures("e1", "Avery Chen", department="Engineering", tenure_years=2.4, months_since_last_raise=22, months_since_last_promotion=30, performance_rating=4.5, engagement_score=0.42, compa_ratio=0.82, overtime_hours_last_30d=38),
        AttritionFeatures("e2", "Jordan Patel", department="Sales", tenure_years=1.8, months_since_last_raise=14, months_since_last_promotion=20, performance_rating=3.2, engagement_score=0.61, compa_ratio=0.97, pto_balance_days=22),
        AttritionFeatures("e5", "Riley Singh", department="Design", tenure_years=2.0, months_since_last_raise=18, months_since_last_promotion=24, performance_rating=4.8, compa_ratio=0.88, role_change_in_last_180d=True, pto_balance_days=19),
    ]
    attrition_preds = predict_batch(sample_employees)
    high_risk = [p for p in attrition_preds if p.band == "high"]

    # ---- Build priorities
    priorities: list[Priority] = []

    if cases_high:
        priorities.append(Priority(
            id="case-high", kind="compliance",
            title=f"{cases_high} high-severity case{'s' if cases_high != 1 else ''} open",
            detail="Investigations need triage. Route to HR + legal.",
            urgency="urgent", cta_label="Open ombudsman", cta_href="/app/ombudsman",
            impact="high", icon="⚠",
        ))

    if pto_pending:
        priorities.append(Priority(
            id="pto-pending", kind="hr",
            title=f"{pto_pending} PTO request{'s' if pto_pending != 1 else ''} awaiting approval",
            detail="Managers need to approve or decline. Auto-reminders are scheduled.",
            urgency="today", cta_label="Review PTO", cta_href="/app/pto",
            impact="medium", icon="🗓",
        ))

    if employees_invited:
        priorities.append(Priority(
            id="onboarding-invited", kind="onboarding",
            title=f"{employees_invited} new hire{'s' if employees_invited != 1 else ''} not yet started",
            detail="Send onboarding packets and confirm Day 1 readiness.",
            urgency="this_week", cta_label="Open onboarding", cta_href="/app/onboarding",
            impact="medium", icon="👋",
        ))

    if onboarding_open:
        priorities.append(Priority(
            id="onboarding-open", kind="onboarding",
            title=f"{onboarding_open} onboarding packet{'s' if onboarding_open != 1 else ''} in progress",
            detail="Track outstanding documents and signature steps.",
            urgency="this_week", cta_label="Track packets", cta_href="/app/onboarding",
            impact="low", icon="📨",
        ))

    if candidates_offer:
        priorities.append(Priority(
            id="offers-out", kind="hiring",
            title=f"{candidates_offer} candidate{'s' if candidates_offer != 1 else ''} at offer stage",
            detail="Decisions waiting. Don't lose high-band candidates to delay.",
            urgency="today", cta_label="Open talent", cta_href="/app/talent",
            impact="high", icon="📩",
        ))

    if candidates_interview:
        priorities.append(Priority(
            id="interviews-pending", kind="hiring",
            title=f"{candidates_interview} candidate{'s' if candidates_interview != 1 else ''} need interview feedback",
            detail="Recruiting agent can draft scorecards and schedule next rounds.",
            urgency="today", cta_label="Run recruiting agent", cta_href="/app/agents?agent=recruiting",
            impact="medium", icon="🎤",
        ))

    if high_risk:
        # A PRIORITY IS A THING TO DO THIS WEEK, ABOUT A PERSON.
        # This read "1 employee at high attrition risk · this week · IMPACT
        # HIGH · Including: Avery Chen. Drivers: comp drift + promotion delay +
        # workload." Avery Chen is in sample_employees above. Fixing the
        # headline and the narrative left this untouched, and the priorities
        # list is the part of the cockpit people actually work through.
        #
        # It is kept, because a buyer should see what the model produces — but
        # not as an urgent action, and not naming anyone as though they were on
        # the payroll.
        priorities.append(Priority(
            id="attrition-risk", kind="risk",
            title=("Attrition model is running on sample data, not your "
                   "employees"),
            detail=(f"It scored {len(sample_employees)} illustrative people and "
                    f"flagged {len(high_risk)} as high risk. To score your own "
                    "workforce it needs tenure, performance ratings, "
                    "engagement, compa-ratio and time since the last raise."),
            urgency="this_week", cta_label="Open risk engine", cta_href="/app/risk",
            impact="low", icon="🛡",
        ))

    # ---- Build recommendations (forward-looking, never auto-apply)
    recommendations: list[Recommendation] = []

    if open_jobs and candidates_total / max(open_jobs, 1) < 4:
        recommendations.append(Recommendation(
            id="rec-pipeline-thin",
            headline=f"Pipeline thin: {candidates_total} candidates for {open_jobs} open roles",
            rationale="Healthy SMB pipeline is ~5 qualified candidates per open role. Boost sourcing or syndicate to more boards.",
            confidence="high",
            requires_approval_by=["hr", "admin"],
            suggested_action="Run the recruiting agent and enable ATS syndication for open roles.",
            horizon_days=14,
        ))

    if high_risk:
        for p in high_risk[:3]:
            recommendations.append(Recommendation(
                id=f"rec-retain-{p.employee_id}",
                headline=f"Retention conversation recommended for {p.name} (sample)",
                rationale=(
                    "; ".join(p.drivers[:3])
                    + " — this is one of the illustrative people the attrition "
                      "model scores, not an employee in your organisation."
                ),
                is_sample=True,
                confidence="medium",
                requires_approval_by=["manager", "hr"],
                suggested_action=(p.suggested_actions[0] if p.suggested_actions else "Schedule a stay interview with the manager."),
                horizon_days=7,
            ))

    if cases_open and cases_high == 0:
        recommendations.append(Recommendation(
            id="rec-case-review",
            headline=f"{cases_open} case{'s' if cases_open != 1 else ''} still in investigation",
            rationale="Closing cases inside 30 days improves trust in the reporting channel.",
            confidence="medium",
            requires_approval_by=["hr", "legal"],
            suggested_action="Re-prioritise oldest case files and update reporters with status.",
            horizon_days=10,
        ))

    if employees_total >= 8 and onboarding_open == 0 and employees_invited == 0:
        recommendations.append(Recommendation(
            id="rec-workforce-plan",
            headline="Run a workforce planning agent for next quarter",
            rationale="Quiet period is the right time to model hiring growth, comp budget, and team load-balance.",
            confidence="medium",
            requires_approval_by=["owner", "hr"],
            suggested_action="Open the Workforce Planning agent.",
            horizon_days=21,
        ))

    # ---- Health
    funnel_stage_total = max(1, candidates_total)
    advance_rate = (candidates_interview + candidates_offer + candidates_hired) / funnel_stage_total
    health: list[HealthMetric] = [
        HealthMetric("headcount", "Headcount", employees_total, unit="", note=f"{employees_invited} pending Day 1"),
        HealthMetric("open_jobs", "Open requisitions", open_jobs, band=_band_for_pending(open_jobs)),
        HealthMetric("pipeline", "Candidates in pipeline", candidates_total, note=f"{int(advance_rate*100)}% advance rate"),
        HealthMetric("pto_pending", "PTO awaiting approval", pto_pending, band=_band_for_pending(pto_pending)),
        HealthMetric("cases_open", "Open cases", cases_open, band="alert" if cases_high else _band_for_pending(cases_open)),
        HealthMetric("attrition_high", "High flight-risk (sample cohort)", len(high_risk),
                     band="ok", note="illustrative — no attrition signal on your employees"),
    ]

    # ---- Headline + summary (deterministic, scannable)
    if cases_high:
        headline = "Action required: high-severity case open."
    elif candidates_offer:
        headline = f"{candidates_offer} offer{'s' if candidates_offer != 1 else ''} pending — close the loop."
    elif open_jobs:
        headline = f"{open_jobs} open requisition{'s' if open_jobs != 1 else ''}. Pipeline coverage looks "+("strong." if candidates_total >= open_jobs*5 else "thin.")
    else:
        headline = "Quiet day across hiring, risk, and compliance. Good time to plan."

    summary_parts: list[str] = [
        f"{employees_total} employee{'s' if employees_total != 1 else ''} · "
        f"{open_jobs} open role{'s' if open_jobs != 1 else ''} · "
        f"{candidates_total} candidate{'s' if candidates_total != 1 else ''} in pipeline."
    ]
    if pto_pending:
        summary_parts.append(f"{pto_pending} PTO requests need a manager decision.")
    if onboarding_open:
        summary_parts.append(f"{onboarding_open} onboarding packets in progress.")
    # The flight-risk cohort is a sample, so it neither leads the brief nor
    # names anyone as this company's retention concern. It is reported as what
    # it is, at the end, once.
    if high_risk:
        summary_parts.append(
            f"The attrition model has no signals for your employees yet; it ran "
            f"on {len(sample_employees)} sample people and flagged "
            f"{len(high_risk)} as high risk. Those names are illustrative.")
    summary = " ".join(summary_parts)

    return CPOReport(
        generated_at=datetime.utcnow().isoformat() + "Z",
        org_id=org_id,
        priorities=priorities,
        recommendations=recommendations,
        health=health,
        headline=headline,
        summary=summary,
    )
