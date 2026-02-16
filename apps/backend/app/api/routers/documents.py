from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from uuid import UUID
from datetime import datetime
import json

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent
from app.core.config import settings

router = APIRouter(prefix="/documents", tags=["documents"])


# =========================================================
# PRESIGNED UPLOAD PATH
# =========================================================
@router.post("/presign")
async def presign_upload(payload: dict, actor: Actor = Depends(require_org)):

    if actor.role not in ("owner","admin","hr","manager","employee"):
        raise HTTPException(status_code=403, detail="Not allowed")

    bucket = payload.get("bucket") or getattr(settings, "supabase_storage_bucket", "foundry-people")
    category = payload.get("category") or "other"
    filename = payload.get("filename") or "upload.bin"
    employee_id = payload.get("employee_id")

    path = f"{actor.org_id}/{employee_id or actor.user_id}/{category}/{filename}"

    # NOTE: Replace with real signed upload call in production
    return {"bucket": bucket, "path": path}


# =========================================================
# REGISTER DOCUMENT AFTER UPLOAD
# =========================================================
@router.post("")
async def register_document(payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    org_id = UUID(actor.org_id)

    res = await db.execute(text("""
      insert into public.documents(
        org_id, employee_id, category, storage_bucket, storage_path,
        mime_type, sha256, status, expires_at, uploaded_by_user_id
      )
      values (
        :org_id, :employee_id, :category, :bucket, :path,
        :mime, :sha256, :status, :expires_at, :uploader
      )
      returning id
    """), {
        "org_id": str(org_id),
        "employee_id": payload.get("employee_id"),
        "category": payload.get("category","other"),
        "bucket": payload.get("storage_bucket"),
        "path": payload.get("storage_path"),
        "mime": payload.get("mime_type"),
        "sha256": payload.get("sha256"),
        "status": payload.get("status","uploaded"),
        "expires_at": payload.get("expires_at"),
        "uploader": str(UUID(actor.user_id)),
    })

    doc_id = res.first()[0]

    db.add(AuditEvent(
        org_id=org_id,
        actor_user_id=UUID(actor.user_id),
        actor_role=actor.role,
        event_type="document.registered",
        entity_type="document",
        entity_id=doc_id,
        payload=payload
    ))

    await db.commit()
    return {"id": str(doc_id)}


# =========================================================
# SECURE DOWNLOAD LINK (CHAIN OF CUSTODY)
# =========================================================
@router.get("/{doc_id}/access")
async def access_document(doc_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    row = (await db.execute(text("""
        select storage_bucket, storage_path, locked
        from public.documents
        where id=:id and org_id=:org_id
    """), {"id": doc_id, "org_id": actor.org_id})).first()

    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    # Log evidence access
    await db.execute(text("""
        insert into public.view_events(org_id, actor_user_id, actor_role, entity_type, entity_id, path)
        values (:org_id, :uid, :role, 'document', :doc_id, 'download')
    """), {"org_id": actor.org_id, "uid": actor.user_id, "role": actor.role, "doc_id": doc_id})

    await db.commit()

    # In production return signed URL
    return {"bucket": row[0], "path": row[1], "locked": row[2]}


# =========================================================
# VERSION UPLOAD (replace document)
# =========================================================
@router.post("/{doc_id}/version")
async def new_version(doc_id: str, payload: dict, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    # Prevent overwrite of locked evidence
    locked = (await db.execute(text("""
        select locked from public.documents where id=:id and org_id=:org
    """), {"id": doc_id, "org": actor.org_id})).scalar()

    if locked:
        raise HTTPException(status_code=403, detail="Document locked")

    await db.execute(text("""
        insert into public.document_versions(document_id, storage_path, sha256, uploaded_by_user_id)
        values (:doc, :path, :sha, :uid)
    """), {"doc": doc_id, "path": payload.get("storage_path"), "sha": payload.get("sha256"), "uid": actor.user_id})

    await db.commit()
    return {"version_added": True}


# =========================================================
# LIST DOCUMENTS
# =========================================================
@router.get("")
async def list_documents(actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    res = await db.execute(text("""
        select * from public.documents
        where org_id = :org_id
        order by created_at desc
    """), {"org_id": actor.org_id})

    cols = res.keys()
    return [dict(zip(cols, row)) for row in res.fetchall()]


# =========================================================
# EXPORT LEGAL PACKET (critical for lawsuits)
# =========================================================
@router.get("/legal-packet/{employee_id}")
async def legal_packet(employee_id: str, actor: Actor = Depends(require_org), db: AsyncSession = Depends(db_session)):

    if actor.role not in ("owner","admin","hr","legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    rows = (await db.execute(text("""
        select id, category, storage_path, created_at
        from public.documents
        where org_id=:org_id and employee_id=:eid
        order by created_at asc
    """), {"org_id": actor.org_id, "eid": employee_id})).fetchall()

    return {
        "employee_id": employee_id,
        "documents": [
            {"id": str(r[0]), "category": r[1], "path": r[2], "created_at": str(r[3])}
            for r in rows
        ]
    }

