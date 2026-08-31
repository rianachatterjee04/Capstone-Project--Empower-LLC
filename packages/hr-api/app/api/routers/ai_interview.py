"""AI Interview router.

Endpoints:
- POST /ai-interview/sessions               : start a new interview session
- POST /ai-interview/sessions/{id}/answer   : submit answer to a question
- POST /ai-interview/sessions/{id}/complete : finalize + return summary
- GET  /ai-interview/sessions/{id}          : fetch a session
- GET  /ai-interview/sessions               : list sessions for the org

Sessions are kept in-process for the demo to avoid forcing a DB migration.
They survive within the running backend; this is deliberate so the demo runs
out of the box. All actions also write to AuditEvent so the org keeps a
defensible record.
"""
from __future__ import annotations

import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import AuditEvent
from app.services.ai_interview_service import (
    InterviewQuestion,
    InterviewResponse,
    generate_questions,
    score_answer,
    summarize_interview,
)
from app.services import adaptive_interview_service as adaptive
from app.services import candidate_integrity_service as integrity
from app.services.interview_fairness_service import check_question, fairness_summary


router = APIRouter(prefix="/ai-interview", tags=["ai-interview"])


@dataclass
class _Session:
    id: str
    org_id: str
    candidate_id: Optional[str]
    candidate_name: Optional[str]
    job_id: Optional[str]
    job_title: str
    job_description: str
    resume_text: str
    questions: list[InterviewQuestion]
    # answers[qid] is now the full InterviewResponse (mode + duration + transcript + meta)
    answers: dict[str, InterviewResponse] = field(default_factory=dict)
    summary: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    completed_at: Optional[str] = None
    # --- Adaptive engine state (additive) ---
    rubric: list[str] = field(default_factory=list)          # competencies for the role
    coverage: dict = field(default_factory=dict)              # competency -> {signal_strength, probes, ...}
    transcript: list = field(default_factory=list)            # [{question, answer, competency, quality, score}]
    asked_texts: set = field(default_factory=set)             # de-dupe question text
    evidence: dict = field(default_factory=dict)              # competency -> [quotes]
    max_questions: int = adaptive.DEFAULT_MAX_QUESTIONS
    current_question_id: Optional[str] = None                # the question awaiting an answer
    outcome: Optional[dict] = None                            # explainable scorecard + fraud + fairness

    def rendered_transcript(self) -> str:
        lines = []
        for t in self.transcript:
            lines.append(f"Interviewer: {t.get('question','')}")
            lines.append(f"Candidate: {t.get('answer','')}")
        return "\n".join(lines)

    def to_public_dict(self) -> dict:
        return {
            "id": self.id,
            "org_id": self.org_id,
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate_name,
            "job_id": self.job_id,
            "job_title": self.job_title,
            "questions": [q.to_dict() for q in self.questions],
            "answers": [
                {
                    "question_id": qid,
                    "answer": resp.answer,
                    "mode": resp.mode,
                    "duration_sec": resp.duration_sec,
                    "words_per_minute": resp.words_per_minute,
                    "has_face": resp.has_face,
                    "media_meta": resp.media_meta,
                }
                for qid, resp in self.answers.items()
            ],
            "summary": self.summary,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": "completed" if self.summary else "in_progress",
            # Adaptive surface
            "rubric": self.rubric,
            "coverage": adaptive.coverage_progress(self.coverage, self.rubric) if self.rubric else None,
            "transcript": self.transcript,
            "current_question_id": self.current_question_id,
            "outcome": self.outcome,
        }


_lock = threading.RLock()
_sessions: dict[str, _Session] = {}


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager")


