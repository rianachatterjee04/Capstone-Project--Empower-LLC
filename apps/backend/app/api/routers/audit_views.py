from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from datetime import datetime, timedelta

from app.api.deps import require_org, db_session, Actor

router = APIRouter(prefix="/audit", tags=["audit"])


# =========================================================
# BASIC VIEW LOGS (existing behavior)
# =========================================================
@router.get("/views")
async def views(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session), limit: int = 200):

    if actor.role not in ("owner","admin","hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        select * from public.view_events
        where org_id = :org_id
        order by created_at desc
        limit :limit
    """), {"org_id": actor.org_id, "limit": limit})

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]


# =========================================================
# EMPLOYEE ACCESS HISTORY
# who accessed a specific employee record
# =========================================================
@router.get("/employee/{employee_id}")
async def employee_access(employee_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        select actor_user_id, actor_role, path, created_at
        from public.view_events
        where org_id=:org_id and entity_type='employee' and entity_id=:eid
        order by created_at desc
    """), {"org_id": actor.org_id, "eid": employee_id})

    rows = res.fetchall()

    return {
        "employee_id": employee_id,
        "access_log": [
            {
                "viewer": str(r[0]),
                "role": r[1],
                "endpoint": r[2],
                "time": str(r[3])
            }
            for r in rows
        ]
    }


# =========================================================
# EVIDENCE ACCESS TRACKING
# Required for legal investigations
# =========================================================
@router.get("/evidence/{case_id}")
async def evidence_access(case_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        select actor_user_id, actor_role, created_at
        from public.view_events
        where org_id=:org_id
        and entity_type='investigation_case'
        and entity_id=:cid
        order by created_at desc
    """), {"org_id": actor.org_id, "cid": case_id})

    rows = res.fetchall()

    return {
        "case_id": case_id,
        "evidence_viewers": [
            {"viewer": str(r[0]), "role": r[1], "time": str(r[2])}
            for r in rows
        ]
    }


# =========================================================
# SUSPICIOUS ACTIVITY DETECTION
# Detect mass employee viewing
# =========================================================
@router.get("/suspicious")
async def suspicious(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","security"):
        raise HTTPException(status_code=403, detail="Not allowed")

    since = datetime.utcnow() - timedelta(hours=1)

    res = await db.execute(text("""
        select actor_user_id, count(*) as views
        from public.view_events
        where org_id=:org_id and created_at > :since
        group by actor_user_id
        having count(*) > 50
    """), {"org_id": actor.org_id, "since": since})

    rows = res.fetchall()

    return {
        "alerts": [
            {"user": str(r[0]), "views_last_hour": int(r[1])}
            for r in rows
        ]
    }


# =========================================================
# DATA EXPORT HISTORY
# Required for SOC2
# =========================================================
@router.get("/exports")
async def exports(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session), limit: int = 100):

    if actor.role not in ("owner","admin","hr","security"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(text("""
        select actor_user_id, export_type, created_at
        from public.data_exports
        where org_id=:org_id
        order by created_at desc
        limit :limit
    """), {"org_id": actor.org_id, "limit": limit})

    rows = res.fetchall()

    return [
        {"user": str(r[0]), "export": r[1], "time": str(r[2])}
        for r in rows
    ]

