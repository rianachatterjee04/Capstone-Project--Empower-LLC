from __future__ import annotations
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import decode_supabase_jwt, get_actor_from_claims, AuthError
from app.db.session import get_db

class Actor:
    def __init__(self, user_id: str, org_id: str | None, role: str, claims: dict):
        self.user_id = user_id
        self.org_id = org_id
        self.role = role
        self.claims = claims

def require_auth(authorization: str = Header(...)) -> Actor:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_supabase_jwt(token)
        actor = get_actor_from_claims(claims)
        return Actor(actor["user_id"], actor.get("org_id"), actor["role"], actor["claims"])
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

async def require_org(actor: Actor = Depends(require_auth)) -> Actor:
    if not actor.org_id:
        raise HTTPException(status_code=400, detail="Missing org_id in JWT app_metadata")
    return actor

async def db_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    return db
