"""Settings hub router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.settings_service import (
    get_settings,
    toggle_automation,
    toggle_integration,
    update_brand,
    update_org,
    update_security,
)


router = APIRouter(prefix="/settings-hub", tags=["settings-hub"])


def _privileged(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr")


@router.get("")
async def get_all(actor: Actor = Depends(require_org)):
    return get_settings(actor.org_id)


@router.patch("/org")
async def patch_org(payload: dict, actor: Actor = Depends(require_org)):
    if not _privileged(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return update_org(actor.org_id, payload)


@router.patch("/brand")
async def patch_brand(payload: dict, actor: Actor = Depends(require_org)):
    if not _privileged(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return update_brand(actor.org_id, payload)


@router.post("/integrations/{key}/toggle")
async def toggle_integration_route(key: str, payload: dict | None = None, actor: Actor = Depends(require_org)):
    if not _privileged(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    connected = (payload or {}).get("connected")
    out = toggle_integration(actor.org_id, key, connected)
    if out is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return out


@router.post("/automations/{rule_id}/toggle")
async def toggle_automation_route(rule_id: str, payload: dict | None = None, actor: Actor = Depends(require_org)):
    if not _privileged(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    enabled = (payload or {}).get("enabled")
    out = toggle_automation(actor.org_id, rule_id, enabled)
    if out is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    return out


@router.patch("/security")
async def patch_security(payload: dict, actor: Actor = Depends(require_org)):
    if not _privileged(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return update_security(actor.org_id, payload)
