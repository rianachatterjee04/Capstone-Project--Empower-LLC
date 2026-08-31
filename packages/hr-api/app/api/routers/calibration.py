"""9-Box Calibration router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.calibration_service import (
    calibrate_managers,
    grid_snapshot,
    highlights,
    list_placements,
    upsert_placement,
)

router = APIRouter(prefix="/calibration", tags=["calibration"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "manager")


@router.get("/grid")
async def grid(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return grid_snapshot(actor.org_id)


@router.get("/placements")
async def placements(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [p.to_dict() for p in list_placements(actor.org_id)]}


@router.post("/placements")
async def upsert(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    employee_id = (payload.get("employee_id") or "").strip()
    employee_name = (payload.get("employee_name") or "").strip()
    if not employee_id or not employee_name:
        raise HTTPException(status_code=400, detail="employee_id, employee_name required")
    p = upsert_placement(
        actor.org_id,
        employee_id=employee_id,
        employee_name=employee_name,
        team=(payload.get("team") or "").strip(),
        manager_id=(payload.get("manager_id") or "").strip(),
        manager_name=(payload.get("manager_name") or "").strip(),
        performance=int(payload.get("performance") or 2),
        potential=int(payload.get("potential") or 2),
        rationale=(payload.get("rationale") or "").strip(),
    )
    return p.to_dict()


@router.get("/managers")
async def managers(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return calibrate_managers(actor.org_id)


@router.get("/highlights")
async def hi(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return highlights(actor.org_id)
