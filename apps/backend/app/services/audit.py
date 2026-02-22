from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AuditEvent
from datetime import datetime
import uuid


async def audit_log(
    session: AsyncSession,
    org_id,
    actor_user_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str,
    meta: dict | None = None,
):
    evt = AuditEvent(
        id=uuid.uuid4(),
        org_id=org_id,
        actor_user_id=actor_user_id,
        actor_role=None,
        event_type=action,
        entity_type=entity_type,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        payload=meta or {},
    )
    session.add(evt)