from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.workflow.engine import engine

router = APIRouter(prefix="/recruiting", tags=["recruiting"])


# ---------------------------------------------------------
# CREATE JOB REQUISITION
# ---------------------------------------------------------
@router.post("/jobs")
async def create_job(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","recruiter"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        insert into public.job_requisitions(
            org_id, title, department, hiring_manager_id, status
        )
        values (:org_id, :title, :dept, :manager, 'open')
        returning id
    """), {
        "org_id": actor.org_id,
        "title": payload.get("title"),
        "dept": payload.get("department"),
        "manager": payload.get("hiring_manager_id")
    })

    job_id = res.first()[0]
    await db.commit()
    return {"job_id": str(job_id)}


# ---------------------------------------------------------
# APPLY CANDIDATE
# ---------------------------------------------------------
@router.post("/jobs/{job_id}/apply")
async def apply(job_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        insert into public.candidates(
            org_id, job_id, name, email, resume_text, stage
        )
        values (:org_id, :job, :name, :email, :resume, 'applied')
        returning id
    """), {
        "org_id": actor.org_id,
        "job": job_id,
        "name": payload.get("name"),
        "email": payload.get("email"),
        "resume": payload.get("resume_text")
    })

    cid = res.first()[0]

    engine.trigger(f"candidate_applied:{cid}")

    await db.commit()
    return {"candidate_id": str(cid)}


# ---------------------------------------------------------
# MOVE STAGE (PIPELINE)
# ---------------------------------------------------------
@router.post("/candidates/{candidate_id}/stage")
async def move_stage(candidate_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    stage = payload.get("stage")

    await db.execute(text("""
        update public.candidates
        set stage=:stage
        where id=:cid and org_id=:org_id
    """), {"stage": stage, "cid": candidate_id, "org_id": actor.org_id})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="candidate.stage_changed",
        entity_type="candidate",
        entity_id=UUID(candidate_id),
        payload={"stage": stage}
    ))

    engine.trigger(f"candidate_stage_changed:{candidate_id}:{stage}")

    await db.commit()
    return {"stage": stage}


# ---------------------------------------------------------
# INTERVIEW SCORECARD
# ---------------------------------------------------------
@router.post("/candidates/{candidate_id}/scorecard")
async def scorecard(candidate_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    await db.execute(text("""
        insert into public.interview_scorecards(
            org_id, candidate_id, interviewer_id, score, notes
        )
        values (:org_id, :cid, :uid, :score, :notes)
    """), {
        "org_id": actor.org_id,
        "cid": candidate_id,
        "uid": actor.user_id,
        "score": payload.get("score"),
        "notes": payload.get("notes")
    })

    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# HIRING COMMITTEE DECISION
# ---------------------------------------------------------
@router.post("/candidates/{candidate_id}/decision")
async def hiring_decision(candidate_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    decision = payload.get("decision")

    await db.execute(text("""
        update public.candidates
        set decision=:decision
        where id=:cid and org_id=:org_id
    """), {"decision": decision, "cid": candidate_id, "org_id": actor.org_id})

    engine.trigger(f"hiring_decision:{candidate_id}:{decision}")

    await db.commit()
    return {"decision": decision}


# ---------------------------------------------------------
# CREATE OFFER (APPROVAL REQUIRED)
# ---------------------------------------------------------
@router.post("/candidates/{candidate_id}/offer")
async def create_offer(candidate_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("hr","admin","owner"):
        raise HTTPException(status_code=403, detail="Restricted")

    res = await db.execute(text("""
        insert into public.approval_requests(
            org_id, type, title, status, metadata
        )
        values (:org_id, 'offer', :title, 'pending', :meta::jsonb)
        returning id
    """), {
        "org_id": actor.org_id,
        "title": f"Offer approval for candidate {candidate_id}",
        "meta": json.dumps(payload)
    })

    approval_id = res.first()[0]
    await db.commit()

    return {"approval_id": str(approval_id)}


# ---------------------------------------------------------
# LIST PIPELINE
# ---------------------------------------------------------
@router.get("/jobs/{job_id}/pipeline")
async def view_pipeline(job_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        select id, name, email, stage, decision
        from public.candidates
        where org_id=:org_id and job_id=:job
        order by created_at desc
    """), {"org_id": actor.org_id, "job": job_id})

    rows = res.mappings().all()
    return {"candidates": [dict(r) for r in rows]}

