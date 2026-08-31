"""
Control-plane data access.

Reads/writes the `cp_*` tables in the PLATFORM Supabase project via the
service-role key. Every module backend already ships the `supabase` client, so
this adds no new infra — only a second (platform) connection.

Env:
  PLATFORM_SUPABASE_URL          (falls back to SUPABASE_URL)
  PLATFORM_SUPABASE_SERVICE_KEY  (falls back to SUPABASE_KEY / SUPABASE_SERVICE_KEY)
"""
from __future__ import annotations
import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

from supabase import create_client, Client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(*names: str) -> Optional[str]:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    return None


@lru_cache(maxsize=1)
def control_plane() -> Client:
    url = _env("PLATFORM_SUPABASE_URL", "SUPABASE_URL")
    key = _env("PLATFORM_SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_KEY", "SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "fintra_entitlements: missing PLATFORM_SUPABASE_URL / "
            "PLATFORM_SUPABASE_SERVICE_KEY (or SUPABASE_URL / SUPABASE_KEY)."
        )
    client = create_client(url, key)
    # Mirror accounting's HTTP/1.1 fix — postgrest-py's hardcoded http2 pool dies
    # under bursts. Harmless if the swap fails.
    try:
        from postgrest.utils import SyncClient
        old = client.postgrest.session
        client.postgrest.session = SyncClient(
            base_url=str(old.base_url),
            headers=dict(old.headers),
            timeout=old.timeout,
            follow_redirects=True,
            http2=False,
        )
    except Exception:
        pass
    return client


# -- thin typed accessors over cp_* tables ---------------------------------

def get_subscription(org_id: str, module_key: str) -> Optional[dict[str, Any]]:
    r = (
        control_plane().table("cp_subscriptions").select("*")
        .eq("org_id", org_id).eq("module_key", module_key).limit(1).execute()
    )
    return (r.data or [None])[0]


def get_seat(org_id: str, module_key: str, user_id: str) -> Optional[dict[str, Any]]:
    r = (
        control_plane().table("cp_seat_assignments").select("user_id")
        .eq("org_id", org_id).eq("module_key", module_key)
        .eq("user_id", user_id).limit(1).execute()
    )
    return (r.data or [None])[0]


def count_seats(org_id: str, module_key: str) -> int:
    r = (
        control_plane().table("cp_seat_assignments").select("user_id", count="exact")
        .eq("org_id", org_id).eq("module_key", module_key).execute()
    )
    return r.count or 0


def get_quota(org_id: str, app_key: str) -> Optional[dict[str, Any]]:
    r = (
        control_plane().table("cp_ai_quota").select("*")
        .eq("org_id", org_id).eq("app_key", app_key).limit(1).execute()
    )
    return (r.data or [None])[0]


def upsert_quota(row: dict[str, Any]) -> None:
    control_plane().table("cp_ai_quota").upsert(row, on_conflict="org_id,app_key").execute()


def insert_ledger(row: dict[str, Any]) -> None:
    control_plane().table("cp_ai_usage_ledger").insert(row).execute()


# ===========================================================================
# v2 ENTERPRISE accessors — org caps, per-seat AI, API keys, idempotency,
# security events.
# ===========================================================================

def get_org(org_id: str) -> Optional[dict[str, Any]]:
    r = control_plane().table("cp_organizations").select("*").eq("id", org_id).limit(1).execute()
    return (r.data or [None])[0]


def count_members(org_id: str) -> int:
    r = (
        control_plane().table("cp_org_members").select("user_id", count="exact")
        .eq("org_id", org_id).execute()
    )
    return r.count or 0


def get_seat_full(org_id: str, module_key: str, user_id: str) -> Optional[dict[str, Any]]:
    r = (
        control_plane().table("cp_seat_assignments").select("*")
        .eq("org_id", org_id).eq("module_key", module_key)
        .eq("user_id", user_id).limit(1).execute()
    )
    return (r.data or [None])[0]


def update_seat_ai(org_id: str, module_key: str, user_id: str, *,
                   ai_token_limit: Optional[int] = None,
                   ai_tokens_used: Optional[int] = None,
                   ai_period_start: Optional[str] = None) -> None:
    patch: dict[str, Any] = {}
    if ai_token_limit is not None:
        patch["ai_token_limit"] = int(ai_token_limit)
    if ai_tokens_used is not None:
        patch["ai_tokens_used"] = int(ai_tokens_used)
    if ai_period_start is not None:
        patch["ai_period_start"] = ai_period_start
    if not patch:
        return
    (control_plane().table("cp_seat_assignments").update(patch)
     .eq("org_id", org_id).eq("module_key", module_key).eq("user_id", user_id).execute())


# -- security events (append-only auth/anomaly trail) -----------------------
def log_security_event(event: str, *, org_id: Optional[str] = None, user_id: Optional[str] = None,
                       email: Optional[str] = None, ip: Optional[str] = None,
                       user_agent: Optional[str] = None, detail: Optional[dict] = None) -> None:
    try:
        control_plane().table("cp_security_events").insert({
            "event": event, "org_id": org_id, "user_id": user_id, "email": email,
            "ip": ip, "user_agent": user_agent, "detail": detail or {},
        }).execute()
    except Exception:
        pass


# -- idempotency ------------------------------------------------------------
def get_idempotent(key: str) -> Optional[dict[str, Any]]:
    r = control_plane().table("cp_idempotency_keys").select("*").eq("key", key).limit(1).execute()
    return (r.data or [None])[0]


def save_idempotent(key: str, org_id: Optional[str], endpoint: str, response: Any) -> None:
    try:
        control_plane().table("cp_idempotency_keys").insert({
            "key": key, "org_id": org_id, "endpoint": endpoint, "response": response,
        }).execute()
    except Exception:
        pass


# -- API keys (only the sha256 hash is stored) ------------------------------
def find_api_key_by_prefix(prefix: str) -> Optional[dict[str, Any]]:
    # Exclude revoked keys, and exclude keys whose expiry is already past.
    # (verify_api_key re-checks expires_at as a defense-in-depth backstop.)
    now = _now_iso()
    r = (control_plane().table("cp_api_keys").select("*")
         .eq("prefix", prefix).is_("revoked_at", "null")
         .or_(f"expires_at.is.null,expires_at.gt.{now}")
         .limit(1).execute())
    return (r.data or [None])[0]


def insert_api_key(row: dict[str, Any]) -> dict[str, Any]:
    return control_plane().table("cp_api_keys").insert(row).execute().data[0]


def touch_api_key(key_id: str) -> None:
    try:
        (control_plane().table("cp_api_keys").update({"last_used_at": _now_iso()})
         .eq("id", key_id).execute())
    except Exception:
        pass


def list_api_keys(org_id: str) -> list[dict[str, Any]]:
    return (control_plane().table("cp_api_keys")
            .select("id,name,prefix,scopes,created_at,last_used_at,expires_at,revoked_at")
            .eq("org_id", org_id).order("created_at", desc=True).execute().data or [])


def revoke_api_key(org_id: str, key_id: str) -> None:
    (control_plane().table("cp_api_keys").update({"revoked_at": _now_iso()})
     .eq("org_id", org_id).eq("id", key_id).execute())
