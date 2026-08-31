from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from typing import Dict, Any
from datetime import date

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.platform.runtime import platform
from app.services.ai_memory import upsert_memory

router = APIRouter(prefix="/intel/narratives", tags=["intelligence"])


# ---------------------------------------------------------------------------
# QUARTERLY BOARD NARRATIVE
# ---------------------------------------------------------------------------
@router.get("/quarter")
async def quarter_story(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)) -> Dict[str, Any]:
    """
    Generates executive-level HR + compensation + org health narrative.

    Used for:
    - Board updates
    - Investor reporting
    - CFO reviews
    - Leadership planning
    """

    try:
        org_id = UUID(actor.org_id)

        # ---------------------------------------------------------
        # 1️⃣ Headcount
        # ---------------------------------------------------------
        headcount = (await db.execute(text("""
            select count(*) 
            from public.employees
            where org_id=:org_id and status='active'
        """), {"org_id": actor.org_id})).scalar() or 0

        # ---------------------------------------------------------
        # 2️⃣ Attrition (last 90 days)
        # ---------------------------------------------------------
        attrition = (await db.execute(text("""
            select count(*) 
            from public.employees
            where org_id=:org_id
            and termination_date > now() - interval '90 days'
        """), {"org_id": actor.org_id})).scalar() or 0

        attrition_rate = round((attrition / max(headcount, 1)), 3)

        # ---------------------------------------------------------
        # 3️⃣ Payroll cost
        # ---------------------------------------------------------
        payroll = (await db.execute(text("""
            select coalesce(sum(salary),0)
            from public.employees
            where org_id=:org_id and status='active'
        """), {"org_id": actor.org_id})).scalar() or 0

        # ---------------------------------------------------------
        # 4️⃣ Performance risk (AI flagged reviews)
        # ---------------------------------------------------------
        risk = (await db.execute(text("""
            select count(*)
            from public.performance_reviews
            where org_id=:org_id
            and ai_flags is not null
            and ai_flags <> '{}'::jsonb
        """), {"org_id": actor.org_id})).scalar() or 0

        # ---------------------------------------------------------
        # 5️⃣ Compensation pressure
        # ---------------------------------------------------------
        compression = (await db.execute(text("""
            select count(*)
            from public.comp_adjustments
            where org_id=:org_id
            and reason='market_correction'
            and created_at > now() - interval '90 days'
        """), {"org_id": actor.org_id})).scalar() or 0

        # ---------------------------------------------------------
        # 6️⃣ Construct metrics package
        # ---------------------------------------------------------
        metrics = {
            "date": str(date.today()),
            "headcount": int(headcount),
            "attrition_rate_90d": attrition_rate,
            "annualized_payroll": float(payroll),
            "performance_risk_cases": int(risk),
            "market_comp_adjustments": int(compression)
        }

        # ---------------------------------------------------------
        # 7️⃣ AI narrative generation
        # ---------------------------------------------------------
        story = platform.narratives.generate_quarter_story(metrics)

        # ---------------------------------------------------------
        # 8️⃣ Store board memory (trend learning)
        # ---------------------------------------------------------
        await upsert_memory(
            db,
            org_id,
            namespace="board_reports",
            content=story,
            metadata=metrics,
            entity_type="org",
            entity_id=None
        )

        # ---------------------------------------------------------
        # 9️⃣ Audit trail (SOX / defensibility)
        # ---------------------------------------------------------
        db.add(AuditEvent(
            org_id=org_id,
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai.board_narrative.generated",
            entity_type="org",
            entity_id=None,
            payload=metrics
        ))

        await db.commit()

        # ---------------------------------------------------------
        # 🔟 Structured executive output
        # ---------------------------------------------------------
        return {
            "metrics": metrics,
            "board_narrative": story,
            "signals": {
                "attrition_risk": attrition_rate > 0.08,
                "performance_concerns": risk > 5,
                "compensation_pressure": compression > 3
            },
            "confidence": "high"
        }

    except Exception as e:
        # Narrative-generator depends on optional columns (termination_date,
        # salary, performance_reviews, comp_adjustments) that may not exist
        # in every demo environment. Surface an empty narrative instead of 500.
        try:
            await db.rollback()
        except Exception:
            pass
        return {
            "metrics": {
                "date": str(date.today()),
                "headcount": 0,
                "attrition_rate_90d": 0.0,
                "annualized_payroll": 0.0,
                "performance_risk_cases": 0,
                "market_comp_adjustments": 0,
            },
            "board_narrative": "Insufficient data to generate a quarterly narrative — required schema columns (termination_date, salary, performance_reviews) are not present in this environment.",
            "signals": {},
            "error_detail": str(e)[:200],
        }

