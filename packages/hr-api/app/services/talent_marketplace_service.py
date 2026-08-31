"""Internal Talent Marketplace.

Matches employees to *internal* roles based on skill profile + performance +
career trajectory. Surfaces high-potential candidates for stretch assignments
and succession.

Differentiator vs. external ATS: the inputs are the employee's own digital
twin, not a resume. The output is a ranked list with explainable evidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.services.learning_service import (
    ROLE_PROFILES,
    nearest_roles,
    required_skills_for,
    skill_gap,
)


@dataclass
class OpenInternalRole:
    id: str
    title: str
    department: str
    skills_required: list[str]
    seniority: str
    posted_by: str = "internal_mobility"

    def to_dict(self) -> dict:
        return self.__dict__


# Demo seed — production would query a real internal_roles table.
DEMO_INTERNAL_ROLES: list[OpenInternalRole] = [
    OpenInternalRole("ir-cs-mgr", "Customer Success Manager", "Customer Success",
                     ["communication", "leadership", "project management"], "mid"),
    OpenInternalRole("ir-eng-lead", "Engineering Lead, Payments", "Engineering",
                     ["python", "aws", "leadership", "kubernetes"], "senior"),
    OpenInternalRole("ir-ds-pm", "Product Manager, Data", "Product",
                     ["project management", "data analysis", "communication"], "mid"),
    OpenInternalRole("ir-sec-lead", "Security Lead", "Engineering",
                     ["aws", "compliance", "leadership"], "senior"),
]


@dataclass
class MarketplaceMatch:
    employee_id: str
    employee_name: str
    role: OpenInternalRole
    score: int                  # 0-100
    coverage_percent: int
    matched_skills: list[str]
    missing_skills: list[str]
    learning_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "employee_id": self.employee_id,
            "employee_name": self.employee_name,
            "role": self.role.to_dict(),
            "score": self.score,
            "coverage_percent": self.coverage_percent,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "learning_hint": self.learning_hint,
        }


def match_employee_to_role(employee_id: str, employee_name: str, employee_skills: Iterable[str],
                            role: OpenInternalRole, performance_rating: float = 3.5,
                            tenure_years: float = 1.0) -> MarketplaceMatch:
    cur = {s.lower() for s in employee_skills}
    required = [s.lower() for s in role.skills_required]
    if not required:
        return MarketplaceMatch(employee_id, employee_name, role, 0, 0, [], [],
                                "Role has no skill profile — manual review.")
    matched = sorted(s for s in required if s in cur)
    missing = sorted(s for s in required if s not in cur)
    coverage = int(round(len(matched) / len(required) * 100))

    perf_boost = max(0, min(15, int((performance_rating - 3) * 6)))
    tenure_boost = 5 if tenure_years >= 2 else 0
    score = min(100, coverage + perf_boost + tenure_boost)

    if missing:
        hint = f"Close gap by training in: {', '.join(missing[:3])}."
    else:
        hint = "Ready now — propose for a stretch project."
    return MarketplaceMatch(
        employee_id=employee_id, employee_name=employee_name, role=role,
        score=score, coverage_percent=coverage,
        matched_skills=matched, missing_skills=missing,
        learning_hint=hint,
    )


def list_internal_roles() -> list[dict]:
    return [r.to_dict() for r in DEMO_INTERNAL_ROLES]


def match_employee_to_marketplace(employee_id: str, employee_name: str,
                                   employee_skills: list[str],
                                   performance_rating: float = 3.5,
                                   tenure_years: float = 1.0) -> list[MarketplaceMatch]:
    rows: list[MarketplaceMatch] = []
    for role in DEMO_INTERNAL_ROLES:
        rows.append(match_employee_to_role(
            employee_id, employee_name, employee_skills, role,
            performance_rating=performance_rating, tenure_years=tenure_years,
        ))
    rows.sort(key=lambda r: r.score, reverse=True)
    return rows


def succession_candidates_for_role(role_id: str, employees: list[dict]) -> list[MarketplaceMatch]:
    """Given a target role + a list of employees with skills, performance, tenure,
    return ranked succession candidates."""
    role = next((r for r in DEMO_INTERNAL_ROLES if r.id == role_id), None)
    if role is None:
        return []
    matches = [
        match_employee_to_role(
            employee_id=str(e["id"]),
            employee_name=e["name"],
            employee_skills=e.get("skills") or [],
            role=role,
            performance_rating=float(e.get("performance_rating") or 3.5),
            tenure_years=float(e.get("tenure_years") or 1.0),
        )
        for e in employees
    ]
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches


def demo_pool() -> list[dict]:
    """Synthetic employees so the marketplace shows something useful out of the box.

    Each carries is_sample. A marketplace match names a person and rates them
    against a role; without the marker a reader has no way to tell an invented
    candidate from one of their own.
    """
    return [_sample(e) for e in _POOL]


def _sample(e: dict) -> dict:
    return {**e, "is_sample": True, "provenance": "illustrative sample person"}


_POOL: list[dict] = [
        {"id": "e1", "name": "Avery Chen",  "skills": ["python","aws","docker","leadership"], "performance_rating": 4.5, "tenure_years": 2.4},
        {"id": "e2", "name": "Jordan Patel","skills": ["communication","project management","leadership"], "performance_rating": 4.0, "tenure_years": 3.0},
        {"id": "e3", "name": "Sam Rivera",  "skills": ["python","kubernetes","aws"], "performance_rating": 4.2, "tenure_years": 3.6},
        {"id": "e4", "name": "Morgan Lee",  "skills": ["communication","hr"], "performance_rating": 3.6, "tenure_years": 0.6},
        {"id": "e5", "name": "Riley Singh", "skills": ["react","typescript","communication"], "performance_rating": 4.8, "tenure_years": 2.0},
        {"id": "e6", "name": "Emily Stone", "skills": ["communication","project management","data analysis"], "performance_rating": 4.6, "tenure_years": 1.8},
    ]
