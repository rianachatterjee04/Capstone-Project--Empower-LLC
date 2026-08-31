from __future__ import annotations

import json
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

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

    # Do not bind `basis` as postgresql.JSONB: the dialect renders `:basis::jsonb`, and asyncpg
    # then mixes `$1..$4` with an untouched `:basis::jsonb` token → PostgresSyntaxError.
    # The column is `amount`. This wrote `allocation_amount`, the same
    # disagreement the router had with itself and which the table's migration
    # calls out by name -- fixed there, missed here.
    #
    # The ON CONFLICT target was wrong too: the unique constraint is
    # (pool_id, employee_id), not (org_id, pool_id, employee_id), so a second
    # calculation for the same pool raised "no unique or exclusion constraint
    # matching the ON CONFLICT specification" rather than updating the
    # allocation. Recalculating a bonus pool is the normal case, not the edge.
    insert_alloc = text("""
        insert into public.bonus_allocations(org_id, pool_id, employee_id, amount, basis)
        values (:org_id, :pool_id, :employee_id, :amt, cast(:basis_json as jsonb))
        on conflict (pool_id, employee_id)
        do update set amount = excluded.amount, basis = excluded.basis
    """).bindparams(bindparam("basis_json", type_=String))

    for a in allocs:
        await db.execute(
            insert_alloc,
            {
                "org_id": str(org_id),
                "pool_id": str(pool_id),
                "employee_id": a["employee_id"],
                "amt": a["allocation_amount"],
                "basis_json": json.dumps(a["basis"]),
            },
        )

    await db.execute(
        text("update public.bonus_pools set status = 'calculated' where id = :id and org_id = :org_id"),
        {"id": str(pool_id), "org_id": str(org_id)},
    )
    # Caller commits with audit row in the same transaction.
    return {"total": total, "allocations": allocs}
