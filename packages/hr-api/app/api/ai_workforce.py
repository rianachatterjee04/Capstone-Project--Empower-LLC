"""AI-Workforce live-data router.

Read-only GET endpoints that back the HR AI-workforce dashboards. Every query
is scoped to the caller's org_id and wrapped in try/except so a missing table
(some of these are provisioned by optional migrations) returns [] instead of a
500. Pattern mirrors app/api/routers/audit_views.py.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org

router = APIRouter(prefix="/ai-workforce", tags=["ai-workforce"])

# SECURITY: table names are interpolated into SQL via f-strings. All current callers pass
# hardcoded literals, but to keep this safe against any future caller forwarding client
# input, validate the identifier against a strict pattern before interpolation.
_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")


def _safe_table(table: str) -> str:
    if not _IDENT_RE.match(table):
        raise ValueError(f"Unsafe table identifier: {table!r}")
    return table


async def _select_org(db: AsyncSession, table: str, org_id: str, limit: int):
    """Run a read-only `SELECT * ... WHERE org_id=:org` and return list[dict].

    Returns [] (after rolling back) if the table is missing or the query fails,
    so an unprovisioned table never surfaces as a 500.
    """
    table = _safe_table(table)
    # Not every AI-workforce table has a created_at column (some use started_at,
    # updated_at, or a composite key), so we don't hard-order on it — we order on
    # whichever common timestamp the table exposes, falling back to no ordering.
    order_col = ""
    for cand in ("created_at", "started_at", "updated_at", "period", "detected_at"):
        try:
            chk = await db.execute(
                text("""select 1 from information_schema.columns
                        where table_schema='public' and table_name=:t and column_name=:c limit 1"""),
                {"t": table, "c": cand},
            )
            if chk.first():
                order_col = f"order by {cand} desc"
                break
        except Exception:
            await db.rollback()
    try:
        res = await db.execute(
            text(f"select * from public.{table} where org_id = :org_id {order_col} limit :limit"),
            {"org_id": org_id, "limit": limit},
        )
        cols = res.keys()
        return [dict(zip(cols, row)) for row in res.fetchall()]
    except Exception:
        await db.rollback()
        return []


# =========================================================
# WORKFORCE REGISTRY
# =========================================================
@router.get("/registry")
async def registry(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    return await _select_org(db, "workforce_registry", actor.org_id, limit)


# =========================================================
# AI SKILLS
# =========================================================
async def _join_employees(db: AsyncSession, table: str, org_id: str, limit: int):
    """Like _select_org but joins employees to add employee_name/department."""
    table = _safe_table(table)
    try:
        res = await db.execute(
            text(f"""
                select t.*, e.legal_name as employee_name, e.department as department
                from public.{table} t
                left join public.employees e on e.id = t.employee_id
                where t.org_id = :org_id
                limit :limit
            """),
            {"org_id": org_id, "limit": limit},
        )
        cols = res.keys()
        return [dict(zip(cols, row)) for row in res.fetchall()]
    except Exception:
        await db.rollback()
        return await _select_org(db, table, org_id, limit)


@router.get("/skills")
async def skills(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 400,
):
    return {"skills": await _join_employees(db, "ai_skills", actor.org_id, limit)}


# =========================================================
# AI PRODUCTIVITY
# =========================================================
@router.get("/productivity")
async def productivity(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    return {"productivity": await _join_employees(db, "ai_productivity", actor.org_id, limit)}


# =========================================================
# AI ONBOARDING RUNS
# =========================================================
@router.get("/onboarding")
async def onboarding(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    return await _select_org(db, "ai_onboarding_runs", actor.org_id, limit)


# =========================================================
# WORKFORCE AI SESSIONS
# =========================================================
@router.get("/sessions")
async def sessions(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    return await _select_org(db, "wf_ai_sessions", actor.org_id, limit)


# =========================================================
# WORKFORCE AI PROFICIENCY
# =========================================================
@router.get("/proficiency")
async def proficiency(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    return await _select_org(db, "wf_ai_proficiency", actor.org_id, limit)


# =========================================================
# PAYROLL AGENT RUNS
# =========================================================
@router.get("/payroll/runs")
async def payroll_runs(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    return await _select_org(db, "payroll_agent_runs", actor.org_id, limit)


# =========================================================
# PAYROLL ALERTS
# =========================================================
@router.get("/payroll/alerts")
async def payroll_alerts(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    return await _select_org(db, "payroll_alerts", actor.org_id, limit)


# =========================================================
# PAYROLL TRUST SCORES
# =========================================================
@router.get("/payroll/trust-scores")
async def payroll_trust_scores(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    limit: int = 200,
):
    return await _select_org(db, "payroll_trust_scores", actor.org_id, limit)
