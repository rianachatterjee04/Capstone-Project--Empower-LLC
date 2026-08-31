"""Interviews router — Interview Copilot CRUD + scorecards + summary.

Mounted at /api/interviews.  This is the **new** Interview Copilot surface;
the existing /api/ai-interview (solo Web Speech) and /api/interview-loops
(panel orchestration) routers stay untouched.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services.interview_copilot_service import (
    create_interview,
    generate_candidate_specific_questions,
    generate_interview_plan,
    get_interview,
    list_interviews,
    list_questions,
    mark_question_asked,
    update_interview,
)
from app.services.interview_scorecard_service import (
    draft_from_transcript,
    list_scorecards,
    submit_scorecard,
    update_competency,
    upsert_scorecard,
)
from app.services.interview_summary_service import generate_post_interview_summary
from app.services.interview_score_review_service import (
    adjust_review,
    build_explanation,
    open_review,
)
from app.services.interview_transcription_service import (
    full_transcript,
    get_consent,
    list_lines,
    record_consent,
)


router = APIRouter(prefix="/interviews", tags=["interviews"])


def _allowed(actor: Actor) -> bool:
    return actor.role in ("owner", "admin", "hr", "recruiter", "manager")


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
@router.get("")
async def list_endpoint(actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [i.to_dict() for i in list_interviews(actor.org_id)]}


@router.post("")
async def create_endpoint(payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    candidate_name = (payload.get("candidate_name") or "").strip()
    job_title = (payload.get("job_title") or "").strip()
    if not candidate_name or not job_title:
        raise HTTPException(status_code=400, detail="candidate_name and job_title required")
    iv = create_interview(
        org_id=actor.org_id,
        candidate_id=payload.get("candidate_id"),
        candidate_name=candidate_name,
        job_id=payload.get("job_id"),
        job_title=job_title,
        interview_type=(payload.get("interview_type") or "screen").lower(),
        duration_minutes=int(payload.get("duration_minutes") or 60),
        scheduled_at=payload.get("scheduled_at"),
        participants=payload.get("participants") or [],
        created_by=actor.claims.get("email"),
    )
    return iv.to_dict()


@router.get("/{interview_id}")
async def get_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    iv = get_interview(actor.org_id, interview_id)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    return iv.to_dict()


@router.patch("/{interview_id}")
async def patch_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    iv = update_interview(actor.org_id, interview_id, payload)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    return iv.to_dict()


# ---------------------------------------------------------------------------
# Pre-interview prep
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/generate-plan")
async def generate_plan_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    iv = get_interview(actor.org_id, interview_id)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    plan = generate_interview_plan(
        interview_type=iv.interview_type,
        job_title=iv.job_title,
        job_description=payload.get("job_description") or "",
        candidate_summary=payload.get("candidate_summary") or "",
        extracted_skills=payload.get("extracted_skills") or [],
        skill_gaps=payload.get("skill_gaps") or [],
    )
    update_interview(actor.org_id, interview_id, {"interview_plan": plan})
    return plan


@router.post("/{interview_id}/generate-questions")
async def generate_questions_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    iv = get_interview(actor.org_id, interview_id)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    qs = generate_candidate_specific_questions(
        interview_id=interview_id,
        interview_type=iv.interview_type,
        job_title=iv.job_title,
        candidate_summary=payload.get("candidate_summary") or "",
        skill_gaps=payload.get("skill_gaps") or [],
        n_questions=int(payload.get("n_questions") or 7),
    )
    return {"items": [q.to_dict() for q in qs]}


@router.get("/{interview_id}/questions")
async def list_questions_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [q.to_dict() for q in list_questions(interview_id)]}


@router.post("/{interview_id}/questions/{question_id}/asked")
async def mark_asked_endpoint(interview_id: str, question_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    q = mark_question_asked(interview_id, question_id)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return q.to_dict()


# ---------------------------------------------------------------------------
# Consent + transcript (live)
# ---------------------------------------------------------------------------
@router.get("/{interview_id}/consent")
async def get_consent_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return get_consent(interview_id).to_dict()


@router.post("/{interview_id}/consent")
async def record_consent_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    try:
        rec = record_consent(
            interview_id,
            candidate_consent_status=payload.get("candidate_consent_status"),
            interviewer_consent_status=payload.get("interviewer_consent_status"),
            recording_enabled=payload.get("recording_enabled"),
            recorded_by=actor.claims.get("email"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rec.to_dict()


@router.post("/{interview_id}/transcript")
async def push_transcript_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    from app.services.interview_transcription_service import append_line
    line = append_line(
        interview_id,
        speaker=(payload.get("speaker") or "unknown").lower(),
        speaker_name=payload.get("speaker_name"),
        text=(payload.get("text") or "").strip(),
        confidence=float(payload.get("confidence") or 0.85),
    )
    if not line:
        raise HTTPException(status_code=403, detail="Consent not granted — transcript not captured.")
    return line.to_dict()


@router.get("/{interview_id}/transcript")
async def list_transcript_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    lines = list_lines(interview_id)
    return {
        "items": [l.to_dict() for l in lines],
        "rendered": full_transcript(interview_id),
    }


# ---------------------------------------------------------------------------
# Scorecard
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/scorecard")
async def upsert_scorecard_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    competencies = payload.get("competencies") or []
    if not competencies:
        raise HTTPException(status_code=400, detail="competencies required")
    sc = upsert_scorecard(
        interview_id=interview_id,
        interviewer_id=payload.get("interviewer_id") or actor.user_id,
        interviewer_name=payload.get("interviewer_name") or actor.claims.get("email", "Interviewer"),
        competencies=competencies,
    )
    return sc.to_dict()


@router.get("/{interview_id}/scorecard")
async def list_scorecards_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return {"items": [s.to_dict() for s in list_scorecards(interview_id)]}


@router.patch("/{interview_id}/scorecard/{scorecard_id}")
async def patch_competency_endpoint(interview_id: str, scorecard_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    competency = (payload.get("competency") or "").strip()
    if not competency:
        raise HTTPException(status_code=400, detail="competency required")
    sc = update_competency(
        interview_id=interview_id,
        scorecard_id=scorecard_id,
        competency=competency,
        rating=payload.get("rating"),
        notes=payload.get("notes"),
        evidence_snippets=payload.get("evidence_snippets"),
    )
    if not sc:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    return sc.to_dict()


@router.post("/{interview_id}/scorecard/{scorecard_id}/draft")
async def draft_scorecard_endpoint(interview_id: str, scorecard_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    iv = get_interview(actor.org_id, interview_id)
    candidate = iv.candidate_name if iv else "the candidate"
    return {"drafted": draft_from_transcript(
        interview_id=interview_id,
        competencies=payload.get("competencies") or [],
        candidate_name=candidate,
    )}


@router.post("/{interview_id}/scorecard/{scorecard_id}/submit")
async def submit_scorecard_endpoint(interview_id: str, scorecard_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    overall = payload.get("overall_rating")
    rec = payload.get("overall_recommendation")
    conf = payload.get("interviewer_confidence")
    if overall is None or rec is None or conf is None:
        raise HTTPException(status_code=400, detail="overall_rating, overall_recommendation, interviewer_confidence required")
    sc = submit_scorecard(
        interview_id=interview_id,
        scorecard_id=scorecard_id,
        overall_rating=int(overall),
        overall_recommendation=rec,
        interviewer_confidence=int(conf),
    )
    if not sc:
        raise HTTPException(status_code=404, detail="Scorecard not found")
    return sc.to_dict()


# ---------------------------------------------------------------------------
# Explainable scoring + Human-in-the-loop (HITL) recourse
# ---------------------------------------------------------------------------
@router.get("/{interview_id}/score-explanation")
async def score_explanation_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    return build_explanation(actor.org_id, interview_id)


@router.post("/{interview_id}/score-review")
async def open_score_review_endpoint(interview_id: str, payload: dict, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason required")
    return open_review(
        actor.org_id, interview_id,
        dimension=(payload.get("dimension") or "overall"),
        reason=reason,
        requested_by=payload.get("requested_by") or actor.claims.get("email", "requester"),
        requested_by_role=payload.get("requested_by_role") or actor.role,
        original_rating=payload.get("original_rating"),
        scorecard_id=payload.get("scorecard_id"),
    )


@router.patch("/{interview_id}/score-review/{review_id}")
async def adjust_score_review_endpoint(interview_id: str, review_id: str, payload: dict, actor: Actor = Depends(require_org)):
    # Only calibrated reviewers may adjust a score.
    if actor.role not in ("owner", "admin", "hr", "manager"):
        raise HTTPException(status_code=403, detail="Only HR/manager reviewers may adjust a score")
    reason = (payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="reason required for an audit-traceable adjustment")
    out = adjust_review(
        actor.org_id, interview_id, review_id,
        reviewer=payload.get("reviewer") or actor.claims.get("email", "reviewer"),
        adjusted_rating=payload.get("adjusted_rating"),
        reason=reason,
    )
    if not out:
        raise HTTPException(status_code=404, detail="Score review not found")
    return out


# ---------------------------------------------------------------------------
# Post-interview
# ---------------------------------------------------------------------------
@router.post("/{interview_id}/post-summary")
async def post_summary_endpoint(interview_id: str, actor: Actor = Depends(require_org)):
    if not _allowed(actor):
        raise HTTPException(status_code=403, detail="Not allowed")
    iv = get_interview(actor.org_id, interview_id)
    if not iv:
        raise HTTPException(status_code=404, detail="Interview not found")
    return generate_post_interview_summary(
        interview_id=interview_id,
        candidate_name=iv.candidate_name,
        job_title=iv.job_title,
    )
