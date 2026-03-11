"""
Internal endpoints for AI Orchestrator -> Backend.

Protected via `X-Internal-AI-Secret`.
These endpoints are called by Temporal / cron workers, NEVER by clients.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from app.core.json_utils import json_safe
import uuid

from app.api.deps import require_internal_ai
from app.db.deps import get_db
from app.db.models import (
    Case,
    Candidate,
    OnboardingPacket,
)
from app.services.escalation import should_escalate
from app.services.audit import audit_log
from app.services.ai import rescore_candidate_ai
from app.services.notifications import enqueue_notification

router = APIRouter(prefix="/internal/ai", tags=["internal-ai"])


# ---------------------------------------------------------
# CASE ESCALATION ENGINE
# ---------------------------------------------------------
@router.post("/tick/escalations")
async def tick_escalations(_: None = Depends(require_internal_ai), db: AsyncSession = Depends(get_db)):

    q = select(Case).where(Case.status.in_(["open", "investigating", "escalated"]))
    res = await db.execute(q)
    cases = list(res.scalars().all())

    escalated = 0

    for rpt in cases:
        if should_escalate(rpt.severity, rpt.created_at):
            rpt.status = "escalated"
            rpt.escalation_level += 1

            await audit_log(
                db,
                rpt.org_id,
                None,
                "case.auto_escalate",
                "case",
                str(rpt.id),
                {"level": rpt.escalation_level}
            )

            escalated += 1

    await db.commit()
    return {"scanned": len(cases), "escalated": escalated}


# ---------------------------------------------------------
# ONBOARDING REMINDERS
# ---------------------------------------------------------
@router.post("/tick/onboarding-reminders")
async def onboarding_reminders(_: None = Depends(require_internal_ai), db: AsyncSession = Depends(get_db)):

    cutoff = datetime.utcnow() - timedelta(days=2)

    q = select(OnboardingPacket).where(
        OnboardingPacket.status == "in_progress",
        OnboardingPacket.updated_at < cutoff
    )

    res = await db.execute(q)
    packets = list(res.scalars().all())

    sent = 0

    for pkt in packets:
        await enqueue_notification(
            db,
            pkt.org_id,
            pkt.employee_id,
            "onboarding_reminder",
            {"packet_id": str(pkt.id)}
        )
        sent += 1

    return {"reminders_sent": sent}


# ---------------------------------------------------------
# RE-SCORE STALE CANDIDATES
# ---------------------------------------------------------
@router.post("/tick/rescore-candidates")
async def rescore_candidates(_: None = Depends(require_internal_ai), db: AsyncSession = Depends(get_db)):

    cutoff = datetime.utcnow() - timedelta(days=14)

    q = select(Candidate).where(
        Candidate.status == "screened",
        Candidate.updated_at < cutoff
    )

    res = await db.execute(q)
    candidates = list(res.scalars().all())

    rescored = 0

    for c in candidates:
        new_score, summary = await rescore_candidate_ai(c.resume_text)
        c.ai_score = new_score
        c.ai_summary = summary

        await audit_log(db, c.org_id, None, "candidate.ai_rescored", "candidate", str(c.id), {"score": new_score})
        rescored += 1

    await db.commit()
    return {"rescored": rescored}
