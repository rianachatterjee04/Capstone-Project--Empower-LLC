"""Employee skills and role skill requirements.

Two jobs:

  * Employee skills: what each person can do, and how well (level 1 to 4).
  * Role requirements: what each role needs, and how well (level 1 to 4).

The skill gap analysis compares the two, so they share one scale. Both live in
Postgres (see migrations/20261029_employee_skills.sql), so nothing is lost when
the server restarts.

The pure helpers at the top (cleaning names, checking levels, comparing a
person to a role) need no database. The functions below them are thin SQL.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.learning_service import ROLE_PROFILES, required_skills_for

MIN_LEVEL = 1
MAX_LEVEL = 4
DEFAULT_LEVEL = 2
MAX_NAME_LENGTH = 80
LEVEL_NAMES = {1: "Beginner", 2: "Working", 3: "Advanced", 4: "Expert"}
SOURCES = ("self", "hr")


class SkillsError(Exception):
    """A request the person can fix. ``status`` is the HTTP code to answer with."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------
def clean_name(value: object, what: str = "skill") -> str:
    """Lower case, single spaces. "  Python  " and "python" are the same skill."""
    if not isinstance(value, str):
        raise SkillsError(f"The {what} must be text.")
    name = re.sub(r"\s+", " ", value).strip().lower()
    if not name:
        raise SkillsError(f"The {what} cannot be empty.")
    if len(name) > MAX_NAME_LENGTH:
        raise SkillsError(f"The {what} must be {MAX_NAME_LENGTH} characters or fewer.")
    return name


def check_level(value: object) -> int:
    # bool is an int in Python, so True would otherwise pass as level 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise SkillsError(f"The level must be a whole number from {MIN_LEVEL} to {MAX_LEVEL}.")
    if value < MIN_LEVEL or value > MAX_LEVEL:
        raise SkillsError(f"The level must be from {MIN_LEVEL} to {MAX_LEVEL}.")
    return value


def clean_requirements(items: object) -> list[dict]:
    """Validate a whole list of {skill, required_level}. A repeated skill keeps the last level."""
    if not isinstance(items, list):
        raise SkillsError("items must be a list.")
    by_skill: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            raise SkillsError("Each item needs a skill and a required_level.")
        skill = clean_name(item.get("skill"))
        level = check_level(item.get("required_level", DEFAULT_LEVEL))
        by_skill[skill] = level
    return [{"skill": s, "required_level": lv} for s, lv in sorted(by_skill.items())]


def compare_to_role(skills: Iterable[dict], requirements: Iterable[dict]) -> dict:
    """Which required skills a person meets, is below, or is missing.

    ``skills`` are {skill, level}; ``requirements`` are {skill, required_level}.
    """
    have = {clean_name(s["skill"]): int(s["level"]) for s in skills}
    met, below, missing = [], [], []
    for r in requirements:
        name, need = r["skill"], int(r["required_level"])
        level = have.get(name)
        row = {"skill": name, "required_level": need, "level": level}
        if level is None:
            missing.append(row)
        elif level < need:
            below.append(row)
        else:
            met.append(row)
    total = len(met) + len(below) + len(missing)
    return {
        "met": met,
        "below": below,
        "missing": missing,
        "coverage_percent": int(round(len(met) / total * 100)) if total else 0,
    }


def default_requirements(role: str) -> list[dict]:
    """The built in starting list for a role, at the default level."""
    return [{"skill": s, "required_level": DEFAULT_LEVEL} for s in required_skills_for(role)]


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------
async def employee_exists(db: AsyncSession, org_id: str, employee_id: str) -> bool:
    row = (await db.execute(text("""
        select 1 from public.employees
         where id = cast(:employee_id as uuid) and org_id = cast(:org_id as uuid)
    """), {"employee_id": employee_id, "org_id": org_id})).first()
    return row is not None


async def employee_id_for_user(db: AsyncSession, org_id: str, user_id: str) -> Optional[str]:
    """The employee record that belongs to this signed in user, if any."""
    try:
        row = (await db.execute(text("""
            select id from public.employees
             where org_id = cast(:org_id as uuid) and user_id = cast(:user_id as uuid)
             limit 1
        """), {"org_id": org_id, "user_id": user_id})).first()
    except Exception:
        # user_id is not always a uuid (dev tokens). No match is the safe answer.
        await db.rollback()
        return None
    return str(row[0]) if row else None


