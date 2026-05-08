from __future__ import annotations

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_org, db_session, Actor
from app.db.models import AuditEvent

router = APIRouter(prefix="/verification", tags=["verification"])


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


async def documents_column_names(db: AsyncSession) -> set[str]:
    """Public.documents columns (for choosing UPDATE shape without failing a statement)."""
    r = await db.execute(
        text("""
            select column_name
            from information_schema.columns
            where table_schema = 'public' and table_name = 'documents'
        """)
    )
    return {row[0] for row in r.fetchall()}


# =========================================================
# REVIEW QUEUE
# =========================================================
@router.get("/queue")
async def queue(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    if not await table_exists(db, "documents"):
        return []

    res = await db.execute(
        text("""
            select *
            from public.documents
            where org_id = :org_id
              and status in ('uploaded', 'in_review')
            order by created_at asc
        """),
        {"org_id": actor.org_id},
    )

    cols = list(res.keys())
    return [dict(zip(cols, row)) for row in res.fetchall()]


# =========================================================
# ASSIGN REVIEWER
# =========================================================
@router.post("/documents/{doc_id}/assign")
async def assign(
    doc_id: str,
    reviewer_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)
    doc_uuid = as_uuid(doc_id)

    if org_id is None or user_id is None or doc_uuid is None:
        raise HTTPException(status_code=400, detail="Invalid identifiers")

    if not await table_exists(db, "documents"):
        raise HTTPException(
            status_code=503,
            detail="documents table is not available yet. Run the documents migration first.",
        )

    cols = await documents_column_names(db)
    if "reviewer_employee_id" in cols:
        result = await db.execute(
            text("""
                update public.documents
                set reviewer_employee_id = :rid,
                    status = 'in_review'
                where id = :id and org_id = :org_id
            """),
            {"rid": reviewer_id, "id": doc_uuid, "org_id": org_id},
        )
    else:
        result = await db.execute(
            text("""
                update public.documents
                set status = 'in_review'
                where id = :id and org_id = :org_id
            """),
            {"id": doc_uuid, "org_id": org_id},
        )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found")

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=user_id,
            actor_role=actor.role,
            event_type="document.assigned",
            entity_type="document",
            entity_id=doc_uuid,
            payload={"reviewer": reviewer_id},
        )
    )

    await db.commit()
    return {"assigned": True}


# =========================================================
# VERIFY / REJECT DOCUMENT
# =========================================================
@router.post("/documents/{doc_id}/verify")
async def verify(
    doc_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)
    doc_uuid = as_uuid(doc_id)

    if org_id is None or user_id is None or doc_uuid is None:
        raise HTTPException(status_code=400, detail="Invalid identifiers")

    if not await table_exists(db, "documents"):
        raise HTTPException(
            status_code=503,
            detail="documents table is not available yet. Run the documents migration first.",
        )

    status = payload.get("status", "verified")
    reason = payload.get("reason")
    expires_days = payload.get("expires_in_days")

    if status not in ("verified", "rejected", "in_review"):
        raise HTTPException(status_code=400, detail="Invalid status")

    expires_at_val: date | None = None
    if expires_days and status == "verified":
        expires_at_val = (datetime.utcnow() + timedelta(days=int(expires_days))).date()

    params = {
        "status": status,
        "reason": reason,
        "expires_at": expires_at_val,
        "id": doc_uuid,
        "org_id": org_id,
    }

    cols = await documents_column_names(db)
    has_extended = "rejection_reason" in cols and "verified_at" in cols

    if has_extended:
        result = await db.execute(
            text("""
                update public.documents
                set status = :status,
                    rejection_reason = case when :status = 'rejected' then :reason else null end,
                    expires_at = coalesce(cast(:expires_at as date), expires_at),
                    verified_at = case when :status = 'verified' then now() else verified_at end
                where id = :id and org_id = :org_id
            """),
            params,
        )
    else:
        result = await db.execute(
            text("""
                update public.documents
                set status = :status,
                    expires_at = coalesce(cast(:expires_at as date), expires_at)
                where id = :id and org_id = :org_id
            """),
            params,
        )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found")

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=user_id,
            actor_role=actor.role,
            event_type="document.status_changed",
            entity_type="document",
            entity_id=doc_uuid,
            payload={
                "status": status,
                "reason": reason,
                "expires_at": str(expires_at_val) if expires_at_val else None,
            },
        )
    )

    await db.commit()
    return {"ok": True, "status": status}


# =========================================================
# EXPIRING DOCUMENTS ALERT
# =========================================================
@router.get("/expiring")
async def expiring(
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
    days: int = 30,
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")

    if not await table_exists(db, "documents"):
        return []

    res = await db.execute(
        text("""
            select id, employee_id, expires_at
            from public.documents
            where org_id = :org_id
              and expires_at is not null
              and expires_at < now() + cast((:days || ' days') as interval)
            order by expires_at asc
        """),
        {"org_id": actor.org_id, "days": days},
    )

    rows = res.fetchall()

    return [
        {
            "document_id": str(r[0]),
            "employee_id": str(r[1]) if r[1] is not None else None,
            "expires_at": str(r[2]),
        }
        for r in rows
    ]


# =========================================================
# LOCK DOCUMENT (legal hold)
# =========================================================
@router.post("/documents/{doc_id}/lock")
async def lock(
    doc_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr", "legal"):
        raise HTTPException(status_code=403, detail="Not allowed")

    org_id = as_uuid(actor.org_id)
    user_id = as_uuid(actor.user_id)
    doc_uuid = as_uuid(doc_id)

    if org_id is None or user_id is None or doc_uuid is None:
        raise HTTPException(status_code=400, detail="Invalid identifiers")

    if not await table_exists(db, "documents"):
        raise HTTPException(
            status_code=503,
            detail="documents table is not available yet. Run the documents migration first.",
        )

    result = await db.execute(
        text("""
            update public.documents
            set is_locked = true
            where id = :id and org_id = :org_id
        """),
        {"id": doc_uuid, "org_id": org_id},
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found")

    db.add(
        AuditEvent(
            org_id=org_id,
            actor_user_id=user_id,
            actor_role=actor.role,
            event_type="document.locked",
            entity_type="document",
            entity_id=doc_uuid,
            payload={},
        )
    )

    await db.commit()
    return {"locked": True}
