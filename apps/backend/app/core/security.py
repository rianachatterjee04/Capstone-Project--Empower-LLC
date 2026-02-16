from __future__ import annotations
from functools import lru_cache
from typing import Any, Dict
import httpx
from jose import jwt, JWTError
from app.core.config import settings

class AuthError(Exception):
    pass

@lru_cache(maxsize=1)
def _jwks() -> Dict[str, Any]:
    if not settings.supabase_jwks_url:
        return {}
    with httpx.Client(timeout=10.0) as client:
        r = client.get(str(settings.supabase_jwks_url))
        r.raise_for_status()
        return r.json()

def decode_supabase_jwt(token: str) -> Dict[str, Any]:
    try:
        if settings.supabase_jwks_url:
            jwks = _jwks()
            headers = jwt.get_unverified_header(token)
            kid = headers.get("kid")
            keys = jwks.get("keys", [])
            key = next((k for k in keys if k.get("kid") == kid), None)
            if not key:
                raise AuthError("JWT key not found (kid mismatch)")
            return jwt.decode(token, key, algorithms=["RS256"], options={"verify_aud": False})
        if settings.supabase_jwt_secret:
            return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], options={"verify_aud": False})
        raise AuthError("Auth not configured: set SUPABASE_JWKS_URL or SUPABASE_JWT_SECRET")
    except (JWTError, StopIteration) as e:
        raise AuthError("Invalid token") from e

def get_actor_from_claims(claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = claims.get("sub")
    if not sub:
        raise AuthError("Missing sub claim")
    app_md = claims.get("app_metadata") or {}
    user_md = claims.get("user_metadata") or {}
    org_id = app_md.get("org_id") or user_md.get("org_id")
    role = app_md.get("role") or user_md.get("role") or "employee"
    return {"user_id": sub, "org_id": org_id, "role": role, "claims": claims}
