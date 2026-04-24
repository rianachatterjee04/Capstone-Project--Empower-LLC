from __future__ import annotations
import logging
from typing import Optional, Tuple
from sqlalchemy import text
from starlette.types import ASGIApp, Scope, Receive, Send
from app.db.session import AsyncSessionLocal
from app.core.security import decode_supabase_jwt, get_actor_from_claims

logger = logging.getLogger("audit")

def _infer(path: str) -> Tuple[Optional[str], Optional[str]]:
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3 and parts[0] == "api":
        return parts[1], parts[2]
    return None, None

class ViewAuditMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        # Only process HTTP requests for the audit
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Execute the request first to ensure the UI gets its data ASAP
        await self.app(scope, receive, send)

        # Fire-and-forget audit — never blocks or re-raises into ASGI
        import asyncio
        asyncio.ensure_future(self._audit(scope))

    async def _audit(self, scope: Scope):
        path = scope.get("path", "")
        method = scope.get("method", "")

        if method == "GET" and path.startswith("/api/"):
            headers = dict(scope.get("headers", []))
            auth_header = headers.get(b"authorization", b"").decode("utf-8")

            if auth_header.startswith("Bearer "):
                try:
                    token = auth_header.split(" ", 1)[1].strip()

                    # Skip audit for dev tokens (not real JWTs)
                    if token.startswith("dev:"):
                        return

                    claims = decode_supabase_jwt(token)
                    actor = get_actor_from_claims(claims)
                    org_id = actor.get("org_id")

                    if org_id:
                        entity_type, entity_id = _infer(path)
                        ua = headers.get(b"user-agent", b"").decode("utf-8")

                        async with AsyncSessionLocal() as db:
                            await db.execute(text("""
                                INSERT INTO public.view_events(
                                    org_id, actor_user_id, actor_role, route,
                                    entity_type, entity_id, user_agent
                                )
                                VALUES (:org_id, :actor_user_id, :actor_role, :route, :entity_type, :entity_id, :ua)
                            """), {
                                "org_id": org_id,
                                "actor_user_id": actor.get("user_id"),
                                "actor_role": actor.get("role"),
                                "route": path,
                                "entity_type": entity_type,
                                "entity_id": entity_id,
                                "ua": ua,
                            })
                            await db.commit()
                except Exception as e:
                    logger.error(f"Audit Log Failed: {e}")