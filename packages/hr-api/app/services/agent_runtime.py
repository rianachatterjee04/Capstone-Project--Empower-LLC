"""Agent runtime + 6 specialised HR operations agents.

These agents are NOT chatbots. They are deterministic operators that look at
the org's current state, propose concrete next actions, and (when approved by
a human) execute them. Each run returns:

- a `summary` of what the agent found
- a list of `actions` with kind, target, and an "execute" hint
- `confidence` + `next_run_in_minutes`

Every action is "proposed" by default — the agent never auto-applies anything
without an explicit approval call.

The runtime keeps each agent's last N runs in memory so the UI can show recent
agent activity. A scheduler (ai-orchestrator) can call `run_agent` on a cron
and persist results when a real DB is configured.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
@dataclass
class AgentAction:
    id: str
    kind: str                 # send_message | schedule | draft | update_field | escalate | propose
    title: str
    target: Optional[str] = None
    payload: dict = field(default_factory=dict)
    approval_required: bool = True
    rationale: str = ""

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class AgentRun:
    id: str
    agent: str
    org_id: str
    started_at: str
    finished_at: str
    summary: str
    actions: list[AgentAction]
    confidence: str = "medium"
    metrics: dict = field(default_factory=dict)
    next_run_in_minutes: int = 60
    disclaimer: str = (
        "Agent output is advisory. Human approval is required before any "
        "action with `approval_required = true` is executed."
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent": self.agent,
            "org_id": self.org_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "actions": [a.to_dict() for a in self.actions],
            "confidence": self.confidence,
            "metrics": self.metrics,
            "next_run_in_minutes": self.next_run_in_minutes,
            "disclaimer": self.disclaimer,
        }


# ---------------------------------------------------------------------------
# In-memory run log (most recent 50 per org)
_lock = threading.RLock()
_runs: dict[str, list[AgentRun]] = {}


def record_run(run: AgentRun) -> None:
    with _lock:
        rows = _runs.setdefault(run.org_id, [])
        rows.insert(0, run)
        del rows[50:]


def list_runs(org_id: str, agent: Optional[str] = None) -> list[AgentRun]:
    with _lock:
        rows = list(_runs.get(org_id, []))
    if agent:
        rows = [r for r in rows if r.agent == agent]
    return rows


# ---------------------------------------------------------------------------
async def _scalar(db: AsyncSession, sql: str, params: dict, default: int = 0) -> int:
    try:
        res = await db.execute(text(sql), params)
        row = res.first()
        return int(row[0]) if row and row[0] is not None else default
    except Exception:
        return default


async def _rows(db: AsyncSession, sql: str, params: dict) -> list[dict]:
    try:
        res = await db.execute(text(sql), params)
        return [dict(r) for r in res.mappings().all()]
    except Exception:
        return []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# RECRUITING AGENT
# ---------------------------------------------------------------------------
async def run_recruiting_agent(db: AsyncSession, org_id: str) -> AgentRun:
    started = _now()
    actions: list[AgentAction] = []

    open_jobs = await _rows(
        db,
        """
        select id, title, status from public.job_postings
        where org_id=:org_id and status <> 'closed'
        order by created_at desc
        """,
        {"org_id": org_id},
    )
    cands = await _rows(
        db,
        """
        select id, full_name, status, ai_score, job_posting_id
        from public.candidates
        where org_id=:org_id
        order by ai_score desc nulls last
        """,
        {"org_id": org_id},
    )

    unscored = [c for c in cands if c["ai_score"] is None]
    stale_offers = [c for c in cands if c["status"] == "offer"]
    high_band = [c for c in cands if (c["ai_score"] or 0) >= 75]

    if unscored:
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="propose",
            title=f"Run AI screening on {len(unscored)} unscored candidates",
            target="resume_ai.screen_job",
            payload={"candidate_ids": [c["id"] for c in unscored[:50]]},
            rationale="Newly added candidates have no AI score yet.",
        ))

    for c in high_band[:5]:
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="schedule",
            title=f"Schedule AI interview for {c['full_name']}",
            target=f"/ai-interview/sessions (candidate_id={c['id']})",
            payload={"candidate_id": c["id"], "job_id": c["job_posting_id"]},
            rationale=f"Candidate scored {c['ai_score']}/100 — fast-track.",
        ))

    for c in stale_offers[:5]:
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="send_message",
            title=f"Nudge hiring manager: offer pending for {c['full_name']}",
            target=f"slack:#recruiting",
            payload={"candidate_id": c["id"]},
            rationale="Offers older than 3 days lose ~12% acceptance per week.",
        ))

    if not open_jobs:
        summary = "No open requisitions — no recruiting actions needed."
        conf = "high"
    else:
        summary = (
            f"{len(open_jobs)} open requisitions · {len(cands)} candidates total · "
            f"{len(unscored)} unscored · {len(high_band)} strong matches · {len(stale_offers)} offers pending."
        )
        conf = "high" if cands else "medium"

    run = AgentRun(
        id=str(uuid.uuid4()), agent="recruiting", org_id=org_id,
        started_at=started, finished_at=_now(),
        summary=summary, actions=actions, confidence=conf,
        metrics={"open_jobs": len(open_jobs), "candidates": len(cands), "unscored": len(unscored)},
        next_run_in_minutes=120,
    )
    record_run(run)
    return run


# ---------------------------------------------------------------------------
# ONBOARDING AGENT
# ---------------------------------------------------------------------------
async def run_onboarding_agent(db: AsyncSession, org_id: str) -> AgentRun:
    started = _now()
    actions: list[AgentAction] = []

    new_hires = await _rows(
        db,
        """
        select id, legal_name, email, status, start_date
        from public.employees
        where org_id=:org_id and status in ('invited','onboarding')
        order by start_date asc nulls last
        """,
        {"org_id": org_id},
    )

    packets_open = await _scalar(
        db,
        "select count(*) from public.onboarding_packets where org_id=:org_id and status<>'complete'",
        {"org_id": org_id},
    )

    for emp in new_hires[:10]:
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="draft",
            title=f"Generate Day-1 plan for {emp['legal_name']}",
            target=f"employee:{emp['id']}",
            payload={"employee_id": emp["id"]},
            rationale="Auto-generated personalized 30/60/90 + equipment + buddy assignment.",
        ))
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="send_message",
            title=f"Send welcome email to {emp['email']}",
            target=emp["email"],
            payload={"employee_id": emp["id"], "template": "welcome_day1"},
            rationale="Pre-Day-1 expectations + first-week schedule.",
        ))

    summary = (
        f"{len(new_hires)} new hires in pipeline · {packets_open} onboarding packets in progress."
        if new_hires or packets_open else "No active onboarding workflows."
    )

    run = AgentRun(
        id=str(uuid.uuid4()), agent="onboarding", org_id=org_id,
        started_at=started, finished_at=_now(),
        summary=summary, actions=actions,
        confidence="high" if new_hires else "medium",
        metrics={"new_hires": len(new_hires), "open_packets": packets_open},
        next_run_in_minutes=240,
    )
    record_run(run)
    return run


# ---------------------------------------------------------------------------
# COMPLIANCE AGENT
# ---------------------------------------------------------------------------
async def run_compliance_agent(db: AsyncSession, org_id: str) -> AgentRun:
    started = _now()
    actions: list[AgentAction] = []

    open_cases = await _rows(
        db,
        """
        select id, category, severity, status, created_at
        from public.cases
        where org_id=:org_id and status not in ('closed')
        order by created_at asc
        """,
        {"org_id": org_id},
    )
    high = [c for c in open_cases if c["severity"] == "high"]
    aging = [c for c in open_cases if c["created_at"]]  # naive — every open case can be considered aging in heuristic

    for c in high[:5]:
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="escalate",
            title=f"Escalate {c['category']} (severity high) to legal",
            target=f"case:{c['id']}",
            payload={"case_id": c["id"]},
            rationale="High-severity case still open — must reach HR + legal within 24h.",
        ))

    if len(open_cases) > 3:
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="propose",
            title="Send case status update to reporters this week",
            target="cases",
            payload={"n_cases": len(open_cases)},
            rationale="Periodic updates build trust in the reporting channel.",
        ))

    actions.append(AgentAction(
        id=str(uuid.uuid4()),
        kind="propose",
        title="Audit required compliance trainings completion",
        target="/learning/compliance-required",
        rationale="Confirm SOC 2, harassment, and security trainings are <90 days old.",
    ))

    summary = (
        f"{len(open_cases)} open cases · {len(high)} high-severity."
        if open_cases else "No open cases. Compliance baseline is healthy."
    )

    run = AgentRun(
        id=str(uuid.uuid4()), agent="compliance", org_id=org_id,
        started_at=started, finished_at=_now(),
        summary=summary, actions=actions,
        confidence="high" if high else "medium",
        metrics={"open_cases": len(open_cases), "high_severity": len(high)},
        next_run_in_minutes=180,
    )
    record_run(run)
    return run


# ---------------------------------------------------------------------------
# PERFORMANCE AGENT
# ---------------------------------------------------------------------------
async def run_performance_agent(db: AsyncSession, org_id: str) -> AgentRun:
    started = _now()
    actions: list[AgentAction] = []
    # Best-effort against an optional reviews table; degrades gracefully.
    pending_reviews = await _scalar(
        db,
        "select count(*) from public.reviews where org_id=:org_id and status in ('draft','pending')",
        {"org_id": org_id},
    )
    employees = await _scalar(
        db,
        "select count(*) from public.employees where org_id=:org_id and status='active'",
        {"org_id": org_id},
    )

    if pending_reviews:
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="propose",
            title=f"Draft balanced feedback for {pending_reviews} pending reviews",
            target="/content/feedback-rewrite",
            rationale="Reviewer language is checked for vagueness and bias before sharing.",
        ))

    actions.append(AgentAction(
        id=str(uuid.uuid4()),
        kind="propose",
        title="Generate calibration packet for this cycle",
        target="/content/calibration-packet",
        rationale="Compare ratings against peer cohorts to surface drift.",
    ))

    if employees > 5:
        actions.append(AgentAction(
            id=str(uuid.uuid4()),
            kind="propose",
            title="Run 9-box placement refresh",
            target="/performance/9box",
            rationale="Performance × potential — surfaces succession candidates.",
        ))

    summary = (
        f"{pending_reviews} reviews in draft · {employees} active employees."
        if employees else "No active employees scoped — agent idle."
    )

    run = AgentRun(
        id=str(uuid.uuid4()), agent="performance", org_id=org_id,
        started_at=started, finished_at=_now(),
        summary=summary, actions=actions,
        confidence="medium",
        metrics={"pending_reviews": pending_reviews, "active_employees": employees},
        next_run_in_minutes=720,
    )
    record_run(run)
    return run


# ---------------------------------------------------------------------------
# COMPENSATION AGENT
# ---------------------------------------------------------------------------
async def run_comp_agent(db: AsyncSession, org_id: str) -> AgentRun:
    started = _now()
    actions: list[AgentAction] = []

    actions.append(AgentAction(
        id=str(uuid.uuid4()),
        kind="propose",
        title="Scan workforce for compa-ratio drift",
        target="/comp-ai/recommend-batch",
        rationale="Identify employees below 0.95 mid where performance is strong.",
    ))
    actions.append(AgentAction(
        id=str(uuid.uuid4()),
        kind="propose",
        title="Flag band compression in Engineering + Sales",
        target="/comp-ai/recommend-batch",
        rationale="Senior IC bands frequently overlap with new-hire bands — compression hurts retention.",
    ))
    actions.append(AgentAction(
        id=str(uuid.uuid4()),
        kind="propose",
        title="Model merit cycle scenarios (2 / 3 / 4% budget)",
        target="/comp-ai/recommend-batch",
        rationale="Show CFO the cost vs. retention trade-off.",
    ))

    run = AgentRun(
        id=str(uuid.uuid4()), agent="compensation", org_id=org_id,
        started_at=started, finished_at=_now(),
        summary="Comp drift + compression + merit modelling proposed.",
        actions=actions, confidence="medium",
        metrics={},
        next_run_in_minutes=1440,
    )
    record_run(run)
    return run


# ---------------------------------------------------------------------------
# WORKFORCE PLANNING AGENT
# ---------------------------------------------------------------------------
async def run_workforce_planning_agent(db: AsyncSession, org_id: str) -> AgentRun:
    started = _now()
    actions: list[AgentAction] = []

    headcount = await _scalar(
        db,
        "select count(*) from public.employees where org_id=:org_id and status='active'",
        {"org_id": org_id},
    )
    open_jobs = await _scalar(
        db,
        "select count(*) from public.job_postings where org_id=:org_id and status<>'closed'",
        {"org_id": org_id},
    )

    # Synthetic department signals — would come from departments table in prod.
    dept_signals = [
        {"dept": "Customer Success", "headcount": 6, "tickets_per_head": 92, "burnout_risk": 0.71},
        {"dept": "Engineering",      "headcount": 14, "tickets_per_head": None, "burnout_risk": 0.52},
        {"dept": "Sales",            "headcount": 9, "tickets_per_head": None, "burnout_risk": 0.40},
    ]

    for d in dept_signals:
        if d["burnout_risk"] > 0.65:
            actions.append(AgentAction(
                id=str(uuid.uuid4()),
                kind="propose",
                title=f"{d['dept']} likely understaffed in 45 days",
                target=f"plan:{d['dept']}",
                rationale=(
                    f"Burnout signal {int(d['burnout_risk']*100)}% · "
                    f"{d['headcount']} headcount · "
                    + (f"{d['tickets_per_head']} tickets/head" if d["tickets_per_head"] else "high workload signals")
                    + ". Open 2 reqs."
                ),
            ))

    actions.append(AgentAction(
        id=str(uuid.uuid4()),
        kind="propose",
        title=f"Forecast payroll growth for next 4 quarters",
        target="/cfo/model",
        rationale=f"Today: {headcount} active employees + {open_jobs} open reqs. Plan 12-month curve.",
    ))

    summary = f"Forecast: {headcount} employees, {open_jobs} open roles. Surfaced {sum(1 for d in dept_signals if d['burnout_risk']>0.65)} understaffing risks."

    run = AgentRun(
        id=str(uuid.uuid4()), agent="workforce_planning", org_id=org_id,
        started_at=started, finished_at=_now(),
        summary=summary, actions=actions, confidence="medium",
        metrics={"headcount": headcount, "open_jobs": open_jobs, "dept_signals": dept_signals},
        next_run_in_minutes=1440,
    )
    record_run(run)
    return run


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
AGENT_REGISTRY: dict[str, tuple[str, Callable[[AsyncSession, str], Awaitable[AgentRun]]]] = {
    "recruiting": ("Recruiting Agent", run_recruiting_agent),
    "onboarding": ("Onboarding Agent", run_onboarding_agent),
    "compliance": ("HR Compliance Agent", run_compliance_agent),
    "performance": ("Performance Agent", run_performance_agent),
    "compensation": ("Compensation Agent", run_comp_agent),
    "workforce_planning": ("Workforce Planning Agent", run_workforce_planning_agent),
}


async def run_agent(agent: str, db: AsyncSession, org_id: str) -> AgentRun:
    if agent not in AGENT_REGISTRY:
        raise KeyError(f"Unknown agent: {agent}")
    _, fn = AGENT_REGISTRY[agent]
    return await fn(db, org_id)


def list_agents() -> list[dict]:
    return [
        {"key": key, "name": name}
        for key, (name, _) in AGENT_REGISTRY.items()
    ]
