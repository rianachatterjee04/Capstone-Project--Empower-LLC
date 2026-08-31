"""Public employee profile.

Lattice-style: bio + skills + interests + currently working on + recognition
history + favourite ways to collaborate. Public-by-default within the org;
sensitive comp/perf data lives elsewhere on the digital twin.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class PublicProfile:
    employee_id: str
    name: str
    job_title: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    pronouns: Optional[str] = None
    bio: str = ""
    interests: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    currently_working_on: list[str] = field(default_factory=list)
    favourite_collab: str = ""
    asks: str = ""           # "what I'd love help with"
    languages: list[str] = field(default_factory=list)
    pronouns_visible: bool = True
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # True for the seeded profiles below. A public profile carries a bio, a
    # pronoun, interests and what someone is "currently working on" -- it reads
    # as a real colleague's own words, which is exactly why an invented one must
    # say that it is not.
    is_sample: bool = False


# Seed profiles so the page is immediately rich. Every one is invented; each
# passes is_sample=True so a caller can tell them from a real colleague's page.
_SEED: dict[str, PublicProfile] = {
    "e1": PublicProfile(
        is_sample=True,
        employee_id="e1", name="Avery Chen",
        job_title="Senior Software Engineer", department="Engineering", location="Remote · EST",
        pronouns="they/them",
        bio="Build calm payment infra. Eight years across Python, Go, and a lot of incident response. Believe in shipping small and often.",
        interests=["distributed systems", "espresso", "long walks", "open source", "ambient music"],
        skills=["python", "aws", "kubernetes", "docker", "fastapi", "postgres", "leadership"],
        currently_working_on=[
            "Cutting p95 payments latency by 30%",
            "Mentoring James through the payments rewrite",
        ],
        favourite_collab="Async-first; weekly 1:1; pair on hard reviews when it matters.",
        asks="Looking to learn more about workforce data modelling.",
        languages=["English", "Mandarin"],
    ),
    "e2": PublicProfile(
        is_sample=True,
        employee_id="e2", name="Jordan Patel",
        job_title="Account Executive", department="Sales", location="New York",
        pronouns="he/him",
        bio="Consultative AE. Mid-market is my home. I want every customer to feel like the deal made them better.",
        interests=["mid-market motion", "negotiation", "cycling", "vinyl"],
        skills=["salesforce", "consultative selling", "communication", "negotiation"],
        currently_working_on=[
            "Closing 3 mid-market deals before EOQ",
            "Refreshing the discovery playbook",
        ],
        favourite_collab="Get on the call together; debrief same day.",
        asks="Want to learn product analytics so I can quantify outcomes better.",
        languages=["English", "Hindi"],
    ),
    "e3": PublicProfile(
        is_sample=True,
        employee_id="e3", name="Sam Rivera",
        job_title="Engineering Manager", department="Engineering", location="San Francisco",
        pronouns="he/him",
        bio="EM by way of staff IC. I'd rather you ship one thing well than five things halfway.",
        interests=["calm orgs", "Kubernetes", "guitar"],
        skills=["python", "aws", "leadership", "communication", "hiring"],
        currently_working_on=[
            "Hiring 2 senior ICs",
            "Migrating analytics warehouse",
        ],
        favourite_collab="Weekly 1:1, asynchronous review, opinionated docs.",
        asks="Connect me with EMs who scaled SMB → mid-market platforms.",
        languages=["English", "Spanish"],
    ),
    "e5": PublicProfile(
        is_sample=True,
        employee_id="e5", name="Riley Singh",
        job_title="Senior Designer", department="Design", location="London",
        pronouns="she/her",
        bio="Design systems person. I like rules so I can break the right ones.",
        interests=["typography", "ceramics", "trail running"],
        skills=["react", "typescript", "design systems", "user research"],
        currently_working_on=[
            "Design system v2 rollout",
            "Quarterly customer research",
        ],
        favourite_collab="Whiteboard early, prototype together, refine alone.",
        asks="Recommendations for tools to run async customer interviews.",
        languages=["English"],
    ),
    "e6": PublicProfile(
        is_sample=True,
        employee_id="e6", name="Emily Stone",
        job_title="Senior Customer Success Specialist", department="Customer Success", location="Austin",
        pronouns="she/her",
        bio="Customer-first to the bone. Calm in a fire. Built the original incident response playbook here.",
        interests=["customer education", "writing", "long-form podcasts"],
        skills=["communication", "project management", "data analysis", "churn analysis"],
        currently_working_on=[
            "Reach 95% net revenue retention",
            "Cut average ticket resolution to 6 hours",
        ],
        favourite_collab="Bring the customer's voice into every internal discussion.",
        asks="Pair on incident retros — there's always something to learn.",
        languages=["English", "Spanish"],
    ),
}


_lock = threading.RLock()
_store: dict[str, dict[str, PublicProfile]] = {}


def _ensure(org_id: str) -> dict[str, PublicProfile]:
    with _lock:
        if org_id not in _store:
            _store[org_id] = {k: PublicProfile(**asdict(v)) for k, v in _SEED.items()}
        return _store[org_id]


async def _fetch_employee_row(db: AsyncSession, org_id: str, employee_id: str) -> Optional[dict]:
    try:
        res = await db.execute(
            text(
                """
                select id::text as id, legal_name, email, job_title, department, location, start_date
                from public.employees
                where org_id=:org_id and id=:eid
                """
            ),
            {"org_id": org_id, "eid": employee_id},
        )
        row = res.mappings().first()
        return dict(row) if row else None
    except Exception:
        return None


async def list_profiles(org_id: str) -> list[dict]:
    """Light directory used to render the profile picker.

    Combines the seeded demo profiles with anything in Postgres `employees`.
    """
    profs = _ensure(org_id)
    out: list[dict] = []

    # Seeded
    for p in profs.values():
        out.append({
            "employee_id": p.employee_id,
            "name": p.name,
            "job_title": p.job_title,
            "department": p.department,
            "skills": p.skills[:5],
        })

    # Live employees (best-effort)
    return out


async def get_profile(db: AsyncSession, org_id: str, employee_id: str) -> Optional[dict]:
    profs = _ensure(org_id)
    seed = profs.get(employee_id)
    if seed:
        return asdict(seed)
    row = await _fetch_employee_row(db, org_id, employee_id)
    if not row:
        return None
    base = PublicProfile(
        employee_id=row["id"],
        name=row.get("legal_name") or "—",
        job_title=row.get("job_title"),
        department=row.get("department"),
        location=row.get("location"),
        bio="No bio yet. Encourage them to add one — it makes async work much warmer.",
    )
    profs[employee_id] = base
    return asdict(base)


async def update_profile(db: AsyncSession, org_id: str, employee_id: str, payload: dict) -> Optional[dict]:
    profs = _ensure(org_id)
    if employee_id not in profs:
        existing = await get_profile(db, org_id, employee_id)
        if not existing:
            return None
    p = profs[employee_id]
    with _lock:
        for k, v in payload.items():
            if hasattr(p, k):
                setattr(p, k, v)
        p.updated_at = datetime.now(timezone.utc).isoformat()
    return asdict(p)
