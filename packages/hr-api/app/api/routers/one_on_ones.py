"""1:1s router — recurring manager ↔ report meetings.

Thin router over oneonone_service (in-process, org-scoped), mirroring the
goals.py / recognition.py pattern. Private agenda notes are filtered server-side
by the acting user's id before any payload leaves the process.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services import oneonone_service as svc


router = APIRouter(prefix="/one-on-ones", tags=["one_on_ones"])


def _series_or_403(actor: Actor, series_id: str):
    s = svc._find_series(actor.org_id, series_id)
    if not s:
        raise HTTPException(status_code=404, detail="Series not found")
    if not svc.can_view_series(s, actor.user_id, actor.role):
        raise HTTPException(status_code=403, detail="Not a participant in this 1:1")
    return s


def _meeting_or_403(actor: Actor, meeting_id: str):
    s, m = svc._find_meeting(actor.org_id, meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    if not svc.can_view_series(s, actor.user_id, actor.role):
        raise HTTPException(status_code=403, detail="Not a participant in this 1:1")
    return s, m


# --- Series -----------------------------------------------------------------
@router.get("/series")
async def list_series(actor: Actor = Depends(require_org)):
    return svc.list_series(actor.org_id, actor.user_id, actor.role)


@router.post("/series")
async def create_series(payload: dict, actor: Actor = Depends(require_org)):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    out = svc.create_series(actor.org_id, payload)
    if not out:
        raise HTTPException(status_code=400, detail="manager_user_id and report_user_id required")
    return out


# --- Meetings ---------------------------------------------------------------
@router.get("/series/{series_id}/meetings")
async def list_meetings(series_id: str, actor: Actor = Depends(require_org)):
    _series_or_403(actor, series_id)
    return svc.list_meetings(actor.org_id, series_id, actor.user_id)


@router.post("/series/{series_id}/meetings")
async def create_meeting(series_id: str, payload: dict, actor: Actor = Depends(require_org)):
    _series_or_403(actor, series_id)
    out = svc.create_meeting(actor.org_id, series_id, payload)
    if not out:
        raise HTTPException(status_code=404, detail="Series not found")
    return out


@router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str, actor: Actor = Depends(require_org)):
    _meeting_or_403(actor, meeting_id)
    return svc.get_meeting(actor.org_id, meeting_id, actor.user_id)


@router.patch("/meetings/{meeting_id}/status")
async def set_status(meeting_id: str, payload: dict, actor: Actor = Depends(require_org)):
    _meeting_or_403(actor, meeting_id)
    out = svc.set_meeting_status(actor.org_id, meeting_id, str(payload.get("status") or ""))
    if not out:
        raise HTTPException(status_code=400, detail="Invalid status")
    return out


# --- Agenda items -----------------------------------------------------------
@router.post("/meetings/{meeting_id}/agenda")
async def add_agenda(meeting_id: str, payload: dict, actor: Actor = Depends(require_org)):
    s, _ = _meeting_or_403(actor, meeting_id)
    role = svc._viewer_role(s, actor.user_id, actor.role)
    out = svc.add_agenda_item(
        actor.org_id, meeting_id,
        text=str(payload.get("text") or ""),
        author_user_id=actor.user_id,
        author_role=role,
        is_private=bool(payload.get("is_private", False)),
    )
    if not out:
        raise HTTPException(status_code=400, detail="text required")
    return out


@router.patch("/agenda/{agenda_id}")
async def update_agenda(agenda_id: str, payload: dict, actor: Actor = Depends(require_org)):
    s, _, a = svc._find_agenda(actor.org_id, agenda_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agenda item not found")
    if not svc.can_view_series(s, actor.user_id, actor.role):
        raise HTTPException(status_code=403, detail="Not a participant in this 1:1")
    out = svc.update_agenda_item(actor.org_id, agenda_id, actor.user_id, actor.role, payload)
    if not out:
        raise HTTPException(status_code=403, detail="Cannot edit this item")
    return out


@router.delete("/agenda/{agenda_id}")
async def delete_agenda(agenda_id: str, actor: Actor = Depends(require_org)):
    s, _, a = svc._find_agenda(actor.org_id, agenda_id)
    if not a:
        raise HTTPException(status_code=404, detail="Agenda item not found")
    if not svc.can_view_series(s, actor.user_id, actor.role):
        raise HTTPException(status_code=403, detail="Not a participant in this 1:1")
    if not svc.delete_agenda_item(actor.org_id, agenda_id, actor.user_id, actor.role):
        raise HTTPException(status_code=403, detail="Cannot delete this item")
    return {"deleted": True}


# --- Shared talking points --------------------------------------------------
@router.post("/meetings/{meeting_id}/talking-points")
async def add_talking_point(meeting_id: str, payload: dict, actor: Actor = Depends(require_org)):
    _meeting_or_403(actor, meeting_id)
    out = svc.add_talking_point(actor.org_id, meeting_id, str(payload.get("text") or ""), actor.user_id)
    if not out:
        raise HTTPException(status_code=400, detail="text required")
    return out


# --- Action items -----------------------------------------------------------
@router.post("/meetings/{meeting_id}/actions")
async def add_action(meeting_id: str, payload: dict, actor: Actor = Depends(require_org)):
    _meeting_or_403(actor, meeting_id)
    out = svc.add_action_item(
        actor.org_id, meeting_id,
        text=str(payload.get("text") or ""),
        assignee_user_id=payload.get("assignee_user_id"),
        due=payload.get("due"),
    )
    if not out:
        raise HTTPException(status_code=400, detail="text required")
    return out


@router.patch("/actions/{action_id}")
async def update_action(action_id: str, payload: dict, actor: Actor = Depends(require_org)):
    s, _, a = svc._find_action(actor.org_id, action_id)
    if not a:
        raise HTTPException(status_code=404, detail="Action item not found")
    if not svc.can_view_series(s, actor.user_id, actor.role):
        raise HTTPException(status_code=403, detail="Not a participant in this 1:1")
    out = svc.set_action_done(actor.org_id, action_id, bool(payload.get("done", True)))
    return out


# --- AI assist (fail-soft) --------------------------------------------------
@router.post("/series/{series_id}/suggest-agenda")
async def suggest_agenda(series_id: str, actor: Actor = Depends(require_org)):
    _series_or_403(actor, series_id)
    return svc.suggest_agenda(actor.org_id, series_id)
