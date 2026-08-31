"""Recruiting Cockpit router — the API behind the agentic recruiting layer.

Endpoints expose the ``recruiting_intelligence_service`` capabilities so the
recruiter cockpit page can render a calm, mission-control surface.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import Candidate, JobPosting
from app.services.recruiting_intelligence_service import (
    candidate_experience_signals,
    candidate_insights,
    detect_bottlenecks,
    draft_outreach,
    funnel_metrics,
    recruiter_productivity,
    rollup_scorecard,
    source_for_job,
    talent_pools,
)


router = APIRouter(prefix="/recruiting-cockpit", tags=["recruiting-cockpit"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager")


# ---------------------------------------------------------------------------
@router.get("/today")
async def today(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Single roll-up the cockpit's hero card pulls — recruiter's day at a glance."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    org_uuid = UUID(actor.org_id)
    prod = await recruiter_productivity(db, org_uuid)
    bottlenecks = await detect_bottlenecks(db, org_uuid)
    cx = await candidate_experience_signals(db, org_uuid, limit=6)
    priorities: list[dict] = []

    # Stitch a prioritised "do this today" list from cross-signals
    for b in bottlenecks:
        if b.severity in ("critical", "alert"):
            priorities.append({
                "kind": "bottleneck",
                "severity": b.severity,
                "title": f"Clear {b.stage_label} stall on {b.job_title}",
                "detail": b.note,
                "job_id": b.job_id,
            })
    for s in cx:
        if s.risk in ("ghosted", "stalled"):
            priorities.append({
                "kind": "candidate_experience",
                "severity": "alert" if s.risk == "stalled" else "critical",
                "title": f"Re-engage {s.candidate_name}",
                "detail": s.note,
                "candidate_id": s.candidate_id,
            })
    # Cap to keep the UI calm
    priorities = priorities[:8]
    return {
        "productivity": prod.to_dict(),
        "bottlenecks": [b.to_dict() for b in bottlenecks],
        "candidate_experience": [c.to_dict() for c in cx],
        "today_priorities": priorities,
    }


@router.get("/bottlenecks")
async def bottlenecks(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    out = await detect_bottlenecks(db, UUID(actor.org_id))
    return {"items": [b.to_dict() for b in out]}


@router.get("/funnel")
async def funnel(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    out = await funnel_metrics(db, UUID(actor.org_id))
    return {"items": [f.to_dict() for f in out]}


@router.get("/sourcing/{job_id}")
async def sourcing(
    job_id: str,
    limit: int = Query(12, ge=1, le=50),
    include_current_applicants: bool = Query(False),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        job_uuid = UUID(job_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job_id")
    matches = await source_for_job(
        db,
        UUID(actor.org_id),
        job_uuid,
        limit=limit,
        include_current_applicants=include_current_applicants,
    )
    return {"items": [m.to_dict() for m in matches]}


@router.post("/outreach/draft")
async def outreach_draft(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Draft a first-touch + follow-up message for a candidate."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    candidate_id = payload.get("candidate_id")
    job_id = payload.get("job_id")
    channel = (payload.get("channel") or "email").lower()
    tone = (payload.get("tone") or "warm").lower()
    company_name = (payload.get("company_name") or "Foundry People").strip()
    recruiter_name = (payload.get("recruiter_name") or actor.claims.get("email") or "the recruiting team").strip()

    candidate = None
    job = None
    if candidate_id:
        try:
            candidate = (await db.execute(
                select(Candidate).where(Candidate.id == UUID(candidate_id), Candidate.org_id == UUID(actor.org_id))
            )).scalar_one_or_none()
        except Exception:
            pass
    if job_id:
        try:
            job = (await db.execute(
                select(JobPosting).where(JobPosting.id == UUID(job_id), JobPosting.org_id == UUID(actor.org_id))
            )).scalar_one_or_none()
        except Exception:
            pass

    candidate_name = (payload.get("candidate_name") or (candidate.full_name if candidate else "there")).strip()
    job_title = (payload.get("job_title") or (job.title if job else "the role")).strip()
    job_description = (payload.get("job_description") or (job.description if job else "")).strip()
    resume_text = (payload.get("resume_text") or (candidate.resume_text if candidate else "")).strip()

    draft = draft_outreach(
        candidate_name=candidate_name,
        candidate_id=str(candidate.id) if candidate else (candidate_id or ""),
        job_title=job_title,
        job_description=job_description,
        candidate_resume=resume_text,
        channel=channel,
        tone=tone,
        company_name=company_name,
        recruiter_name=recruiter_name,
    )
    return draft.to_dict()


@router.get("/candidates/{candidate_id}/insights")
async def insights(
    candidate_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        cuid = UUID(candidate_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid candidate_id")
    out = await candidate_insights(db, UUID(actor.org_id), cuid)
    if not out:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return out.to_dict()


@router.get("/talent-pools")
async def pools(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    out = await talent_pools(db, UUID(actor.org_id))
    return {"items": [p.to_dict() for p in out]}


@router.get("/productivity")
async def productivity(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    out = await recruiter_productivity(db, UUID(actor.org_id))
    return out.to_dict()


@router.get("/candidate-experience")
async def cx(
    limit: int = Query(20, ge=1, le=100),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    out = await candidate_experience_signals(db, UUID(actor.org_id), limit=limit)
    return {"items": [s.to_dict() for s in out]}


@router.post("/scorecard")
async def scorecard(
    payload: dict,
    actor: Actor = Depends(require_org),
):
    """Roll up AI screen + interview + reference signals into one card."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    candidate_id = payload.get("candidate_id") or ""
    candidate_name = payload.get("candidate_name") or ""
    if not candidate_name:
        raise HTTPException(status_code=400, detail="candidate_name required")
    out = rollup_scorecard(
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        job_id=payload.get("job_id"),
        ai_screen_score=payload.get("ai_screen_score"),
        interview_overall=payload.get("interview_overall"),
        interview_dimensions=payload.get("interview_dimensions") or {},
        reference_overall=payload.get("reference_overall"),
        reference_band=payload.get("reference_band"),
        notes=payload.get("notes") or [],
    )
    return out.to_dict()
