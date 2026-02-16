from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.services.bonus_calc import calculate_bonus_pool

router = APIRouter(prefix="/bonuses", tags=["bonuses"])


# =========================================================
# CREATE BONUS POOL
# =========================================================
@router.post("/pools")
async def create_pool(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    if payload.get("total_amount") is None:
        raise HTTPException(status_code=400, detail="total_amount required")

    res = await db.execute(text("""
        insert into public.bonus_pools(org_id, name, cycle_id, currency, total_amount, status)
        values (:org_id, :name, :cycle_id, :currency, :total, 'draft')
        returning id
    """), {
        "org_id": actor.org_id,
        "name": payload.get("name", "Bonus Pool"),
        "cycle_id": payload.get("cycle_id"),
        "currency": payload.get("currency", "USD"),
        "total": payload.get("total_amount"),
    })

    pool_id = res.first()[0]

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="bonus_pool.created",
        entity_type="bonus_pool",
        entity_id=pool_id,
        payload=payload
    ))

    await db.commit()
    return {"id": str(pool_id)}


# =========================================================
# CALCULATE BONUS ALLOCATIONS
# =========================================================
@router.post("/pools/{pool_id}/calculate")
async def calc(pool_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    cycle_id = payload.get("cycle_id")

    result = await calculate_bonus_pool(
        db,
        UUID(actor.org_id),
        UUID(pool_id),
        UUID(cycle_id) if cycle_id else None
    )

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="bonus_pool.calculated",
        entity_type="bonus_pool",
        entity_id=UUID(pool_id),
        payload=result
    ))

    await db.commit()
    return result


# =========================================================
# MANUAL ADJUSTMENT (critical for HR reality)
# =========================================================
@router.post("/pools/{pool_id}/adjust/{employee_id}")
async def adjust(pool_id: str, employee_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    new_amount = payload.get("amount")
    reason = payload.get("reason", "manual adjustment")

    await db.execute(text("""
        update public.bonus_allocations
        set amount=:amt, adjusted=true, adjusted_reason=:reason
        where org_id=:org_id and pool_id=:pool and employee_id=:emp
    """), {
        "org_id": actor.org_id,
        "pool": pool_id,
        "emp": employee_id,
        "amt": new_amount,
        "reason": reason
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="bonus.adjusted",
        entity_type="bonus_allocation",
        entity_id=UUID(employee_id),
        payload={"pool": pool_id, "amount": new_amount, "reason": reason}
    ))

    await db.commit()
    return {"adjusted": True}


# =========================================================
# FINALIZE POOL (LOCK)
# =========================================================
@router.post("/pools/{pool_id}/finalize")
async def finalize(pool_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    await db.execute(text("""
        update public.bonus_pools
        set status='finalized', finalized_at=now()
        where org_id=:org_id and id=:id
    """), {"org_id": actor.org_id, "id": pool_id})

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="bonus_pool.finalized",
        entity_type="bonus_pool",
        entity_id=UUID(pool_id),
        payload={}
    ))

    await db.commit()
    return {"status": "locked"}


# =========================================================
# EMPLOYEE BONUS VIEW
# =========================================================
@router.get("/my")
async def my_bonus(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    row = (await db.execute(text("""
        select bp.name, ba.amount, bp.currency, bp.status
        from public.bonus_allocations ba
        join public.bonus_pools bp on bp.id = ba.pool_id
        join public.employees e on e.id = ba.employee_id
        where e.user_id=:uid and bp.org_id=:org_id
        order by bp.created_at desc
        limit 1
    """), {"uid": actor.user_id, "org_id": actor.org_id})).first()

    if not row:
        return {"bonus": None}

    return {
        "pool": row[0],
        "amount": float(row[1]),
        "currency": row[2],
        "status": row[3]
    }


# =========================================================
# LIST POOLS
# =========================================================
@router.get("/pools")
async def list_pools(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        select * from public.bonus_pools
        where org_id=:org_id
        order by created_at desc
    """), {"org_id": actor.org_id})

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]


# =========================================================
# ALLOCATIONS
# =========================================================
@router.get("/pools/{pool_id}/allocations")
async def allocations(pool_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        select * from public.bonus_allocations
        where org_id=:org_id and pool_id=:pool_id
    """), {"org_id": actor.org_id, "pool_id": pool_id})

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]

