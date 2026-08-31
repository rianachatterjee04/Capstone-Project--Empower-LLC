"""Internal talent marketplace router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org, required_field
from app.services.talent_marketplace_service import (
    demo_pool,
    list_internal_roles,
    match_employee_to_marketplace,
    succession_candidates_for_role,
)


router = APIRouter(prefix="/marketplace", tags=["marketplace"])


@router.get("/roles")
async def roles(_: Actor = Depends(require_org)):
    return {"items": list_internal_roles()}


@router.post("/match-employee")
async def match_employee(payload: dict, _: Actor = Depends(require_org)):
    if not payload.get("employee_id") or not payload.get("employee_name"):
        raise HTTPException(status_code=400, detail="employee_id and employee_name required")
    matches = match_employee_to_marketplace(
        employee_id=str(required_field(payload, "employee_id")),
        employee_name=str(required_field(payload, "employee_name")),
        employee_skills=payload.get("skills") or [],
        performance_rating=float(payload.get("performance_rating") or 3.5),
        tenure_years=float(payload.get("tenure_years") or 1.0),
    )
    return {"items": [m.to_dict() for m in matches]}


@router.get("/succession/{role_id}")
async def succession(role_id: str, actor: Actor = Depends(require_org)):
    # Real succession pool = the org's high-performance / high-potential 9-box
    # placements (calibration_service). Fall back to the demo pool only when no
    # employee has been calibrated into the top-right cell yet.
    from app.services.calibration_service import succession_pool
    pool = succession_pool(actor.org_id) or demo_pool()
    matches = succession_candidates_for_role(role_id, pool)
    return {"items": [m.to_dict() for m in matches]}


@router.get("/demo-pool")
async def pool(_: Actor = Depends(require_org)):
    return {"items": demo_pool()}
