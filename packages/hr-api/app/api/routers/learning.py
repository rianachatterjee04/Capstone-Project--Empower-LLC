"""Learning hub + skills graph router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.learning_service import (
    build_learning_path,
    extract_skills_from_text,
    list_courses,
    nearest_roles,
    recommend_courses_for_gap,
    required_skills_for,
    skill_gap,
)

router = APIRouter(prefix="/learning", tags=["learning"])


def _policy_as_course(row) -> dict:
    name = row["name"] or "Policy"
    body = row["body"] or ""
    skills = extract_skills_from_text(f"{name} {body}") or ["compliance"]
    return {
        "id": str(row["id"]),
        "title": name,
        "provider": "Org policy",
        "level": "intro",
        "duration_minutes": 60,
        "skills": skills[:6],
        "is_compliance": True,
    }


async def _org_policies(db: AsyncSession, org_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        select id, name, body, status
          from public.policies
         where org_id = cast(:org_id as uuid)
           and lower(status) in ('published', 'active', 'approved')
         order by created_at desc
    """), {"org_id": org_id})).mappings().all()
    return [_policy_as_course(r) for r in rows]


async def _org_job_titles(db: AsyncSession, org_id: str) -> list[str]:
    rows = (await db.execute(text("""
        select distinct job_title
          from public.employees
         where org_id = cast(:org_id as uuid)
           and job_title is not null
           and trim(job_title) <> ''
         order by job_title
    """), {"org_id": org_id})).all()
    return [r[0] for r in rows]


@router.get("/courses")
async def courses(
    skill: str | None = None,
    compliance: bool = False,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if compliance:
        policies = await _org_policies(db, actor.org_id)
        if policies:
            if skill:
                s = skill.lower()
                policies = [c for c in policies if s in " ".join(c["skills"]).lower() or s in c["title"].lower()]
            return {"items": policies}
    return {"items": list_courses(skill=skill, compliance_only=compliance)}


@router.get("/compliance-required")
async def compliance(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Required compliance training = published org policies (ack / read)."""
    policies = await _org_policies(db, actor.org_id)
    return {"items": policies}


@router.post("/skill-gap")
async def gap(payload: dict, _: Actor = Depends(require_org)):
    current = payload.get("current_skills") or []
    if isinstance(current, str):
        current = [s.strip() for s in current.split(",") if s.strip()]
    target = payload.get("target_role") or ""
    if not target:
        raise HTTPException(status_code=400, detail="target_role required")
    gap_payload = skill_gap(current, target)
    courses = recommend_courses_for_gap(gap_payload.get("gap", []))
    return {**gap_payload, "recommended_courses": courses}


@router.post("/path")
async def path(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    current_skills = payload.get("current_skills") or []
    if isinstance(current_skills, str):
        current_skills = [s.strip() for s in current_skills.split(",") if s.strip()]
    current_role = payload.get("current_role") or ""
    target_role = payload.get("target_role") or ""

    built = build_learning_path(current_role, target_role, current_skills)
    # Prefer org policies that touch the skill gap over the static catalog alone.
    gap_skills = (built.get("skill_gap") or {}).get("gap") or []
    policies = await _org_policies(db, actor.org_id)
    if policies and gap_skills:
        gap_l = {s.lower() for s in gap_skills}
        matched = [
            p for p in policies
            if gap_l & {s.lower() for s in p["skills"]} or any(s in p["title"].lower() for s in gap_l)
        ]
        if matched:
            built["recommended_courses"] = matched[:6] + [
                c for c in built.get("recommended_courses") or [] if c not in matched
            ][:6]
            built["estimated_hours"] = round(
                sum(c.get("duration_minutes", 60) for c in built["recommended_courses"]) / 60.0, 1
            )
            built["next_steps"] = [f"Complete {c['title']}" for c in built["recommended_courses"][:3]]
    return built


@router.get("/role-profile/{role}")
async def role_profile(role: str, _: Actor = Depends(require_org)):
    return {"role": role, "required_skills": required_skills_for(role)}


@router.post("/extract-skills")
async def extract(payload: dict, _: Actor = Depends(require_org)):
    return {"skills": extract_skills_from_text(payload.get("text") or "")}


@router.post("/nearest-roles")
async def mobility(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    current = payload.get("current_skills") or []
    if isinstance(current, str):
        current = [s.strip() for s in current.split(",") if s.strip()]
    # Prefer mobility into roles that already exist in this org.
    titles = await _org_job_titles(db, actor.org_id)
    if titles:
        cur = {s.lower() for s in current}
        ranked = []
        for title in titles:
            needs = required_skills_for(title) or extract_skills_from_text(title)
            if not needs:
                continue
            have = [s for s in needs if s.lower() in cur]
            coverage = int(round(len(have) / len(needs) * 100))
            ranked.append({
                "role": title,
                "coverage_percent": coverage,
                "matched_skills": have,
                "missing_skills": [s for s in needs if s.lower() not in cur],
            })
        ranked.sort(key=lambda r: r["coverage_percent"], reverse=True)
        if ranked:
            return {"items": ranked[:5]}
    return {"items": nearest_roles(current)}
