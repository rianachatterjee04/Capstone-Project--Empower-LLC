from __future__ import annotations
from typing import Any, Dict, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json, hashlib

async def append_ledger(db: AsyncSession, org_id: UUID, payload: Dict[str, Any]) -> str:
    prev = (await db.execute(text("select hash from public.audit_ledger where org_id=:org_id order by created_at desc limit 1"),
                            {"org_id": str(org_id)})).first()
    prev_hash = prev[0] if prev else None
    blob = json.dumps({"prev": prev_hash, "payload": payload}, sort_keys=True).encode("utf-8")
    h = hashlib.sha256(blob).hexdigest()
    res = await db.execute(text("""
        insert into public.audit_ledger(org_id, prev_hash, payload, hash)
        values (:org_id, :prev_hash, cast(:payload as jsonb), :hash)
        returning id
    """), {"org_id": str(org_id), "prev_hash": prev_hash, "payload": json.dumps(payload), "hash": h})
    return str(res.first()[0])
