from __future__ import annotations
from typing import Any, Dict, List, Optional
import httpx

HARVEST_BASE = "https://harvest.greenhouse.io/v1"

async def harvest_get(api_key: str, path: str, params: Optional[dict]=None) -> Any:
    auth = (api_key, "")  # HTTP Basic with api_key as username
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{HARVEST_BASE}{path}", auth=auth, params=params or {})
        resp.raise_for_status()
        return resp.json()

async def list_jobs(api_key: str) -> List[Dict[str, Any]]:
    return await harvest_get(api_key, "/jobs")

async def list_candidates(api_key: str) -> List[Dict[str, Any]]:
    return await harvest_get(api_key, "/candidates")
