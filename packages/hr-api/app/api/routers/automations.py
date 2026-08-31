"""Workflow Automations router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.automations_service import (
    ACTIONS,
    TEMPLATES,
    TRIGGERS,
    create_automation,
    delete_automation,
    get_automation,
    install_template,
    list_automations,
    list_runs,
    trigger_automation,
    update_automation,
)

router = APIRouter(prefix="/automations", tags=["automations"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr")


@router.get("/taxonomy")
async def taxonomy(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {
        "triggers": TRIGGERS,
        "actions": ACTIONS,
    }


@router.get("/templates")
async def templates(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": TEMPLATES}


@router.post("/templates/{template_id}/install")
async def install(template_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    a = install_template(actor.org_id, template_id)
    if not a:
        raise HTTPException(status_code=404, detail="Template not found")
    return a.to_dict()


@router.get("")
async def list_endpoint(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [a.to_dict() for a in list_automations(actor.org_id)]}


@router.post("")
async def create_endpoint(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    name = (payload.get("name") or "").strip()
    trigger_key = (payload.get("trigger_key") or "").strip()
    actions = payload.get("actions") or []
    if not name or not trigger_key or not actions:
        raise HTTPException(status_code=400, detail="name, trigger_key, actions required")
    a = create_automation(
        actor.org_id,
        name=name,
        description=(payload.get("description") or "").strip(),
        trigger_key=trigger_key,
        filters=payload.get("filters") or {},
        actions=actions,
        enabled=bool(payload.get("enabled", True)),
    )
    return a.to_dict()


@router.patch("/{automation_id}")
async def patch_endpoint(automation_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    a = update_automation(actor.org_id, automation_id, payload)
    if not a:
        raise HTTPException(status_code=404, detail="Automation not found")
    return a.to_dict()


@router.delete("/{automation_id}")
async def delete_endpoint(automation_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    ok = delete_automation(actor.org_id, automation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Automation not found")
    return {"deleted": True}


@router.post("/{automation_id}/trigger")
async def trigger(automation_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    run = trigger_automation(actor.org_id, automation_id, payload or {})
    if not run:
        raise HTTPException(status_code=404, detail="Automation not found")
    return run.to_dict()


@router.get("/runs")
async def runs(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [r.to_dict() for r in list_runs(actor.org_id)]}
