"""People CRM router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.people_crm_service import (
    add_note,
    create_contact,
    get_contact,
    list_contacts,
    list_pipelines,
    signals_summary,
    update_contact,
)


router = APIRouter(prefix="/crm", tags=["people-crm"])


@router.get("/summary")
async def summary(actor: Actor = Depends(require_org)):
    return signals_summary(actor.org_id)


@router.get("/pipelines")
async def pipelines(actor: Actor = Depends(require_org)):
    return {"items": list_pipelines()}


@router.get("/contacts")
async def contacts(
    pipeline: str | None = None,
    status: str | None = None,
    owner: str | None = None,
    q: str | None = None,
    actor: Actor = Depends(require_org),
):
    return {"items": list_contacts(actor.org_id, pipeline=pipeline, status=status, owner=owner, q=q)}


@router.get("/contacts/{contact_id}")
async def contact(contact_id: str, actor: Actor = Depends(require_org)):
    out = get_contact(actor.org_id, contact_id)
    if not out:
        raise HTTPException(status_code=404, detail="Contact not found")
    return out


@router.post("/contacts")
async def create(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in ("owner", "admin", "hr", "manager", "recruiter"):
        raise HTTPException(status_code=403, detail="Not allowed")
    if not payload.get("name"):
        raise HTTPException(status_code=400, detail="name required")
    return create_contact(actor.org_id, payload)


@router.patch("/contacts/{contact_id}")
async def patch(contact_id: str, payload: dict, actor: Actor = Depends(require_org)):
    out = update_contact(actor.org_id, contact_id, payload)
    if not out:
        raise HTTPException(status_code=404, detail="Contact not found")
    return out


@router.post("/contacts/{contact_id}/notes")
async def note(contact_id: str, payload: dict, actor: Actor = Depends(require_org)):
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="body required")
    author = payload.get("author") or actor.claims.get("email") or "Internal"
    out = add_note(actor.org_id, contact_id, body, author)
    if not out:
        raise HTTPException(status_code=404, detail="Contact not found")
    return out
