from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.json_utils import json_safe

from app.api.deps import Actor, db_session, require_org

router = APIRouter(prefix="/audit", tags=["audit"])


# =========================================================
# BASIC VIEW LOGS
# =========================================================
@router.get("/views")
async def views(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(
        text("""
            select * from public.view_events
            where org_id = :org_id
            order by created_at desc
            limit :limit
        """),
        {"org_id": actor.org_id, "limit": limit},
    )

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]


# =========================================================
# EMPLOYEE ACCESS HISTORY
# =========================================================
@router.get("/employee/{employee_id}")
async def employee_access(
    employee_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(
        text("""
            select actor_user_id, actor_role, path, created_at
            from public.view_events
            where org_id = :org_id
              and entity_type = 'employee'
              and entity_id = :eid
            order by created_at desc
        """),
        {"org_id": actor.org_id, "eid": employee_id},
    )

    rows = res.fetchall()

    return {
        "employee_id": employee_id,
        "access_log": [
            {
                "viewer": str(r[0]) if r[0] is not None else None,
                "role": r[1],
                "endpoint": r[2],
                "time": str(r[3]),
            }
            for r in rows
        ],
    }


# =========================================================
# EVIDENCE ACCESS TRACKING
# =========================================================
@router.get("/evidence/{case_id}")
async def evidence_access(
    case_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    res = await db.execute(
        text("""
            select actor_user_id, actor_role, created_at
            from public.view_events
            where org_id = :org_id
              and entity_type = 'investigation_case'
              and entity_id = :cid
            order by created_at desc
        """),
        {"org_id": actor.org_id, "cid": case_id},
    )

    rows = res.fetchall()

    return {
        "case_id": case_id,
        "evidence_viewers": [
            {
                "viewer": str(r[0]) if r[0] is not None else None,
                "role": r[1],
                "time": str(r[2]),
            }
            for r in rows
        ],
    }


# =========================================================
# SUSPICIOUS ACTIVITY DETECTION
# =========================================================
@router.get("/suspicious")
async def suspicious(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "security"):
        raise HTTPException(status_code=403, detail="Not allowed")

    since = datetime.utcnow() - timedelta(hours=1)

    res = await db.execute(
        text("""
            select actor_user_id, count(*) as views
            from public.view_events
            where org_id = :org_id
              and created_at > :since
            group by actor_user_id
            having count(*) > 50
        """),
        {"org_id": actor.org_id, "since": since},
    )

    rows = res.fetchall()

    return {
        "alerts": [
            {
                "user": str(r[0]) if r[0] is not None else None,
                "views_last_hour": int(r[1]),
            }
            for r in rows
        ]
    }


# =========================================================
# DATA EXPORT HISTORY
# =========================================================
@router.get("/exports")
async def exports(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 100,
):
    if actor.role not in ("owner", "admin", "hr", "security"):
        raise HTTPException(status_code=403, detail="Not allowed")

    # Defensive: data_exports table is created by the audit-log migration which
    # may not be provisioned in every demo environment. Return [] instead of 500.
    try:
        res = await db.execute(
            text("""
                select actor_user_id, export_type, created_at
                from public.data_exports
                where org_id = :org_id
                order by created_at desc
                limit :limit
            """),
            {"org_id": actor.org_id, "limit": limit},
        )
        rows = res.fetchall()
    except Exception:
        await db.rollback()
        return []

    return [
        {
            "user": str(r[0]) if r[0] is not None else None,
            "export": r[1],
            "time": str(r[2]),
        }
        for r in rows
    ]
