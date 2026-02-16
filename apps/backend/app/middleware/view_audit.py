from __future__ import annotations
from typing import Callable, Optional, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request
from sqlalchemy import text
from app.db.session import AsyncSessionLocal
from app.core.security import decode_supabase_jwt, get_actor_from_claims

def _infer(path: str) -> Tuple[Optional[str], Optional[str]]:
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "api":
        resource = parts[1]
        candidate = parts[2]
        if len(candidate) >= 32:
            return resource, candidate
    return None, None

class ViewAuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        response: Response = await call_next(request)
        try:
            if request.method != "GET":
                return response
            if not request.url.path.startswith("/api/"):
                return response
            auth = request.headers.get("authorization", "")
            if not auth.startswith("Bearer "):
                return response
            token = auth.split(" ", 1)[1].strip()
            claims = decode_supabase_jwt(token)
            actor = get_actor_from_claims(claims)
            org_id = actor.get("org_id")
            if not org_id:
                return response

            entity_type, entity_id = _infer(request.url.path)
            ip = request.client.host if request.client else None
            ua = request.headers.get("user-agent")

            async with AsyncSessionLocal() as db:
                await db.execute(text("""
                    insert into public.view_events(org_id, actor_user_id, actor_role, route, entity_type, entity_id, ip, user_agent)
                    values (:org_id, :actor_user_id, :actor_role, :route, :entity_type, :entity_id, :ip, :ua)
                """), {
                    "org_id": org_id,
                    "actor_user_id": actor.get("user_id"),
                    "actor_role": actor.get("role"),
                    "route": request.url.path,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "ip": ip,
                    "ua": ua,
                })
                await db.commit()
        except Exception:
            pass
        return response
