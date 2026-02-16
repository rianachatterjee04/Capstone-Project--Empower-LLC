from __future__ import annotations
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json
from app.services.crypto_secrets import encrypt_str, decrypt_str

async def get_connection(db: AsyncSession, org_id: str, provider: str) -> Optional[dict]:
    row = (await db.execute(text("""
        select id, status, token_ciphertext, refresh_ciphertext, webhook_secret, scopes, external_account_id
        from public.integration_connections
        where org_id=:org_id and provider=:provider
    """), {"org_id": org_id, "provider": provider})).mappings().first()
    return dict(row) if row else None

async def upsert_connection_tokens(db: AsyncSession, org_id: str, provider: str, access_token: str,
                                  refresh_token: Optional[str], scopes: Optional[list], external_account_id: Optional[str]=None):
    await db.execute(text("""
        insert into public.integration_connections(org_id, provider, status, token_ciphertext, refresh_ciphertext, scopes, external_account_id, updated_at)
        values (:org_id, :provider, 'connected', :token, :refresh, :scopes, :acct, now())
        on conflict (org_id, provider) do update
        set status='connected', token_ciphertext=excluded.token_ciphertext, refresh_ciphertext=excluded.refresh_ciphertext,
            scopes=excluded.scopes, external_account_id=excluded.external_account_id, updated_at=now()
    """), {
        "org_id": org_id,
        "provider": provider,
        "token": encrypt_str(access_token),
        "refresh": encrypt_str(refresh_token) if refresh_token else None,
        "scopes": scopes,
        "acct": external_account_id,
    })

async def upsert_connection_secret(db: AsyncSession, org_id: str, provider: str, webhook_secret: str, status: str="pending"):
    await db.execute(text("""
        insert into public.integration_connections(org_id, provider, status, webhook_secret, updated_at)
        values (:org_id, :provider, :status, :secret, now())
        on conflict (org_id, provider) do update
        set status=excluded.status, webhook_secret=excluded.webhook_secret, updated_at=now()
    """), {"org_id": org_id, "provider": provider, "status": status, "secret": webhook_secret})

def decrypt_token(ciphertext: str) -> str:
    return decrypt_str(ciphertext)
