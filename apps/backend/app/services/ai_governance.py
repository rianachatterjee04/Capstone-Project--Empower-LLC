
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

async def check_ai_authority(db: AsyncSession, org_id, decision_type, actor_role):
    row = (await db.execute(text("""
      select allowed, requires_human, allowed_roles
      from ai_authority_scopes
      where org_id=:o and decision_type=:d
    """), {"o": org_id, "d": decision_type})).first()

    if not row:
        return {"allowed": False, "requires_human": True}

    allowed, requires_human, roles = row
    return {
        "allowed": allowed and actor_role in roles,
        "requires_human": requires_human
    }
