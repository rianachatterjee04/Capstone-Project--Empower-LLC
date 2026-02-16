from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from typing import Dict, Any

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.modules.equity_health_index import EquityHealth

router = APIRouter(prefix="/intel/equity", tags=["intelligence"])


# ---------------------------------------------------------------------------
# EQUITY FAIRNESS ANALYSIS
# ---------------------------------------------------------------------------
@router.get("/fairness")
async def fairness(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)) -> Dict[str, Any]:
    """
    Calculates equity fairness across departments.

    Uses real employee equity grants and returns:
    - fairness score
    - imbalance detection
    - department breakdown
    """

    try:

        # ---------------------------------------------------------
        # 1️⃣ Load equity grants
        # ---------------------------------------------------------
        rows = (await db.execute(text("""
            select department, coalesce(sum(equity_shares),0) as total_shares
            from public.employees
            where org_id=:org_id and status='active'
            group by department
        """), {"org_id": actor.org_id})).mappings().all()

        if not rows:
            return {
                "equity_fairness_score": 1.0,
                "interpretation": "No equity data",
                "departments": {}
            }

        grants = {r["department"] or "Unknown": float(r["total_shares"]) for r in rows}

        # ---------------------------------------------------------
        # 2️⃣ Run fairness engine
        # ---------------------------------------------------------
        health = EquityHealth(grants)
        score = health.fairness_index()

        # ---------------------------------------------------------
        # 3️⃣ Generate explainability
        # ---------------------------------------------------------
        max_dept = max(grants, key=grants.get)
        min_dept = min(grants, key=grants.get)

        imbalance_ratio = (grants[max_dept] / grants[min_dept]) if grants[min_dept] else None

        if score >= 0.85:
            interpretation = "Equity distribution is well balanced"
        elif score >= 0.65:
            interpretation = "Moderate imbalance detected"
        else:
            interpretation = "High imbalance — compensation review recommended"

        explanation = {
            "largest_holder_department": max_dept,
            "smallest_holder_department": min_dept,
            "imbalance_ratio": imbalance_ratio,
        }

        result = {
            "equity_fairness_score": round(score, 3),
            "interpretation": interpretation,
            "departments": grants,
            "analysis": explanation,
        }

        # ---------------------------------------------------------
        # 4️⃣ Audit log (important for pay transparency compliance)
        # ---------------------------------------------------------
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai.equity_fairness.analyzed",
            entity_type="org",
            entity_id=None,
            payload=result
        ))

        await db.commit()

        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

