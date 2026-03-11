from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.core.config import settings
from app.core.json_utils import json_safe
from app.db.models import AuditEvent

router = APIRouter(prefix="/documents", tags=["documents"])


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


# =========================================================
# PRESIGNED UPLOAD PATH
# =========================================================
@router.post("/presign")
async def presign_upload(
    payload: dict,
    actor: Actor = Depends(require_org),
):
    if actor.role not in ("owner", "admin", "hr", "manager", "employee"):
        raise HTTPException(status_code=403, detail="Not allowed")

    bucket = payload.get("bucket") or getattr(
        settings, "supabase_storage_bucket", "foundry-people"
    )
    category = payload.get("category") or "other"
    filename = payload.get("filename") or "upload.bin"
    employee_id = payload.get("employee_id")

    path = f"{actor.org_id}/{employee_id or actor.user_id}/{category}/{filename}"

    return {"bucket": bucket, "path": path}


# =========================================================
# REGISTER DOCUMENT AFTER UPLOAD
# =========================================================
@router.post("")
async def register_document(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)

    if org_id is None or user_id is None:
        raise HTTPException(status_code=400, detail="Missing actor identifiers")

    if not await table_exists(db, "documents"):
        raise HTTPException(
            status_code=503,
            detail="documents table is not available yet. Run the documents migration first.",
        )

    res = await db.execute(
        text("""
            insert into public.documents(
                org_id,
                employee_id,
                category,
                storage_bucket,
                storage_path,
                mime_type,
                sha256,
                status,
                expires_at,
                uploaded_by_user_id
            )
            values (
                :org_id,
                :employee_id,
                :category,
                :bucket,
                :path,
                :mime,
                :sha256,
                :status,
                :expires_at,
                :uploader
            )
            returning id
        """),
        {
            "org_id": org_id,
            "employee_id": payload.get("employee_id"),
            "category": payload.get("category", "other"),
            "bucket": payload.get("storage_bucket"),
            "path": payload.get("storage_path"),
            "mime": payload.get("mime_type"),
            "sha256": payload.get("sha256"),
            "status": payload.get("status", "uploaded"),
            "expires_at": payload.get("expires_at"),
            "uploader": user_id,
        },
    )

    doc_id = res.scalar()

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=user_id,
            actor_role=actor.role,
            event_type="document.registered",
            entity_type="document",
            entity_id=doc_id,
            payload=json_safe(payload),
        )
    )

    await db.commit()
    return {"id": str(doc_id)}


# =========================================================
# SECURE DOWNLOAD LINK
# =========================================================
@router.get("/{doc_id}/access")
async def access_document(
    doc_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)

    if org_id is None or user_id is None:
        raise HTTPException(status_code=400, detail="Missing actor identifiers")

    if not await table_exists(db, "documents"):
        raise HTTPException(
            status_code=503,
            detail="documents table is not available yet. Run the documents migration first.",
        )

    row = (
        await db.execute(
            text("""
                select storage_bucket, storage_path, locked
                from public.documents
                where id = :id and org_id = :org_id
            """),
            {"id": doc_id, "org_id": org_id},
        )
    ).first()

    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    if await table_exists(db, "view_events"):
        await db.execute(
            text("""
                insert into public.view_events(
                    org_id,
                    actor_user_id,
                    actor_role,
                    entity_type,
                    entity_id,
                    path
                )
                values (
                    :org_id,
                    :uid,
                    :role,
                    'document',
                    :doc_id,
                    'download'
                )
            """),
            {
                "org_id": org_id,
                "uid": user_id,
                "role": actor.role,
                "doc_id": doc_id,
            },
        )

    await db.commit()

    return {
        "bucket": row[0],
        "path": row[1],
        "locked": row[2],
    }


# =========================================================
# VERSION UPLOAD
# =========================================================
@router.post("/{doc_id}/version")
async def new_version(
    doc_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)

    if org_id is None or user_id is None:
        raise HTTPException(status_code=400, detail="Missing actor identifiers")

    if not await table_exists(db, "documents"):
        raise HTTPException(
            status_code=503,
            detail="documents table is not available yet. Run the documents migration first.",
        )

    locked = (
        await db.execute(
            text("""
                select locked
                from public.documents
                where id = :id and org_id = :org
            """),
            {"id": doc_id, "org": org_id},
        )
    ).scalar()

    if locked:
        raise HTTPException(status_code=403, detail="Document locked")

    if not await table_exists(db, "document_versions"):
        raise HTTPException(
            status_code=503,
            detail="document_versions table is not available yet. Run the documents migration first.",
        )

    await db.execute(
        text("""
            insert into public.document_versions(
                document_id,
                storage_path,
                sha256,
                uploaded_by_user_id
            )
            values (:doc, :path, :sha, :uid)
        """),
        {
            "doc": doc_id,
            "path": payload.get("storage_path"),
            "sha": payload.get("sha256"),
            "uid": user_id,
        },
    )

    await db.commit()
    return {"version_added": True}


# =========================================================
# LIST DOCUMENTS
# =========================================================
@router.get("")
async def list_documents(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "documents"):
        return []

    res = await db.execute(
        text("""
            select *
            from public.documents
            where org_id = :org_id
            order by created_at desc
        """),
        {"org_id": org_id},
    )

    cols = list(res.keys())
    return [dict(zip(cols, row)) for row in res.fetchall()]


# =========================================================
# EXPORT LEGAL PACKET
# =========================================================
@router.get("/legal-packet/{employee_id}")
async def legal_packet(
    employee_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    if org_id is None:
        raise HTTPException(status_code=400, detail="Missing org_id")

    if not await table_exists(db, "documents"):
        return {"employee_id": employee_id, "documents": []}

    rows = (
        await db.execute(
            text("""
                select id, category, storage_path, created_at
                from public.documents
                where org_id = :org_id and employee_id = :eid
                order by created_at asc
            """),
            {"org_id": org_id, "eid": employee_id},
        )
    ).fetchall()

    return {
        "employee_id": employee_id,
        "documents": [
            {
                "id": str(r[0]),
                "category": r[1],
                "path": r[2],
                "created_at": str(r[3]),
            }
            for r in rows
        ],
    }
