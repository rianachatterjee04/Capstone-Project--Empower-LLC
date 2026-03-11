from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.json_utils import json_safe
from uuid import UUID
import statistics

from app.api.deps import require_org, db_session, Actor
from app.api.schemas import JobOut, JobCreate, CandidateOut, CandidateCreate
from app.db.models import JobPosting, Candidate, AuditEvent

# ⭐ Behavioral OS
from app.workflow.engine import engine

router = APIRouter(prefix="/recruiting", tags=["recruiting"])


# ---------------------------------------------------------
# Explainable AI Resume Screening (Helper)
# ---------------------------------------------------------
def explainable_ai_score(resume_text: str | None) -> tuple[int, str, list[str]]:
    txt = (resume_text or "").lower()

    skills = {
        "backend": ["python","fastapi","api","sql"],
        "frontend": ["react","typescript","ui","css"],
        "infra": ["aws","docker","kubernetes","security"],
        "domain": ["hr","payroll","compliance","finance"]
    }

    hits = []
    for group in skills.values():
        for kw in group:
            if kw in txt:
                hits.append(kw)

    score = min(100, len(hits) * 10)
    rationale = f"Matched skills: {', '.join(hits) if hits else 'none'}"

    return score, rationale, hits


# ---------------------------------------------------------
# Job Endpoints (GET & POST)
# ---------------------------------------------------------
@router.get("/jobs", response_model=list[JobOut])
async def get_jobs(
    actor: Actor = Depends(require_org), 
    db: AsyncSession = Depends(db_session)
):
    """Fetch all jobs for the current organization."""
    result = await db.execute(
        select(JobPosting).where(JobPosting.org_id == UUID(actor.org_id))
    )
    return result.scalars().all()

@router.post("/jobs", response_model=JobOut)
async def create_job(payload: JobCreate, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)
    
    # ✅ FIX 1: Prevent "multiple values for status" error
    job_data = payload.model_dump()
    job_data.pop("status", None) 

    job = JobPosting(
        org_id=org_id, 
        status="open", 
        **job_data
    )
    
    db.add(job)
    await db.flush()

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="job.created",
        entity_type="job_posting",
        entity_id=job.id,
        payload=payload.model_dump()
    ))

    await db.commit()
    await db.refresh(job)

    # 🔥 Behavioral trigger
    engine.trigger("job.created", {"org_id": actor.org_id, "job_id": str(job.id)})

    return job


# ---------------------------------------------------------
# Candidate Endpoints (GET & POST)
# ---------------------------------------------------------
@router.get("/candidates", response_model=list[CandidateOut])
async def get_candidates(
    actor: Actor = Depends(require_org), 
    db: AsyncSession = Depends(db_session)
):
    """Fetch all candidates for the current organization."""
    result = await db.execute(
        select(Candidate).where(Candidate.org_id == UUID(actor.org_id))
    )
    return result.scalars().all()

@router.post("/candidates", response_model=CandidateOut)
async def create_candidate(payload: CandidateCreate, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = UUID(actor.org_id)
    score, rationale, hits = explainable_ai_score(payload.resume_text)
    status = "screened" if score >= 40 else "needs_review"

    # ✅ FIX 2: Removed 'pipeline_stage' as it was causing an "invalid keyword" error.
    # If your Candidate model uses 'stage' instead of 'pipeline_stage', rename it below.
    cand = Candidate(
        org_id=org_id,
        job_posting_id=payload.job_posting_id,
        full_name=payload.full_name,
        email=payload.email,
        resume_text=payload.resume_text,
        ai_score=score,
        ai_summary=rationale,
        status=status,
        # pipeline_stage="applied",  # <-- Removed to fix 500 error
        ai_metadata={"matched_skills": hits}
    )

    db.add(cand)
    await db.flush()

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="candidate.screened",
        entity_type="candidate",
        entity_id=cand.id,
        payload={"score": score, "rationale": rationale}
    ))

    await db.commit()
    await db.refresh(cand)

    # 🔥 Behavioral OS trigger
    engine.trigger(
        "candidate.created",
        {
            "org_id": actor.org_id,
            "candidate_id": str(cand.id),
            "job_id": str(cand.job_posting_id),
            "ai_score": score,
            "stage": "applied"
        }
    )

    return cand


# ---------------------------------------------------------
# Pipeline & Decisions
# ---------------------------------------------------------
@router.post("/candidates/{candidate_id}/stage")
async def move_stage(candidate_id: str, stage: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    allowed = ["applied","interview","committee","offer","hired","rejected"]
    if stage not in allowed:
        raise HTTPException(status_code=400, detail="Invalid stage")

    cand = await db.get(Candidate, UUID(candidate_id))
    if not cand or str(cand.org_id) != actor.org_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # If the model doesn't have pipeline_stage, this line might also need fixing
    # to match the actual column name (e.g., cand.stage = stage)
    if hasattr(cand, "pipeline_stage"):
        cand.pipeline_stage = stage

    db.add(AuditEvent(
        org_id=cand.org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="candidate.stage_changed",
        entity_type="candidate",
        entity_id=cand.id,
        payload={"stage": stage}
    ))

    await db.commit()
    engine.trigger("candidate.stage_changed", {"org_id": actor.org_id, "candidate_id": str(cand.id), "stage": stage})

    return {"ok": True, "stage": stage}


@router.post("/candidates/{candidate_id}/decision")
async def decision(candidate_id: str, hire: bool, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    cand = await db.get(Candidate, UUID(candidate_id))
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    cand.status = "hired" if hire else "rejected"
    
    if hasattr(cand, "pipeline_stage"):
        cand.pipeline_stage = cand.status

    db.add(AuditEvent(
        org_id=cand.org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="candidate.decision",
        entity_type="candidate",
        entity_id=cand.id,
        payload={"decision": cand.status}
    ))

    await db.commit()
    engine.trigger("candidate.hired" if hire else "candidate.rejected", {"org_id": actor.org_id, "candidate_id": str(cand.id)})

    return {"status": cand.status}
