from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent

router = APIRouter(prefix="/ats", tags=["ats"])


# =========================================================
# STAGE MAPPINGS (External ATS → Foundry stages)
# =========================================================
@router.get("/mappings/{provider}")
async def list_mappings(provider: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    rows = (await db.execute(text("""
        select external_stage, internal_stage
        from public.ats_stage_mappings
        where org_id=:org_id and provider=:provider
        order by external_stage asc
    """), {"org_id": actor.org_id, "provider": provider})).fetchall()

    return {"items": [{"external_stage": r[0], "internal_stage": r[1]} for r in rows]}


@router.post("/mappings/{provider}")
async def upsert_mapping(provider: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    ext = payload.get("external_stage")
    inte = payload.get("internal_stage")

    if not ext or not inte:
        raise HTTPException(status_code=400, detail="external_stage and internal_stage required")

    await db.execute(text("""
        insert into public.ats_stage_mappings(org_id, provider, external_stage, internal_stage, updated_at)
        values (:org_id, :provider, :ext, :int, now())
        on conflict (org_id, provider, external_stage)
        do update set internal_stage=excluded.internal_stage, updated_at=now()
    """), {"org_id": actor.org_id, "provider": provider, "ext": ext, "int": inte})

    await db.commit()
    return {"ok": True}


# =========================================================
# AI SCREENING CRITERIA
# =========================================================
@router.get("/criteria/{provider}/{job_external_id}")
async def get_criteria(provider: str, job_external_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    row = (await db.execute(text("""
        select criteria
        from public.ats_job_screening_criteria
        where org_id=:org_id and provider=:provider and job_external_id=:jid
    """), {"org_id": actor.org_id, "provider": provider, "jid": job_external_id})).first()

    return {"criteria": row[0] if row else {}}


@router.post("/criteria/{provider}/{job_external_id}")
async def set_criteria(provider: str, job_external_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    criteria = payload.get("criteria") or {}

    await db.execute(text("""
        insert into public.ats_job_screening_criteria(org_id, provider, job_external_id, criteria, updated_at)
        values (:org_id, :provider, :jid, :criteria::jsonb, now())
        on conflict (org_id, provider, job_external_id)
        do update set criteria=excluded.criteria, updated_at=now()
    """), {"org_id": actor.org_id, "provider": provider, "jid": job_external_id, "criteria": json.dumps(criteria)})

    await db.commit()
    return {"ok": True}


# =========================================================
# SCREENING SCORES
# =========================================================
@router.get("/scores/{provider}/{candidate_external_id}")
async def scores(provider: str, candidate_external_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    rows = (await db.execute(text("""
        select job_external_id, score, rationale, created_at
        from public.ats_screening_scores
        where org_id=:org_id and provider=:provider and candidate_external_id=:cid
        order by created_at desc
        limit 10
    """), {"org_id": actor.org_id, "provider": provider, "cid": candidate_external_id})).fetchall()

    return {
        "items": [
            {
                "job_external_id": r[0],
                "score": float(r[1]),
                "rationale": r[2],
                "created_at": str(r[3])
            }
            for r in rows
        ]
    }


# =========================================================
# HIRING DECISION (SYSTEM OF RECORD)
# =========================================================
@router.post("/decision/{candidate_id}")
async def record_decision(candidate_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    decision = payload.get("decision")  # hire / reject / hold
    rationale = payload.get("rationale")
    job_id = payload.get("job_id")

    if decision not in ("hire","reject","hold"):
        raise HTTPException(status_code=400, detail="invalid decision")

    await db.execute(text("""
        insert into public.hiring_decisions(org_id, candidate_id, job_id, decision, rationale, decided_by)
        values (:org_id, :cid, :job_id, :decision, :rationale, :actor)
    """), {
        "org_id": actor.org_id,
        "cid": candidate_id,
        "job_id": job_id,
        "decision": decision,
        "rationale": rationale,
        "actor": actor.user_id
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="hiring.decision",
        entity_type="candidate",
        entity_id=UUID(candidate_id),
        payload=payload
    ))

    await db.commit()
    return {"recorded": True}


# =========================================================
# HIRING FREEZE ENFORCEMENT
# =========================================================
@router.get("/freeze-status")
async def freeze_status(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    row = (await db.execute(text("""
        select is_frozen, reason
        from public.hiring_freeze
        where org_id=:org_id
        limit 1
    """), {"org_id": actor.org_id})).first()

    return {"frozen": row[0], "reason": row[1]} if row else {"frozen": False}

