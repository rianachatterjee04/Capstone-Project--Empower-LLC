from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from typing import List, Dict, Any
import pandas as pd

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent

router = APIRouter(prefix="/intel/recon", tags=["intelligence"])


# ---------------------------------------------------------------------------
# RUN RECONCILIATION
# ---------------------------------------------------------------------------
@router.post("/run")
async def run_reconciliation(
    system: str = Query("payroll", description="payroll | hris | equity"),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session)
) -> Dict[str, Any]:
    """Reconciliation Engine -- NOT AVAILABLE in this deployment.

    This endpoint answered 500 UndefinedColumn: it selected full_name, salary
    and equity_shares from employees, and this schema has none of them (it has
    legal_name and preferred_name, and compensation lives in the HR service's
    comp_records).

    Correcting the column names would not have made the endpoint honest. The
    other half of the comparison was a hardcoded fixture:

        external_df = pd.DataFrame([{"name": "Founders", "salary": 120000}])

    So a "reconciliation" would have compared this organisation's real people
    against one invented row and reported the differences as payroll mismatches
    -- findings about money, with no external system involved. Presenting that
    as a reconciliation result is the exact thing a finance buyer would rely on
    and the exact thing we must not fabricate.

    Both blockers are reported rather than either being papered over. The
    comparison machinery is not wired up yet and is ready for a
    real connector.
    """
    if system not in ("payroll", "hris", "equity"):
        raise HTTPException(status_code=400, detail="Invalid system")

    have = {r[0] for r in (await db.execute(text("""
        select column_name from information_schema.columns
        where table_schema='public' and table_name='employees'
    """))).all()}
    needed = {"payroll": {"salary"}, "equity": {"equity_shares"}, "hris": {"status"}}[system]
    missing = sorted(needed - have)

    blockers = []
    if missing:
        blockers.append(
            f"employees does not record {', '.join(missing)} in this schema, so "
            f"there is no internal figure to reconcile"
        )
    blockers.append(
        f"no {system} connector is configured; the external side of this "
        f"comparison is a built-in sample row, not data from your {system} system"
    )

    return {
        "available": False,
        "system": system,
        "external_source": "DEMO_SIMULATED",
        "findings": [],
        "reason": " and ".join(blockers) + ".",
        "note": (
            "No mismatches are reported because none were computed. An empty "
            "findings list here does NOT mean your records reconcile."
        ),
    }


# ---------------------------------------------------------------------------
# QUICK STATUS (UI dashboard polling)
# ---------------------------------------------------------------------------
@router.get("/summary")
async def recon_summary(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):
    """
    Returns last reconciliation status for dashboard indicator.
    """

    row = (await db.execute(text("""
        select payload
        from public.audit_events
        where org_id=:org_id
        and event_type='ai.reconciliation.executed'
        order by created_at desc
        limit 1
    """), {"org_id": actor.org_id})).mappings().first()

    if not row:
        return {"status": "never_run", "issues": 0}

    payload = row["payload"]
    issues = len(payload.get("findings", []))

    return {
        "status": "ok" if issues == 0 else "issues_detected",
        "issues": issues
    }

