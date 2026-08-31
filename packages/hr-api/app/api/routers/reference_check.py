"""AI Reference Check router.

Multi-reference, multimodal (written / audio / video) reference interviews
that share the same DS, scoring shape, and audit pattern as the AI Interview
flow. References can either:
  * Receive an invite link and self-serve their answers, or
  * Be transcribed live by the recruiter on a call.

Sessions are kept in-process for the demo (no schema migration required) and
mirrored to AuditEvent so each org keeps a defensible record.
"""
from __future__ import annotations

import secrets
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent
from app.services.reference_check_service import (
    ReferenceProfile,
    ReferenceQuestion,
    ReferenceResponse,
    RELATIONSHIPS,
    generate_questions,
    score_answer,
    score_reference,
    synthesise,
)


router = APIRouter(prefix="/reference-checks", tags=["reference-checks"])


@dataclass
class _RefSlot:
    profile: ReferenceProfile
    questions: list[ReferenceQuestion]
    responses: dict[str, ReferenceResponse] = field(default_factory=dict)
    submit_token: str = ""

    def to_public_dict(self) -> dict:
        return {
            "profile": self.profile.to_dict(),
            "questions": [q.to_dict() for q in self.questions],
            "responses": [
                {
                    "question_id": qid,
                    "answer": r.answer,
                    "mode": r.mode,
                    "duration_sec": r.duration_sec,
                    "words_per_minute": r.words_per_minute,
                    "has_face": r.has_face,
                    "media_meta": r.media_meta,
                }
                for qid, r in self.responses.items()
            ],
            "submit_token": self.submit_token,
            "is_complete": len(self.responses) >= len(self.questions),
        }


@dataclass
class _RefCheck:
    id: str
    org_id: str
    candidate_id: Optional[str]
    candidate_name: str
    job_id: Optional[str]
    job_title: str
    extra_context: str
    n_questions: int
    references: dict[str, _RefSlot] = field(default_factory=dict)
    summary: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    completed_at: Optional[str] = None

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate_name,
            "job_id": self.job_id,
            "job_title": self.job_title,
            "extra_context": self.extra_context,
            "n_questions": self.n_questions,
            "references": [s.to_public_dict() for s in self.references.values()],
            "summary": self.summary,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": "completed" if self.summary else "in_progress",
        }


_lock = threading.RLock()
_checks: dict[str, _RefCheck] = {}
# token → (check_id, ref_id) lookup so a reference can post answers
# without needing the recruiter's auth token (demo email-link surrogate).
_token_index: dict[str, tuple[str, str]] = {}


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager")


