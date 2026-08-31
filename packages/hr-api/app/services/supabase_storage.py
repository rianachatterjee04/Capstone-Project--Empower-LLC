from __future__ import annotations
from typing import Any, Dict
import httpx
from app.core.config import settings

class StorageError(Exception):
    pass

def _headers() -> Dict[str, str]:
    key = settings.supabase_service_role_key
    if not key:
        raise StorageError("SUPABASE_SERVICE_ROLE_KEY missing")
    return {"Authorization": f"Bearer {key}", "apikey": key, "Content-Type": "application/json"}

async def create_signed_upload_url(bucket: str, path: str, expires_in: int = 600) -> Dict[str, Any]:
    # Supabase Storage endpoint is version-dependent; best-effort implementation.
    url = str(settings.supabase_url).rstrip("/") + f"/storage/v1/object/upload/sign/{bucket}/{path}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(url, headers=_headers(), json={"expiresIn": expires_in})
        if r.status_code >= 400:
            raise StorageError(f"sign upload failed: {r.status_code} {r.text}")
        return r.json()
