"""Predictive attrition / flight-risk router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
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
async def demo(actor: Actor = Depends(require_org)):
    """Synthetic demo data so the UI shows something useful out of the box."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    sample = [
        AttritionFeatures("e1", "Avery Chen", department="Engineering", tenure_years=2.4, months_since_last_raise=22, months_since_last_promotion=30, performance_rating=4.5, engagement_score=0.42, compa_ratio=0.82, overtime_hours_last_30d=38),
        AttritionFeatures("e2", "Jordan Patel", department="Sales", tenure_years=1.8, months_since_last_raise=14, months_since_last_promotion=20, performance_rating=3.2, engagement_score=0.61, compa_ratio=0.97, pto_balance_days=22),
        AttritionFeatures("e3", "Sam Rivera", department="Engineering", tenure_years=3.6, months_since_last_raise=10, months_since_last_promotion=12, performance_rating=4.0, compa_ratio=1.05, engagement_score=0.78),
        AttritionFeatures("e4", "Morgan Lee", department="HR", tenure_years=0.6, months_since_last_raise=6, months_since_last_promotion=0, performance_rating=3.6, compa_ratio=0.99, manager_change_in_last_180d=True),
        AttritionFeatures("e5", "Riley Singh", department="Design", tenure_years=2.0, months_since_last_raise=18, months_since_last_promotion=24, performance_rating=4.8, compa_ratio=0.88, role_change_in_last_180d=True, pto_balance_days=19),
    ]
    # Every person below is invented. An attrition score attached to a NAME
    # reads as a claim about that person, so the payload has to say whose
    # people these are before a screen renders "Avery Chen: high risk".
    return {
        "items": [{**p.to_dict(), "is_sample": True} for p in predict_batch(sample)],
        "all_sample": True,
        "provenance": "these are illustrative sample people, not employees in your organisation",
    }
