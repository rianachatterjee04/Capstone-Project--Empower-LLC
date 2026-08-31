from __future__ import annotations

import json

from app.core.json_utils import json_safe

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from decimal import Decimal
from datetime import date, datetime

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.services.bonus_calc import calculate_bonus_pool

router = APIRouter(prefix="/bonuses", tags=["bonuses"])


def as_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def normalize_value(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def row_to_dict(cols, row):
    return {col: normalize_value(val) for col, val in zip(cols, row)}


# =========================================================
# CREATE BONUS POOL
# =========================================================
@router.post("/pools")
async def create_pool(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    if payload.get("total_amount") is None:
        raise HTTPException(status_code=400, detail="total_amount required")

    org_id = as_uuid(actor.org_id)

    res = await db.execute(
        text("""
            insert into public.bonus_pools
                (org_id, name, cycle_id, currency, total_amount, status)
            values
                (:org_id, :name, :cycle_id, :currency, :total, 'draft')
            returning id
        """),
        {
            "org_id": org_id,
            "name": payload.get("name", "Bonus Pool"),
            "cycle_id": payload.get("cycle_id"),
            "currency": payload.get("currency", "USD"),
            "total": payload.get("total_amount"),
        },
    )

    pool_id = res.first()[0]

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=as_uuid(actor.user_id),
            actor_role=actor.role,
            event_type="bonus_pool.created",
            entity_type="bonus_pool",
            entity_id=pool_id,
            payload=json_safe(payload),
        )
    )

    await db.commit()
    return {"id": str(pool_id)}


# =========================================================
# CALCULATE BONUS ALLOCATIONS
# =========================================================
@router.post("/pools/{pool_id}/calculate")
async def calc(
    pool_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    target_pool_id = as_uuid(pool_id)
    cycle_id = payload.get("cycle_id")

    try:
        result = await calculate_bonus_pool(
            db,
            org_id,
            target_pool_id,
            as_uuid(cycle_id) if cycle_id else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=as_uuid(actor.user_id),
            actor_role=actor.role,
            event_type="bonus_pool.calculated",
            entity_type="bonus_pool",
            entity_id=target_pool_id,
            payload=json_safe(result),
        )
    )

    await db.commit()
    return result


# =========================================================
# MANUAL ADJUSTMENT
# =========================================================
@router.post("/pools/{pool_id}/adjust/{employee_id}")
async def adjust(
    pool_id: str,
    employee_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    new_amount = payload.get("amount")
    reason = payload.get("reason", "manual adjustment")

    if new_amount is None:
        raise HTTPException(status_code=400, detail="amount required")

    await db.execute(
        text("""
            update public.bonus_allocations
            -- `amount`, not `allocation_amount`. The read below joins
            -- ba.amount, under a comment stating the schema column is amount;
            -- this update disagreed with both. With no table to arbitrate,
            -- nothing had ever failed.
            set amount = :amt,
                basis = basis || cast(:patch_json as jsonb)
            where org_id = :org_id
              and pool_id = :pool
              and employee_id = :emp
        """).bindparams(bindparam("patch_json", type_=String)),
        {
            "org_id": org_id,
            "pool": as_uuid(pool_id),
            "emp": as_uuid(employee_id),
            "amt": new_amount,
            "patch_json": json.dumps({"manual_adjustment": True, "reason": reason}),
        },
    )

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=as_uuid(actor.user_id),
            actor_role=actor.role,
            event_type="bonus.adjusted",
            entity_type="bonus_allocation",
            entity_id=as_uuid(employee_id),
            payload={"pool": pool_id, "amount": new_amount, "reason": reason},
        )
    )

    await db.commit()
    return {"adjusted": True}


# =========================================================
# FINALIZE POOL (LOCK)
# =========================================================
@router.post("/pools/{pool_id}/finalize")
async def finalize(
    pool_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "finance"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)

    # Finalising committed the pool's money and said nothing about where it
    # went. A pool with a total_amount and no allocations locked cleanly and
    # answered {"status": "locked"} -- $50,000 set aside for nobody, with an
    # audit event recording that it had been finalised.
    #
    # A pool deliberately finalised at zero is fine. A pool holding money and
    # allocating none of it is a mistake nobody would make on purpose, and the
    # only moment it is cheap to catch is before the lock.
    state = (await db.execute(
        text("""
            select p.total_amount,
                   (select count(*) from public.bonus_allocations a
                     where a.pool_id = p.id and a.org_id = p.org_id) as n_alloc
            from public.bonus_pools p
            where p.org_id = :org_id and p.id = :id
        """),
        {"org_id": org_id, "id": as_uuid(pool_id)},
    )).mappings().first()

    if not state:
        raise HTTPException(status_code=404, detail="Bonus pool not found")

    if state["n_alloc"] == 0 and (state["total_amount"] or 0) > 0:
        raise HTTPException(
            status_code=409,
            detail=(f"this pool holds {state['total_amount']} and has no allocations, "
                    f"so finalising it would commit the money to nobody. "
                    f"Run calculate first, or set the pool total to 0."),
        )

    await db.execute(
        text("""
            update public.bonus_pools
            set status = 'approved'
            where org_id = :org_id
              and id = :id
        """),
        {"org_id": org_id, "id": as_uuid(pool_id)},
    )

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=as_uuid(actor.user_id),
            actor_role=actor.role,
            event_type="bonus_pool.finalized",
            entity_type="bonus_pool",
            entity_id=as_uuid(pool_id),
            payload={},
        )
    )

    await db.commit()
    return {"status": "locked"}


# =========================================================
# EMPLOYEE BONUS VIEW
# =========================================================
@router.get("/my")
async def my_bonus(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)

    # Schema column is bonus_allocations.amount (not allocation_amount); be
    # defensive in case the schema isn't provisioned at all.
    try:
        row = (
            await db.execute(
                text("""
                    select bp.name, ba.amount, bp.currency, bp.status
                    from public.bonus_allocations ba
                    join public.bonus_pools bp on bp.id = ba.pool_id
                    join public.employees e on e.id = ba.employee_id
                    where e.user_id = :uid
                      and bp.org_id = :org_id
                    order by bp.created_at desc
                    limit 1
                """),
                {"uid": actor.user_id, "org_id": org_id},
            )
        ).first()
    except Exception:
        await db.rollback()
        return {"bonus": None, "note": "bonus tables not provisioned"}

    if not row:
        return {"bonus": None}

    return {
        "pool": row[0],
        "amount": float(row[1]),
        "currency": row[2],
        "status": row[3],
    }


# =========================================================
# LIST POOLS
# =========================================================
@router.get("/pools")
async def list_pools(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)

    res = await db.execute(
        text("""
            select *
            from public.bonus_pools
            where org_id = :org_id
            order by created_at desc
        """),
        {"org_id": org_id},
    )

    cols = res.keys()
    return [row_to_dict(cols, row) for row in res.fetchall()]


# =========================================================
# ALLOCATIONS
# =========================================================
@router.get("/pools/{pool_id}/allocations")
async def allocations(
    pool_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)

    res = await db.execute(
        text("""
            select *
            from public.bonus_allocations
            where org_id = :org_id
              and pool_id = :pool_id
        """),
        {"org_id": org_id, "pool_id": as_uuid(pool_id)},
    )

    cols = res.keys()
    return [row_to_dict(cols, row) for row in res.fetchall()]
