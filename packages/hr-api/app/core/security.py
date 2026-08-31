from __future__ import annotations
from functools import lru_cache
from typing import Any, Dict
import httpx
import jwt as pyjwt
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
        header = pyjwt.get_unverified_header(token)
        kid = header.get("kid", "")
        alg = header.get("alg", "HS256")

        if alg == "ES256" and settings.supabase_jwks_url:
            jwks = _jwks()
            keys = jwks.get("keys", [])
            key_data = next((k for k in keys if k.get("kid", "").lower() == kid.lower()), None)
            if key_data:
                public_key = pyjwt.algorithms.ECAlgorithm.from_jwk(key_data)
                return pyjwt.decode(token, public_key, algorithms=["ES256"], options={"verify_aud": False})

        # Fallback to HS256 secret
        if settings.supabase_jwt_secret:
            return pyjwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], options={"verify_aud": False})

        raise AuthError("Auth not configured")
    except pyjwt.PyJWTError as e:
        raise AuthError(f"Invalid token: {e}") from e

def get_actor_from_claims(claims: Dict[str, Any]) -> Dict[str, Any]:
    sub = claims.get("sub")
    if not sub:
        raise AuthError("Missing sub claim")
    app_md = claims.get("app_metadata") or {}
    # SECURITY: org_id and role must come ONLY from app_metadata (server-controlled).
    # user_metadata is self-editable by the end user via supabase.auth.updateUser, so
    # trusting it for authorization would allow self-granted owner role / tenant switching.
    org_id = app_md.get("org_id")
    role = app_md.get("role") or "employee"
    return {"user_id": sub, "org_id": org_id, "role": role, "claims": claims}