"""HTTP surface for the evidence-backed interviewer.

Named `interview_v2` because the older interview routers stay where they are:
they have their own consumers, and replacing them in the same commit as a new
domain would make the diff impossible to review. Nothing here imports them.

EVERY HANDLER TAKES actor.org_id AND PASSES IT DOWN.
The repository refuses to read or write without it. service_role bypasses RLS,
so the tenant filter in the query is the control, not a backstop.

The playback endpoint is the one that matters commercially: it returns the
scorecard, the debrief, the transcript and the evidence with millisecond
offsets, all bound together, so the recruiter UI can turn any assessment into
a click that starts the video at the moment the candidate said it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, db_session, require_org
from app.db.models import Candidate, JobPosting
from app.interview import dto as DTO
from app.interview import media as MED
from app.interview import models as M
from app.interview import repository as R
from app.interview import runner

router = APIRouter(prefix="/interview-v2", tags=["interview-v2"])

ADMIN_ROLES = ("owner", "admin", "hr", "recruiter")


async def _require_interview(db, actor, interview_id):
    """Resolve an interview inside the CALLER's org, or 404.

    Every interview-scoped endpoint goes through this, so "not yours" has one
    answer instead of four. Before it there were four:

      start       409, sharing an exception type with "consent was withdrawn",
                  so a caller could not tell a tenancy refusal from a consent
                  problem.
      next        200 {"finished": true} -- the plan loaded empty because the
                  query is org-scoped, and the handler read that as "this
                  interview is over".
      alignment   200, a full zero-valued report on someone else's interview.
      finalise    500. load_plan returned None and the next line took .id off
                  it. An unhandled AttributeError on a tenancy boundary is the
                  worst of the four: it is indistinguishable from the server
                  being broken, and what it prints depends on configuration.

    No content ever leaked -- every underlying query is scoped by org, which is
    why they came back empty rather than full. This is about giving the boundary
    one honest answer.

    404 rather than 403: "that exists but is not yours" confirms the interview
    exists, which tells a competitor this candidate is being interviewed.
    """
    interview = await R.get_interview(db, org_id=actor.org_id,
                                      interview_id=interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview



def _require_recruiter(actor: Actor) -> None:
    if getattr(actor, "role", None) not in ADMIN_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Interview administration is limited to HR and recruiters")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ConsentIn(BaseModel):
    candidate_id: UUID
    disclosure_text: str = Field(min_length=20)
    policy_version: str = "2026.08"
    interview: bool = True
    audio: bool = True
    video: bool = True
    transcript: bool = True
    ai_analysis: bool = True


class PrepareIn(BaseModel):
    job_posting_id: UUID
    candidate_id: UUID
    consent_id: Optional[UUID] = None
    role_config: Optional[Dict[str, Any]] = None


class AnswerIn(BaseModel):
    question_id: UUID
    answer_text: str
    attempt_id: Optional[UUID] = None
    recording_start_ms: Optional[int] = None
    recording_end_ms: Optional[int] = None


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

@router.post("/consent")
async def record_consent(payload: ConsentIn, actor: Actor = Depends(require_org),
                         db: AsyncSession = Depends(db_session)) -> dict:
    """Record consent. Separate grants, because consenting to be interviewed
    is not consenting to be recorded."""
    row = await R.create_consent(
        db, org_id=actor.org_id, candidate_id=payload.candidate_id,
        disclosure_text=payload.disclosure_text,
        policy_version=payload.policy_version,
        interview=payload.interview, audio=payload.audio, video=payload.video,
        transcript=payload.transcript, ai_analysis=payload.ai_analysis)
    await db.commit()
    return {"consent_id": str(row.id), "granted_at": row.granted_at.isoformat(),
            "permits_recording": row.permits_recording}


@router.post("/prepare")
async def prepare(payload: PrepareIn, actor: Actor = Depends(require_org),
                  db: AsyncSession = Depends(db_session)) -> dict:
    """Extract claims, build the plan, persist both."""
    _require_recruiter(actor)

    res = await db.execute(select(Candidate).where(
        Candidate.org_id == actor.org_id, Candidate.id == payload.candidate_id))
    candidate = res.scalar_one_or_none()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")

    jres = await db.execute(select(JobPosting).where(
        JobPosting.org_id == actor.org_id,
        JobPosting.id == payload.job_posting_id))
    job = jres.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job posting not found")

    if not (candidate.resume_text or "").strip():
        raise HTTPException(
            status_code=422,
            detail=("This candidate has no resume text. The interview would "
                    "have nothing candidate-specific to ask about, and a "
                    "generic interview is not what this product does."))

    out = await runner.prepare(
        db, org_id=actor.org_id, job_posting_id=job.id,
        candidate_id=candidate.id, job_title=job.title,
        resume_text=candidate.resume_text or "",
        role_config=payload.role_config, consent_id=payload.consent_id)
    await db.commit()

    plan = out["plan"]
    return {
        "interview_id": str(out["interview"].id),
        "rubric": plan.rubric_key,
        "coverage": plan.coverage(),
        "claims_extracted": len(out["claims"]),
        "competencies": [
            {"key": c.competency_key, "label": c.competency_label,
             "required": c.is_required, "weight": c.role_weight,
             "hook": c.candidate_hook,
             "question": c.initial_question}
            for c in plan.competencies],
    }


@router.post("/{interview_id}/start")
async def start(interview_id: UUID, actor: Actor = Depends(require_org),
                db: AsyncSession = Depends(db_session)) -> dict:
    await _require_interview(db, actor, interview_id)
    try:
        attempt = await runner.start(db, org_id=actor.org_id,
                                     interview_id=interview_id)
    except runner.InterviewNotFound:
        raise HTTPException(status_code=404, detail="Interview not found")
    except runner.ConsentMissing as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await db.commit()
    return {"attempt_id": str(attempt.id),
            "attempt_number": attempt.attempt_number}


# ---------------------------------------------------------------------------
# The conversation
# ---------------------------------------------------------------------------

@router.get("/{interview_id}/next")
async def next_question(interview_id: UUID, attempt_id: Optional[UUID] = None,
                        actor: Actor = Depends(require_org),
                        db: AsyncSession = Depends(db_session)) -> dict:
    """The next question.

    THE RESPONSE DEPENDS ON WHO IS ASKING. A candidate gets the question and a
    flag saying whether it is a follow-up. Staff additionally get the
    competency, the probe depth and the intent -- which is live-monitoring
    information and is also, to a candidate, a running commentary on how they
    are doing.
    """
    await _require_interview(db, actor, interview_id)
    step = await runner.next_question(db, org_id=actor.org_id,
                                      interview_id=interview_id,
                                      attempt_id=attempt_id)
    await db.commit()
    staff = getattr(actor, "role", None) in ADMIN_ROLES

    # Every candidate branch goes through candidate_safe, including the ones
    # that are obviously fine today. The point of a boundary is that it holds
    # when someone adds a field in a hurry, and a branch that bypasses it is
    # exactly where that field will be added. `step.reason` is staff-only: it
    # names why the runner has no question, which is internal state.
    if step.finished:
        return (DTO.candidate_safe(
                    {"finished": True,
                     "message": "That's everything — thank you."})
                if not staff else
                {"finished": True, "reason": step.reason})
    if not step.has_question:
        return (DTO.candidate_safe({"finished": False, "waiting": True})
                if not staff else
                {"finished": False, "waiting": True, "reason": step.reason})

    q = step.question
    if not staff:
        return DTO.candidate_safe({"finished": False,
                                   "question": DTO.candidate_question(q)})

    return {"finished": False, "question": {
        "id": str(q.id), "text": q.question_text, "kind": q.question_kind,
        "sequence": q.sequence_number, "probe_depth": q.probe_depth,
        "competency_id": str(q.competency_id) if q.competency_id else None}}


@router.post("/{interview_id}/answer")
async def answer(interview_id: UUID, payload: AnswerIn,
                 actor: Actor = Depends(require_org),
                 db: AsyncSession = Depends(db_session)) -> dict:
    try:
        out = await runner.submit_answer(
            db, org_id=actor.org_id, interview_id=interview_id,
            question_id=payload.question_id, answer_text=payload.answer_text,
            attempt_id=payload.attempt_id,
            recording_start_ms=payload.recording_start_ms,
            recording_end_ms=payload.recording_end_ms)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    await db.commit()

    # THE AUDIENCE BOUNDARY.
    # This used to return the gap analysis to everyone and rely on the
    # candidate UI to ignore it. Anyone with DevTools then saw which
    # competency was being probed, that their last answer read as vague, and
    # how much evidence it produced -- enough to game the rest of the
    # interview. Hiding it in React is not a control.
    if getattr(actor, "role", None) not in ADMIN_ROLES:
        return DTO.candidate_answer_ack(out["answer"])

    an = out["analysis"]
    return {
        "answer_id": str(out["answer"].id),
        "evidence_captured": len(out["evidence"]),
        "recruiter_view": {
            "substantive": an.is_substantive,
            "specific": an.is_specific,
            "ownership_clear": an.ownership_is_clear,
            "gaps": an.gaps,
        },
    }


@router.post("/{interview_id}/finalise")
async def finalise(interview_id: UUID, actor: Actor = Depends(require_org),
                   db: AsyncSession = Depends(db_session)) -> dict:
    _require_recruiter(actor)
    await _require_interview(db, actor, interview_id)
    out = await runner.finalise(db, org_id=actor.org_id,
                                interview_id=interview_id)
    await db.commit()
    card = out["scorecard"]
    return {
        "overall_state": card.overall_state,
        "overall_score": card.overall_score,
        "overall_confidence": card.overall_confidence,
        "completeness": card.completeness_state,
        "uncovered_required": card.uncovered_required,
        "decision_authority": card.decision_authority,
    }


# ---------------------------------------------------------------------------
# Recruiter playback -- the commercial surface
# ---------------------------------------------------------------------------

@router.get("/{interview_id}/playback")
async def playback(interview_id: UUID, actor: Actor = Depends(require_org),
                   db: AsyncSession = Depends(db_session)) -> dict:
    """Everything the recruiter review page needs, bound together.

    Assessments carry the evidence ids that support them; evidence carries the
    quote and the millisecond offset. That join is what turns a score into a
    click into the recording.
    """
    _require_recruiter(actor)

    interview = await R.get_interview(db, org_id=actor.org_id,
                                      interview_id=interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    cres = await db.execute(select(Candidate).where(
        Candidate.org_id == actor.org_id, Candidate.id == interview.candidate_id))
    candidate = cres.scalar_one_or_none()
    jres = await db.execute(select(JobPosting).where(
        JobPosting.org_id == actor.org_id,
        JobPosting.id == interview.job_posting_id))
    job = jres.scalar_one_or_none()

    plan = await R.load_plan(db, org_id=actor.org_id, interview_id=interview_id)
    comps = (await R.load_competencies(db, org_id=actor.org_id, plan_id=plan.id)
             if plan else [])
    labels = {c.competency_key: c.competency_label for c in comps}

    qa = await R.load_qa(db, org_id=actor.org_id, interview_id=interview_id)
    evidence = await R.load_evidence(db, org_id=actor.org_id,
                                     interview_id=interview_id)

    ares = await db.execute(select(M.CompetencyAssessment).where(
        M.CompetencyAssessment.org_id == actor.org_id,
        M.CompetencyAssessment.interview_id == interview_id))
    assessments = list(ares.scalars().all())

    link_rows = (await db.execute(text("""
        SELECT ae.assessment_id, ae.evidence_id, ae.role
        FROM public.assessment_evidence ae
        JOIN public.competency_assessments ca ON ca.id = ae.assessment_id
        WHERE ca.interview_id = :i AND ca.org_id = :o"""),
        {"i": interview_id, "o": actor.org_id})).all()
    links: Dict[str, List[dict]] = {}
    for assessment_id, evidence_id, role in link_rows:
        links.setdefault(str(assessment_id), []).append(
            {"evidence_id": str(evidence_id), "role": role})

    sres = await db.execute(select(M.InterviewScorecard).where(
        M.InterviewScorecard.org_id == actor.org_id,
        M.InterviewScorecard.interview_id == interview_id))
    card = sres.scalar_one_or_none()

    dres = await db.execute(select(M.InterviewSummary).where(
        M.InterviewSummary.org_id == actor.org_id,
        M.InterviewSummary.interview_id == interview_id))
    debrief = dres.scalar_one_or_none()

    tres = await db.execute(select(M.TranscriptSegment).where(
        M.TranscriptSegment.org_id == actor.org_id,
        M.TranscriptSegment.interview_id == interview_id,
        M.TranscriptSegment.is_current.is_(True)
    ).order_by(M.TranscriptSegment.sequence_number))
    transcript = list(tres.scalars().all())

    rres = await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.org_id == actor.org_id,
        M.RecordingAsset.interview_id == interview_id,
        M.RecordingAsset.deleted_at.is_(None)
    ).order_by(M.RecordingAsset.part_number))
    recordings = list(rres.scalars().all())

    vres = await db.execute(text("""
        SELECT cv.verdict, cv.established_text, cv.rationale, cv.confidence,
               cc.claim_text, cc.source_excerpt, cc.source_kind, cc.claim_type
        FROM public.claim_verifications cv
        JOIN public.candidate_claims cc ON cc.id = cv.claim_id
        WHERE cv.interview_id = :i AND cv.org_id = :o"""),
        {"i": interview_id, "o": actor.org_id})

    return {
        "interview": {
            "id": str(interview.id), "status": interview.status,
            "mode": interview.mode,
            "candidate": {"id": str(candidate.id), "name": candidate.full_name}
            if candidate else None,
            "job": {"id": str(job.id), "title": job.title} if job else None,
        },
        "scorecard": {
            "overall_state": card.overall_state,
            "overall_score": float(card.overall_score) if card and card.overall_score is not None else None,
            "overall_confidence": float(card.overall_confidence) if card and card.overall_confidence is not None else None,
            "completeness": card.completeness_state,
            "uncovered_required": card.uncovered_required,
            "decision_authority": card.decision_authority,
            "rubric": f"{card.rubric_key} {card.rubric_version}",
        } if card else None,
        "assessments": [{
            "id": str(a.id), "competency_key": a.competency_key,
            "label": labels.get(a.competency_key, a.competency_key),
            "state": a.state,
            "score": float(a.score) if a.score is not None else None,
            "confidence": float(a.confidence) if a.confidence is not None else None,
            "rationale": a.rationale, "missing_evidence": a.missing_evidence,
            "evidence": links.get(str(a.id), []),
        } for a in assessments],
        "evidence": [{
            "id": str(e.id), "competency_key": e.competency_key,
            "polarity": e.polarity, "kind": e.evidence_kind,
            "quote": e.quote, "rationale": e.rationale,
            "strength": float(e.strength),
            "start_ms": e.quote_start_ms, "end_ms": e.quote_end_ms,
            "answer_id": str(e.answer_id),
        } for e in evidence],
        "conversation": [{
            "question_id": str(q.id), "sequence": q.sequence_number,
            "kind": q.question_kind, "probe_depth": q.probe_depth,
            "question": q.question_text, "intent": q.intent,
            "competency_id": str(q.competency_id) if q.competency_id else None,
            "answer": ({"id": str(a.id), "text": a.answer_text,
                        "start_ms": a.recording_start_ms,
                        "end_ms": a.recording_end_ms,
                        "substantive": a.is_substantive} if a else None),
        } for q, a in qa],
        "plan": [{
            "key": c.competency_key, "label": c.competency_label,
            "why": c.why_it_matters, "hook": c.candidate_hook,
            "required": c.is_required, "weight": float(c.role_weight),
        } for c in comps],
        "claim_verifications": [{
            "verdict": r[0], "established": r[1], "rationale": r[2],
            "confidence": float(r[3]) if r[3] is not None else None,
            "claim": r[4], "source_excerpt": r[5], "source_kind": r[6],
            "claim_type": r[7],
        } for r in vres],
        "debrief": {
            "headline": debrief.headline,
            "overall_assessment": debrief.overall_assessment,
            "strengths": debrief.strengths,
            "weaknesses": debrief.weaknesses,
            # The list is stored on the row; forgetting it here would have
            # made a competency assessed, persisted, and still absent from the
            # page -- which is the defect the column was added to fix.
            "also_assessed": getattr(debrief, "also_assessed", None) or [],
            "contradictions": debrief.contradictions,
            "unresolved_questions": debrief.unresolved_questions,
            "recommended_followup": debrief.recommended_followup,
        } if debrief else None,
        "transcript": [{
            "id": str(t.id), "speaker": t.speaker, "sequence": t.sequence_number,
            "start_ms": t.start_ms, "end_ms": t.end_ms, "text": t.text,
            "source": t.source, "revision": t.revision,
            # HOW THIS TEXT WAS OBTAINED.
            # `source` says ASR; it does not say whether the candidate's own
            # browser produced the text and posted it, or the server read it
            # off the stored media. An assessment cites these segments as
            # evidence, so the difference belongs in front of whoever is
            # relying on it. NULL means unrecorded, not "the good one".
            "asr_adapter": t.asr_adapter,
            "asr_confidence": (float(t.asr_confidence)
                               if t.asr_confidence is not None else None),
        } for t in transcript],
        "transcript_provenance": _transcript_provenance(transcript),
        # NO `storage_ref`. It was in this payload, so every recruiter's
        # browser received an absolute server filesystem path -- the media
        # root, the organisation's UUID and the interview's UUID as a
        # directory tree. The client needs a URL it can fetch, and
        # `storage_kind` is the only part of the storage arrangement it has
        # any business knowing.
        # WHETHER THE MEDIA IS THE WHOLE RECORDING.
        # Without this a recruiter sees a player either way, and a recording
        # missing the answer an assessment rests on looks identical to a
        # complete one.
        "recording_completeness": MED.assess_completeness(
            recordings, interview.recording_parts_expected).as_dict(),
        "recordings": [{
            "id": str(r.id), "media_kind": r.media_kind, "part": r.part_number,
            "storage_kind": r.storage_kind,
            "href": (f"/api/interview-v2/{interview_id}/media/"
                     f"{r.part_number}"),
            "duration_ms": r.duration_ms,
            "timeline_offset_ms": r.timeline_offset_ms,
        } for r in recordings],
    }


@router.get("/list")
async def list_interviews(status: Optional[str] = None,
                          limit: int = 50,
                          actor: Actor = Depends(require_org),
                          db: AsyncSession = Depends(db_session)) -> dict:
    """Every interview in this organisation, with enough to decide what to open.

    WHY THIS EXISTS
    Nothing in the application linked to the review page. The recruiter surface
    the whole product is built around -- the scorecard, the evidence, the
    recording -- was reachable only by typing a UUID into the address bar.

    Each row carries the scorecard's completeness and decision authority, not
    just the score, because "2.3/4 on an INCOMPLETE interview" and "2.3/4 on a
    complete one" are different things to open.
    """
    _require_recruiter(actor)
    limit = max(1, min(int(limit), 200))

    where = "i.org_id = :o"
    params: Dict[str, Any] = {"o": actor.org_id}
    if status:
        where += " AND i.status = :s"
        params["s"] = status.upper()

    rows = (await db.execute(text(f"""
        SELECT i.id, i.status, i.mode, i.started_at, i.ended_at,
               i.created_at,
               c.full_name, c.email,
               j.title AS job_title,
               sc.overall_score, sc.overall_confidence, sc.overall_state,
               sc.completeness_state, sc.uncovered_required,
               sc.rubric_key, sc.decision_authority,
               (SELECT count(*) FROM public.recording_assets r
                 WHERE r.interview_id = i.id AND r.org_id = i.org_id
                   AND r.deleted_at IS NULL) AS recording_parts,
               (SELECT count(*) FROM public.interview_questions q
                 WHERE q.interview_id = i.id AND q.org_id = i.org_id)
                 AS questions
        FROM public.interviews i
        JOIN public.candidates c ON c.id = i.candidate_id AND c.org_id = i.org_id
        JOIN public.job_postings j
          ON j.id = i.job_posting_id AND j.org_id = i.org_id
        LEFT JOIN public.interview_scorecards sc
          ON sc.interview_id = i.id AND sc.org_id = i.org_id
        WHERE {where}
        ORDER BY i.created_at DESC
        LIMIT {limit}"""), params)).mappings().all()

    def row(r):
        return {
            "id": str(r["id"]),
            "candidate": r["full_name"],
            "email": r["email"],
            "job_title": r["job_title"],
            "status": r["status"],
            "mode": r["mode"],
            "questions": r["questions"],
            "recording_parts": r["recording_parts"],
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "ended_at": r["ended_at"].isoformat() if r["ended_at"] else None,
            "score": (float(r["overall_score"])
                      if r["overall_score"] is not None else None),
            "confidence": (float(r["overall_confidence"])
                           if r["overall_confidence"] is not None else None),
            "overall_state": r["overall_state"],
            "completeness_state": r["completeness_state"],
            "uncovered_required": r["uncovered_required"] or [],
            "rubric_key": r["rubric_key"],
            "decision_authority": r["decision_authority"],
            # NO UI ROUTES HERE. The API used to return
            # `review_href: "/app/interview-review/{id}"`, which puts the
            # frontend's routing table inside the backend and makes a page
            # unreachable-looking to any tool that scans the frontend for
            # links -- because the only place the path appears is a server
            # response. The client owns its own routes.
        }

    return {
        "interviews": [row(r) for r in rows],
        "note": ("A score is decision support for a recruiter, never a hiring "
                 "decision. An INCOMPLETE interview did not establish "
                 "everything the rubric asks for, and its overall figure is "
                 "not comparable with a complete one."),
    }


@router.get("/compare")
async def compare(job_posting_id: UUID, actor: Actor = Depends(require_org),
                  db: AsyncSession = Depends(db_session)) -> dict:
    """Candidates for one role, side by side.

    Compared on the same competencies, while being explicit that the QUESTIONS
    differed -- that is the consequence of a personalised interview and hiding
    it would make the comparison look more like-for-like than it is.
    """
    _require_recruiter(actor)

    rows = (await db.execute(text("""
        SELECT i.id, c.full_name, ca.competency_key, ca.state, ca.score,
               ca.confidence, sc.completeness_state, sc.overall_score,
               sc.overall_confidence
        FROM public.interviews i
        JOIN public.candidates c ON c.id = i.candidate_id
        LEFT JOIN public.competency_assessments ca ON ca.interview_id = i.id
        LEFT JOIN public.interview_scorecards sc ON sc.interview_id = i.id
        WHERE i.org_id = :o AND i.job_posting_id = :j
        ORDER BY c.full_name, ca.competency_key"""),
        {"o": actor.org_id, "j": job_posting_id})).all()

    people: Dict[str, dict] = {}
    for (iv_id, name, key, state, score, conf, completeness,
         overall, overall_conf) in rows:
        p = people.setdefault(str(iv_id), {
            "interview_id": str(iv_id), "candidate": name,
            "completeness": completeness,
            "overall_score": float(overall) if overall is not None else None,
            "overall_confidence": float(overall_conf) if overall_conf is not None else None,
            "competencies": {}})
        if key:
            p["competencies"][key] = {
                "state": state,
                "score": float(score) if score is not None else None,
                "confidence": float(conf) if conf is not None else None}

    return {
        "candidates": list(people.values()),
        "note": ("Candidates are compared on the same competencies. The "
                 "QUESTIONS differed, because each interview was built from "
                 "that candidate's own claims. A competency showing "
                 "INSUFFICIENT_EVIDENCE was not established by the interview "
                 "and is not a low score."),
        "decision_authority": "RECRUITER_DECISION_SUPPORT",
    }


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

@router.get("/media/capability")
async def media_capability(actor: Actor = Depends(require_org)) -> dict:
    """What this deployment can actually capture and transcribe.

    The UI reads this to decide what to tell the candidate. It must never
    imply a capability that is absent: a decorative red dot over a recorder
    that is not running is the specific lie this endpoint prevents.
    """
    return {
        "storage_kind": MED.storage_kind(),
        "storage_is_durable": MED.storage_kind() in (MED.LOCAL_FILE,
                                                     MED.OBJECT_STORE),
        "accepted_containers": sorted({m.split(";")[0]
                                       for m in MED.ALLOWED_MIME}),
        "max_part_bytes": MED.MAX_PART_BYTES,
        "asr": MED.asr_status(),
        "container_repair": {
            "webm_duration_written": True,
            "note": ("MediaRecorder writes a LIVE WebM: unknown-size Segment, "
                     "no Cues, no Duration. A browser loading one reports "
                     "duration = Infinity, which means no scrubber and no "
                     "dependable seek. The duration the browser measured is "
                     "written into the container on upload so the recruiter "
                     "player can scrub and seek. There is still no Cues "
                     "index, so a long backward seek may rescan clusters."),
        },
        "note": ("Media is captured by the browser and uploaded here. "
                 "storage_kind says where it actually lands; nothing claims "
                 "object storage unless it is configured."),
    }


@router.post("/{interview_id}/media")
async def upload_media(interview_id: UUID,
                       file: UploadFile = File(...),
                       media_kind: str = Form("VIDEO"),
                       part_number: int = Form(1),
                       timeline_offset_ms: int = Form(0),
                       duration_ms: Optional[int] = Form(None),
                       attempt_id: Optional[UUID] = Form(None),
                       actor: Actor = Depends(require_org),
                       db: AsyncSession = Depends(db_session)) -> dict:
    """Store one captured part.

    CONSENT IS CHECKED HERE TOO, not only at interview start. Consenting to be
    interviewed is not consenting to be recorded, and the two are separate
    grants on the consent row precisely so this can refuse.
    """
    # FastAPI resolves Form() defaults during request handling. Called
    # directly -- which the tests do, and which any internal caller might --
    # the raw Form sentinel arrives instead of None and reaches the database
    # as a bogus UUID. Coerce rather than require every caller to know that.
    if not isinstance(attempt_id, UUID):
        attempt_id = None
    if not isinstance(duration_ms, int):
        duration_ms = None
    if not isinstance(part_number, int):
        part_number = 1
    if not isinstance(timeline_offset_ms, int):
        timeline_offset_ms = 0
    if not isinstance(media_kind, str):
        media_kind = "VIDEO"

    interview = await R.get_interview(db, org_id=actor.org_id,
                                      interview_id=interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    consent = None
    if interview.consent_id:
        res = await db.execute(select(M.InterviewConsent).where(
            M.InterviewConsent.org_id == actor.org_id,
            M.InterviewConsent.id == interview.consent_id))
        consent = res.scalar_one_or_none()

    if consent is None or not consent.permits_recording:
        raise HTTPException(
            status_code=409,
            detail=("this candidate has not consented to being recorded. "
                    "Consenting to be interviewed is a separate grant, and "
                    "this refusal is what makes that separation real."))
    wanted = "consent_video" if media_kind == "VIDEO" else "consent_audio"
    if not getattr(consent, wanted, False):
        raise HTTPException(
            status_code=409,
            detail=f"the candidate did not consent to {media_kind.lower()} capture")

    data = await file.read()

    # WRITE THE DURATION INTO THE CONTAINER BEFORE STORING IT.
    # MediaRecorder writes a LIVE WebM: unknown-size Segment, no Cues, no
    # Duration. A browser loading it reports `video.duration === Infinity`,
    # which means no scrubber and no dependable seek -- and the recruiter
    # debrief is built entirely around "click any assessment and the recording
    # seeks to the moment the candidate said it".
    #
    # The browser already measured the duration and sends it with the part.
    # Writing it in here is the difference between a stored file and a
    # playable one. `ensure_webm_duration` returns the bytes untouched
    # whenever it is not confident: a recording that plays without a scrubber
    # is a limitation, a recording corrupted by a hopeful muxer is a lost
    # interview.
    repair = MED.ensure_webm_duration(data, duration_ms)
    data = repair.data

    try:
        stored = MED.store_part(
            org_id=actor.org_id, interview_id=interview_id, data=data,
            mime_type=file.content_type or "video/webm",
            media_kind=media_kind, part_number=part_number,
            timeline_offset_ms=timeline_offset_ms, duration_ms=duration_ms)
    except MED.MediaRefused as exc:
        status = 409 if exc.code == "PART_ALREADY_EXISTS" else 422
        raise HTTPException(status_code=status,
                            detail={"code": exc.code, "detail": exc.detail})

    row = M.RecordingAsset(org_id=actor.org_id, interview_id=interview_id,
                           **stored.as_row(attempt_id=attempt_id))
    db.add(row)
    await R.record_event(db, org_id=actor.org_id, interview_id=interview_id,
                         attempt_id=attempt_id, event_type="MEDIA_STORED",
                         actor_kind="CANDIDATE",
                         payload={"part": part_number, "bytes": stored.byte_size,
                                  "sha256": stored.sha256,
                                  "storage_kind": stored.storage_kind})
    # A PART ARRIVING AFTER THE SEAL RE-OPENS THE QUESTION.
    # It happens legitimately -- a retry that finally succeeds, a reconnect --
    # and it also happens when something is wrong. Either way the recording is
    # no longer what it was sealed as, so the state is recomputed against the
    # count it was sealed with rather than left saying SEALED.
    await db.flush()
    verdict = await _refresh_recording_state(db, actor.org_id, interview)
    await db.commit()

    return {"recording_id": str(row.id), "part_number": stored.part_number,
            "byte_size": stored.byte_size, "sha256": stored.sha256,
            "storage_kind": stored.storage_kind,
            "recording": verdict.as_dict(),
            "container": {
                "duration_repaired": repair.changed,
                "duration_is_authoritative": repair.duration_is_authoritative,
                "note": repair.reason,
            }}


class TranscriptIn(BaseModel):
    """Results the browser's SpeechRecognition produced during the call."""
    results: List[Dict[str, Any]]
    attempt_id: Optional[UUID] = None
    recording_part: int = 1
    answer_id: Optional[UUID] = None


