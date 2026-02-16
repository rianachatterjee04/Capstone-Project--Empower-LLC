from __future__ import annotations
from typing import Any, Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

def _rating_weight(rating: float | None) -> float:
    if rating is None:
        return 1.0
    return max(0.5, min(2.0, float(rating) / 3.0))

async def calculate_bonus_pool(db: AsyncSession, org_id: UUID, pool_id: UUID, cycle_id: UUID | None = None) -> Dict[str, Any]:
    pool = (await db.execute(
        text("select total_amount from public.bonus_pools where id=:id and org_id=:org_id"),
        {"id": str(pool_id), "org_id": str(org_id)},
    )).first()
    if not pool:
        raise ValueError("Pool not found")
    total = float(pool[0])

    if cycle_id:
        rows = (await db.execute(text("""
            select pr.employee_id, pr.rating
            from public.performance_reviews pr
            where pr.org_id=:org_id and pr.cycle_id=:cycle_id
        """), {"org_id": str(org_id), "cycle_id": str(cycle_id)})).fetchall()
    else:
        rows = (await db.execute(
            text("select id, null::numeric as rating from public.employees where org_id=:org_id and status='active'"),
            {"org_id": str(org_id)},
        )).fetchall()

    weights = [(emp_id, _rating_weight(rating)) for emp_id, rating in rows]
    if not weights:
        return {"total": total, "allocations": []}

    denom = sum(w for _, w in weights)
    allocs = []
    for emp_id, w in weights:
        amt = round(total * (w / denom), 2)
        allocs.append({"employee_id": str(emp_id), "allocation_amount": amt, "basis": {"rating_weight": w}})

    for a in allocs:
        await db.execute(text("""
            insert into public.bonus_allocations(org_id, pool_id, employee_id, allocation_amount, basis)
            values (:org_id, :pool_id, :employee_id, :amt, :basis::jsonb)
            on conflict (org_id, pool_id, employee_id)
            do update set allocation_amount=excluded.allocation_amount, basis=excluded.basis
        """), {
            "org_id": str(org_id),
            "pool_id": str(pool_id),
            "employee_id": a["employee_id"],
            "amt": a["allocation_amount"],
            "basis": json.dumps(a["basis"]),
        })

    await db.execute(text("update public.bonus_pools set status='calculated' where id=:id and org_id=:org_id"),
                     {"id": str(pool_id), "org_id": str(org_id)})
    await db.commit()
    return {"total": total, "allocations": allocs}
