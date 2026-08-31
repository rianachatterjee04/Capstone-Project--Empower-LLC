from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.core.json_utils import json_safe
from uuid import UUID
import httpx
from datetime import datetime

from app.api.deps import require_org, db_session, Actor

router = APIRouter(prefix="/push", tags=["push"])


# ---------------------------------------------------------
# REGISTER DEVICE TOKEN
# ---------------------------------------------------------
@router.post("/register")
async def register(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    token = payload.get("expo_push_token")
    if not token:
        raise HTTPException(status_code=400, detail="expo_push_token required")

    await db.execute(text("""
        insert into public.expo_push_tokens(org_id, user_id, token, platform, created_at)
        values (:org_id, :user_id, :token, :platform, now())
        on conflict (org_id, token) do update
        set user_id = excluded.user_id
    """), {
        "org_id": actor.org_id,
        "user_id": actor.user_id,
        "token": token,
        "platform": payload.get("platform","unknown")
    })

    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------
# INTERNAL SEND FUNCTION
# ---------------------------------------------------------
async def _send_push(tokens, title: str, body: str, data: dict | None = None):

    messages = []
    for t in tokens:
        messages.append({
            "to": t,
            "title": title,
            "body": body,
            "data": data or {}
        })

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post("https://exp.host/--/api/v2/push/send", json=messages)

    return resp.status_code


# ---------------------------------------------------------
# SEND TO USER
# ---------------------------------------------------------
@router.post("/notify-user/{user_id}")
async def notify_user(user_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","manager","system"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rows = (await db.execute(text("""
        select token from public.expo_push_tokens
        where org_id=:org_id and user_id=:user_id
    """), {"org_id": actor.org_id, "user_id": user_id})).fetchall()

    if not rows:
        return {"ok": False, "reason": "no_tokens"}

    status = await _send_push(
        [r[0] for r in rows],
        payload.get("title","Foundry Notification"),
        payload.get("message","You have an update"),
        payload.get("data")
    )

    return {"ok": True, "status": status}


# ---------------------------------------------------------
# SEND TO ROLE (HR / MANAGERS / EXEC)
# ---------------------------------------------------------
@router.post("/notify-role/{role}")
async def notify_role(role: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","system"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rows = (await db.execute(text("""
        select t.token
        from public.expo_push_tokens t
        join public.users u on u.id=t.user_id
        where t.org_id=:org_id and u.role=:role
    """), {"org_id": actor.org_id, "role": role})).fetchall()

    if not rows:
        return {"ok": False, "reason": "no_tokens"}

    status = await _send_push(
        [r[0] for r in rows],
        payload.get("title","Foundry Alert"),
        payload.get("message"),
        payload.get("data")
    )

    return {"ok": True, "status": status}


# ---------------------------------------------------------
# BROADCAST ORG ALERT (LEGAL / PAYROLL / INCIDENT)
# ---------------------------------------------------------
@router.post("/broadcast")
async def broadcast(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal","system"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rows = (await db.execute(text("""
        select token from public.expo_push_tokens
        where org_id=:org_id
        limit 500
    """), {"org_id": actor.org_id})).fetchall()

    if not rows:
        return {"ok": False, "reason": "no_tokens"}

    status = await _send_push(
        [r[0] for r in rows],
        payload.get("title","Company Notification"),
        payload.get("message"),
        payload.get("data")
    )

    return {"ok": True, "status": status}


# ---------------------------------------------------------
# SYSTEM WORKFLOW ALERT (used by Temporal / automation)
# ---------------------------------------------------------
@router.post("/workflow-event")
async def workflow_event(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """
    This is called automatically by workflows:
    - escalation overdue
    - approval requested
    - onboarding step pending
    - performance review due
    """

    target_user = payload.get("user_id")
    message = payload.get("message","Workflow update")

    rows = (await db.execute(text("""
        select token from public.expo_push_tokens
        where org_id=:org_id and user_id=:user_id
    """), {"org_id": actor.org_id, "user_id": target_user})).fetchall()

    if not rows:
        return {"ok": False}

    await _send_push([r[0] for r in rows], "Action Required", message, payload.get("data"))

    return {"ok": True}

