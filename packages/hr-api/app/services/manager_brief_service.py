"""Manager OS — daily manager briefing.

Synthesises a single mission-control view for a manager:
- approvals waiting on them (PTO, comp, packets, agent actions)
- attrition + burnout signals on their team
- review cycle progression
- hiring pipeline for their open roles
- recognition opportunities

The brief is intentionally scoped: it never surfaces signals about employees
outside the manager's team. Everything is read-only summary — no auto actions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.attrition_service import AttritionFeatures, predict_batch
from app.services.tasks_service import list_tasks


@dataclass
class BriefSignal:
    kind: str           # approval | attrition | review | hiring | recognition | learning
    severity: str       # urgent | today | this_week | low
    title: str
    detail: str
    cta_label: str
    cta_href: str
    subject: Optional[str] = None
    # WHOSE TEAM THIS IS ABOUT.
    #
    # The manager brief's action feed opened with "Avery Chen · high attrition
    # risk · urgent · Compa-ratio ...", on a page titled "Who needs my
    # attention today" whose rows are described as "every row is a decision you
    # can make from here". Avery Chen is in _synthetic_features() below. This
    # is the same invented person as the risk engine and the exec brief, on the
    # screen that asks a manager to act today.
    is_sample: bool = False

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class ManagerBrief:
    generated_at: str
    manager_name: str
    department: str
    headline: str
    summary: str
    counts: dict
    signals: list[BriefSignal]
    suggested_actions: list[BriefSignal] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "manager_name": self.manager_name,
            "department": self.department,
            "headline": self.headline,
            "summary": self.summary,
            "counts": self.counts,
            "signals": [s.to_dict() for s in self.signals],
            "suggested_actions": [s.to_dict() for s in self.suggested_actions],
        }


# Demo manager roster — mirrors the synthetic data the rest of the system uses.
_MANAGERS = {
    "Sam Rivera": {
        "department": "Engineering",
        "team": ["Avery Chen", "Jordan Patel"],
        "open_reqs": 2,
    },
    "Casey Quinn": {
        "department": "HR",
        "team": ["Morgan Lee"],
        "open_reqs": 0,
    },
    "Riley Manager": {
        "department": "Design",
        "team": ["Riley Singh"],
        "open_reqs": 1,
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _scalar(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        row = (await db.execute(text(sql), params)).first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _synthetic_features() -> list[AttritionFeatures]:
    return [
        AttritionFeatures("e1", "Avery Chen",  department="Engineering", tenure_years=2.4, months_since_last_raise=22, months_since_last_promotion=30, performance_rating=4.5, engagement_score=0.42, compa_ratio=0.82, overtime_hours_last_30d=38),
        AttritionFeatures("e2", "Jordan Patel", department="Sales",      tenure_years=1.8, months_since_last_raise=14, months_since_last_promotion=20, performance_rating=3.2, engagement_score=0.61, compa_ratio=0.97, pto_balance_days=22),
        AttritionFeatures("e5", "Riley Singh",  department="Design",     tenure_years=2.0, months_since_last_raise=18, months_since_last_promotion=24, performance_rating=4.8, compa_ratio=0.88, role_change_in_last_180d=True, pto_balance_days=19),
    ]


def list_managers() -> list[dict]:
    return [{"name": name, "department": meta["department"]} for name, meta in _MANAGERS.items()]


async def build_brief(db: AsyncSession, org_id: str, manager_name: str) -> ManagerBrief:
    meta = _MANAGERS.get(manager_name)
    if not meta:
        meta = list(_MANAGERS.values())[0]
        manager_name = list(_MANAGERS.keys())[0]
    team = set(meta["team"])
    department = meta["department"]

    pto_pending = await _scalar(
        db,
        "select count(*) from public.pto_requests where org_id=:org_id and status='pending'",
        {"org_id": org_id},
    )
    candidates_offer = await _scalar(
        db,
        "select count(*) from public.candidates where org_id=:org_id and status='offer'",
        {"org_id": org_id},
    )
    candidates_interview = await _scalar(
        db,
        "select count(*) from public.candidates where org_id=:org_id and status='interview'",
        {"org_id": org_id},
    )

    preds = predict_batch(_synthetic_features())
    team_preds = [p for p in preds if p.name in team]
    high = [p for p in team_preds if p.band == "high"]
    medium = [p for p in team_preds if p.band == "medium"]

    # Tasks owned by the manager (or marked manager-action)
    manager_tasks = list_tasks(org_id, owner_role="manager")
    manager_tasks_open = [t for t in manager_tasks if t["status"] != "done"]
    team_tasks = [t for t in manager_tasks_open if (t.get("related_employee_name") in team) or (t.get("department") == department)]

    overdue = 0
    for t in team_tasks:
        if not t.get("due_at"):
            continue
        try:
            d = datetime.fromisoformat(t["due_at"])
            if d < _now():
                overdue += 1
        except Exception:
            pass

    signals: list[BriefSignal] = []

    if pto_pending:
        signals.append(BriefSignal(
            kind="approval",
            severity="today",
            title=f"{pto_pending} PTO request{'s' if pto_pending != 1 else ''} awaiting approval",
            detail="Open the PTO queue and review pending requests.",
            cta_label="Open PTO",
            cta_href="/app/pto",
        ))

    if overdue:
        signals.append(BriefSignal(
            kind="approval",
            severity="urgent" if overdue >= 3 else "today",
            title=f"{overdue} task{'s' if overdue != 1 else ''} overdue",
            detail="Tasks past their due date on your team. Tap to triage.",
            cta_label="Open work hub",
            cta_href="/app/work?owner_role=manager",
        ))

    for p in high:
        signals.append(BriefSignal(
            kind="attrition",
            # Not urgent: it is not about anyone on this manager's team.
            severity="this_week",
            title=f"{p.name} · high attrition risk (sample)",
            detail="; ".join(p.drivers[:2]),
            cta_label="Open twin",
            cta_href=f"/app/digital-twin?id={p.employee_id}",
            subject=p.name,
            is_sample=True,
        ))
    for p in medium:
        signals.append(BriefSignal(
            kind="attrition",
            severity="this_week",
            is_sample=True,
            title=f"{p.name} · medium attrition risk (sample)",
            detail="; ".join(p.drivers[:2]),
            cta_label="Open twin",
            cta_href=f"/app/digital-twin?id={p.employee_id}",
            subject=p.name,
        ))

    if candidates_offer + candidates_interview:
        signals.append(BriefSignal(
            kind="hiring",
            severity="today",
            title=f"{candidates_interview + candidates_offer} candidate{'s' if (candidates_interview + candidates_offer) != 1 else ''} in your pipeline",
            detail=f"{candidates_interview} at interview · {candidates_offer} at offer.",
            cta_label="Open talent",
            cta_href="/app/talent",
        ))

    # Review cycle reminder — pulled from tasks tagged 'review' if any
    review_tasks = [t for t in manager_tasks_open if "review" in (t.get("tags") or [])]
    if review_tasks:
        signals.append(BriefSignal(
            kind="review",
            severity="this_week",
            title=f"{len(review_tasks)} review action{'s' if len(review_tasks) != 1 else ''} on you",
            detail="Self → manager → calibration → approval → delivery.",
            cta_label="Open cycle",
            cta_href="/app/performance",
        ))

    # Suggested actions — calmer second list. Always include 1:1 nudges and recognition.
    suggested: list[BriefSignal] = []
    for member in team:
        suggested.append(BriefSignal(
            kind="recognition",
            severity="low",
            title=f"Schedule 1:1 with {member}",
            detail="Weekly rhythm keeps signal strong.",
            cta_label="Open work hub",
            cta_href=f"/app/work?owner_name={member}",
            subject=member,
        ))
    if high:
        suggested.append(BriefSignal(
            kind="attrition",
            severity="this_week",
            title=f"Plan retention conversation with {high[0].name}",
            detail="Compa + workload. Loop HR on the comp piece.",
            cta_label="Comp review",
            cta_href="/app/comp",
            subject=high[0].name,
        ))
    suggested.append(BriefSignal(
        kind="learning",
        severity="low",
        title="Review your team's skills graph",
        detail="The team's coverage to next-level roles is updated weekly.",
        cta_label="Open marketplace",
        cta_href="/app/marketplace",
    ))

    counts = {
        "approvals_pending": pto_pending,
        "tasks_open": len(team_tasks),
        "tasks_overdue": overdue,
        "team_size": len(team),
        "team_high_risk": len(high),
        "team_medium_risk": len(medium),
        "hiring_in_motion": candidates_offer + candidates_interview,
    }

    # Count only signals about this manager's own people. The attrition rows
    # come from a sample cohort, and "2 signals on your team this week" was
    # counting one of them.
    real = [s for s in signals if not s.is_sample]
    if any(s.severity == "urgent" for s in real):
        headline = f"Action required for {department} team."
    elif real:
        headline = f"{len(real)} signal{'s' if len(real) != 1 else ''} on your team this week."
    elif signals:
        headline = (f"Nothing on your {department} team this week. The attrition "
                    "rows below are a sample.")
    else:
        headline = f"{department} team is steady. Good time to invest in 1:1s."

    summary = (
        f"{len(team)} direct report{'s' if len(team) != 1 else ''} · "
        f"{len(team_tasks)} open tasks · {overdue} overdue · "
        f"{len(high)} high-risk · {pto_pending} PTO awaiting your call."
    )

    return ManagerBrief(
        generated_at=_now().isoformat(),
        manager_name=manager_name,
        department=department,
        headline=headline,
        summary=summary,
        counts=counts,
        signals=signals,
        suggested_actions=suggested,
    )
