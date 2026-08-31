"""Content generation router — JDs, scorecards, balanced feedback, onboarding."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org, required_field
from app.services.content_gen_service import (
    generate_interview_scorecard,
    generate_job_description,
    generate_onboarding_plan,
    rewrite_balanced,
    detect_vague_or_biased,
)


router = APIRouter(prefix="/content", tags=["content"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "manager", "recruiter")


@router.post("/job-description")
async def jd(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    if not payload.get("title"):
        raise HTTPException(status_code=400, detail="title required")
    return generate_job_description(
        title=required_field(payload, "title"),
        level=payload.get("level") or "mid",
        department=payload.get("department") or "",
        location=payload.get("location") or "Remote",
        notes=payload.get("notes") or "",
    )


@router.post("/interview-scorecard")
async def scorecard(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    if not payload.get("role"):
        raise HTTPException(status_code=400, detail="role required")
    return generate_interview_scorecard(
        role=required_field(payload, "role"),
        competencies=payload.get("competencies") or None,
    )


@router.post("/feedback/detect")
async def detect(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return detect_vague_or_biased(payload.get("text") or "")


@router.post("/feedback/rewrite")
async def rewrite(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    if not payload.get("text"):
        raise HTTPException(status_code=400, detail="text required")
    return rewrite_balanced(
        text=required_field(payload, "text"),
        employee_name=payload.get("employee_name") or "the employee",
    )


@router.post("/onboarding-plan")
async def onboarding(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    if not payload.get("employee_name") or not payload.get("role"):
        raise HTTPException(status_code=400, detail="employee_name and role required")
    return generate_onboarding_plan(
        employee_name=required_field(payload, "employee_name"),
        role=required_field(payload, "role"),
        manager_name=payload.get("manager_name") or "your manager",
        start_date=payload.get("start_date") or "Day 1",
    )
