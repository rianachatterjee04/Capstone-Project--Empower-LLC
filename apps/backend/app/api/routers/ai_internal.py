"""
Internal endpoints for AI Orchestrator -> Backend.

Protected via `X-Internal-AI-Secret`.
These endpoints are called by Temporal / cron workers, NEVER by clients.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timedelta
import uuid

from app.api.deps import require_internal_ai
from app.db.deps import get_db
from app.db.models import (
    CaseReport,
    Candidate,
    OnboardingPacket,
    Document,
    PerformanceReview,
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

    q = select(CaseReport).where(CaseReport.status.in_(["open","investigating","escalated"]))
    res = await db.execute(q)
    cases = list(res.scalars().all())

    escalated = 0

    for rpt in cases:
        if should_escalate(rpt.severity, rpt.last_action_at):
            rpt.status = "escalated"
            rpt.escalation_level += 1

            await audit_log(
                db,
                rpt.org_id,
                None,
                "case.auto_escalate",
                "case_report",
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
# DOCUMENT EXPIRATION WATCHER
# ---------------------------------------------------------
@router.post("/tick/document-expiration")
async def expire_documents(_: None = Depends(require_internal_ai), db: AsyncSession = Depends(get_db)):

    today = datetime.utcnow().date()

    q = select(Document).where(
        Document.expires_at != None,
        Document.expires_at < today,
        Document.status == "verified"
    )

    res = await db.execute(q)
    docs = list(res.scalars().all())

    expired = 0

    for d in docs:
        d.status = "expired"
        await audit_log(db, d.org_id, None, "document.expired", "document", str(d.id), {})
        expired += 1

    await db.commit()
    return {"expired": expired}


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


# ---------------------------------------------------------
# PERFORMANCE REVIEW NUDGE
# ---------------------------------------------------------
@router.post("/tick/performance-nudges")
async def performance_nudges(_: None = Depends(require_internal_ai), db: AsyncSession = Depends(get_db)):

    cutoff = datetime.utcnow() - timedelta(days=5)

    q = select(PerformanceReview).where(
        PerformanceReview.status == "draft",
        PerformanceReview.updated_at < cutoff
    )

    res = await db.execute(q)
    reviews = list(res.scalars().all())

    nudged = 0

    for r in reviews:
        await enqueue_notification(
            db,
            r.org_id,
            r.employee_id,
            "performance_review_reminder",
            {"review_id": str(r.id)}
        )
        nudged += 1

    return {"nudges_sent": nudged}