# ---------------------------------------------------------------------------
@router.post("")
async def create_check(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    candidate_name = (payload.get("candidate_name") or "").strip()
    if not candidate_name:
        raise HTTPException(status_code=400, detail="candidate_name required")

    check = _RefCheck(
        id=str(uuid.uuid4()),
        org_id=actor.org_id,
        candidate_id=payload.get("candidate_id"),
        candidate_name=candidate_name,
        job_id=payload.get("job_id"),
        job_title=(payload.get("job_title") or "").strip() or "Unknown Role",
        extra_context=(payload.get("extra_context") or "").strip(),
        n_questions=int(payload.get("n_questions") or 8),
    )

    with _lock:
        _checks[check.id] = check

    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="reference_check.created",
            entity_type="reference_check",
            entity_id=UUID(check.id),
            payload={"candidate_name": candidate_name, "job_title": check.job_title},
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return check.to_public_dict()


@router.get("")
async def list_checks(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    with _lock:
        rows = [c.to_public_dict() for c in _checks.values() if c.org_id == actor.org_id]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return {"items": rows}


@router.get("/{check_id}")
async def get_check(check_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    with _lock:
        c = _checks.get(check_id)
    if not c or c.org_id != actor.org_id:
        raise HTTPException(status_code=404, detail="Check not found")
    return c.to_public_dict()


@router.post("/{check_id}/references")
async def add_reference(
    check_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    relationship = (payload.get("relationship") or "manager").lower()
    if relationship not in RELATIONSHIPS:
        relationship = "other"

    with _lock:
        check = _checks.get(check_id)
        if not check or check.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Check not found")

    ref_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(16)
    profile = ReferenceProfile(
        id=ref_id,
        name=name,
        email=(payload.get("email") or "").strip(),
        title=(payload.get("title") or "").strip(),
        company=(payload.get("company") or "").strip(),
        relationship=relationship,
        tenure_months=int(payload.get("tenure_months") or 0),
        invited_at=datetime.utcnow().isoformat() + "Z",
        consent_recorded=bool(payload.get("consent_recorded") or False),
    )

    questions = generate_questions(
        candidate_name=check.candidate_name,
        relationship=relationship,
        job_title=check.job_title,
        extra_context=check.extra_context,
        n_questions=check.n_questions,
        provider=payload.get("provider") or "auto",
    )

    slot = _RefSlot(profile=profile, questions=questions, submit_token=token)
    with _lock:
        check.references[ref_id] = slot
        _token_index[token] = (check_id, ref_id)

    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="reference_check.reference_added",
            entity_type="reference_check",
            entity_id=UUID(check.id),
            payload={
                "reference_id": ref_id,
                "name": name,
                "relationship": relationship,
                "n_questions": len(questions),
            },
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return slot.to_public_dict()


@router.post("/{check_id}/references/{ref_id}/respond")
async def submit_response(
    check_id: str,
    ref_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
):
    """Recruiter-mediated path — the recruiter is on a call with the
    reference and transcribes the answer (or uses the live STT / video
    capture component) on the candidate's behalf."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    qid = payload.get("question_id")
    answer = (payload.get("answer") or "").strip()
    if not qid:
        raise HTTPException(status_code=400, detail="question_id required")

    mode = (payload.get("mode") or "written").lower()
    if mode not in ("written", "audio", "video"):
        mode = "written"
    duration_sec = float(payload.get("duration_sec") or 0.0)
    words_per_minute = float(payload.get("words_per_minute") or 0.0)
    has_face = bool(payload.get("has_face") or False)
    media_meta = payload.get("media_meta") or {}

    with _lock:
        check = _checks.get(check_id)
        if not check or check.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Check not found")
        slot = check.references.get(ref_id)
        if not slot:
            raise HTTPException(status_code=404, detail="Reference not found")
        q = next((qq for qq in slot.questions if qq.id == qid), None)
        if not q:
            raise HTTPException(status_code=400, detail="Unknown question_id")
        slot.responses[qid] = ReferenceResponse(
            question_id=qid,
            answer=answer,
            mode=mode,
            duration_sec=duration_sec,
            words_per_minute=words_per_minute,
            has_face=has_face,
            media_meta=media_meta,
        )

    scored = score_answer(q, answer, mode=mode, duration_sec=duration_sec, has_face=has_face)
    return {"question": q.to_dict(), "scored": scored.to_dict()}


# ---------------- token-based self-serve (no auth, for invite links) -------
@router.get("/respond/{token}")
async def fetch_self_serve(token: str):
    with _lock:
        ref = _token_index.get(token)
        if not ref:
            raise HTTPException(status_code=404, detail="Invalid or expired link")
        check_id, ref_id = ref
        check = _checks.get(check_id)
        if not check:
            raise HTTPException(status_code=404, detail="Reference check not found")
        slot = check.references.get(ref_id)
        if not slot:
            raise HTTPException(status_code=404, detail="Reference not found")
    return {
        "check": {
            "id": check.id,
            "candidate_name": check.candidate_name,
            "job_title": check.job_title,
        },
        "reference": slot.profile.to_dict(),
        "questions": [q.to_dict() for q in slot.questions],
        "responses_submitted": len(slot.responses),
    }


@router.post("/respond/{token}")
async def submit_self_serve(token: str, payload: dict):
    """Self-serve answer submission via invite link — no recruiter auth.
    Same payload shape as /respond above."""
    with _lock:
        ref = _token_index.get(token)
        if not ref:
            raise HTTPException(status_code=404, detail="Invalid or expired link")
        check_id, ref_id = ref
        check = _checks.get(check_id)
        slot = check.references.get(ref_id) if check else None
    if not check or not slot:
        raise HTTPException(status_code=404, detail="Reference check not found")

    qid = payload.get("question_id")
    answer = (payload.get("answer") or "").strip()
    if not qid:
        raise HTTPException(status_code=400, detail="question_id required")

    mode = (payload.get("mode") or "written").lower()
    if mode not in ("written", "audio", "video"):
        mode = "written"
    duration_sec = float(payload.get("duration_sec") or 0.0)
    words_per_minute = float(payload.get("words_per_minute") or 0.0)
    has_face = bool(payload.get("has_face") or False)
    media_meta = payload.get("media_meta") or {}

    with _lock:
        q = next((qq for qq in slot.questions if qq.id == qid), None)
        if not q:
            raise HTTPException(status_code=400, detail="Unknown question_id")
        slot.responses[qid] = ReferenceResponse(
            question_id=qid,
            answer=answer,
            mode=mode,
            duration_sec=duration_sec,
            words_per_minute=words_per_minute,
            has_face=has_face,
            media_meta=media_meta,
        )

    scored = score_answer(q, answer, mode=mode, duration_sec=duration_sec, has_face=has_face)
    return {
        "question": q.to_dict(),
        "scored": scored.to_dict(),
        "remaining": max(0, len(slot.questions) - len(slot.responses)),
    }


@router.post("/{check_id}/references/{ref_id}/complete")
async def complete_reference(
    check_id: str,
    ref_id: str,
    actor: Actor = Depends(require_org),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    with _lock:
        check = _checks.get(check_id)
        if not check or check.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Check not found")
        slot = check.references.get(ref_id)
        if not slot:
            raise HTTPException(status_code=404, detail="Reference not found")
        slot.profile.completed_at = datetime.utcnow().isoformat() + "Z"
    return slot.to_public_dict()


@router.post("/{check_id}/complete")
async def complete_check(
    check_id: str,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    with _lock:
        check = _checks.get(check_id)
        if not check or check.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Check not found")

    scored_refs = []
    for slot in check.references.values():
        if slot.responses:
            scored_refs.append(score_reference(
                slot.profile, slot.questions, list(slot.responses.values()),
            ))

    summary = synthesise(check.candidate_name, check.job_title, scored_refs)
    with _lock:
        check.summary = summary.to_dict()
        check.completed_at = datetime.utcnow().isoformat() + "Z"

    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="reference_check.completed",
            entity_type="reference_check",
            entity_id=UUID(check.id),
            payload={
                "score": summary.overall_score,
                "band": summary.band,
                "recommendation": summary.recommendation,
                "n_references": summary.n_references,
            },
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return check.to_public_dict()


@router.post("/preview-questions")
async def preview_questions(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    qs = generate_questions(
        candidate_name=(payload.get("candidate_name") or "the candidate"),
        relationship=(payload.get("relationship") or "manager"),
        job_title=(payload.get("job_title") or ""),
        extra_context=(payload.get("extra_context") or ""),
        n_questions=int(payload.get("n_questions") or 6),
        provider=payload.get("provider") or "auto",
    )
    return {"items": [q.to_dict() for q in qs]}