@router.post("/{interview_id}/transcript")
async def submit_transcript(interview_id: UUID, payload: TranscriptIn,
                            actor: Actor = Depends(require_org),
                            db: AsyncSession = Depends(db_session)) -> dict:
    """Persist transcript segments and bind them to the recording part.

    The binding is what makes a later click work: a segment carries the
    recording_asset_id it belongs to, so the player knows which file to open
    as well as where to seek.
    """
    interview = await R.get_interview(db, org_id=actor.org_id,
                                      interview_id=interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    res = await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.org_id == actor.org_id,
        M.RecordingAsset.interview_id == interview_id,
        M.RecordingAsset.part_number == payload.recording_part))
    part = res.scalar_one_or_none()

    drafts = MED.BrowserSpeechAdapter().transcribe(results=payload.results)

    base = (await db.execute(select(M.TranscriptSegment.sequence_number).where(
        M.TranscriptSegment.org_id == actor.org_id,
        M.TranscriptSegment.interview_id == interview_id)
        .order_by(M.TranscriptSegment.sequence_number.desc()).limit(1))
    ).scalar_one_or_none() or 0

    saved = []
    for d in drafts:
        seg = M.TranscriptSegment(
            org_id=actor.org_id, interview_id=interview_id,
            attempt_id=payload.attempt_id, answer_id=payload.answer_id,
            recording_asset_id=part.id if part else None,
            speaker=d.speaker, sequence_number=base + d.sequence_number,
            start_ms=d.start_ms, end_ms=d.end_ms, text=d.text,
            asr_confidence=d.asr_confidence, source=d.source,
            asr_adapter=d.adapter)
        db.add(seg)
        saved.append(seg)
    await db.commit()

    return {"segments": len(saved),
            "bound_to_recording": str(part.id) if part else None,
            "adapter": MED.BrowserSpeechAdapter().name,
            "note": ("bound_to_recording is null when no media has been "
                     "uploaded yet; those segments are a transcript but not "
                     "aligned evidence.")}


