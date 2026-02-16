from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json
import uuid
from datetime import datetime

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.ai.screening import screen

router = APIRouter(prefix="/screening", tags=["screening"])


# ------------------------------------------------------------
# CRITERIA BUILDER (HR) — SAVE SCREENING CRITERIA PER JOB
# ------------------------------------------------------------
@router.post("/criteria")
async def create_criteria(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner", "admin", "hr", "recruiter"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        insert into public.screening_criteria(
            org_id, job_id, name, criteria, created_by
        )
        values (:org_id, :job_id, :name, :criteria, :uid)
        returning id
    """), {
        "org_id": actor.org_id,
        "job_id": payload.get("job_id"),
        "name": payload.get("name") or "default",
        "criteria": json.dumps(payload.get("criteria") or {}),
        "uid": actor.user_id
    })

    cid = res.first()[0]

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="screening.criteria.created",
        entity_type="screening_criteria",
        entity_id=cid,
        payload=payload
    ))

    await db.commit()
    return {"criteria_id": str(cid)}


@router.get("/criteria")
async def list_criteria(job_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        select id, name, criteria, created_at
        from public.screening_criteria
        where org_id=:org_id and job_id=:job_id
        order by created_at desc
    """), {"org_id": actor.org_id, "job_id": job_id})

    rows = res.mappings().all()
    return {"items": [dict(r) for r in rows]}


# ------------------------------------------------------------
# RUN SCREENING (AI) — EXPLAINABILITY + BIAS FLAGS + AUDIT
# ------------------------------------------------------------
@router.post("/run")
async def run_screening(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner", "admin", "hr", "recruiter", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    resume_text = payload.get("resume_text") or ""
    criteria_text = payload.get("criteria_text") or ""

    if not resume_text or not criteria_text:
        raise HTTPException(status_code=400, detail="resume_text and criteria_text required")

    result = screen(resume_text, criteria_text)

    # minimal bias flags (heuristic placeholder — replace with real bias model later)
    bias_flags = []
    banned_terms = ["age", "gender", "religion", "married", "pregnant"]
    lower = resume_text.lower()
    if any(t in lower for t in banned_terms):
        bias_flags.append("sensitive_attribute_detected")

    decision_id = uuid.uuid4()

    # persist decision for audit defensibility
    await db.execute(text("""
        insert into public.ai_decisions(
            id, org_id, decision_type, entity_type, entity_id,
            inputs, outputs, created_at
        )
        values (:id, :org_id, 'resume_screening', 'candidate', :candidate_id,
                :inputs::jsonb, :outputs::jsonb, now())
    """), {
        "id": decision_id,
        "org_id": actor.org_id,
        "candidate_id": payload.get("candidate_id"),
        "inputs": json.dumps({
            "resume_text": resume_text[:20000],  # avoid unlimited storage
            "criteria_text": criteria_text[:20000],
            "job_id": payload.get("job_id"),
        }),
        "outputs": json.dumps({
            "result": result,
            "bias_flags": bias_flags
        })
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="screening.run",
        entity_type="ai_decision",
        entity_id=decision_id,
        payload={"candidate_id": payload.get("candidate_id"), "job_id": payload.get("job_id")}
    ))

    await db.commit()

    # return explainability report
    return {
        "decision_id": str(decision_id),
        "score": result.get("score"),
        "explanation": result.get("reason"),
        "bias_flags": bias_flags,
        "recommendation": "advance" if (result.get("score") or 0) >= (payload.get("min_score") or 3) else "reject",
        "rejection_reason": None if (result.get("score") or 0) >= (payload.get("min_score") or 3) else "insufficient_match"
    }


# ------------------------------------------------------------
# DECISION EXPLANATION FETCH (AUDIT DEFENSE)
# ------------------------------------------------------------
@router.get("/decision/{decision_id}")
async def get_decision(decision_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        select id, decision_type, entity_type, entity_id, inputs, outputs, created_at
        from public.ai_decisions
        where org_id=:org_id and id=:id
    """), {"org_id": actor.org_id, "id": decision_id})

    row = res.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Decision not found")

    return dict(row)

