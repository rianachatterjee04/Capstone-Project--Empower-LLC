"""Team operating workspaces.

Per-department operational page data:
- goals (lightweight; lives alongside tasks for now)
- hiring pipeline scoped to the team
- onboarding in flight on the team
- workload + attrition signals
- learning gaps
- recent activity

Designed to be the daily home for any department.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.attrition_service import AttritionFeatures, predict_batch
from app.services.tasks_service import list_tasks, projects_overview


# -------------------- Demo team scaffolding --------------------
TEAM_PROFILES: dict[str, dict] = {
    "Engineering": {
        "manager": "Sam Rivera",
        "mission": "Ship reliable, secure platform infrastructure that scales with the company.",
        "goals": [
            {"title": "Cut p95 latency on payments by 30%", "owner": "Avery Chen", "due": "Sep 30"},
            {"title": "Migrate analytics warehouse to managed Snowflake", "owner": "Sam Rivera", "due": "Aug 15"},
            {"title": "Roll out continuous compliance scanning", "owner": "Engineering Lead", "due": "Aug 30"},
        ],
        "open_reqs": 2,
        "primary_skills": ["python", "aws", "kubernetes", "leadership"],
    },
    "Design": {
        "manager": "Riley Manager",
        "mission": "Make every Foundry surface feel calm, premium, and inevitable.",
        "goals": [
            {"title": "Ship the new design system v2", "owner": "Riley Singh", "due": "Aug 1"},
            {"title": "Run quarterly customer research", "owner": "Riley Singh", "due": "Aug 20"},
        ],
        "open_reqs": 1,
        "primary_skills": ["react", "typescript", "communication"],
    },
    "Sales": {
        "manager": "Jamie Cole",
        "mission": "Win mid-market deals with a calm, consultative motion.",
        "goals": [
            {"title": "Land 5 mid-market logos in Q3", "owner": "Jordan Patel", "due": "Sep 30"},
            {"title": "Refresh ICP + outbound playbook", "owner": "Jamie Cole", "due": "Aug 5"},
        ],
        "open_reqs": 1,
        "primary_skills": ["communication", "salesforce", "project management"],
    },
    "HR": {
        "manager": "Reese Allen",
        "mission": "Operate Foundry People itself — the company's HR operating system.",
        "goals": [
            {"title": "Q2 review cycle complete by Aug 30", "owner": "People Ops", "due": "Aug 30"},
            {"title": "Close 100% of high-severity ombudsman cases inside 30 days", "owner": "Legal + HR", "due": "Ongoing"},
        ],
        "open_reqs": 0,
        "primary_skills": ["hr", "communication", "compliance"],
    },
    "Customer Success": {
        "manager": "Avery CS Lead",
        "mission": "Make every customer renewal feel inevitable.",
        "goals": [
            {"title": "Reach 95% net revenue retention by EOY", "owner": "CS Lead", "due": "Dec 31"},
            {"title": "Cut average ticket resolution to 6 hours", "owner": "CS Ops", "due": "Aug 15"},
        ],
        "open_reqs": 1,
        "primary_skills": ["communication", "project management", "data analysis"],
    },
}


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def list_teams() -> list[dict]:
    """The five department TEMPLATES this product ships.

    These are not the reader's departments. The managers (Sam Rivera, Riley
    Manager), the missions, the goals and their named owners, and the open_reqs
    counts are all fixed here. The page rendered "Departments 5 · Headcount 0 ·
    Open requisitions 5" for an organisation with one employee in Operations
    and two genuinely open requisitions — three of those four numbers were
    template constants sitting beside one real zero, which is why the screen
    read as broken.

    Headcount per team IS real: build_workspace counts employees whose
    department matches. A template with nobody in it is a template.
    """
    rows: list[dict] = []
    for name, meta in TEAM_PROFILES.items():
        rows.append({
            "slug": slugify(name),
            "name": name,
            "manager": meta["manager"],
            "mission": meta["mission"],
            "open_reqs": meta.get("open_reqs", 0),
            "primary_skills": list(meta.get("primary_skills", [])),
            "goals": list(meta.get("goals", [])),
            "is_template": True,
            "template_note": (
                "A department template shipped with the product. Its manager, "
                "mission, goals and requisition count are examples; headcount is "
                "counted from your own employee records."
            ),
        })
    return rows


def find_team(slug_or_name: str) -> Optional[str]:
    needle = slug_or_name.lower()
    for name in TEAM_PROFILES:
        if slugify(name) == needle or name.lower() == needle:
            return name
    return None


def _synthetic_features() -> list[AttritionFeatures]:
    return [
        AttritionFeatures("e1", "Avery Chen",   department="Engineering",      tenure_years=2.4, months_since_last_raise=22, months_since_last_promotion=30, performance_rating=4.5, engagement_score=0.42, compa_ratio=0.82, overtime_hours_last_30d=38),
        AttritionFeatures("e2", "Jordan Patel", department="Sales",            tenure_years=1.8, months_since_last_raise=14, months_since_last_promotion=20, performance_rating=3.2, engagement_score=0.61, compa_ratio=0.97, pto_balance_days=22),
        AttritionFeatures("e3", "Sam Rivera",   department="Engineering",      tenure_years=3.6, months_since_last_raise=10, months_since_last_promotion=12, performance_rating=4.0, compa_ratio=1.05, engagement_score=0.78),
        AttritionFeatures("e4", "Morgan Lee",   department="HR",               tenure_years=0.6, months_since_last_raise=6,  months_since_last_promotion=0,  performance_rating=3.6, compa_ratio=0.99, manager_change_in_last_180d=True),
        AttritionFeatures("e5", "Riley Singh",  department="Design",           tenure_years=2.0, months_since_last_raise=18, months_since_last_promotion=24, performance_rating=4.8, compa_ratio=0.88, role_change_in_last_180d=True, pto_balance_days=19),
        AttritionFeatures("e6", "Emily Stone",  department="Customer Success", tenure_years=1.8, months_since_last_raise=10, months_since_last_promotion=20, performance_rating=4.6, engagement_score=0.71, compa_ratio=0.94),
    ]


async def _scalar(db, sql: str, params: dict) -> int:
    try:
        row = (await db.execute(text(sql), params)).first()
        return int(row[0]) if row and row[0] is not None else 0
    except Exception:
        return 0


async def _rows(db, sql: str, params: dict) -> list[dict]:
    try:
        res = await db.execute(text(sql), params)
        return [dict(r) for r in res.mappings().all()]
    except Exception:
        return []


async def build_workspace(db: AsyncSession, org_id: str, team_name: str) -> dict:
    meta = TEAM_PROFILES[team_name]

    employees = await _rows(
        db,
        """
        select id::text, legal_name, email, job_title, department, status
        from public.employees
        where org_id=:org_id and lower(coalesce(department, '')) = lower(:dept)
        order by legal_name
        """,
        {"org_id": org_id, "dept": team_name},
    )
    headcount = len(employees)

    candidates = await _rows(
        db,
        """
        select c.id::text, c.full_name, c.status, c.ai_score, j.title as job_title
        from public.candidates c
        left join public.job_postings j on j.id = c.job_posting_id
        where c.org_id=:org_id
        """,
        {"org_id": org_id},
    )
    # Best-effort scope to dept by job title
    team_candidates = [
        c for c in candidates
        if (c.get("job_title") or "").lower().find(team_name.lower()[:4]) != -1
    ]

    onboarding_open = await _scalar(
        db,
        """
        select count(*) from public.onboarding_packets p
        join public.employees e on e.id = p.employee_id
        where p.org_id = :org_id
          and p.status <> 'activated'
          and lower(coalesce(e.department, '')) = lower(:dept)
        """,
        {"org_id": org_id, "dept": team_name},
    )

    preds = predict_batch(_synthetic_features())
    team_preds = [p for p in preds if p.department == team_name]
    high_risk = [p for p in team_preds if p.band == "high"]
    medium_risk = [p for p in team_preds if p.band == "medium"]

    tasks = list_tasks(org_id, department=team_name)
    overdue = 0
    now = datetime.now(timezone.utc)
    for t in tasks:
        if t.get("status") == "done" or not t.get("due_at"):
            continue
        try:
            d = datetime.fromisoformat(t["due_at"])
            if d < now:
                overdue += 1
        except Exception:
            pass

    return {
        "team": team_name,
        "slug": slugify(team_name),
        "manager": meta["manager"],
        "mission": meta["mission"],
        "primary_skills": meta.get("primary_skills", []),
        "goals": meta.get("goals", []),
        "headcount": headcount,
        "employees": employees,
        "hiring": {
            "open_reqs": meta.get("open_reqs", 0),
            "candidates": team_candidates,
        },
        "onboarding_open": onboarding_open,
        "risk": {
            "high": [p.to_dict() for p in high_risk],
            "medium": [p.to_dict() for p in medium_risk],
        },
        "tasks": {
            "items": tasks[:25],
            "open": sum(1 for t in tasks if t["status"] != "done"),
            "overdue": overdue,
        },
        "projects": [p for p in projects_overview(org_id) if team_name in (p.get("departments") or [])],
    }


async def teams_summary(db: AsyncSession, org_id: str) -> list[dict]:
    rows = []
    for team in list_teams():
        w = await build_workspace(db, org_id, team["name"])
        rows.append({
            "slug": team["slug"],
            "name": team["name"],
            "manager": team["manager"],
            "mission": team["mission"],
            "headcount": w["headcount"],
            "open_reqs": team["open_reqs"],
            "onboarding_open": w["onboarding_open"],
            "tasks_overdue": w["tasks"]["overdue"],
            "tasks_open": w["tasks"]["open"],
            "high_risk": len(w["risk"]["high"]),
            "medium_risk": len(w["risk"]["medium"]),
            # headcount is counted from employees; manager, mission, goals,
            # open_reqs and the risk cohort are template constants.
            "is_template": team.get("is_template", False),
            "template_note": team.get("template_note"),
        })
    return rows