async def _refresh_recording_state(db, org_id, interview, *,
                                   expected=None):
    """Recompute the interview's recording state from what is actually held."""
    res = await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.org_id == org_id,
        M.RecordingAsset.interview_id == interview.id,
        M.RecordingAsset.deleted_at.is_(None)))
    parts = res.scalars().all()
    want = expected if expected is not None else interview.recording_parts_expected
    verdict = MED.assess_completeness(parts, want)
    interview.recording_state = verdict.state
    interview.recording_state_detail = verdict.detail

    # PERSIST THE COUNT WHATEVER THE VERDICT.
    # The first version stored it only on SEALED, so a client sealing with a
    # count that did NOT match got INCOMPLETE in the response and the row kept
    # its old expectation -- and the very next read recomputed the recording as
    # complete. The reported state has to be the stored state, or the
    # discrepancy disappears the moment anybody looks again.
    if expected is not None:
        interview.recording_parts_expected = int(expected)
        if interview.recording_sealed_at is None:
            interview.recording_sealed_at = datetime.now(timezone.utc)
    return verdict


@router.post("/{interview_id}/recording/seal")
async def seal_recording(interview_id: UUID,
                         payload: Dict[str, Any],
                         actor: Actor = Depends(require_org),
                         db: AsyncSession = Depends(db_session)) -> dict:
    """The client states how many parts it produced; the server checks.

    WHY SEALING IS AN EXPLICIT STEP
    A part that never reached the server leaves no trace on the server, so the
    browser is the only party that can say "that was all of them". Until it
    does, the state is CAPTURING -- holding three parts is not holding all the
    parts, and a recording that quietly counts itself complete is how an
    assessment ends up defended by media that is missing the answer it rests
    on.

    Sealing is idempotent and it is NOT a promise: if the count does not match
    what is held, the recording is marked INCOMPLETE with the missing part
    numbers named, and the recruiter's player refuses to seek into the gaps.
    """
    interview = await R.get_interview(db, org_id=actor.org_id,
                                      interview_id=interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    raw = payload.get("parts_expected")
    if raw is None:
        raise HTTPException(
            status_code=422,
            detail=("parts_expected is required. Sealing without it would be "
                    "the server deciding a recording is complete because it "
                    "cannot see what is missing."))
    try:
        expected = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422,
                            detail="parts_expected must be a whole number")
    if expected < 0:
        raise HTTPException(status_code=422,
                            detail="parts_expected cannot be negative")

    verdict = await _refresh_recording_state(db, actor.org_id, interview,
                                             expected=expected)
    await R.record_event(db, org_id=actor.org_id, interview_id=interview_id,
                         event_type="RECORDING_SEALED", actor_kind="CANDIDATE",
                         payload=verdict.as_dict())
    await db.commit()
    return {"interview_id": str(interview_id), **verdict.as_dict()}


