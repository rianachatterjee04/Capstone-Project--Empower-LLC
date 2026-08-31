"""AI compensation review router."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent
from app.services.comp_ai_service import CompInput, recommend, recommend_batch


router = APIRouter(prefix="/comp-ai", tags=["comp-ai"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "manager")


def _to_input(row: dict) -> CompInput:
    if not row.get("employee_id") or not row.get("current_salary"):
        raise HTTPException(status_code=400, detail="employee_id and current_salary required")
    return CompInput(
        employee_id=str(row["employee_id"]),
        name=row.get("name") or "",
        job_title=row.get("job_title") or "",
        department=row.get("department"),
        current_salary=float(row["current_salary"]),
        currency=row.get("currency") or "USD",
        tenure_years=float(row.get("tenure_years") or 1),
        performance_rating=float(row.get("performance_rating") or 3),
        last_review_summary=row.get("last_review_summary") or "",
        market_p25=row.get("market_p25"),
        market_p50=row.get("market_p50"),
        market_p75=row.get("market_p75"),
        market_p90=row.get("market_p90"),
        band_min=row.get("band_min"),
        band_max=row.get("band_max"),
        cohort_median=row.get("cohort_median"),
        promotion_ready=bool(row.get("promotion_ready") or False),
    )


@router.post("/recommend")
async def recommend_one(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    rec = recommend(_to_input(payload)).to_dict()
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="comp_ai.recommend",
            entity_type="employee",
            entity_id=UUID(payload["employee_id"]) if _is_uuid(payload.get("employee_id")) else None,
            payload={
                "suggested_mid": rec["suggested_mid"],
                "promotion_recommended": rec["promotion_recommended"],
                "flags": rec["equity_flags"],
            },
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return rec


@router.post("/recommend-batch")
async def recommend_many(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    rows = payload.get("employees") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="employees array required")
    recs = recommend_batch([_to_input(r) for r in rows])
    out = [r.to_dict() for r in recs]
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="comp_ai.recommend_batch",
            entity_type="comp_cycle",
            payload={"n": len(out)},
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return {"items": out}


def _is_uuid(val) -> bool:
    try:
        UUID(str(val))
        return True
    except Exception:
        return False
