from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
import json

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent

router = APIRouter(prefix="/cfo", tags=["cfo"])


# =========================================================
# SCENARIO MODELING
# =========================================================
@router.post("/scenario")
async def scenario(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","finance","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    current = int(payload.get("current_headcount", 0))
    hires = int(payload.get("planned_hires", 0))
    attr = float(payload.get("attrition_rate", 0.0))
    avg_salary = float(payload.get("avg_salary", 0.0))
    benefits_pct = float(payload.get("benefits_percent", 0.22))
    bonus_pct = float(payload.get("bonus_percent", 0.10))
    runway_cash = float(payload.get("cash_available", 0))

    future = current + hires - int(current * attr)

    salary_cost = future * avg_salary
    benefits_cost = salary_cost * benefits_pct
    bonus_cost = salary_cost * bonus_pct

    total_annual_cost = salary_cost + benefits_cost + bonus_cost
    monthly_burn = total_annual_cost / 12 if total_annual_cost else 0
    runway_months = runway_cash / monthly_burn if monthly_burn else None

    result = {
        "future_headcount": future,
        "salary_cost": salary_cost,
        "benefits_cost": benefits_cost,
        "bonus_cost": bonus_cost,
        "total_annual_cost": total_annual_cost,
        "monthly_burn": monthly_burn,
        "runway_months": runway_months
    }

    # Save scenario snapshot
    await db.execute(text("""
        insert into public.cfo_scenarios(org_id, payload, result)
        values (:org_id, :payload::jsonb, :result::jsonb)
    """), {
        "org_id": actor.org_id,
        "payload": json.dumps(payload),
        "result": json.dumps(result)
    })

    db.add(AuditEvent(
        org_id=UUID(actor.org_id),
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="cfo.scenario_created",
        entity_type="cfo_scenario",
        entity_id=None,
        payload=result
    ))

    await db.commit()
    return result


# =========================================================
# SCENARIO HISTORY
# =========================================================
@router.get("/scenarios")
async def list_scenarios(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session), limit: int = 20):

    res = await db.execute(text("""
        select id, created_at, result
        from public.cfo_scenarios
        where org_id=:org_id
        order by created_at desc
        limit :limit
    """), {"org_id": actor.org_id, "limit": limit})

    rows = res.fetchall()

    return [
        {"id": str(r[0]), "created_at": str(r[1]), "result": r[2]}
        for r in rows
    ]


# =========================================================
# ORG SNAPSHOT
# =========================================================
@router.get("/org-summary")
async def org_summary(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    hc = (await db.execute(text("""
        select count(*) from public.employees
        where org_id=:org_id and status='active'
    """), {"org_id": actor.org_id})).first()[0]

    payroll = (await db.execute(text("""
        select coalesce(sum(base_salary),0)
        from public.employees
        where org_id=:org_id and status='active'
    """), {"org_id": actor.org_id})).first()[0]

    return {
        "headcount": int(hc),
        "annual_salary_cost": float(payroll)
    }


# =========================================================
# BOARD NARRATIVE (what CFO actually needs)
# =========================================================
@router.get("/board-narrative")
async def narrative(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    last = (await db.execute(text("""
        select result from public.cfo_scenarios
        where org_id=:org_id
        order by created_at desc
        limit 1
    """), {"org_id": actor.org_id})).first()

    if not last:
        return {"narrative": "No workforce scenario generated yet."}

    r = last[0]

    text_summary = (
        f"Projected headcount: {r['future_headcount']}. "
        f"Annual cost: ${round(r['total_annual_cost']/1_000_000,2)}M. "
        f"Estimated runway: {round(r['runway_months'],1) if r['runway_months'] else 'N/A'} months."
    )

    return {"narrative": text_summary}