@router.get("/{interview_id}/recording")
async def recording_state(interview_id: UUID,
                          actor: Actor = Depends(require_org),
                          db: AsyncSession = Depends(db_session)) -> dict:
    """What is held, and whether it is the whole thing."""
    _require_recruiter(actor)
    interview = await R.get_interview(db, org_id=actor.org_id,
                                      interview_id=interview_id)
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")

    res = await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.org_id == actor.org_id,
        M.RecordingAsset.interview_id == interview_id,
        M.RecordingAsset.deleted_at.is_(None)).order_by(
            M.RecordingAsset.part_number))
    parts = res.scalars().all()
    verdict = MED.assess_completeness(parts,
                                      interview.recording_parts_expected)
    return {
        "interview_id": str(interview_id),
        **verdict.as_dict(),
        "sealed_at": (interview.recording_sealed_at.isoformat()
                      if interview.recording_sealed_at else None),
        "parts": [{
            "part": p.part_number, "media_kind": p.media_kind,
            "byte_size": p.byte_size, "duration_ms": p.duration_ms,
            "timeline_offset_ms": p.timeline_offset_ms,
            "href": f"/api/interview-v2/{interview_id}/media/{p.part_number}",
        } for p in parts],
    }


@router.get("/{interview_id}/alignment")
async def alignment(interview_id: UUID, actor: Actor = Depends(require_org),
                    db: AsyncSession = Depends(db_session)) -> dict:
    """Do the transcript offsets land inside the recorded media?

    This is the difference between a timestamp and an alignment, reported
    rather than assumed. A recruiter should be able to see that the evidence
    links were checked against the artifact.
    """
    _require_recruiter(actor)
    await _require_interview(db, actor, interview_id)

    segs = list((await db.execute(select(M.TranscriptSegment).where(
        M.TranscriptSegment.org_id == actor.org_id,
        M.TranscriptSegment.interview_id == interview_id,
        M.TranscriptSegment.is_current.is_(True))
        .order_by(M.TranscriptSegment.sequence_number))).scalars().all())
    parts = list((await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.org_id == actor.org_id,
        M.RecordingAsset.interview_id == interview_id,
        M.RecordingAsset.deleted_at.is_(None)))).scalars().all())

    problems = MED.verify_alignment(segs, parts)
    return {
        "segments": len(segs),
        "recording_parts": len(parts),
        "aligned": not problems and bool(segs) and bool(parts),
        "problems": [{"segment_index": p.segment_index, "code": p.code,
                      "detail": p.detail} for p in problems],
        "verified_against": ("the recording parts' measured durations and "
                             "boundaries, not application event timestamps"),
    }


