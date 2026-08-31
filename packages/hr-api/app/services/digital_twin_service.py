"""Employee Digital Twin aggregator.

Collects everything we know about an employee — profile, skills, performance,
comp, PTO, workload signals, career trajectory — into a single object that
agents and the UI can read uniformly. This is the substrate for personalised
guidance: career paths, learning, attrition risk, marketplace matching.

The aggregator is best-effort and gracefully degrades when source tables are
missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.attrition_service import AttritionFeatures, predict
from app.services.learning_service import (
    extract_skills_from_text,
    nearest_roles,
    skill_gap,
)
from app.services.talent_marketplace_service import match_employee_to_marketplace


@dataclass
class DigitalTwin:
    employee_id: str
    name: str
    email: Optional[str]
    job_title: Optional[str]
    department: Optional[str]
    location: Optional[str]
    start_date: Optional[str]
    tenure_years: float
    skills: list[str]
    performance_rating: float
    compa_ratio: Optional[float]
    pto_balance_days: Optional[float]
    engagement_score: Optional[float]
    growth_signals: list[str]
    attrition: dict
    nearest_roles: list[dict]
    marketplace_matches: list[dict]
    skill_gap_to_next: dict
    # True when no employee row was found and the twin was built from an
    # invented seed. A twin carries a name, a title, inferred skills and an
    # attrition score -- rendered, that is a set of claims about a colleague,
    # and nothing distinguished a real one from a fabricated one.
    is_sample: bool = False

    def to_dict(self) -> dict:
        return self.__dict__


async def _fetch_row(db: AsyncSession, employee_id: str, org_id: str) -> Optional[dict]:
    try:
        res = await db.execute(
            text(
                """
                select id::text, legal_name, email, job_title, department,
                       location, start_date, status
                from public.employees
                where id=:eid and org_id=:org_id
                """
            ),
            {"eid": employee_id, "org_id": org_id},
        )
        row = res.mappings().first()
        return dict(row) if row else None
    except Exception:
        return None


def _demo_twin(employee_id: str) -> dict:
    # A "digital twin" carries a name, a title and inferred skills. Rendered, it
    # is a claim about a colleague. Every seed here is invented, and the twin
    # built from one is marked is_sample so a caller can tell.
    seeds = {
        "e1": {"name": "Avery Chen", "title": "Senior Software Engineer", "dept": "Engineering",
               "skills_text": "8 years of python, fastapi, aws, docker, kubernetes; led payments platform; SQL, communication, leadership."},
        "e2": {"name": "Jordan Patel", "title": "Account Executive", "dept": "Sales",
               "skills_text": "Salesforce; consultative selling; communication; project management; account growth."},
        "e3": {"name": "Sam Rivera", "title": "Engineering Manager", "dept": "Engineering",
               "skills_text": "Python, AWS, Kubernetes, leadership, communication, hiring."},
        "e5": {"name": "Riley Singh", "title": "Senior Designer", "dept": "Design",
               "skills_text": "react, typescript, design systems, user research, communication."},
        "e6": {"name": "Emily Stone", "title": "Senior CS Specialist", "dept": "Customer Success",
               "skills_text": "communication, project management, data analysis, churn analysis, leadership coaching."},
    }
    seed = seeds.get(employee_id, {
        "name": "Sample Employee",
        "title": "Software Engineer",
        "dept": "Engineering",
        "skills_text": "python, sql, aws, react",
    })
    return seed


async def build_twin(db: AsyncSession, employee_id: str, org_id: str) -> DigitalTwin:
    row = await _fetch_row(db, employee_id, org_id)
    is_sample = row is None
    if not row:
        seed = _demo_twin(employee_id)
        name = seed["name"]
        title = seed["title"]
        dept = seed["dept"]
        skills = extract_skills_from_text(seed["skills_text"])
        email = None
        location = None
        start_date = None
        tenure_years = 2.0
    else:
        name = row["legal_name"]
        title = row["job_title"]
        dept = row["department"]
        skills = []
        email = row["email"]
        location = row["location"]
        start_date = row["start_date"].isoformat() if row.get("start_date") else None
        # Tenure heuristic
        tenure_years = 1.0
        if start_date:
            try:
                from datetime import datetime as _dt
                d = _dt.fromisoformat(start_date)
                tenure_years = max(0.1, (_dt.utcnow() - d).days / 365.25)
            except Exception:
                tenure_years = 1.0

    # Performance + comp signals — best-effort SQL probe
    perf = 3.5
    compa = None
    pto_balance = None
    engagement = None
    try:
        prow = await db.execute(
            text("select rating from public.performance_reviews where org_id=:org_id and employee_id=:eid order by created_at desc limit 1"),
            {"org_id": org_id, "eid": employee_id},
        )
        first = prow.first()
        if first and first[0] is not None:
            perf = float(first[0])
    except Exception:
        pass

    # Attrition prediction
    pred = predict(AttritionFeatures(
        employee_id=employee_id, name=name, department=dept,
        tenure_years=tenure_years, performance_rating=perf,
        compa_ratio=compa, pto_balance_days=pto_balance, engagement_score=engagement,
    ))

    # Growth signals
    growth: list[str] = []
    if tenure_years >= 3 and pred.band != "high":
        growth.append("Eligible for a stretch project or promotion conversation.")
    if perf >= 4.2:
        growth.append("Top-quartile performance trend.")
    if not skills:
        growth.append("Skills not yet captured — invite employee to self-document.")

    # Marketplace + nearest roles
    market_matches = [m.to_dict() for m in match_employee_to_marketplace(
        employee_id=employee_id, employee_name=name,
        employee_skills=skills, performance_rating=perf, tenure_years=tenure_years,
    )][:5]
    nearest = nearest_roles(skills) if skills else []
    # Default skill gap: to the top nearest role
    default_target = (nearest[0]["role"] if nearest else (title or "")).lower() if nearest else ""
    gap = skill_gap(skills, default_target) if default_target else {
        "target_role": title or "",
        "known": skills,
        "needed": [],
        "gap": [],
        "coverage_percent": 100,
        "note": "No target role set.",
    }

    return DigitalTwin(
        is_sample=is_sample,
        employee_id=employee_id,
        name=name,
        email=email,
        job_title=title,
        department=dept,
        location=location,
        start_date=start_date,
        tenure_years=round(tenure_years, 1),
        skills=skills,
        performance_rating=perf,
        compa_ratio=compa,
        pto_balance_days=pto_balance,
        engagement_score=engagement,
        growth_signals=growth,
        attrition=pred.to_dict(),
        nearest_roles=nearest,
        marketplace_matches=market_matches,
        skill_gap_to_next=gap,
    )
