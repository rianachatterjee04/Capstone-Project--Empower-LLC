"""
People / HR live report endpoints — power the native HR Reports center with real
data computed from the employees table. Mounted under /api/reports.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_org, db_session, Actor

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/headcount")
async def headcount(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Headcount by department → {rows:[[department, count]], total}."""
    rows = (await db.execute(text(
        "SELECT COALESCE(NULLIF(department,''),'Unassigned') AS dept, COUNT(*) AS n "
        "FROM public.employees WHERE org_id = :org GROUP BY dept ORDER BY n DESC"
    ), {"org": actor.org_id})).all()
    out = [[r[0], int(r[1])] for r in rows]
    return {"rows": out, "total": sum(r[1] for r in out)}


@router.get("/attrition")
async def attrition(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Headcount by status (active vs offboarding/terminated) → {rows:[[status, count]]}."""
    rows = (await db.execute(text(
        "SELECT COALESCE(NULLIF(status,''),'unknown') AS st, COUNT(*) AS n "
        "FROM public.employees WHERE org_id = :org GROUP BY st ORDER BY n DESC"
    ), {"org": actor.org_id})).all()
    return {"rows": [[str(r[0]).replace('_', ' ').title(), int(r[1])] for r in rows]}


async def _safe_rows(db: AsyncSession, sql: str, org: str) -> list:
    """Run a grouped query, returning [] if the table/columns aren't present."""
    try:
        res = (await db.execute(text(sql), {"org": org})).all()
        return [list(r) for r in res]
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass
        return []


@router.get("/pto")
async def pto(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """PTO requests by status → {rows:[[status, count]]}."""
    rows = await _safe_rows(db,
        "SELECT INITCAP(COALESCE(NULLIF(status,''),'pending')) AS st, COUNT(*) AS n "
        "FROM public.pto_requests WHERE org_id = :org GROUP BY st ORDER BY n DESC", actor.org_id)
    return {"rows": [[r[0], int(r[1])] for r in rows]}


@router.get("/compensation")
async def compensation(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Avg base comp by department (from comp_records); falls back to market benchmark
    by role → {rows:[[label, amount]]}."""
    rows = await _safe_rows(db,
        "SELECT COALESCE(NULLIF(e.department,''),'Unassigned') AS dept, ROUND(AVG(c.base_salary)) AS med "
        "FROM comp_records c JOIN public.employees e ON e.id = c.employee_id "
        "WHERE c.org_id = :org GROUP BY dept ORDER BY med DESC", actor.org_id)
    if not rows:
        rows = await _safe_rows(db,
            "SELECT job_title, ROUND(AVG(p50)) AS med FROM public.market_benchmarks "
            "WHERE org_id = :org GROUP BY job_title ORDER BY med DESC LIMIT 20", actor.org_id)
    return {"rows": [[r[0], int(r[1]) if r[1] is not None else 0] for r in rows]}


@router.get("/performance")
async def performance(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Performance reviews by status → {rows:[[status, count]]} (empty if no table)."""
    rows = await _safe_rows(db,
        "SELECT INITCAP(COALESCE(NULLIF(status,''),'pending')) AS st, COUNT(*) AS n "
        "FROM public.performance_reviews WHERE org_id = :org GROUP BY st ORDER BY n DESC", actor.org_id)
    return {"rows": [[r[0], int(r[1])] for r in rows]}


@router.get("/recruiting-funnel")
async def recruiting_funnel(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """Hiring funnel from employee lifecycle status → {stages:[{stage, count}]}."""
    rows = (await db.execute(text(
        "SELECT COALESCE(NULLIF(status,''),'unknown') AS st, COUNT(*) AS n "
        "FROM public.employees WHERE org_id = :org GROUP BY st"
    ), {"org": actor.org_id})).all()
    by = {str(r[0]).lower(): int(r[1]) for r in rows}
    order = [("pending_onboarding", "Onboarding"), ("active", "Active"),
             ("on_leave", "On leave"), ("offboarding", "Offboarding"), ("terminated", "Departed")]
    stages = [{"stage": label, "count": by.get(key, 0)} for key, label in order]
    return {"stages": stages}
