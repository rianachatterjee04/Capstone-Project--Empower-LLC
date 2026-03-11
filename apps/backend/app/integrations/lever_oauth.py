from __future__ import annotations

from typing import Dict, Any
from urllib.parse import urlencode

import httpx

from app.core.config import settings

TOKEN_URL = "https://auth.lever.co/oauth/token"
AUTH_URL = "https://auth.lever.co/oauth/authorize"


def build_auth_url(state: str) -> str:
    if not settings.lever_client_id:
        raise RuntimeError("LEVER_CLIENT_ID missing")
    if not settings.lever_redirect_uri:
        raise RuntimeError("LEVER_REDIRECT_URI missing")

    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.lever_client_id,
            "redirect_uri": settings.lever_redirect_uri,
            "state": state,
        }
    )
    return f"{AUTH_URL}?{query}"


async def exchange_code(code: str) -> Dict[str, Any]:
    if not settings.lever_client_id or not settings.lever_client_secret:
        raise RuntimeError("LEVER_CLIENT_ID/LEVER_CLIENT_SECRET missing")
    if not settings.lever_redirect_uri:
        raise RuntimeError("LEVER_REDIRECT_URI missing")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.lever_redirect_uri,
        "client_id": settings.lever_client_id,
        "client_secret": settings.lever_client_secret,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(TOKEN_URL, data=data)
        resp.raise_for_status()
        return resp.json()
