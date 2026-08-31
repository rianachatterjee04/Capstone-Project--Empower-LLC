from __future__ import annotations
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def replay_events(db: AsyncSession, org_id: UUID, provider: str) -> dict:
    await db.execute(text("""
        insert into public.integration_cursors(org_id, provider, cursor, updated_at)
        values (:org_id, :provider, '{}'::jsonb, now())
        on conflict (org_id, provider) do update set cursor='{}'::jsonb, updated_at=now()
    """), {"org_id": str(org_id), "provider": provider})
    count = (await db.execute(text("select count(*) from public.integration_events where org_id=:org_id and provider=:provider"),
                             {"org_id": str(org_id), "provider": provider})).first()[0]
    return {"events": int(count), "cursor_reset": True}
