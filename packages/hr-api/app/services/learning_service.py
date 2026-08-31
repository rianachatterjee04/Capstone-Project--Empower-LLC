"""Learning & skills graph service (Sana-inspired layer, original IP).

Provides:
- skills extraction from a role / job description
- skill-gap analysis vs. an employee's current skill set
- course recommendations from a built-in catalog
- learning path generation based on the target role
- internal mobility (nearest-role) suggestions

The catalog is in-process for demo purposes; in production this would back
onto Postgres tables. All public APIs operate on plain dicts so the FastAPI
router can return them directly without extra schema layers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from app.services.resume_matching_service import extract_skills


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Course:
    id: str
    title: str
    provider: str
    level: str           # "intro" | "intermediate" | "advanced"
    duration_minutes: int
    skills: tuple[str, ...]
    is_compliance: bool = False


CATALOG: list[Course] = [
    Course("c-py-101", "Python for Working Professionals", "Foundry Learning", "intro", 240, ("python",)),
    Course("c-py-301", "Production Python — Async, Typing, Testing", "Foundry Learning", "advanced", 360, ("python", "fastapi")),
    Course("c-ts-201", "TypeScript Deep Dive", "Foundry Learning", "intermediate", 300, ("typescript", "javascript")),
    Course("c-react-201", "Modern React with Server Components", "Foundry Learning", "intermediate", 320, ("react", "typescript", "next.js")),
    Course("c-sql-101", "SQL Fundamentals", "Foundry Learning", "intro", 180, ("sql", "postgresql")),
    Course("c-aws-201", "AWS for Engineers", "Foundry Learning", "intermediate", 420, ("aws", "docker")),
    Course("c-k8s-301", "Kubernetes in Production", "Foundry Learning", "advanced", 480, ("kubernetes", "docker")),
    Course("c-ml-201", "Applied ML for Product Teams", "Foundry Learning", "intermediate", 360, ("machine learning", "python", "data analysis")),
    Course("c-llm-301", "Building with LLMs", "Foundry Learning", "advanced", 300, ("llm", "nlp", "python")),
    Course("c-lead-101", "Leading without Authority", "Foundry Learning", "intro", 180, ("leadership", "communication")),
    Course("c-comm-201", "Executive Communication", "Foundry Learning", "intermediate", 200, ("communication",)),
    Course("c-pm-101", "Agile & Scrum Essentials", "Foundry Learning", "intro", 160, ("project management",)),

    # Compliance
    Course("c-comp-soc2", "SOC 2 Awareness Training", "Foundry Compliance", "intro", 60, ("compliance",), is_compliance=True),
    Course("c-comp-harassment", "Workplace Respect & Harassment Prevention", "Foundry Compliance", "intro", 75, ("compliance",), is_compliance=True),
    Course("c-comp-privacy", "Data Privacy & GDPR Basics", "Foundry Compliance", "intro", 60, ("compliance",), is_compliance=True),
    Course("c-comp-security", "Security Basics for All Employees", "Foundry Compliance", "intro", 45, ("compliance",), is_compliance=True),
]


# ---------------------------------------------------------------------------
# Role -> required-skill profile
# ---------------------------------------------------------------------------
ROLE_PROFILES: dict[str, list[str]] = {
    "software engineer": ["python", "sql", "react", "aws", "docker"],
    "senior software engineer": ["python", "sql", "react", "aws", "docker", "kubernetes", "leadership"],
    "staff engineer": ["python", "aws", "kubernetes", "leadership", "communication", "ci/cd"],
    "data engineer": ["python", "sql", "postgresql", "aws", "snowflake"],
    "data scientist": ["python", "machine learning", "data analysis", "sql", "nlp"],
    "ml engineer": ["python", "machine learning", "llm", "aws", "docker"],
    "product manager": ["project management", "communication", "leadership", "data analysis"],
    "engineering manager": ["leadership", "communication", "project management", "python", "aws"],
    "hr manager": ["hr", "communication", "compliance", "leadership"],
    "sales executive": ["communication", "salesforce"],
    "designer": ["communication", "react"],
}


def _course_to_dict(c: Course) -> dict:
    return {
        "id": c.id,
        "title": c.title,
        "provider": c.provider,
        "level": c.level,
        "duration_minutes": c.duration_minutes,
        "skills": list(c.skills),
        "is_compliance": c.is_compliance,
    }


def _normalize_role(title: str) -> Optional[str]:
    t = (title or "").strip().lower()
    if not t:
        return None
    if t in ROLE_PROFILES:
        return t
    # fuzzy contains match
    for key in ROLE_PROFILES:
        if all(word in t for word in key.split()):
            return key
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def list_courses(skill: Optional[str] = None, compliance_only: bool = False) -> list[dict]:
    rows = CATALOG
    if compliance_only:
        rows = [c for c in rows if c.is_compliance]
    if skill:
        s = skill.lower()
        rows = [c for c in rows if s in c.skills]
    return [_course_to_dict(c) for c in rows]


def required_skills_for(role: str) -> list[str]:
    norm = _normalize_role(role)
    return list(ROLE_PROFILES.get(norm, [])) if norm else []


def skill_gap(current_skills: Iterable[str], target_role: str) -> dict:
    cur = {s.lower() for s in current_skills}
    needed = required_skills_for(target_role)
    if not needed:
        return {
            "target_role": target_role,
            "known": sorted(cur),
            "needed": [],
            "gap": [],
            "coverage_percent": 0,
            "note": "Role profile not found — using free-form skill list only.",
        }
    have = sorted(s for s in needed if s in cur)
    missing = sorted(s for s in needed if s not in cur)
    coverage = int(round((len(have) / max(len(needed), 1)) * 100))
    return {
        "target_role": target_role,
        "known": have,
        "needed": needed,
        "gap": missing,
        "coverage_percent": coverage,
    }


def recommend_courses_for_gap(gap_skills: Iterable[str], max_results: int = 6) -> list[dict]:
    gap = [s.lower() for s in gap_skills]
    if not gap:
        return []
    scored: list[tuple[int, Course]] = []
    for c in CATALOG:
        if c.is_compliance:
            continue
        overlap = sum(1 for s in c.skills if s in gap)
        if overlap > 0:
            scored.append((overlap, c))
    scored.sort(key=lambda kv: kv[0], reverse=True)
    return [_course_to_dict(c) for _, c in scored[:max_results]]


def required_compliance_training() -> list[dict]:
    return [_course_to_dict(c) for c in CATALOG if c.is_compliance]


def build_learning_path(current_role: str, target_role: str, current_skills: Iterable[str]) -> dict:
    gap = skill_gap(current_skills, target_role)
    courses = recommend_courses_for_gap(gap.get("gap", []))
    return {
        "from_role": current_role,
        "to_role": target_role,
        "skill_gap": gap,
        "recommended_courses": courses,
        "estimated_hours": round(sum(c["duration_minutes"] for c in courses) / 60.0, 1),
        "next_steps": [
            f"Complete {c['title']}" for c in courses[:3]
        ] or ["No further courses required — you meet the target skill profile."],
    }


def nearest_roles(current_skills: Iterable[str], max_results: int = 5) -> list[dict]:
    """Return roles ordered by coverage of the employee's existing skills."""
    cur = {s.lower() for s in current_skills}
    if not cur:
        return []
    ranked: list[dict] = []
    for role, needs in ROLE_PROFILES.items():
        if not needs:
            continue
        have = [s for s in needs if s in cur]
        coverage = int(round(len(have) / len(needs) * 100))
        ranked.append({
            "role": role,
            "coverage_percent": coverage,
            "matched_skills": have,
            "missing_skills": [s for s in needs if s not in cur],
        })
    ranked.sort(key=lambda r: r["coverage_percent"], reverse=True)
    return ranked[:max_results]


def extract_skills_from_text(text: str) -> list[str]:
    """Thin wrapper exposing the ontology-based extractor for the API layer."""
    skills, _ = extract_skills(text or "")
    return sorted(skills)
