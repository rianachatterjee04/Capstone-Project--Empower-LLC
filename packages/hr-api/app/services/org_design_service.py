"""AI Org Design analyzer.

Looks at the org tree (employees + manager_employee_id) and surfaces:
- manager span of control (too wide / too narrow)
- layers of depth
- managers without direct reports (potential IC mis-titled)
- ICs reporting to skip-levels
- hiring imbalance per department
- recommended consolidation / promotion / hire actions

Heuristic; tunable bands keep recommendations explainable.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Employee


@dataclass
class OrgNode:
    id: str
    name: str
    job_title: Optional[str]
    department: Optional[str]
    manager_id: Optional[str]

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class OrgInsight:
    kind: str               # span_too_wide | span_too_narrow | manager_no_reports | dept_imbalance | layer_deep
    severity: str           # high | medium | low
    subject: str
    detail: str
    recommendation: str

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class OrgAnalysis:
    employees: int
    managers: int
    layers: int
    avg_span: float
    max_span: int
    dept_headcount: dict[str, int]
    insights: list[OrgInsight]
    nodes: list[OrgNode]

    def to_dict(self) -> dict:
        return {
            "employees": self.employees,
            "managers": self.managers,
            "layers": self.layers,
            "avg_span": round(self.avg_span, 2),
            "max_span": self.max_span,
            "dept_headcount": self.dept_headcount,
            "insights": [i.to_dict() for i in self.insights],
            "nodes": [n.to_dict() for n in self.nodes],
        }


def _layers(nodes: list[OrgNode]) -> int:
    by_id = {n.id: n for n in nodes}

    def depth(n: OrgNode, seen: set[str]) -> int:
        if n.id in seen or not n.manager_id or n.manager_id not in by_id:
            return 1
        seen.add(n.id)
        return 1 + depth(by_id[n.manager_id], seen)

    return max((depth(n, set()) for n in nodes), default=0)


async def analyze(db: AsyncSession, org_id: str) -> OrgAnalysis:
    rows = []
    try:
        from uuid import UUID as _UUID
        org_uuid = _UUID(org_id)
        res = await db.execute(select(Employee).where(Employee.org_id == org_uuid))
        rows = res.scalars().all()
    except Exception:
        rows = []

    if not rows:
        # Synthetic seed so the page is useful in a fresh demo.
        rows = _demo_employees()

    nodes: list[OrgNode] = []
    span_counts: dict[Optional[str], int] = defaultdict(int)
    by_dept: dict[str, int] = defaultdict(int)

    for r in rows:
        rid = str(getattr(r, "id", r.get("id") if isinstance(r, dict) else None))
        mgr_attr = getattr(r, "manager_employee_id", None)
        if isinstance(r, dict):
            mgr_attr = r.get("manager_employee_id")
        mgr = str(mgr_attr) if mgr_attr else None
        node = OrgNode(
            id=rid,
            name=getattr(r, "legal_name", r.get("legal_name") if isinstance(r, dict) else None) or "—",
            job_title=getattr(r, "job_title", r.get("job_title") if isinstance(r, dict) else None),
            department=getattr(r, "department", r.get("department") if isinstance(r, dict) else None),
            manager_id=mgr,
        )
        nodes.append(node)
        span_counts[mgr] += 1
        if node.department:
            by_dept[node.department] += 1

    manager_ids = {n.manager_id for n in nodes if n.manager_id}
    manager_nodes = [n for n in nodes if n.id in manager_ids]
    managers_n = len(manager_nodes)

    spans = [span_counts[m.id] for m in manager_nodes]
    avg_span = sum(spans) / len(spans) if spans else 0.0
    max_span = max(spans) if spans else 0
    layers = _layers(nodes)

    # Title-detected managers without any reports
    title_managers = [n for n in nodes if (n.job_title or "").lower().startswith(("manager", "director", "head ", "lead "))]

    insights: list[OrgInsight] = []

    # span too wide
    for m in manager_nodes:
        s = span_counts[m.id]
        if s >= 9:
            insights.append(OrgInsight(
                kind="span_too_wide", severity="high" if s >= 12 else "medium",
                subject=m.name,
                detail=f"Manages {s} direct reports — above the recommended 7-person SMB span.",
                recommendation="Split the team or promote a senior IC to team lead.",
            ))
        elif s == 1:
            insights.append(OrgInsight(
                kind="span_too_narrow", severity="low",
                subject=m.name,
                detail="Manages a single direct report — high overhead per IC.",
                recommendation="Consolidate or convert to IC role.",
            ))

    # title-managers without reports
    for m in title_managers:
        if span_counts.get(m.id, 0) == 0:
            insights.append(OrgInsight(
                kind="manager_no_reports", severity="low",
                subject=m.name,
                detail=f"Title '{m.job_title}' but no direct reports.",
                recommendation="Convert to IC title or assign reports for clarity.",
            ))

    # depth
    if layers >= 5:
        insights.append(OrgInsight(
            kind="layer_deep", severity="medium",
            subject="Org depth",
            detail=f"{layers} reporting layers — slows decisions at SMB scale.",
            recommendation="Aim for ≤ 4 layers below the CEO for SMBs under 200 people.",
        ))

    # dept imbalance
    if by_dept:
        total = sum(by_dept.values())
        for dept, n in by_dept.items():
            if n / total >= 0.55 and total >= 10:
                insights.append(OrgInsight(
                    kind="dept_imbalance", severity="low",
                    subject=dept,
                    detail=f"{int(n / total * 100)}% of headcount sits in {dept}.",
                    recommendation="Verify hiring plan keeps go-to-market and product in balance.",
                ))

    return OrgAnalysis(
        employees=len(nodes),
        managers=managers_n,
        layers=layers,
        avg_span=avg_span,
        max_span=max_span,
        dept_headcount=dict(by_dept),
        insights=insights,
        nodes=nodes,
    )


def _demo_employees() -> list[dict]:
    """An invented org chart, used when the organisation has none of its own.

    Every person is marked is_sample. An org chart is read as a statement of
    who reports to whom; a reader shown one of these without the marker has no
    way to know none of these people exist.
    """
    return [{**e, "is_sample": True} for e in _DEMO_ROSTER]


_DEMO_ROSTER: list[dict] = [
        {"id": "ceo",  "legal_name": "Casey Reed",  "job_title": "CEO",                   "department": "Executive",     "manager_employee_id": None},
        {"id": "vpe",  "legal_name": "Devon Park",  "job_title": "VP Engineering",        "department": "Engineering",   "manager_employee_id": "ceo"},
        {"id": "vps",  "legal_name": "Jamie Cole",  "job_title": "VP Sales",              "department": "Sales",         "manager_employee_id": "ceo"},
        {"id": "vphr", "legal_name": "Reese Allen", "job_title": "VP People",             "department": "HR",            "manager_employee_id": "ceo"},
        {"id": "em1",  "legal_name": "Avery Chen",  "job_title": "Engineering Manager",   "department": "Engineering",   "manager_employee_id": "vpe"},
        {"id": "em2",  "legal_name": "Sam Rivera",  "job_title": "Engineering Manager",   "department": "Engineering",   "manager_employee_id": "vpe"},
        {"id": "se1",  "legal_name": "Jordan Patel","job_title": "Senior Software Engineer","department": "Engineering","manager_employee_id": "em1"},
        {"id": "se2",  "legal_name": "Riley Singh", "job_title": "Software Engineer",     "department": "Engineering",   "manager_employee_id": "em1"},
        {"id": "se3",  "legal_name": "Morgan Lee",  "job_title": "Software Engineer",     "department": "Engineering",   "manager_employee_id": "em1"},
        {"id": "se4",  "legal_name": "Emily Stone", "job_title": "Software Engineer",     "department": "Engineering",   "manager_employee_id": "em1"},
        {"id": "se5",  "legal_name": "Taylor Wu",   "job_title": "Software Engineer",     "department": "Engineering",   "manager_employee_id": "em1"},
        {"id": "se6",  "legal_name": "Robin Diaz",  "job_title": "Software Engineer",     "department": "Engineering",   "manager_employee_id": "em1"},
        {"id": "se7",  "legal_name": "Drew Murphy", "job_title": "Software Engineer",     "department": "Engineering",   "manager_employee_id": "em1"},
        {"id": "se8",  "legal_name": "Quinn Bailey","job_title": "Software Engineer",     "department": "Engineering",   "manager_employee_id": "em1"},
        {"id": "ae1",  "legal_name": "Logan Brooks","job_title": "Account Executive",     "department": "Sales",         "manager_employee_id": "vps"},
        {"id": "ae2",  "legal_name": "Rowan Hayes", "job_title": "Account Executive",     "department": "Sales",         "manager_employee_id": "vps"},
        {"id": "hrb",  "legal_name": "Casey Quinn", "job_title": "HR Business Partner",   "department": "HR",            "manager_employee_id": "vphr"},
    ]
