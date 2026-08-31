"""Interview AI router — live-assist endpoints for the Copilot UI.

Separated from /api/interviews (CRUD) so the AI-assist surface is its own
audit boundary. Distinct from the existing /api/ai-interview (solo Web
Speech interviewer) — both coexist.

All endpoints emit an `assist_mode` field in the response so the UI can
tell whether the LLM or local fallback produced the suggestion.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.interview_copilot_service import (
    get_interview,
    live_context,
    record_insight,
    suggest_follow_up_questions,
    summarise_live_answer,
    map_answer_to_scorecard,
    InterviewInsight,
)
from app.services.interview_fairness_service import check_question, check_scorecard_note, fairness_summary
from app.services.interview_transcription_service import full_transcript


router = APIRouter(prefix="/interview-ai", tags=["interview-ai"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager")


@router.get("/{interview_id}/live-context")
async def live_context_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    """Single roll-up the live UI right-rail consumes."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    iv = get_interview(actor.org_id, interview_id)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    # Pull competencies from the interview plan if generated, else infer
    competencies = []
    plan = iv.interview_plan
    if isinstance(plan, dict):
        competencies = plan.get("focus_areas") or []
    if not competencies:
        # default per interview_type
        competencies = ["communication", "technical_depth", "ownership", "collaboration"]
    return live_context(
        interview_id=interview_id,
        scorecard_competencies=competencies,
    )


@router.post("/{interview_id}/assist")
async def assist_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    """The catch-all 'What should I ask / summarise this answer / etc.' endpoint.

    payload: {action: "...", ...}
    """
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    iv = get_interview(actor.org_id, interview_id)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    action = (payload.get("action") or "").lower()
    competency = payload.get("competency") or "communication"
    latest_answer = payload.get("latest_answer") or ""

    if action == "summarise_answer":
        return {"action": action, "result": summarise_live_answer(latest_answer)}
    if action == "follow_up":
        return {"action": action, "result": suggest_follow_up_questions(
            latest_answer=latest_answer,
            competency=competency,
            asked_already=payload.get("asked_already") or [],
            n=int(payload.get("n") or 3),
        )}
    if action == "map_to_scorecard":
        return {"action": action, "result": map_answer_to_scorecard(
            latest_answer=latest_answer,
            scorecard_competencies=payload.get("competencies") or [],
        )}
    if action == "check_question_fairness":
        text = (payload.get("text") or latest_answer).strip()
        flags = check_question(text)
        return {
            "action": action,
            "flags": [f.to_dict() for f in flags],
            "summary": fairness_summary(flags),
        }
    if action == "check_note_fairness":
        text = (payload.get("text") or latest_answer).strip()
        evidence = payload.get("evidence_snippets") or []
        flags = check_scorecard_note(text, evidence_snippets=evidence)
        return {
            "action": action,
            "flags": [f.to_dict() for f in flags],
            "summary": fairness_summary(flags),
        }
    raise HTTPException(status_code=400, detail=f"Unknown assist action: {action!r}")


@router.post("/{interview_id}/follow-up-questions")
async def follow_up_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": suggest_follow_up_questions(
        latest_answer=payload.get("latest_answer") or "",
        competency=payload.get("competency") or "communication",
        asked_already=payload.get("asked_already") or [],
        n=int(payload.get("n") or 3),
    )}


@router.post("/{interview_id}/summarize-answer")
async def summarize_answer_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"summary": summarise_live_answer(payload.get("text") or "")}


@router.post("/{interview_id}/insight")
async def record_insight_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title required")
    ins = InterviewInsight(
        id="",
        interview_id=interview_id,
        type=(payload.get("type") or "info").lower(),
        severity=(payload.get("severity") or "info").lower(),
        title=title,
        description=(payload.get("description") or "").strip(),
        evidence=payload.get("evidence") or [],
        recommended_action=(payload.get("recommended_action") or "").strip(),
    )
    import uuid as _u
    ins.id = str(_u.uuid4())
    return record_insight(interview_id, ins).to_dict()


@router.get("/{interview_id}/insights")
async def list_insights_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    from app.services.interview_copilot_service import list_insights
    return {"items": [i.to_dict() for i in list_insights(interview_id)]}


@router.get("/{interview_id}/transcript-rendered")
async def rendered_transcript_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    """Convenience: full transcript as a single string (for the AI panel)."""
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"transcript": full_transcript(interview_id)}
