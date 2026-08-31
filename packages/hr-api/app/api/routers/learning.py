"""Learning hub + skills graph router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.learning_service import (
    build_learning_path,
    extract_skills_from_text,
    list_courses,
    nearest_roles,
    recommend_courses_for_gap,
    required_compliance_training,
    required_skills_for,
    skill_gap,
)

router = APIRouter(prefix="/learning", tags=["learning"])


@router.get("/courses")
async def courses(skill: str | None = None, compliance: bool = False, _: Actor = Depends(require_org)):
    return {"items": list_courses(skill=skill, compliance_only=compliance)}


@router.get("/compliance-required")
async def compliance(_: Actor = Depends(require_org)):
    return {"items": required_compliance_training()}


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
async def path(payload: dict, _: Actor = Depends(require_org)):
    return build_learning_path(
        current_role=payload.get("current_role") or "",
        target_role=payload.get("target_role") or "",
        current_skills=payload.get("current_skills") or [],
    )


@router.get("/role-profile/{role}")
async def role_profile(role: str, _: Actor = Depends(require_org)):
    return {"role": role, "required_skills": required_skills_for(role)}


@router.post("/extract-skills")
async def extract(payload: dict, _: Actor = Depends(require_org)):
    return {"skills": extract_skills_from_text(payload.get("text") or "")}


@router.post("/nearest-roles")
async def mobility(payload: dict, _: Actor = Depends(require_org)):
    current = payload.get("current_skills") or []
    if isinstance(current, str):
        current = [s.strip() for s in current.split(",") if s.strip()]
    return {"items": nearest_roles(current)}
