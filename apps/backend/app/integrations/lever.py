from __future__ import annotations
from typing import Any, Dict, Optional, List
import httpx

API_BASE = "https://api.lever.co/v1"

async def api_get(access_token: str, path: str, params: Optional[dict]=None) -> Any:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{API_BASE}{path}", headers=headers, params=params or {})
        resp.raise_for_status()
        return resp.json()

async def list_postings(access_token: str) -> List[Dict[str, Any]]:
    # Lever postings (public) vs opportunities (private). Use opportunities as "candidates".
    return await api_get(access_token, "/postings")

async def list_opportunities(access_token: str) -> List[Dict[str, Any]]:
    return await api_get(access_token, "/opportunities")
