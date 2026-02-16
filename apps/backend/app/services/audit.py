from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import AuditLog
from datetime import datetime
import uuid

async def audit_log(session: AsyncSession, org_id, actor_user_id: str | None, action: str, entity_type: str, entity_id: str, meta: dict | None = None):
    evt = AuditLog(
        id=uuid.uuid4(),
        org_id=org_id,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        meta=meta or {},
        created_at=datetime.utcnow(),
    )
    session.add(evt)