# ---------------------------------------------------------------------------
# Employee skills
# ---------------------------------------------------------------------------
def _skill_row(r) -> dict:
    return {
        "skill": r["skill"],
        "level": r["level"],
        "level_name": LEVEL_NAMES.get(r["level"], ""),
        "source": r["source"],
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }


async def list_employee_skills(db: AsyncSession, org_id: str, employee_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        select skill, level, source, updated_at
          from public.employee_skills
         where org_id = cast(:org_id as uuid) and employee_id = cast(:employee_id as uuid)
         order by skill
    """), {"org_id": org_id, "employee_id": employee_id})).mappings().all()
    return [_skill_row(r) for r in rows]


async def save_employee_skill(
    db: AsyncSession, org_id: str, employee_id: str, skill: object, level: object, source: str,
) -> dict:
    name = clean_name(skill)
    lv = check_level(level)
    if source not in SOURCES:
        raise SkillsError("Unknown source.")
    row = (await db.execute(text("""
        insert into public.employee_skills (org_id, employee_id, skill, level, source)
        values (cast(:org_id as uuid), cast(:employee_id as uuid), :skill, :level, :source)
        on conflict (org_id, employee_id, skill)
        do update set level = excluded.level, source = excluded.source, updated_at = now()
        returning skill, level, source, updated_at
    """), {"org_id": org_id, "employee_id": employee_id, "skill": name, "level": lv, "source": source})
    ).mappings().first()
    await db.commit()
    return _skill_row(row)


async def remove_employee_skill(db: AsyncSession, org_id: str, employee_id: str, skill: object) -> bool:
    name = clean_name(skill)
    res = await db.execute(text("""
        delete from public.employee_skills
         where org_id = cast(:org_id as uuid)
           and employee_id = cast(:employee_id as uuid)
           and skill = :skill
    """), {"org_id": org_id, "employee_id": employee_id, "skill": name})
    await db.commit()
    return (res.rowcount or 0) > 0


# ---------------------------------------------------------------------------
# Role requirements
# ---------------------------------------------------------------------------
async def list_roles(db: AsyncSession, org_id: str) -> list[dict]:
    """Roles an organisation has set up, plus the built in ones nobody has changed."""
    rows = (await db.execute(text("""
        select role, count(*) as n
          from public.role_skill_requirements
         where org_id = cast(:org_id as uuid)
         group by role
    """), {"org_id": org_id})).mappings().all()
    custom = {r["role"]: int(r["n"]) for r in rows}
    out = [{"role": r, "skill_count": n, "is_default": False} for r, n in custom.items()]
    for role, skills in ROLE_PROFILES.items():
        if role not in custom:
            out.append({"role": role, "skill_count": len(skills), "is_default": True})
    return sorted(out, key=lambda x: x["role"])


async def get_role_requirements(db: AsyncSession, org_id: str, role: object) -> dict:
    name = clean_name(role, "role")
    rows = (await db.execute(text("""
        select skill, required_level
          from public.role_skill_requirements
         where org_id = cast(:org_id as uuid) and role = :role
         order by skill
    """), {"org_id": org_id, "role": name})).mappings().all()
    if rows:
        items = [{"skill": r["skill"], "required_level": r["required_level"]} for r in rows]
        return {"role": name, "items": items, "is_default": False}
    return {"role": name, "items": default_requirements(name), "is_default": True}


async def set_role_requirements(db: AsyncSession, org_id: str, role: object, items: object) -> dict:
    """Replace a role's whole list. An empty list clears it back to the built in default."""
    name = clean_name(role, "role")
    cleaned = clean_requirements(items)
    await db.execute(text("""
        delete from public.role_skill_requirements
         where org_id = cast(:org_id as uuid) and role = :role
    """), {"org_id": org_id, "role": name})
    for item in cleaned:
        await db.execute(text("""
            insert into public.role_skill_requirements (org_id, role, skill, required_level)
            values (cast(:org_id as uuid), :role, :skill, :level)
        """), {"org_id": org_id, "role": name, "skill": item["skill"], "level": item["required_level"]})
    await db.commit()
    return await get_role_requirements(db, org_id, name)