def _parse_range(header: Optional[str], size: int):
    """One `Range: bytes=a-b`, or None.

    Deliberately narrow: a single range only. Multipart ranges need a
    multipart/byteranges body, no media element asks for them, and half an
    implementation of one is worse than none.

    Returns (start, end_inclusive), or the string "unsatisfiable".
    """
    if not header:
        return None
    header = header.strip()
    if not header.lower().startswith("bytes="):
        return None
    spec = header[6:].split(",")[0].strip()
    if "-" not in spec:
        return None
    lo, _, hi = spec.partition("-")
    try:
        if lo == "":                       # bytes=-500 -> the last 500 bytes
            n = int(hi)
            if n <= 0:
                return "unsatisfiable"
            start, end = max(0, size - n), size - 1
        else:
            start = int(lo)
            end = int(hi) if hi else size - 1
    except ValueError:
        return None
    if start >= size or start < 0 or end < start:
        return "unsatisfiable"
    return start, min(end, size - 1)



#: What the recruiter is told about where a transcript came from. Named
#: explicitly rather than inferred in the client, because two clients would
#: infer it two ways and one of them would be generous.
_ADAPTER_AUTHORITY = {
    "browser-speech": (
        "CLIENT_REPORTED",
        "recognised live by the candidate's browser and sent to us. It is "
        "tied to the recording by a shared clock, not re-derived from the "
        "media, so we cannot independently confirm the wording."),
    "local-whisper": (
        "SERVER_DERIVED",
        "transcribed here from the stored recording, and reproducible by "
        "anyone holding the file."),
    "demo-fixture": (
        "DEMO_FIXTURE",
        "seeded for a demonstration. No speech was recognised: this is the "
        "scripted answer text at the scripted offsets, shown so the page can "
        "be seen working, and it is not evidence of anything a person said."),
}


