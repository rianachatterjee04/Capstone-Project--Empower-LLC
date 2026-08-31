from __future__ import annotations
import logging
from typing import Optional, Tuple
import json
import uuid

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

                        # view_events has `path` and a jsonb `meta`; this used
                        # to insert `route` and `user_agent`, which do not
                        # exist. Every write raised UndefinedColumn, the except
                        # below swallowed it, and the table held zero rows --
                        # so "we record who viewed what" was not true of a
                        # single request ever served. Nothing surfaced it
                        # because dev tokens return early, above, and only a
                        # real browser session reaches this code.
                        async with AsyncSessionLocal() as db:
                            await db.execute(text("""
                                INSERT INTO public.view_events(
                                    id, org_id, actor_user_id, actor_role, path,
                                    entity_type, entity_id, meta
                                )
                                VALUES (:id, :org_id, :actor_user_id, :actor_role, :path,
                                        :entity_type, :entity_id, cast(:meta as jsonb))
                            """), {
                                # id is NOT NULL and had no server default: the
                                # model declares a Python-side default, which a
                                # raw INSERT never invokes. Correcting the column
                                # names alone still failed on this.
                                "id": str(uuid.uuid4()),
                                "org_id": org_id,
                                "actor_user_id": actor.get("user_id"),
                                "actor_role": actor.get("role"),
                                "path": path,
                                "entity_type": entity_type,
                                "entity_id": entity_id,
                                "meta": json.dumps({"user_agent": ua}),
                            })
                            await db.commit()
                except Exception as e:
                    # Deliberately does not fail the request -- an audit write
                    # must not take the product down. But say plainly that the
                    # record is MISSING, not that "logging failed": the whole
                    # point of this table is that someone can later ask who
                    # looked at a record, and a gap in it is a gap in the answer.
                    logger.error(
                        "VIEW AUDIT NOT RECORDED for %s (org=%s): %s -- this "
                        "access is absent from view_events", path, org_id, e,
                    )