"""AI Helpdesk router — RAG-backed Q&A over policy + benefits documents."""
from __future__ import annotations

from uuid import UUID

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent
from app.services import hr_answer_service, hr_documents_service as docs_svc
from app.services.rag_service import add_document, answer, list_documents, retrieve


router = APIRouter(prefix="/ai-helpdesk", tags=["ai-helpdesk"])

_ADMIN_ROLES = ("owner", "admin", "hr")


def _require_admin(actor: Actor) -> None:
    if actor.role not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Not allowed")


async def _audit(db: AsyncSession, actor: Actor, event_type: str, payload: dict) -> None:
    """Best effort, like the existing helpdesk routes: a failed audit write must
    not undo the change the person just made."""
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type=event_type,
            entity_type="knowledge_doc",
            payload=payload,
        ))
        await db.commit()
    except Exception:
        await db.rollback()


def _raise(err: docs_svc.DocumentError) -> None:
    raise HTTPException(status_code=err.status, detail=err.message)


@router.get("/documents")
async def documents(actor: Actor = Depends(require_org)):
    is_admin = actor.role in _ADMIN_ROLES
    items = list_documents(actor.org_id, include_archived=is_admin)
    if not is_admin:
        # Everyone in the org can read the list. Who uploaded what, and the file
        # hash, are for the people who manage documents.
        items = [{k: v for k, v in item.items() if k != "meta"} for item in items]
    return {"items": items}


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Upload a PDF, Word, text or Markdown file. Its text becomes searchable."""
    _require_admin(actor)
    # One byte over the limit is enough to know the file is too big.
    data = await file.read(docs_svc.MAX_FILE_BYTES + 1)
    try:
        out = await run_in_threadpool(
            docs_svc.store_upload,
            org_id=actor.org_id,
            user_id=actor.user_id,
            filename=file.filename or "",
            data=data,
            title=title,
            category=category,
        )
    except docs_svc.DocumentError as err:
        _raise(err)
    await _audit(db, actor, "ai_helpdesk.document_uploaded", {
        "title": out["title"], "filename": out["filename"], "kind": out["kind"],
        "size_bytes": out["size_bytes"], "doc_id": out["id"],
    })
    return out


@router.patch("/documents/{doc_id}")
async def edit_document(
    doc_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    _require_admin(actor)
    try:
        out = docs_svc.rename_or_recategorise(
            actor.org_id, doc_id, title=payload.get("title"), category=payload.get("category"))
    except docs_svc.DocumentError as err:
        _raise(err)
    await _audit(db, actor, "ai_helpdesk.document_edited", {"doc_id": doc_id})
    return out


@router.post("/documents/{doc_id}/archive")
async def archive_document(
    doc_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    _require_admin(actor)
    try:
        out = docs_svc.archive(actor.org_id, doc_id)
    except docs_svc.DocumentError as err:
        _raise(err)
    await _audit(db, actor, "ai_helpdesk.document_archived", {"doc_id": doc_id})
    return out


@router.post("/documents/{doc_id}/restore")
async def restore_document(
    doc_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    _require_admin(actor)
    try:
        out = docs_svc.restore(actor.org_id, doc_id)
    except docs_svc.DocumentError as err:
        _raise(err)
    await _audit(db, actor, "ai_helpdesk.document_restored", {"doc_id": doc_id})
    return out


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    _require_admin(actor)
    try:
        docs_svc.delete(actor.org_id, doc_id)
    except docs_svc.DocumentError as err:
        _raise(err)
    await _audit(db, actor, "ai_helpdesk.document_deleted", {"doc_id": doc_id})
    return {"deleted": True, "id": doc_id}


@router.post("/documents")
async def upsert_document(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if actor.role not in ("owner", "admin", "hr"):
        raise HTTPException(status_code=403, detail="Not allowed")
    title = (payload.get("title") or "").strip()
    body = (payload.get("body") or "").strip()
    if not title or not body:
        raise HTTPException(status_code=400, detail="title and body required")
    out = add_document(
        org_id=actor.org_id,
        title=title,
        body=body,
        category=payload.get("category") or "policy",
        source=payload.get("source") or "internal",
    )
    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai_helpdesk.document_added",
            entity_type="knowledge_doc",
            payload={"title": title, "category": payload.get("category")},
        ))
        await db.commit()
    except Exception:
        await db.rollback()
    return out


@router.post("/ask")
async def ask(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question required")

    audience = payload.get("audience") or ("admin" if actor.role in ("owner", "admin", "hr") else "employee")
    result = answer(actor.org_id, question, audience=audience)

    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai_helpdesk.ask",
            entity_type="ai_helpdesk",
            payload={
                "question": question[:500],
                "needs_escalation": result["needs_escalation"],
                "citations": [c["id"] for c in result.get("citations", [])],
            },
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return result


@router.post("/respond")
async def respond(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    """Answer a question from the org's active documents, written by the AI.

    /ask is unchanged. This route returns how the answer was generated and
    which documents it rests on, and checks the model's reply before using it.
    """
    question = (payload.get("question") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question required")
    if len(question) > hr_answer_service.QUESTION_LIMIT:
        raise HTTPException(
            status_code=400,
            detail=f"question must be {hr_answer_service.QUESTION_LIMIT} characters or fewer")

    def _work() -> dict:
        excerpts = retrieve(actor.org_id, question, top_k=3)
        return hr_answer_service.generate_response(question, excerpts, org_id=actor.org_id)

    result = await run_in_threadpool(_work)

    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai_helpdesk.respond",
            entity_type="ai_helpdesk",
            payload={
                "question": question[:500],
                "generated_by": result["generated_by"],
                "needs_escalation": result["needs_escalation"],
                "sources": [s["id"] for s in result["sources_used"]],
            },
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return {"question": question, **result}
