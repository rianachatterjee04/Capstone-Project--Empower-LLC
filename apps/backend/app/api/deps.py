from __future__ import annotations
import os
import uuid
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db

class Actor:
    def __init__(self, user_id: str, org_id: str | None, role: str, claims: dict):
        self.user_id = user_id
        self.org_id = org_id
        self.role = role
        self.claims = claims

def _decode_supabase_jwt(token: str) -> dict:
    import jwt as pyjwt
    import json, base64, httpx
    try:
        header_part = token.split(".")[0]
        padding = 4 - len(header_part) % 4
        header = json.loads(base64.urlsafe_b64decode(header_part + "=" * padding))
        alg = header.get("alg", "HS256")
        kid = header.get("kid", "")
    except Exception:
        alg = "HS256"
        kid = ""

    if alg == "ES256":
        supabase_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        if not supabase_url:
            raise HTTPException(status_code=401, detail="SUPABASE_URL not configured")
        try:
            jwks_url = f"{supabase_url}/auth/v1/.well-known/jwks.json"
            resp = httpx.get(jwks_url, timeout=5)
            jwks = resp.json()
            keys = jwks.get("keys", [])
            key_data = next((k for k in keys if k.get("kid", "").lower() == kid.lower()), None)
            if not key_data:
                raise HTTPException(status_code=401, detail=f"JWT key not found for kid: {kid}")
            public_key = pyjwt.algorithms.ECAlgorithm.from_jwk(key_data)
            return pyjwt.decode(token, public_key, algorithms=["ES256"], options={"verify_aud": False})
        except pyjwt.PyJWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=401, detail=f"Token verification failed: {e}")
    else:
        secret = os.getenv("SUPABASE_JWT_SECRET", "")
        if not secret:
            raise HTTPException(status_code=401, detail="SUPABASE_JWT_SECRET not configured")
        try:
            return pyjwt.decode(token, secret, algorithms=["HS256"], options={"verify_aud": False})
        except pyjwt.PyJWTError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def require_auth(authorization: str = Header(...)) -> Actor:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token.startswith("dev:"):
        parts = token.split(":")
        org_id = parts[1] if len(parts) > 1 and parts[1] else "11111111-1111-1111-1111-111111111111"
        role = parts[2] if len(parts) > 2 and parts[2] else "owner"
        email = parts[3] if len(parts) > 3 and parts[3] else "dev@local.test"
        user_id = parts[4] if len(parts) > 4 and parts[4] else "22222222-2222-2222-2222-222222222222"
        try:
            uuid.UUID(org_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Dev token org_id must be a UUID")
        try:
            uuid.UUID(user_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Dev token user_id must be a UUID")
        return Actor(user_id=user_id, org_id=org_id, role=role, claims={"email": email, "dev": True})
    claims = _decode_supabase_jwt(token)
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing sub claim")
    app_meta = claims.get("app_metadata") or {}
    user_meta = claims.get("user_metadata") or {}
    org_id = app_meta.get("org_id") or user_meta.get("org_id") or None
    role = app_meta.get("role") or user_meta.get("role") or "employee"
    email = claims.get("email") or ""
    return Actor(user_id=user_id, org_id=org_id, role=role, claims={**claims, "email": email})

async def require_org(
    actor: Actor = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    if actor.org_id:
        return actor
    if not actor.claims.get("dev") and actor.claims.get("email"):
        email = actor.claims["email"]
        row = (await db.execute(
            text("SELECT org_id, id FROM public.employees WHERE email = :email LIMIT 1"),
            {"email": email},
        )).first()
        if row:
            actor.org_id = str(row[0])
            await db.execute(
                text("UPDATE public.employees SET user_id = :uid WHERE id = :eid AND user_id IS NULL"),
                {"uid": actor.user_id, "eid": str(row[1])},
            )
            await db.commit()
            return actor
    raise HTTPException(status_code=400, detail="Missing org_id — ask HR to add you to the org.")

async def db_session(db: AsyncSession = Depends(get_db)) -> AsyncSession:
    return db

def require_internal_ai(x_internal_ai_secret: str = Header(...)) -> None:
    expected = os.getenv("INTERNAL_AI_SHARED_SECRET", "dev-internal-secret")
    if x_internal_ai_secret != expected:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal secret")
