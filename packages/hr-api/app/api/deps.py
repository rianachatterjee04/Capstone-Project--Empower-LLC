from __future__ import annotations
import logging
import os
import hmac
import uuid
from fastapi import Header, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.session import get_db


def _is_prod() -> bool:
    """Secure default: treat the app as PRODUCTION unless an env value says otherwise.

    Local dev sets ENV=development (or dev/test/local), which makes this False so the
    dev-auth bypass and dev secret fallbacks keep working locally. An unset env is
    treated as production.
    """
    try:
        from app.core.config import settings
        v = (settings.env or "production").lower()
    except Exception:
        v = (os.getenv("APP_ENV") or os.getenv("ENV") or "production").lower()
    return v not in ("development", "dev", "test", "local")


def _dev_auth_enabled() -> bool:
    """The dev: bearer bypass is reachable ONLY outside production.

    SECURITY / prod-guard: this bypass mints a fully-authorized Actor from an
    unsigned `dev:` token whose org_id and role are supplied by the caller, so in
    production it is equivalent to no authentication at all. It is therefore hard
    off whenever _is_prod() is true, and no environment variable can re-enable it.

    Outside production it stays enabled as before, so local dev is unaffected.
    Setting FINTRA_ALLOW_DEMO_TOKEN=1 in production is a misconfiguration: we
    refuse it and log loudly rather than honoring it, because a single env var
    must not be able to defeat authentication.
    """
    if _is_prod():
        if os.getenv("FINTRA_ALLOW_DEMO_TOKEN") == "1":
            logging.error(
                "SECURITY: FINTRA_ALLOW_DEMO_TOKEN=1 is set in a PRODUCTION "
                "environment. REFUSING to enable the unsigned dev: auth bypass. "
                "Unset this variable."
            )
        return False
    return True


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

    # SECURITY: Pin accepted algorithms instead of trusting the token's own header.
    # The hgbx Supabase project issues ES256 (asymmetric/JWKS) tokens, which is the
    # only scheme accepted in production. HS256 (symmetric shared secret) is permitted
    # only in non-production so the local dev stack keeps working. This prevents the
    # classic alg-confusion attack where an attacker who learns the HS256 secret flips
    # alg to forge tokens.
    if alg not in ("ES256", "HS256"):
        raise HTTPException(status_code=401, detail=f"Unsupported token algorithm: {alg}")
    if alg == "HS256" and _is_prod():
        raise HTTPException(status_code=401, detail="HS256 tokens are not accepted in production")

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
    if _dev_auth_enabled() and token.startswith("dev:"):
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
    # SECURITY: org_id and role are authorization-relevant claims. In Supabase,
    # user_metadata is writable by the end user via supabase.auth.updateUser, whereas
    # app_metadata is server-only. Trust ONLY app_metadata; never fall back to
    # user_metadata (that would allow self-granted owner role / tenant switching).
    org_id = app_meta.get("org_id") or None
    role = app_meta.get("role") or "employee"
    email = claims.get("email") or ""
    return Actor(user_id=user_id, org_id=org_id, role=role, claims={**claims, "email": email})

async def require_org(
    actor: Actor = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> Actor:
    if actor.org_id:
        return actor
    # SECURITY: only auto-bind a user to a pre-created employee row when the JWT's
    # email is cryptographically verified. An unverified email is attacker-influenceable
    # and could let someone silently claim another employee's identity/org.
    email_verified = bool(
        actor.claims.get("email_verified")
        or (actor.claims.get("user_metadata") or {}).get("email_verified")
    )
    if not actor.claims.get("dev") and actor.claims.get("email") and email_verified:
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
    expected = os.getenv("INTERNAL_AI_SHARED_SECRET")
    # Fail closed: in production a missing/unset secret must NOT fall back to a
    # publicly-known default. In non-prod keep the dev fallback so the local stack works.
    if not expected:
        if _is_prod():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Internal AI auth not configured",
            )
        expected = "dev-internal-secret"
    # Constant-time comparison to avoid timing side channels.
    if not hmac.compare_digest(x_internal_ai_secret, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid internal secret")


def required_field(payload: dict, key: str, *, what: str | None = None):
    """Read a field a handler cannot work without, or refuse with 422.

    A number of write endpoints are declared as `payload: dict`. FastAPI cannot
    validate an untyped dict, so nothing rejects an incomplete body and the
    handler's own `payload["stakeholder_id"]` raised KeyError -- which surfaced
    to the caller as:

        500  {"message": "Internal Server Error", "detail": "'stakeholder_id'"}

    A sweep of the 143 parameterless write endpoints found nine of these, all on
    the equity surface the cap-table integrators work against. "Internal Server
    Error" tells an integrator our software is broken; it is the wrong claim and
    the wrong status. A missing field is the caller's to fix, and 422 is how you
    say so.

    This does not tighten what the endpoints accept -- it only replaces a crash
    with the refusal that should always have been there.
    """
    if not isinstance(payload, dict):
        raise HTTPException(422, detail=f"expected a JSON object, got {type(payload).__name__}")
    if key not in payload or payload[key] is None:
        raise HTTPException(422, detail=f"'{key}' is required{f' ({what})' if what else ''}")
    return payload[key]
