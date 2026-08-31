"""Referral Intelligence router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import Actor, require_org
from app.services.referrals_service import (
    jobs_for_employee,
    leaderboard,
    list_referrals,
    rank_employees_for_job,
    stats,
    submit_referral,
    update_referral_status,
)

router = APIRouter(prefix="/referrals", tags=["referrals"])


def _allowed(actor: Actor) -> bool:
    # Every employee can see/submit referrals; HR sees all.
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager", "employee")


@router.get("/stats")
async def stats_endpoint(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return stats(actor.org_id)


@router.get("/leaderboard")
async def leaderboard_endpoint(limit: int = Query(10, ge=1, le=50), actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [p.__dict__ for p in leaderboard(actor.org_id, limit=limit)]}


@router.get("")
async def list_endpoint(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [r.to_dict() for r in list_referrals(actor.org_id)]}


@router.post("")
async def submit_endpoint(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    candidate_name = (payload.get("candidate_name") or "").strip()
    referrer_employee_id = (payload.get("referrer_employee_id") or "").strip()
    job_id = (payload.get("job_id") or "").strip()
    if not candidate_name or not referrer_employee_id or not job_id:
        raise HTTPException(status_code=400, detail="referrer_employee_id, job_id, candidate_name required")
    ref = submit_referral(
        actor.org_id,
        referrer_employee_id,
        job_id,
        candidate_name,
        candidate_email=(payload.get("candidate_email") or "").strip(),
        relationship=(payload.get("relationship") or "former_colleague"),
        note=(payload.get("note") or "").strip(),
    )
    return ref.to_dict()


@router.patch("/{referral_id}")
async def patch_status(referral_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    status = (payload.get("status") or "").strip()
    if status not in ("submitted", "contacted", "interviewing", "hired", "not_hired", "withdrawn"):
        raise HTTPException(status_code=400, detail="invalid status")
    out = update_referral_status(actor.org_id, referral_id, status)
    if not out:
        raise HTTPException(status_code=404, detail="Referral not found")
    return out.to_dict()


@router.get("/matches-for-employee/{employee_id}")
async def matches_for_employee(employee_id: str, limit: int = Query(6, ge=1, le=20), actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [m.__dict__ for m in jobs_for_employee(actor.org_id, employee_id, limit=limit)]}


@router.post("/matches-for-job")
async def matches_for_job(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    job_id = (payload.get("job_id") or "").strip()
    job_title = (payload.get("job_title") or "").strip()
    job_skills = payload.get("job_skills") or []
    if not job_id or not job_title:
        raise HTTPException(status_code=400, detail="job_id, job_title required")
    items = rank_employees_for_job(actor.org_id, job_id, job_title, job_skills, limit=int(payload.get("limit") or 8))
    return {"items": [m.__dict__ for m in items]}
