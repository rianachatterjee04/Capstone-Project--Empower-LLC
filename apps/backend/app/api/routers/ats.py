from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.core.json_utils import json_safe
from app.db.models import AuditEvent

router = APIRouter(prefix="/ats", tags=["ats"])


def as_uuid(value) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def table_exists(db: AsyncSession, table_name: str) -> bool:
    result = await db.execute(
        text("select to_regclass(:table_name)"),
        {"table_name": f"public.{table_name}"},
    )
    return result.scalar() is not None


@router.get("/providers")
async def providers(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    connected = {"greenhouse": False, "lever": False}

    if await table_exists(db, "integrations"):
        rows = (
            await db.execute(
                text("""
                    select provider, status
                    from public.integrations
                    where org_id = :org_id
                      and provider in ('greenhouse', 'lever')
                """),
                {"org_id": org_id},
            )
        ).fetchall()

        for provider, status in rows:
            connected[str(provider)] = str(status).lower() in ("connected", "active", "ok")

    return {
        "items": [
            {"provider": "greenhouse", "connected": connected["greenhouse"]},
            {"provider": "lever", "connected": connected["lever"]},
        ]
    }


@router.post("/publish")
async def publish_job(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Not allowed")

    provider = payload.get("provider")
    job_id = payload.get("job_id")
    title = payload.get("title")

    if not provider:
        raise HTTPException(status_code=400, detail="provider required")
    if provider not in ("greenhouse", "lever"):
        raise HTTPException(status_code=400, detail="invalid provider")
    if not job_id and not title:
        raise HTTPException(status_code=400, detail="job_id or title required")

    return {
        "published": True,
        "provider": provider,
        "job_id": job_id,
        "title": title,
        "mode": "stub",
    }


@router.get("/mappings/{provider}")
async def list_mappings(
    provider: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "ats_stage_mappings"):
        return {"items": []}

    rows = (
        await db.execute(
            text("""
                select external_stage, internal_stage
                from public.ats_stage_mappings
                where org_id = :org_id and provider = :provider
                order by external_stage asc
            """),
            {"org_id": org_id, "provider": provider},
        )
    ).fetchall()

    return {
        "items": [
            {"external_stage": r[0], "internal_stage": r[1]}
            for r in rows
        ]
    }


@router.post("/mappings/{provider}")
async def upsert_mapping(
    provider: str,
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    ext = payload.get("external_stage")
    inte = payload.get("internal_stage")

    if not ext or not inte:
        raise HTTPException(status_code=400, detail="external_stage and internal_stage required")

    if not await table_exists(db, "ats_stage_mappings"):
        raise HTTPException(
            status_code=503,
            detail="ats_stage_mappings table is not available yet. Run the ATS migration first.",
        )

    await db.execute(
        text("""
            insert into public.ats_stage_mappings(
                org_id,
                provider,
                external_stage,
                internal_stage,
                updated_at
            )
            values (
                :org_id,
                :provider,
                :external_stage,
                :internal_stage,
                now()
            )
            on conflict (org_id, provider, external_stage)
            do update set
                internal_stage = excluded.internal_stage,
                updated_at = now()
        """),
        {
            "org_id": org_id,
            "provider": provider,
            "external_stage": ext,
            "internal_stage": inte,
        },
    )

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=user_id,
            actor_role=actor.role,
            event_type="ats.mapping_upserted",
            entity_type="ats_stage_mapping",
            entity_id=None,
            payload=json_safe(
                {
                    "provider": provider,
                    "external_stage": ext,
                    "internal_stage": inte,
                }
            ),
        )
    )

    await db.commit()

    return {
        "ok": True,
        "provider": provider,
        "external_stage": ext,
        "internal_stage": inte,
    }
