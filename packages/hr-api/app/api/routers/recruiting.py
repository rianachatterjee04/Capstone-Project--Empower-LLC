from __future__ import annotations

import re

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
# Words that carry no signal about what a job needs. Kept small on purpose:
# the point is to drop connectives, not to curate a skills ontology.
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "our", "own", "that", "the", "to",
    "we", "will", "with", "you", "your", "this", "they", "their", "must", "should",
    "can", "able", "work", "working", "role", "team", "years", "year", "experience",
    "strong", "good", "excellent", "ability", "including", "etc", "who", "what",
}

_WORD = re.compile(r"[a-z0-9][a-z0-9+#./&-]*")


def _terms(text: str | None) -> set[str]:
    """Significant lowercase terms in a block of text, whole words only."""
    if not text:
        return set()
    return {
        w for w in _WORD.findall(text.lower())
        if len(w) > 2 and w not in _STOPWORDS and not w.isdigit()
    }


def explainable_ai_score(
    resume_text: str | None,
    job_text: str | None = None,
) -> tuple[int | None, str, list[str]]:
    """How much of what THIS job asks for appears in THIS resume.

    THREE DEFECTS THIS REPLACES
    The previous version matched a resume against a fixed sixteen-word list --
    python, fastapi, react, aws, hr, payroll and so on -- and never looked at
    the job at all. It was not a fit score; it was a software-vocabulary score,
    and its number drove both the candidate's pipeline status and the summary
    shown on their card.

      * A CDL driver applying to a driving job scored 0, "Matched skills: none",
        and was never marked screened.
      * A Senior Accountant scored 10 with the rationale "Matched skills: ui" --
        because "ui" is a substring of "NetSuite".
      * "Worked through rapid growth; therapy dogs in the office" scored 20 and
        was credited with "api" (inside "rapid") and "hr" (inside "through").

    Substring matching against a fixed list produces confident claims about a
    person from words they never wrote. So: whole words only, and measured
    against what the job actually asks for.

    Returns (score, rationale, matched terms). The score is None when there is
    nothing to score against -- an unscreened candidate is a state, not a zero.
    """
    resume_terms = _terms(resume_text)
    job_terms = _terms(job_text)

    if not job_terms:
        return None, (
            "Not scored: this job has no description to match against. "
            "Add requirements to the posting, or screen this candidate by hand."
        ), []

    if not resume_terms:
        return None, (
            "Not scored: no resume text was supplied for this candidate."
        ), []

    matched = sorted(job_terms & resume_terms)
    score = round(100 * len(matched) / len(job_terms))
    rationale = (
        f"Matched {len(matched)} of {len(job_terms)} terms from the job posting"
        + (f": {', '.join(matched[:12])}" if matched else "")
    )
    return score, rationale, matched


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

    # Score against the job this candidate actually applied to. Without the
    # posting the previous version scored everyone against a fixed software
    # vocabulary, so a CDL driver applying to a driving job scored 0 and stayed
    # in "new" while any backend resume scored 100 and jumped to "screened" --
    # for any job whatsoever.
    job_text = None
    if payload.job_posting_id:
        job = (await db.execute(
            select(JobPosting).where(
                JobPosting.id == payload.job_posting_id,
                JobPosting.org_id == org_id,
            )
        )).scalar_one_or_none()
        if job is None:
            raise HTTPException(
                status_code=422,
                detail="that job posting does not exist in this organisation",
            )
        job_text = " ".join(filter(None, [job.title, job.description]))

    score, rationale, _hits = explainable_ai_score(payload.resume_text, job_text)

    # Pipeline columns on the employer recruiting page: new, screened,
    # interview, rejected, hired. A candidate we could not score has NOT been
    # screened -- advancing them on a score that was never computed is how an
    # unread resume ends up looking reviewed.
    status = "screened" if (score is not None and score >= 40) else "new"

    cand = Candidate(
        org_id=org_id,
        job_posting_id=payload.job_posting_id,
        full_name=payload.full_name,
        email=payload.email,
        resume_text=payload.resume_text,
        ai_score=score,
        ai_summary=rationale,
        status=status,
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
# The candidate pipeline vocabulary, in one place.
#
# There were three of them and none agreed. This endpoint accepted
# applied/interview/committee/offer/hired/rejected; the screener writes
# "screened" and "new"; the pipeline screens offer new/screened/interview/
# offer/hired/rejected. So the UI's "-> screened" button returned 400 Invalid
# stage on a value the API itself writes when it scores a resume.
CANDIDATE_STAGES = ("new", "screened", "interview", "offer", "hired", "rejected")

# Older callers and older rows use these names for the same stages.
STAGE_SYNONYMS = {"applied": "new", "interviewing": "interview",
                  "committee": "interview", "offered": "offer",
                  "declined": "rejected"}


@router.post("/candidates/{candidate_id}/stage")
async def move_stage(candidate_id: str, stage: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Move a candidate to a pipeline stage.

    THIS USED TO CHANGE NOTHING AND SAY IT HAD. The write was

        if hasattr(cand, "pipeline_stage"):
            cand.pipeline_stage = stage

    and Candidate has no pipeline_stage column — the field is `status`. The
    guard was always false, so the stage was never written, and the endpoint
    returned {"ok": true} and committed an audit event saying the stage had
    changed. Driving one candidate through interview, offer and hired left them
    on "new" with three candidate.stage_changed rows in audit_events recording
    moves that never happened.

    An audit log that records state transitions the system did not make is
    worse than no audit log, because it is trusted. The comment above the guard
    even said the column name might be wrong.
    """
    key = (stage or "").strip().lower()
    key = STAGE_SYNONYMS.get(key, key)
    if key not in CANDIDATE_STAGES:
        raise HTTPException(status_code=400, detail={
            "reason": "INVALID_STAGE",
            "message": f"{stage!r} is not a pipeline stage.",
            "allowed": list(CANDIDATE_STAGES),
        })

    cand = await db.get(Candidate, UUID(candidate_id))
    if not cand or str(cand.org_id) != actor.org_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    previous = cand.status
    cand.status = key

    # Logged only alongside the write, in the same transaction, and carrying
    # what it moved FROM so the trail can be read back as a sequence.
    db.add(AuditEvent(
        org_id=cand.org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="candidate.stage_changed",
        entity_type="candidate",
        entity_id=cand.id,
        payload={"stage": key, "from": previous, "requested": stage},
    ))

    await db.commit()
    engine.trigger("candidate.stage_changed", {"org_id": actor.org_id, "candidate_id": str(cand.id), "stage": key})

    return {"ok": True, "stage": key, "previous": previous}


@router.post("/candidates/{candidate_id}/decision")
async def decision(candidate_id: str, hire: bool, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Hire or reject a candidate.

    CROSS-TENANT WRITE. This checked the caller's ROLE and then loaded the
    candidate by primary key with no organisation check at all, while
    move_stage twenty lines above does check it. Proved against the running
    API: an owner of org 1111… posted decision?hire=true against a candidate
    belonging to org 2222…, got 200, and the victim organisation's row was
    changed to "hired". The same call to /stage returned 404, because that
    endpoint compares org_id.

    A role check answers "may this person hire someone". It does not answer
    "is this their candidate".
    """
    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    cand = await db.get(Candidate, UUID(candidate_id))
    if not cand or str(cand.org_id) != actor.org_id:
        # Not "forbidden": a tenant must not be able to learn that a row exists
        # in another tenant by the difference between 403 and 404.
        raise HTTPException(status_code=404, detail="Candidate not found")

    cand.status = "hired" if hire else "rejected"

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