# ---------------------------------------------------------------------------
@router.post("/sessions")
async def create_session(
    payload: dict,
    actor: Actor = Depends(require_org),
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    job_title = payload.get("job_title") or "Unknown Role"
    job_description = payload.get("job_description") or ""
    resume_text = payload.get("resume_text") or ""
    n_questions = int(payload.get("n_questions") or 7)
    provider = payload.get("provider") or "auto"

    questions = generate_questions(
        job_title=job_title,
        job_description=job_description,
        resume_text=resume_text,
        n_questions=n_questions,
        provider=provider,
    )

    # --- Anchor the adaptive session on a RUBRIC ---
    # Prefer an explicit competency list (e.g. from generate-plan / the job);
    # otherwise derive it from the generated question set (deduped, ordered).
    rubric = [c for c in (payload.get("competencies") or []) if c]
    if not rubric:
        seen: set[str] = set()
        for q in questions:
            if q.competency and q.competency not in seen:
                seen.add(q.competency)
                rubric.append(q.competency)
    if not rubric:
        rubric = ["role_fit", "technical_depth", "problem_solving", "communication", "ownership"]

    max_questions = int(payload.get("max_questions") or adaptive.DEFAULT_MAX_QUESTIONS)

    sess = _Session(
        id=str(uuid.uuid4()),
        org_id=actor.org_id,
        candidate_id=payload.get("candidate_id"),
        candidate_name=payload.get("candidate_name"),
        job_id=payload.get("job_id"),
        job_title=job_title,
        job_description=job_description,
        resume_text=resume_text,
        questions=questions,
        rubric=rubric,
        coverage=adaptive.init_coverage(rubric),
        max_questions=max_questions,
    )
    # The first question the candidate will answer (adaptive flow drives the rest).
    if questions:
        sess.current_question_id = questions[0].id
        sess.asked_texts.add(questions[0].text)
    with _lock:
        _sessions[sess.id] = sess

    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai_interview.created",
            entity_type="ai_interview_session",
            entity_id=UUID(sess.id),
            payload={"job_title": job_title, "n_questions": len(questions)},
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return sess.to_public_dict()


@router.get("/sessions")
async def list_sessions(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    with _lock:
        rows = [s.to_public_dict() for s in _sessions.values() if s.org_id == actor.org_id]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return {"items": rows}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    with _lock:
        sess = _sessions.get(session_id)
    if not sess or sess.org_id != actor.org_id:
        raise HTTPException(status_code=404, detail="Session not found")
    return sess.to_public_dict()


@router.post("/sessions/{session_id}/answer")
async def submit_answer(
    session_id: str,
    payload: dict,
    actor: Actor = Depends(require_org),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    qid = payload.get("question_id")
    answer_text = (payload.get("answer") or "").strip()
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
        sess = _sessions.get(session_id)
        if not sess or sess.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Session not found")
        q = next((q for q in sess.questions if q.id == qid), None)
        if not q:
            raise HTTPException(status_code=400, detail="Unknown question_id")
        sess.answers[qid] = InterviewResponse(
            question_id=qid,
            answer=answer_text,
            mode=mode,
            duration_sec=duration_sec,
            words_per_minute=words_per_minute,
            has_face=has_face,
            media_meta=media_meta,
        )

    scored = score_answer(
        q,
        answer_text,
        mode=mode,
        duration_sec=duration_sec,
        has_face=has_face,
    )

    # ------------------------------------------------------------------
    # ADAPTIVE LAYER — analyze → update coverage → choose next move →
    # generate the next question (fail-soft). All deterministic.
    # ------------------------------------------------------------------
    analysis = adaptive.analyze_answer(
        q, answer_text, mode=mode, duration_sec=duration_sec, has_face=has_face
    )
    with _lock:
        # ensure this competency is tracked even if it wasn't in the seed rubric
        if q.competency and q.competency not in sess.rubric:
            sess.rubric.append(q.competency)
            sess.coverage.setdefault(
                q.competency,
                {"signal_strength": 0.0, "probes": 0, "best_score": 0, "quality_history": []},
            )
        adaptive.update_coverage(sess.coverage, q.competency, analysis)
        sess.transcript.append({
            "question": q.text,
            "answer": answer_text,
            "competency": q.competency,
            "quality": analysis["quality"],
            "score": analysis["score"],
        })
        for quote in analysis.get("evidence", []):
            sess.evidence.setdefault(q.competency, [])
            if quote not in sess.evidence[q.competency]:
                sess.evidence[q.competency].append(quote)

        asked_count = len(sess.transcript)
        decision = adaptive.choose_next_move(
            sess.coverage,
            last_competency=q.competency,
            quality=analysis["quality"],
            rubric=sess.rubric,
            asked_count=asked_count,
            max_questions=sess.max_questions,
        )

        if decision["move"] == adaptive.WRAP_UP:
            sess.current_question_id = None
            next_payload = {"done": True, "reason": decision.get("reason")}
        else:
            gen = adaptive.generate_next_question(
                move=decision["move"],
                competency=decision["competency"],
                coverage=sess.coverage,
                asked_texts=sess.asked_texts,
                rubric=sess.rubric,
                resume_text=sess.resume_text,
                transcript=sess.rendered_transcript(),
                org_id=sess.org_id,
            )
            new_q = InterviewQuestion(
                id=str(uuid.uuid4()),
                competency=decision["competency"],
                text=gen["text"],
                rationale=f"Adaptive move: {decision['move']} ({decision.get('reason','')})",
            )
            sess.questions.append(new_q)
            sess.asked_texts.add(new_q.text)
            sess.current_question_id = new_q.id
            next_payload = {
                "done": False,
                "move": decision["move"],
                "reason": decision.get("reason"),
                "acknowledgement": adaptive.ack_for(analysis["quality"]),
                "question": new_q.to_dict(),
                "source": gen["source"],
            }

        coverage_map = adaptive.coverage_progress(sess.coverage, sess.rubric)

    # backward-compatible fields (question, scored) + adaptive fields
    return {
        "question": q.to_dict(),
        "scored": scored.to_dict(),
        "analysis": analysis,
        "coverage_map": coverage_map,
        "next": next_payload,
    }


@router.get("/sessions/{session_id}/state")
async def session_state(session_id: str, actor: Actor = Depends(require_org)):
    """Live adaptive state: coverage map, progress, remaining competencies."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    with _lock:
        sess = _sessions.get(session_id)
        if not sess or sess.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Session not found")
        coverage_map = adaptive.coverage_progress(sess.coverage, sess.rubric)
        current = next((q for q in sess.questions if q.id == sess.current_question_id), None)
        asked_count = len(sess.transcript)
        done = sess.summary is not None or (
            sess.current_question_id is None and asked_count > 0
        )
        return {
            "session_id": sess.id,
            "rubric": sess.rubric,
            "coverage_map": coverage_map,
            "asked_count": asked_count,
            "max_questions": sess.max_questions,
            "remaining_competencies": coverage_map["remaining"],
            "current_question": current.to_dict() if current else None,
            "transcript": sess.transcript,
            "done": done,
            "status": "completed" if sess.summary else "in_progress",
        }


def _response_uniformity(answers: list[str]) -> Optional[float]:
    """Cheap, deterministic AI-generation proxy: average pairwise Jaccard
    overlap of answer word-sets. High uniformity across distinct questions is
    a weak signal that answers may be machine-generated / templated."""
    sets = [set(re.findall(r"[a-z']+", (a or "").lower())) for a in answers if (a or "").strip()]
    sets = [s for s in sets if len(s) >= 3]
    if len(sets) < 2:
        return None
    sims: list[float] = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            union = sets[i] | sets[j]
            if not union:
                continue
            sims.append(len(sets[i] & sets[j]) / len(union))
    if not sims:
        return None
    return round(sum(sims) / len(sims), 4)


@router.post("/sessions/{session_id}/complete")
async def complete_session(
    session_id: str,
    actor: Actor = Depends(require_org),
    payload: Optional[dict] = None,
    db: AsyncSession = Depends(db_session),
):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")

    with _lock:
        sess = _sessions.get(session_id)
    if not sess or sess.org_id != actor.org_id:
        raise HTTPException(status_code=404, detail="Session not found")

    responses = list(sess.answers.values())
    summary = summarize_interview(sess.job_title, sess.questions, responses)

    # ------------------------------------------------------------------
    # OUTCOME — reuse the shared explainable-scoring + fraud + fairness work.
    # ------------------------------------------------------------------
    # 1) Explainable scorecard (reuses interview_score_review_service).
    explanation = adaptive.build_explainable_outcome(
        sess.org_id, sess.id,
        coverage=sess.coverage,
        rubric=sess.rubric,
        evidence_by_competency=sess.evidence,
    )

    # 2) Fraud / integrity signals (reuses candidate_integrity_service).
    payload = payload or {}
    integrity_signals = dict(payload.get("integrity_signals") or {})
    uniformity = _response_uniformity([r.answer for r in responses])
    if uniformity is not None and "response_uniformity" not in integrity_signals:
        integrity_signals["response_uniformity"] = uniformity
    fraud = integrity.assess(
        sess.org_id,
        candidate_id=sess.candidate_id or sess.id,
        candidate_name=sess.candidate_name or "Candidate",
        signals=integrity_signals,
        interview_id=sess.id,
        assessed_by="ai-interviewer",
    )

    # 3) Fairness pass over the questions the AI itself asked.
    flag_objs = []
    flag_dicts = []
    for q in sess.questions:
        for f in check_question(q.text):
            flag_objs.append(f)
            flag_dicts.append({**f.to_dict(), "question": q.text})
    fairness = {
        "flags": flag_dicts,
        "summary": fairness_summary(flag_objs),
        "note": (
            "Fairness scan of the AI-generated questions. AI scoring is assistive only; "
            "final hiring decisions require human review and must not rely on protected attributes."
        ),
    }

    outcome = {
        "headline": (
            f"Interviewed → scored → ranked. {sess.candidate_name or 'Candidate'} scored "
            f"{summary.overall_score}/100 ({summary.band}); recommendation: "
            f"{summary.recommendation.replace('_', ' ')}."
        ),
        "explainable_scorecard": explanation,
        "integrity": fraud,
        "fairness": fairness,
        "coverage": adaptive.coverage_progress(sess.coverage, sess.rubric),
    }

    with _lock:
        sess.summary = summary.to_dict()
        sess.outcome = outcome
        sess.current_question_id = None
        sess.completed_at = datetime.utcnow().isoformat() + "Z"

    try:
        db.add(AuditEvent(
            org_id=UUID(actor.org_id),
            actor_user_id=UUID(actor.user_id),
            actor_role=actor.role,
            event_type="ai_interview.completed",
            entity_type="ai_interview_session",
            entity_id=UUID(sess.id),
            payload={
                "score": summary.overall_score,
                "recommendation": summary.recommendation,
                "n_answers": len(responses),
            },
        ))
        await db.commit()
    except Exception:
        await db.rollback()

    return sess.to_public_dict()


@router.post("/preview-questions")
async def preview_questions(payload: dict, actor: Actor = Depends(require_org)):
    """Generate questions without persisting a session — useful for previews
    inside the recruiter UI."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    qs = generate_questions(
        job_title=payload.get("job_title") or "",
        job_description=payload.get("job_description") or "",
        resume_text=payload.get("resume_text") or "",
        n_questions=int(payload.get("n_questions") or 5),
        provider=payload.get("provider") or "auto",
    )
    return {"items": [q.to_dict() for q in qs]}