def _transcript_provenance(segments) -> dict:
    """Summarise how this transcript was obtained.

    The authority of a mixed transcript is the WEAKEST part of it, not the
    average and not the best: one client-reported segment is enough to make
    "this transcript was derived from the recording" untrue.
    """
    adapters = {s.asr_adapter for s in segments}
    if not segments:
        return {"authority": "NONE", "adapters": [],
                "detail": "no transcript segments have been recorded."}
    if None in adapters and "demo-fixture" not in adapters:
        return {
            "authority": "UNKNOWN",
            "adapters": sorted(a for a in adapters if a),
            "detail": ("some segments predate provenance recording, so how "
                       "they were produced is not known. They are not assumed "
                       "to be server-derived."),
        }
    ranked = [_ADAPTER_AUTHORITY.get(
                  a, ("UNKNOWN", "some segments do not record how they were "
                                 "produced" if a is None
                                 else f"unrecognised adapter {a!r}"))
              for a in adapters]
    # CLIENT_REPORTED and UNKNOWN both outrank SERVER_DERIVED downward.
    # A fixture ranks BELOW an unknown adapter. "We do not know how this was
    # produced" still leaves open that a person said it; "this was seeded"
    # closes that question in the other direction, and a demo transcript
    # sitting quietly beside real ones is the single most misleading thing
    # this ladder could allow.
    order = {"DEMO_FIXTURE": -1, "UNKNOWN": 0,
             "CLIENT_REPORTED": 1, "SERVER_DERIVED": 2}
    weakest = min(ranked, key=lambda r: order.get(r[0], 0))
    # `adapters` can still hold a None (a fixture mixed with rows written
    # before provenance was recorded); name it rather than sorting against it.
    listed = sorted(a for a in adapters if a)
    if None in adapters:
        listed.append("unrecorded")
    return {"authority": weakest[0], "adapters": listed,
            "detail": weakest[1]}


