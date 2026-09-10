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


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _scalar(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        row = (await db.execute(text(sql), params)).first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _tenure_years(start_date) -> float:
    if not start_date:
        return 1.0
    try:
        if hasattr(start_date, "year"):
            return max(0.1, (datetime.utcnow().date() - start_date).days / 365.25)
        d = datetime.fromisoformat(str(start_date)).date()
        return max(0.1, (datetime.utcnow().date() - d).days / 365.25)
    except Exception:
        return 1.0


async def list_managers(db: AsyncSession, org_id: str) -> list[dict]:
    """Employees who have at least one active direct report."""
    rows = (await db.execute(text("""
        select m.id, m.legal_name as name, m.department,
               count(r.id)::int as team_size
          from public.employees m
          join public.employees r
            on r.manager_employee_id = m.id
           and r.org_id = m.org_id
           and r.status = 'active'
         where m.org_id = cast(:org_id as uuid)
           and m.status = 'active'
         group by m.id, m.legal_name, m.department
         order by m.legal_name
    """), {"org_id": org_id})).mappings().all()
    return [
        {"name": r["name"], "department": r["department"] or "General", "id": str(r["id"]), "team_size": r["team_size"]}
        for r in rows
    ]


async def _load_manager_team(db: AsyncSession, org_id: str, manager_name: str | None) -> tuple[str, str, list[dict]]:
    """Resolve manager + direct reports from employees.manager_employee_id."""
    managers = await list_managers(db, org_id)
    if not managers:
        return manager_name or "Manager", "General", []

    chosen = None
    if manager_name:
        for m in managers:
            if m["name"].lower() == manager_name.lower():
                chosen = m
                break
    if chosen is None:
        chosen = managers[0]

    reports = (await db.execute(text("""
        select e.id, e.legal_name, e.department, e.start_date,
               (select pr.rating
                  from public.performance_reviews pr
                 where pr.org_id = e.org_id and pr.employee_id = e.id
                   and pr.rating is not null
                 order by pr.created_at desc
                 limit 1) as rating
          from public.employees e
         where e.org_id = cast(:org_id as uuid)
           and e.manager_employee_id = cast(:mgr as uuid)
           and e.status = 'active'
         order by e.legal_name
    """), {"org_id": org_id, "mgr": chosen["id"]})).mappings().all()

    team = [
        {
            "id": str(r["id"]),
            "name": r["legal_name"],
            "department": r["department"] or chosen.get("department") or "General",
            "tenure_years": _tenure_years(r["start_date"]),
            "performance_rating": float(r["rating"]) if r["rating"] is not None else 3.5,
        }
        for r in reports
    ]
    return chosen["name"], chosen.get("department") or "General", team


async def build_brief(db: AsyncSession, org_id: str, manager_name: str | None = None) -> ManagerBrief:
    manager_name, department, team_rows = await _load_manager_team(db, org_id, manager_name)
    team_names = {t["name"] for t in team_rows}

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

    features = [
        AttritionFeatures(
            employee_id=t["id"],
            name=t["name"],
            department=t["department"],
            tenure_years=t["tenure_years"],
            performance_rating=t["performance_rating"],
        )
        for t in team_rows
    ]
    preds = predict_batch(features) if features else []
    high = [p for p in preds if p.band == "high"]
    medium = [p for p in preds if p.band == "medium"]

    manager_tasks = list_tasks(org_id, owner_role="manager")
    manager_tasks_open = [t for t in manager_tasks if t["status"] != "done"]
    team_tasks = [
        t for t in manager_tasks_open
        if (t.get("related_employee_name") in team_names) or (t.get("department") == department)
    ]

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
            severity="urgent",
            title=f"{p.name} · high attrition risk",
            detail="; ".join(p.drivers[:2]),
            cta_label="Open twin",
            cta_href=f"/app/digital-twin?id={p.employee_id}",
            subject=p.name,
            is_sample=False,
        ))
    for p in medium:
        signals.append(BriefSignal(
            kind="attrition",
            severity="this_week",
            is_sample=False,
            title=f"{p.name} · medium attrition risk",
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

    suggested: list[BriefSignal] = []
    for member in sorted(team_names):
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
        "team_size": len(team_rows),
        "team_high_risk": len(high),
        "team_medium_risk": len(medium),
        "hiring_in_motion": candidates_offer + candidates_interview,
    }

    if any(s.severity == "urgent" for s in signals):
        headline = f"Action required for {department} team."
    elif signals:
        headline = f"{len(signals)} signal{'s' if len(signals) != 1 else ''} on your team this week."
    else:
        headline = f"{department} team is steady. Good time to invest in 1:1s."

    summary = (
        f"{len(team_rows)} direct report{'s' if len(team_rows) != 1 else ''} · "
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
