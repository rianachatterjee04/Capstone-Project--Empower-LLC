"""Workforce risk engine.

Cross-cutting alerts that aggregate signals from attrition, PTO, cases,
overtime, manager-change, and compliance. Each alert ships with a `kind`,
`severity`, `subject`, `drivers`, `recommended_action`, and `confidence`.

Designed to feel like CrowdStrike-for-workforce: a continuously running
detector that surfaces what HR/leadership should look at this week.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.attrition_service import AttritionFeatures, predict_batch


@dataclass
class RiskAlert:
    id: str
    kind: str                 # attrition | burnout | compliance | comp_equity | manager | hiring
    severity: str             # high | medium | low
    subject: str
    drivers: list[str]
    recommended_action: str
    confidence: str = "medium"
    # WHOSE WORKFORCE THIS ALERT IS ABOUT.
    #
    # Every layer here runs on _synthetic_workforce(): five invented people
    # with invented compa-ratios, engagement scores and overtime. The page
    # rendered "Workforce risk score 38/100 — high-severity workforce risk
    # detected, review today" and named Avery Chen with "Compa-ratio below
    # 0.85" and "No raise in 22 months", for an organisation whose only
    # employee is a CDL driver. `db` and `org_id` were parameters the scan
    # never used to find people.
    #
    #   employee_record  — one of the customer's own employees
    #   sample_workforce — an illustrative person shipped with the product
    source: str = "sample_workforce"
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class RiskSummary:
    counts: dict[str, int]
    score: int               # 0-100 overall workforce risk
    headline: str
    alerts: list[RiskAlert]
    coverage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "counts": self.counts,
            "score": self.score,
            "headline": self.headline,
            "alerts": [a.to_dict() for a in self.alerts],
            "coverage": self.coverage,
        }


async def _scalar(db: AsyncSession, sql: str, params: dict) -> int:
    try:
        res = await db.execute(text(sql), params)
        row = res.first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


def _synthetic_workforce() -> list[AttritionFeatures]:
    return [
        AttritionFeatures("e1", "Avery Chen", department="Engineering", tenure_years=2.4, months_since_last_raise=22, months_since_last_promotion=30, performance_rating=4.5, engagement_score=0.42, compa_ratio=0.82, overtime_hours_last_30d=38),
        AttritionFeatures("e2", "Jordan Patel", department="Sales", tenure_years=1.8, months_since_last_raise=14, months_since_last_promotion=20, performance_rating=3.2, engagement_score=0.61, compa_ratio=0.97, pto_balance_days=22),
        AttritionFeatures("e3", "Sam Rivera", department="Engineering", tenure_years=3.6, months_since_last_raise=10, months_since_last_promotion=12, performance_rating=4.0, compa_ratio=1.05, engagement_score=0.78),
        AttritionFeatures("e4", "Morgan Lee", department="HR", tenure_years=0.6, months_since_last_raise=6, months_since_last_promotion=0, performance_rating=3.6, compa_ratio=0.99, manager_change_in_last_180d=True),
        AttritionFeatures("e5", "Riley Singh", department="Design", tenure_years=2.0, months_since_last_raise=18, months_since_last_promotion=24, performance_rating=4.8, compa_ratio=0.88, role_change_in_last_180d=True, pto_balance_days=19),
    ]


async def scan(db: AsyncSession, org_id: str) -> RiskSummary:
    alerts: list[RiskAlert] = []
    counts: dict[str, int] = {"attrition": 0, "burnout": 0, "compliance": 0, "comp_equity": 0, "manager": 0, "hiring": 0}

    # ---- Attrition layer
    preds = predict_batch(_synthetic_workforce())
    for p in preds:
        if p.band == "high":
            alerts.append(RiskAlert(
                id=f"attr-{p.employee_id}", kind="attrition", severity="high",
                subject=p.name,
                drivers=p.drivers,
                recommended_action=(p.suggested_actions[0] if p.suggested_actions else "Schedule stay interview"),
                confidence="medium",
            ))
            counts["attrition"] += 1
        elif p.band == "medium":
            counts["attrition"] += 0  # tracked but not surfaced as a top alert

    # ---- Burnout heuristic (overtime + low engagement + tenure)
    for f in _synthetic_workforce():
        if f.overtime_hours_last_30d >= 30 and (f.engagement_score or 1) < 0.55:
            alerts.append(RiskAlert(
                id=f"burnout-{f.employee_id}", kind="burnout", severity="medium",
                subject=f.name,
                drivers=[f"{int(f.overtime_hours_last_30d)} hours overtime last 30d",
                         f"Engagement {int((f.engagement_score or 0)*100)}%"],
                recommended_action="Manager to redistribute load + enforce recovery time off",
            ))
            counts["burnout"] += 1
        if (f.pto_balance_days or 0) > 18 and (f.engagement_score or 1) < 0.6:
            alerts.append(RiskAlert(
                id=f"pto-{f.employee_id}", kind="burnout", severity="low",
                subject=f.name,
                drivers=[f"{f.pto_balance_days:.0f}d unused PTO", "Engagement below baseline"],
                recommended_action="Encourage taking a real break in the next 30 days",
            ))
            counts["burnout"] += 1

    # ---- Compensation equity layer (synthetic)
    for f in _synthetic_workforce():
        if (f.compa_ratio or 1) < 0.85 and f.performance_rating >= 4:
            alerts.append(RiskAlert(
                id=f"comp-{f.employee_id}", kind="comp_equity", severity="medium",
                subject=f.name,
                drivers=[f"Compa-ratio {f.compa_ratio:.2f}", f"Performance {f.performance_rating:.1f}/5"],
                recommended_action="Run comp review with HR",
                confidence="high",
            ))
            counts["comp_equity"] += 1

    # ---- Manager change risk
    for f in _synthetic_workforce():
        if f.manager_change_in_last_180d:
            alerts.append(RiskAlert(
                id=f"mgr-{f.employee_id}", kind="manager", severity="low",
                subject=f.name,
                drivers=["Manager change in last 6 months"],
                recommended_action="Schedule re-onboarding 1:1 with new manager",
                confidence="medium",
            ))
            counts["manager"] += 1

    # ---- Compliance layer (real data when available)
    open_high = await _scalar(
        db,
        "select count(*) from public.cases where org_id=:org_id and severity='high' and status<>'closed'",
        {"org_id": org_id},
    )
    if open_high:
        alerts.append(RiskAlert(
            id="cases-high", kind="compliance", severity="high",
            subject=f"{open_high} high-severity case{'s' if open_high != 1 else ''} open",
            drivers=["Open investigation file requiring HR + legal attention"],
            recommended_action="Open ombudsman risk dashboard and assign owners",
            confidence="high",
            # Counted from public.cases for THIS org — a real finding, not part
            # of the sample cohort. My first pass marked every alert as sample
            # and the test that checks each named subject is in the cohort is
            # what caught it: these two subjects are not people at all.
            source="employee_record",
        ))
        counts["compliance"] += open_high

    # ---- Hiring health
    open_jobs = await _scalar(
        db, "select count(*) from public.job_postings where org_id=:org_id and status<>'closed'", {"org_id": org_id},
    )
    candidates = await _scalar(
        db, "select count(*) from public.candidates where org_id=:org_id", {"org_id": org_id},
    )
    if open_jobs and candidates / max(open_jobs, 1) < 4:
        alerts.append(RiskAlert(
            id="hiring-thin", kind="hiring", severity="medium",
            subject=f"Pipeline thin for {open_jobs} open roles",
            drivers=[f"Only {candidates} candidates across {open_jobs} reqs"],
            recommended_action="Run recruiting agent + enable ATS syndication",
            confidence="high",
            # Counted from public.job_postings and public.candidates for THIS org.
            source="employee_record",
        ))
        counts["hiring"] += 1

    # ---- Score
    weight = {"high": 14, "medium": 7, "low": 3}
    score = min(100, sum(weight[a.severity] for a in alerts))

    # ---- Coverage: whose workforce was actually scanned.
    #
    # The four PEOPLE layers — attrition, burnout, comp equity, manager — read
    # _synthetic_workforce() and name invented individuals. The compliance and
    # hiring layers count this organisation's own cases, requisitions and
    # candidates, and are real findings.
    #
    # The signals the people layers consume — compa-ratio, engagement score,
    # overtime hours, PTO balance, months since last raise — are not recorded
    # against employees in this schema at all, which is why those layers have
    # nothing real to run on.
    own = await _scalar(db, "select count(*) from public.employees "
                            "where org_id = :org and status = 'active'",
                        {"org": org_id})
    sample_alerts = sum(1 for a in alerts if a.source != "employee_record")
    real_alerts = len(alerts) - sample_alerts
    coverage = {
        "your_employees_scanned": 0,
        "your_active_employees": own,
        "sample_people_scanned": len(_synthetic_workforce()),
        "alerts_from_sample": sample_alerts,
        "alerts_from_your_data": real_alerts,
        "people_layers": ["attrition", "burnout", "comp_equity", "manager"],
        "your_data_layers": ["compliance", "hiring"],
        "needs": [
            "compa-ratio against a salary band (comp records + bands)",
            "engagement scores (survey responses)",
            "overtime hours and PTO balances (time and attendance)",
            "months since last raise and last promotion (comp history)",
        ],
        "note": (
            "The attrition, burnout, pay-equity and manager layers ran on "
            f"{len(_synthetic_workforce())} illustrative people shipped with the "
            f"product — not on your {own} active employee"
            f"{'s' if own != 1 else ''} — because none of your employees carry "
            "the signals those layers read. Alerts naming a person are marked. "
            + (f"The compliance and hiring layers did read your own records, and "
               f"produced {real_alerts} alert{'s' if real_alerts != 1 else ''}."
               if real_alerts else
               "The compliance and hiring layers read your own records and found "
               "nothing.")
        ),
    }

    real_high = [a for a in alerts
                 if a.severity == "high" and a.source == "employee_record"]
    if sample_alerts and not real_high:
        # Do not tell someone to review today what is not about them. If a real
        # high-severity finding exists it still leads, and the sample cohort is
        # labelled beneath it.
        headline = ("No high-severity finding about your own workforce. The "
                    "people layers below ran on sample data.")
    elif real_high:
        headline = "High-severity workforce risk detected — review today."
    elif alerts:
        headline = f"{len(alerts)} workforce risk signal{'s' if len(alerts) != 1 else ''} need attention this week."
    else:
        headline = "Workforce risk baseline is healthy."

    return RiskSummary(counts=counts, score=score, headline=headline,
                       alerts=alerts, coverage=coverage)
