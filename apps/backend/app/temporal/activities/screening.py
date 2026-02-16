from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.services.ats_screening import score_candidate

async def enqueue_screening(db: AsyncSession, org_id: UUID, provider: str) -> dict:
    rows = (await db.execute(text("""
        select external_id from public.ats_candidates
        where org_id=:org_id and provider=:provider
        order by updated_at desc
        limit 50
    """), {"org_id": str(org_id), "provider": provider})).fetchall()

    scored = 0
    for (cid,) in rows:
        await score_candidate(db, org_id, provider, str(cid), job_external_id=None)
        scored += 1
    return {"queued": len(rows), "scored": scored}
