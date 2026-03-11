from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.json_utils import json_safe
from sqlalchemy import text
from uuid import UUID

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.services.market_benchmarking import capture_benchmark, PROVIDERS

router = APIRouter(prefix="/market", tags=["market"])


def as_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except ValueError:
        return None


@router.get("/providers")
async def providers(actor: Actor = Depends(require_org)):
    return {"providers": list(PROVIDERS.keys())}


@router.post("/capture")
async def capture(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    job_title = payload.get("job_title")
    if not job_title:
        raise HTTPException(status_code=400, detail="job_title required")

    provider = payload.get("provider", "mock")
    if provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider {provider}")

    location = payload.get("location")
    currency = payload.get("currency", "USD")
    org_id = as_uuid(actor.org_id)

    recent = (
        await db.execute(
            text("""
                select id
                from public.market_benchmarks
                where org_id = :org_id
                  and job_title = :title
                  and provider = :provider
                  and captured_at > now() - interval '24 hours'
                limit 1
            """),
            {
                "org_id": org_id,
                "title": job_title,
                "provider": provider,
            },
        )
    ).first()

    if recent:
        raise HTTPException(status_code=409, detail="Benchmark captured recently (within 24h)")

    row = await capture_benchmark(
        db=db,
        org_id=org_id,
        provider=provider,
        job_title=job_title,
        location=location,
        currency=currency,
    )

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=as_uuid(actor.user_id),
            actor_role=actor.role,
            event_type="market_benchmark.captured",
            entity_type="market_benchmark",
            entity_id=as_uuid(row["id"]),
            payload=row,
        )
    )

    await db.commit()
    return row


@router.get("/benchmarks")
async def list_benchmarks(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    res = await db.execute(
        text("""
            select *
            from public.market_benchmarks
            where org_id = :org_id
            order by captured_at desc
            limit :limit
        """),
        {"org_id": as_uuid(actor.org_id), "limit": limit},
    )

    rows = res.mappings().all()
    return [dict(r) for r in rows]


@router.get("/latest")
async def latest(
    job_title: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    row = (
        await db.execute(
            text("""
                select *
                from public.market_benchmarks
                where org_id = :org_id
                  and job_title = :title
                order by captured_at desc
                limit 1
            """),
            {"org_id": as_uuid(actor.org_id), "title": job_title},
        )
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="No benchmark found")

    return dict(row)


@router.get("/compare/{employee_id}")
async def compare(
    employee_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    emp_id = as_uuid(employee_id)

    emp = (
        await db.execute(
            text("""
                select title, salary
                from public.employees
                where id = :id
                  and org_id = :org_id
            """),
            {"id": emp_id, "org_id": org_id},
        )
    ).first()

    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    title, salary = emp

    bench = (
        await db.execute(
            text("""
                select p50, p75, p90
                from public.market_benchmarks
                where org_id = :org_id
                  and job_title = :title
                order by captured_at desc
                limit 1
            """),
            {"org_id": org_id, "title": title},
        )
    ).first()

    if not bench:
        raise HTTPException(status_code=404, detail="No market benchmark")

    p50, p75, p90 = bench

    if salary < p50:
        position = "below_market"
    elif salary < p75:
        position = "mid_band"
    elif salary < p90:
        position = "competitive"
    else:
        position = "above_market"

    return {
        "employee_salary": float(salary),
        "market_p50": float(p50),
        "market_p75": float(p75),
        "market_p90": float(p90),
        "position": position,
    }
