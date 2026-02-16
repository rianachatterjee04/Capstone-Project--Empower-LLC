from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.deps import get_db

router = APIRouter(tags=["health"])


# ---------------------------------------------------------
# Liveness — is API process alive
# Used by container orchestrators (fast check)
# ---------------------------------------------------------
@router.get("/health")
async def health():
    return {"status": "alive"}


# ---------------------------------------------------------
# Readiness — can system actually serve requests
# Checks database connectivity
# ---------------------------------------------------------
@router.get("/health/ready")
async def readiness(db: AsyncSession = get_db()):
    try:
        await db.execute(text("select 1"))
        return {"status": "ready"}
    except Exception as e:
        return {"status": "not_ready", "reason": str(e)}


# ---------------------------------------------------------
# Deep system check — enterprise diagnostics
# Used by admins / monitoring dashboards
# ---------------------------------------------------------
@router.get("/health/system")
async def system_health(db: AsyncSession = get_db()):
    report = {
        "api": "ok",
        "database": "unknown",
        "migrations": "unknown",
        "workers": "unknown",
        "storage": "unknown"
    }

    # DB check
    try:
        await db.execute(text("select 1"))
        report["database"] = "ok"
    except Exception:
        report["database"] = "down"

    # schema check (critical tables exist)
    try:
        await db.execute(text("select count(*) from public.employees"))
        report["migrations"] = "ok"
    except Exception:
        report["migrations"] = "missing_tables"

    # workers placeholder (Temporal/queue heartbeat later)
    report["workers"] = "unknown"

    # storage placeholder (Supabase/S3 later)
    report["storage"] = "unknown"

    overall = "ok"
    if "down" in report.values() or "missing_tables" in report.values():
        overall = "degraded"

    return {"overall": overall, "services": report}

