from __future__ import annotations
import asyncio
from uuid import UUID
from app.core.celery_app import celery
from app.db.session import AsyncSessionLocal
from app.services.escalation_engine import ensure_case_escalations, escalate_overdue

@celery.task(name="escalations.tick")
def escalations_tick(org_id: str):
    async def _run():
        async with AsyncSessionLocal() as db:
            oid = UUID(org_id)
            await ensure_case_escalations(db, oid)
            await escalate_overdue(db, oid)
    asyncio.run(_run())
    return {"ok": True}
