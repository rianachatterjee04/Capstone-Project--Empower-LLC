"""Predictive attrition / flight-risk router."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.services.attrition_service import AttritionFeatures, predict, predict_batch


router = APIRouter(prefix="/attrition", tags=["attrition"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "manager")


def _to_features(row: dict) -> AttritionFeatures:
    if not row.get("employee_id") or not row.get("name"):
        raise HTTPException(status_code=400, detail="employee_id and name required")
    return AttritionFeatures(
        employee_id=str(row["employee_id"]),
        name=str(row["name"]),
        department=row.get("department"),
        tenure_years=float(row.get("tenure_years") or 1),
        months_since_last_raise=float(row.get("months_since_last_raise") or 12),
        months_since_last_promotion=float(row.get("months_since_last_promotion") or 24),
        performance_rating=float(row.get("performance_rating") or 3),
        engagement_score=row.get("engagement_score"),
        compa_ratio=row.get("compa_ratio"),
        pto_balance_days=row.get("pto_balance_days"),
        overtime_hours_last_30d=float(row.get("overtime_hours_last_30d") or 0),
        manager_change_in_last_180d=bool(row.get("manager_change_in_last_180d") or False),
        role_change_in_last_180d=bool(row.get("role_change_in_last_180d") or False),
    )


def _tenure_years(start_date) -> float:
    if not start_date:
        return 1.0
    try:
        if hasattr(start_date, "year"):
            d = start_date
            if hasattr(d, "tzinfo") and d.tzinfo is not None:
                now = datetime.now(timezone.utc).date()
            else:
                now = datetime.utcnow().date()
            return max(0.1, (now - d).days / 365.25)
        d = datetime.fromisoformat(str(start_date)).date()
        return max(0.1, (datetime.utcnow().date() - d).days / 365.25)
    except Exception:
        return 1.0


@router.post("/predict")
async def predict_one(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return predict(_to_features(payload)).to_dict()


@router.post("/predict-batch")
async def predict_many(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    rows = payload.get("employees") or []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(status_code=400, detail="employees array required")
    preds = predict_batch([_to_features(r) for r in rows])
    return {"items": [p.to_dict() for p in preds]}


@router.get("/demo")
async def demo(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Flight-risk scores for the caller's active employees (org-scoped).

    Path kept as /demo for employer-portal compatibility; payload is real org
    data, not the old invented Avery Chen cohort.
    """
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    rows = (await db.execute(text("""
        select e.id, e.legal_name, e.department, e.start_date,
               (select pr.rating
                  from public.performance_reviews pr
                 where pr.org_id = e.org_id and pr.employee_id = e.id
                   and pr.rating is not null
                 order by pr.created_at desc
                 limit 1) as rating
          from public.employees e
         where e.org_id = cast(:org_id as uuid)
           and e.status = 'active'
         order by e.legal_name
    """), {"org_id": actor.org_id})).mappings().all()

    features = [
        AttritionFeatures(
            employee_id=str(r["id"]),
            name=r["legal_name"],
            department=r["department"],
            tenure_years=_tenure_years(r["start_date"]),
            performance_rating=float(r["rating"]) if r["rating"] is not None else 3.5,
        )
        for r in rows
    ]
    preds = predict_batch(features) if features else []
    return {
        "items": [p.to_dict() for p in preds],
        "all_sample": False,
        "provenance": "scored from your organisation's active employees",
    }
