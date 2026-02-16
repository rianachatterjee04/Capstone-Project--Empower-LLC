from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from typing import List, Dict, Any
import pandas as pd

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.platform.runtime import platform

router = APIRouter(prefix="/intel/recon", tags=["intelligence"])


# ---------------------------------------------------------------------------
# RUN RECONCILIATION
# ---------------------------------------------------------------------------
@router.post("/run")
async def run_reconciliation(
    system: str = Query("payroll", description="payroll | hris | equity"),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session)
) -> List[Dict[str, Any]]:
    """
    Reconciliation Engine

    Compares Foundry internal records against external system snapshot.
    Used for:
    - payroll mismatch detection
    - HRIS inconsistencies
    - equity cap table verification
    """

    try:

        # ---------------------------------------------------------
        # 1️⃣ LOAD INTERNAL DATA (single source of truth)
        # ---------------------------------------------------------
        rows = (await db.execute(text("""
            select id, full_name as name, salary, equity_shares
            from public.employees
            where org_id=:org_id and status='active'
        """), {"org_id": actor.org_id})).mappings().all()

        internal_df = pd.DataFrame([dict(r) for r in rows])

        # ---------------------------------------------------------
        # 2️⃣ LOAD EXTERNAL DATA (SIMULATED CONNECTOR)
        # In real deployment this comes from integrations
        # ---------------------------------------------------------
        if system == "payroll":
            external_df = pd.DataFrame([
                {"name": "Founders", "salary": 120000}
            ])

        elif system == "equity":
            external_df = pd.DataFrame([
                {"name": "Founders", "equity_shares": 5900000}
            ])

        elif system == "hris":
            external_df = pd.DataFrame([
                {"name": "Founders", "status": "active"}
            ])

        else:
            raise HTTPException(status_code=400, detail="Invalid system")

        # ---------------------------------------------------------
        # 3️⃣ RUN RECONCILIATION ENGINE
        # ---------------------------------------------------------
        findings = platform.run_reconciliation(
            internal_df=internal_df,
            external_df=external_df,
            source=system
        )

        results = [
            {
                "severity": f.severity,
                "category": f.category,
                "message": f.message,
                "entity": getattr(f, "entity", None),
                "recommendation": getattr(f, "recommendation", None),
            }
            for f in findings
        ]

        # ---------------------------------------------------------
        # 4️⃣ AUDIT TRAIL (LEGAL DEFENSIBILITY)
        # ---------------------------------------------------------
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai.reconciliation.executed",
            entity_type="org",
            entity_id=None,
            payload={
                "system": system,
                "findings": results
            }
        ))

        await db.commit()

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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

