from __future__ import annotations
from typing import Dict
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json
from datetime import datetime, timezone

from app.integrations.store import get_connection, decrypt_token
from app.integrations.greenhouse import list_jobs as gh_jobs, list_candidates as gh_candidates
from app.integrations.lever import list_postings as lever_postings, list_opportunities as lever_opps

async def _get_cursor(db: AsyncSession, org_id: UUID, provider: str) -> dict:
    row = (await db.execute(text("""
        select cursor from public.integration_cursors where org_id=:org_id and provider=:provider
    """), {"org_id": str(org_id), "provider": provider})).first()
    return row[0] if row else {}

async def _set_cursor(db: AsyncSession, org_id: UUID, provider: str, cursor: dict):
    await db.execute(text("""
        insert into public.integration_cursors(org_id, provider, cursor, updated_at)
        values (:org_id, :provider, :cursor::jsonb, now())
        on conflict (org_id, provider) do update set cursor=excluded.cursor, updated_at=now()
    """), {"org_id": str(org_id), "provider": provider, "cursor": json.dumps(cursor)})

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

async def sync_greenhouse(db: AsyncSession, org_id: UUID) -> Dict[str, int]:
    conn = await get_connection(db, str(org_id), "greenhouse")
    if not conn or not conn.get("token_ciphertext"):
        return {"jobs": 0, "candidates": 0}
    api_key = decrypt_token(conn["token_ciphertext"])
    _ = await _get_cursor(db, org_id, "greenhouse")  # bookmark for future incremental upgrades

    jobs = await gh_jobs(api_key)
    for j in jobs:
        await db.execute(text("""
            insert into public.ats_job_postings(org_id, provider, external_id, title, location, status, payload, updated_at)
            values (:org_id, 'greenhouse', :eid, :title, :location, :status, :payload::jsonb, now())
            on conflict (org_id, provider, external_id) do update
            set title=excluded.title, location=excluded.location, status=excluded.status, payload=excluded.payload, updated_at=now()
        """), {
            "org_id": str(org_id),
            "eid": str(j.get("id")),
            "title": j.get("name") or j.get("title") or "Job",
            "location": (j.get("offices") or [{}])[0].get("name") if isinstance(j.get("offices"), list) and j.get("offices") else None,
            "status": j.get("status"),
            "payload": json.dumps(j),
        })

    cands = await gh_candidates(api_key)
    for c in cands:
        await db.execute(text("""
            insert into public.ats_candidates(org_id, provider, external_id, name, email, stage, payload, updated_at)
            values (:org_id, 'greenhouse', :eid, :name, :email, :stage, :payload::jsonb, now())
            on conflict (org_id, provider, external_id) do update
            set name=excluded.name, email=excluded.email, stage=excluded.stage, payload=excluded.payload, updated_at=now()
        """), {
            "org_id": str(org_id),
            "eid": str(c.get("id")),
            "name": c.get("name"),
            "email": (c.get("email_addresses") or [{}])[0].get("value") if isinstance(c.get("email_addresses"), list) and c.get("email_addresses") else None,
            "stage": None,
            "payload": json.dumps(c),
        })

    await _set_cursor(db, org_id, "greenhouse", {"last_synced_at": _now_iso()})
    return {"jobs": len(jobs), "candidates": len(cands)}

async def sync_lever(db: AsyncSession, org_id: UUID) -> Dict[str, int]:
    conn = await get_connection(db, str(org_id), "lever")
    if not conn or not conn.get("token_ciphertext"):
        return {"jobs": 0, "candidates": 0}
    token = decrypt_token(conn["token_ciphertext"])
    cursor = await _get_cursor(db, org_id, "lever")
    opp_offset = int(cursor.get("opportunities_offset", 0))

    jobs = await lever_postings(token)
    if isinstance(jobs, dict) and "data" in jobs:
        jobs = jobs["data"]
    for j in jobs:
        await db.execute(text("""
            insert into public.ats_job_postings(org_id, provider, external_id, title, location, status, payload, updated_at)
            values (:org_id, 'lever', :eid, :title, :location, :status, :payload::jsonb, now())
            on conflict (org_id, provider, external_id) do update
            set title=excluded.title, location=excluded.location, status=excluded.status, payload=excluded.payload, updated_at=now()
        """), {
            "org_id": str(org_id),
            "eid": str(j.get("id") or j.get("postingId") or j.get("_id") or j.get("text") or "unknown"),
            "title": j.get("text") or j.get("title") or "Posting",
            "location": j.get("categories",{}).get("location") if isinstance(j.get("categories"), dict) else None,
            "status": j.get("state") or j.get("status"),
            "payload": json.dumps(j),
        })

    opps = await lever_opps(token)
    if isinstance(opps, dict) and "data" in opps:
        opps = opps["data"]
    for o in opps:
        name = None
        email = None
        if isinstance(o.get("contacts"), list) and o["contacts"]:
            c = o["contacts"][0]
            name = c.get("name")
            if isinstance(c.get("emails"), list) and c["emails"]:
                email = c["emails"][0]
        await db.execute(text("""
            insert into public.ats_candidates(org_id, provider, external_id, name, email, stage, payload, updated_at)
            values (:org_id, 'lever', :eid, :name, :email, :stage, :payload::jsonb, now())
            on conflict (org_id, provider, external_id) do update
            set name=excluded.name, email=excluded.email, stage=excluded.stage, payload=excluded.payload, updated_at=now()
        """), {
            "org_id": str(org_id),
            "eid": str(o.get("id") or o.get("_id") or "unknown"),
            "name": name,
            "email": email,
            "stage": o.get("stage"),
            "payload": json.dumps(o),
        })

    await _set_cursor(db, org_id, "lever", {"last_synced_at": _now_iso(), "opportunities_offset": opp_offset})
    return {"jobs": len(jobs), "candidates": len(opps)}
