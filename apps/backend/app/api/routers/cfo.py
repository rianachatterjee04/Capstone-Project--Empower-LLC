from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.core.json_utils import json_safe
from app.db.models import AuditEvent

router = APIRouter(prefix="/cfo", tags=["cfo"])


def as_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("select to_regclass(:table_name)"),
        {"table_name": f"public.{table_name}"},
    )
    return result.scalar() is not None


async def column_exists(db: AsyncSession, table_name: str, column_name: str) -> bool:
    result = await db.execute(
        text("""
            select 1
            from information_schema.columns
            where table_schema = 'public'
              and table_name = :table_name
              and column_name = :column_name
            limit 1
        """),
        {"table_name": table_name, "column_name": column_name},
    )
    return result.first() is not None


@router.post("/scenario")
async def scenario(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "finance", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    current = int(payload.get("current_headcount", 0) or 0)
    hires = int(payload.get("planned_hires", 0) or 0)
    attr = float(payload.get("attrition_rate", 0.0) or 0.0)
    avg_salary = float(payload.get("avg_salary", 0.0) or 0.0)
    benefits_pct = float(payload.get("benefits_percent", 0.22) or 0.22)
    bonus_pct = float(payload.get("bonus_percent", 0.10) or 0.10)
    runway_cash = float(payload.get("cash_available", 0.0) or 0.0)

    future = current + hires - int(current * attr)

    salary_cost = future * avg_salary
    benefits_cost = salary_cost * benefits_pct
    bonus_cost = salary_cost * bonus_pct

    total_annual_cost = salary_cost + benefits_cost + bonus_cost
    monthly_burn = total_annual_cost / 12 if total_annual_cost else 0.0
    runway_months = runway_cash / monthly_burn if monthly_burn else None

    result = {
        "future_headcount": future,
        "salary_cost": salary_cost,
        "benefits_cost": benefits_cost,
        "bonus_cost": bonus_cost,
        "total_annual_cost": total_annual_cost,
        "monthly_burn": monthly_burn,
        "runway_months": runway_months,
    }

    if not await table_exists(db, "cfo_scenarios"):
        raise HTTPException(
            status_code=503,
            detail="cfo_scenarios table is not available yet. Run the CFO migration first.",
        )

    await db.execute(
        text("""
            insert into public.cfo_scenarios (org_id, payload, result)
            values (:org_id, cast(:payload as jsonb), cast(:result as jsonb))
        """),
        {
            "org_id": org_id,
            "payload": json.dumps(json_safe(payload)),
            "result": json.dumps(json_safe(result)),
        },
    )

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=user_id,
            actor_role=actor.role,
            event_type="cfo.scenario_created",
            entity_type="cfo_scenario",
            entity_id=None,
            payload=json_safe(result),
        )
    )

    await db.commit()
    return result


@router.get("/scenarios")
async def list_scenarios(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 20,
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "cfo_scenarios"):
        return []

    res = await db.execute(
        text("""
            select id, created_at, result
            from public.cfo_scenarios
            where org_id = :org_id
            order by created_at desc
            limit :limit
        """),
        {"org_id": org_id, "limit": max(1, min(limit, 100))},
    )

    rows = res.fetchall()

    return [
        {
            "id": str(r[0]),
            "created_at": str(r[1]),
            "result": r[2],
        }
        for r in rows
    ]


@router.get("/org-summary")
async def org_summary(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "employees"):
        return {
            "headcount": 0,
            "annual_salary_cost": 0.0,
        }

    hc = (
        await db.execute(
            text("""
                select count(*)
                from public.employees
                where org_id = :org_id and status = 'active'
            """),
            {"org_id": org_id},
        )
    ).scalar() or 0

    annual_salary_cost = 0.0

    if await column_exists(db, "employees", "base_salary"):
        annual_salary_cost = float(
            (
                await db.execute(
                    text("""
                        select coalesce(sum(base_salary), 0)
                        from public.employees
                        where org_id = :org_id and status = 'active'
                    """),
                    {"org_id": org_id},
                )
            ).scalar() or 0
        )

    return {
        "headcount": int(hc),
        "annual_salary_cost": annual_salary_cost,
    }


@router.get("/board-narrative")
async def narrative(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "cfo_scenarios"):
        return {"narrative": "No workforce scenario generated yet."}

    last = (
        await db.execute(
            text("""
                select result
                from public.cfo_scenarios
                where org_id = :org_id
                order by created_at desc
                limit 1
            """),
            {"org_id": org_id},
        )
    ).first()

    if not last:
        return {"narrative": "No workforce scenario generated yet."}

    r = last[0] or {}

    future_headcount = r.get("future_headcount", 0)
    total_annual_cost = float(r.get("total_annual_cost", 0) or 0)
    runway_months = r.get("runway_months")

    text_summary = (
        f"Projected headcount: {future_headcount}. "
        f"Annual cost: ${round(total_annual_cost / 1_000_000, 2)}M. "
        f"Estimated runway: "
        f"{round(runway_months, 1) if runway_months is not None else 'N/A'} months."
    )

    return {"narrative": text_summary}