@router.get("/{interview_id}/media/{part_number}")
async def stream_media(interview_id: UUID, part_number: int,
                       # Annotated `Request` so FastAPI injects it, with a
                       # default so the handler can still be called directly --
                       # which the tests do, and which any internal caller
                       # might. `Optional[Request]` is not a valid FastAPI
                       # annotation; this is.
                       request: Request = None,  # type: ignore[assignment]
                       actor: Actor = Depends(require_org),
                       db: AsyncSession = Depends(db_session)):
    """Serve a recording part back to the recruiter player.

    RANGE REQUESTS ARE THE FEATURE, NOT AN OPTIMISATION.
    This used to answer every request with 200 and the whole file, and no
    `Accept-Ranges` header. A media element that cannot request a byte range
    cannot seek: setting `video.currentTime` either refuses or re-downloads
    from the start, which is precisely the click the debrief is built around --
    "click any assessment and the recording seeks to the moment the candidate
    said it".

    The capability was reported as working because a RecordingAsset row
    existed and the bytes came back. They did. They just could not be sought.
    """
    _require_recruiter(actor)

    res = await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.org_id == actor.org_id,
        M.RecordingAsset.interview_id == interview_id,
        M.RecordingAsset.part_number == part_number,
        M.RecordingAsset.deleted_at.is_(None)))
    row = res.scalar_one_or_none()
    if row is None or not row.storage_ref:
        raise HTTPException(status_code=404, detail="No such recording part")

    try:
        data = MED.read_part(row.storage_ref, org_id=actor.org_id)
    except MED.MediaRefused as exc:
        raise HTTPException(status_code=404,
                            detail={"code": exc.code, "detail": exc.detail})
    size = len(data)
    # `request` is optional so the handler can still be called directly --
    # which the tests do, and which any internal caller might. A caller with no
    # request has not asked for a range.
    header = request.headers.get("range") if request is not None else None
    rng = _parse_range(header, size)

    common = {
        "accept-ranges": "bytes",
        # The player asks for ranges across the whole part; without this the
        # browser caches a partial response and serves it for the next seek.
        "cache-control": "no-store",
    }

    if rng == "unsatisfiable":
        return Response(
            status_code=416, media_type=row.mime_type,
            headers={**common, "content-range": f"bytes */{size}"})

    if rng is None:
        return Response(content=data, media_type=row.mime_type,
                        headers={**common,
                                 "content-length": str(size)})

    start, end = rng
    chunk = data[start:end + 1]
    return Response(
        content=chunk, status_code=206, media_type=row.mime_type,
        headers={**common,
                 "content-range": f"bytes {start}-{end}/{size}",
                 "content-length": str(len(chunk))})
