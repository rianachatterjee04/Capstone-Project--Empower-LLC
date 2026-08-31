"""Persistence for the interview domain.

EVERY FUNCTION TAKES org_id AND FILTERS ON IT.
Not because the column is decorative, but because service_role bypasses RLS:
in this codebase the application's tenant filter is the load-bearing control,
not a backstop behind one. `tests/test_interview_tenancy.py` calls each of
these with a mismatched org and asserts nothing comes back and nothing is
written.

The write helpers are deliberately explicit rather than generic. A generic
`save(obj)` would let a caller persist a row whose org_id came from the object
instead of from the caller's authenticated context, which is exactly how
cross-tenant writes happen.
"""
from __future__ import annotations

import uuid
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.interview import claims as C
from app.interview import models as M
from app.interview.planner import Plan


class TenantMismatch(RuntimeError):
    """A row was requested or written under the wrong organisation."""


# ---------------------------------------------------------------------------
# Claims
# ---------------------------------------------------------------------------

async def save_claims(db: AsyncSession, *, org_id: uuid.UUID,
                      candidate_id: uuid.UUID,
                      job_posting_id: Optional[uuid.UUID],
                      claims: Sequence[C.Claim]) -> List[M.CandidateClaim]:
    """Persist extracted claims. org_id comes from the CALLER, never the claim."""
    rows: List[M.CandidateClaim] = []
    for claim in claims:
        row = M.CandidateClaim(
            org_id=org_id,
            candidate_id=candidate_id,
            job_posting_id=job_posting_id,
            **claim.as_row(),
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    return rows


async def load_claims(db: AsyncSession, *, org_id: uuid.UUID,
                      candidate_id: uuid.UUID) -> List[M.CandidateClaim]:
    res = await db.execute(
        select(M.CandidateClaim)
        .where(M.CandidateClaim.org_id == org_id,
               M.CandidateClaim.candidate_id == candidate_id)
        .order_by(M.CandidateClaim.created_at))
    return list(res.scalars().all())


def to_domain_claims(rows: Iterable[M.CandidateClaim]) -> List[C.Claim]:
    """ORM rows back into the domain object the planner works with."""
    out: List[C.Claim] = []
    for r in rows:
        out.append(C.Claim(
            claim_type=r.claim_type,
            claim_text=r.claim_text,
            source_kind=r.source_kind,
            source_ref=r.source_ref,
            source_excerpt=r.source_excerpt,
            source_span_start=r.source_span_start,
            source_span_end=r.source_span_end,
            subject=r.subject,
            quantity_value=(float(r.quantity_value)
                            if r.quantity_value is not None else None),
            quantity_unit=r.quantity_unit,
            time_period=r.time_period,
            is_inference=r.is_inference,
            confidence=(float(r.confidence) if r.confidence is not None else None),
            extractor=r.extractor,
            model_name=r.model_name,
            model_version=r.model_version,
        ))
    return out


# ---------------------------------------------------------------------------
# Interview + consent
# ---------------------------------------------------------------------------

async def create_consent(db: AsyncSession, *, org_id: uuid.UUID,
                         candidate_id: uuid.UUID, disclosure_text: str,
                         policy_version: str,
                         interview: bool = True, audio: bool = True,
                         video: bool = True, transcript: bool = True,
                         ai_analysis: bool = True,
                         granted_at=None) -> M.InterviewConsent:
    from datetime import datetime, timezone
    row = M.InterviewConsent(
        org_id=org_id, candidate_id=candidate_id,
        disclosure_text=disclosure_text, policy_version=policy_version,
        consent_interview=interview, consent_audio=audio, consent_video=video,
        consent_transcript=transcript, consent_ai_analysis=ai_analysis,
        granted_at=granted_at or datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row


async def create_interview(db: AsyncSession, *, org_id: uuid.UUID,
                           job_posting_id: uuid.UUID, candidate_id: uuid.UUID,
                           consent_id: Optional[uuid.UUID] = None,
                           target_minutes: int = 30,
                           mode: str = "ASYNC_AI") -> M.Interview:
    row = M.Interview(
        org_id=org_id, job_posting_id=job_posting_id,
        candidate_id=candidate_id, consent_id=consent_id,
        target_minutes=target_minutes, mode=mode, status="DRAFT",
    )
    db.add(row)
    await db.flush()
    return row


async def get_interview(db: AsyncSession, *, org_id: uuid.UUID,
                        interview_id: uuid.UUID) -> Optional[M.Interview]:
    res = await db.execute(
        select(M.Interview).where(M.Interview.org_id == org_id,
                                  M.Interview.id == interview_id))
    return res.scalar_one_or_none()


async def start_attempt(db: AsyncSession, *, org_id: uuid.UUID,
                        interview_id: uuid.UUID,
                        user_agent: Optional[str] = None) -> M.InterviewAttempt:
    """Open the next attempt.

    Reconnect creates a NEW attempt against the SAME interview: the plan, the
    claims and every answer already given stay exactly where they are. An
    implementation that created a second interview here would silently split
    one candidate's evidence into two half-assessments.
    """
    res = await db.execute(
        select(M.InterviewAttempt.attempt_number)
        .where(M.InterviewAttempt.org_id == org_id,
               M.InterviewAttempt.interview_id == interview_id)
        .order_by(M.InterviewAttempt.attempt_number.desc()).limit(1))
    last = res.scalar_one_or_none() or 0
    row = M.InterviewAttempt(
        org_id=org_id, interview_id=interview_id,
        attempt_number=last + 1, client_user_agent=user_agent)
    db.add(row)
    await db.flush()
    return row


async def record_event(db: AsyncSession, *, org_id: uuid.UUID,
                       interview_id: uuid.UUID, event_type: str,
                       actor_kind: str, actor_ref: Optional[str] = None,
                       attempt_id: Optional[uuid.UUID] = None,
                       payload: Optional[dict] = None) -> M.InterviewEvent:
    row = M.InterviewEvent(
        org_id=org_id, interview_id=interview_id, attempt_id=attempt_id,
        event_type=event_type, actor_kind=actor_kind, actor_ref=actor_ref,
        payload=payload or {})
    db.add(row)
    await db.flush()
    return row


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

async def save_plan(db: AsyncSession, *, org_id: uuid.UUID,
                    interview_id: uuid.UUID, plan: Plan,
                    claim_rows: Sequence[M.CandidateClaim]) -> M.InterviewPlan:
    """Persist a plan and its competencies, binding hooks to real claim rows.

    `claim_rows` are the persisted claims. The hook on each planned competency
    is matched back to its row by source span, so `hook_claim_id` is a real
    foreign key rather than a copy of the text -- which is what lets the
    recruiter UI show "we asked this because your resume said that".
    """
    plan_row = M.InterviewPlan(
        org_id=org_id, interview_id=interview_id,
        rubric_key=plan.rubric_key, rubric_version=plan.rubric_version,
        generated_by=plan.generated_by, model_name=plan.model_name,
        model_version=plan.model_version, prompt_version=plan.prompt_version,
        fallback_reason=plan.fallback_reason,
        target_minutes=plan.target_minutes,
    )
    db.add(plan_row)
    await db.flush()

    by_span = {
        (r.source_ref, r.source_span_start, r.source_span_end): r
        for r in claim_rows
    }

    for comp in plan.competencies:
        hook_row = None
        if comp.hook_claim is not None:
            hook_row = by_span.get((
                comp.hook_claim.source_ref,
                comp.hook_claim.source_span_start,
                comp.hook_claim.source_span_end))
        db.add(M.InterviewCompetency(
            org_id=org_id, plan_id=plan_row.id,
            competency_key=comp.competency_key,
            competency_label=comp.competency_label,
            why_it_matters=comp.why_it_matters,
            candidate_hook=comp.candidate_hook,
            hook_claim_id=hook_row.id if hook_row else None,
            evidence_needed=comp.evidence_needed,
            initial_question=comp.initial_question,
            followup_objectives=list(comp.followup_objectives),
            role_weight=comp.role_weight,
            is_required=comp.is_required,
            min_evidence_count=comp.min_evidence_count,
            max_probe_depth=comp.max_probe_depth,
            display_order=comp.display_order,
        ))
    await db.flush()
    return plan_row


async def load_plan(db: AsyncSession, *, org_id: uuid.UUID,
                    interview_id: uuid.UUID) -> Optional[M.InterviewPlan]:
    res = await db.execute(
        select(M.InterviewPlan).where(M.InterviewPlan.org_id == org_id,
                                      M.InterviewPlan.interview_id == interview_id))
    return res.scalar_one_or_none()


async def load_competencies(db: AsyncSession, *, org_id: uuid.UUID,
                            plan_id: uuid.UUID) -> List[M.InterviewCompetency]:
    res = await db.execute(
        select(M.InterviewCompetency)
        .where(M.InterviewCompetency.org_id == org_id,
               M.InterviewCompetency.plan_id == plan_id)
        .order_by(M.InterviewCompetency.display_order))
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# Questions + answers
# ---------------------------------------------------------------------------

async def next_sequence(db: AsyncSession, *, org_id: uuid.UUID,
                        interview_id: uuid.UUID) -> int:
    res = await db.execute(
        select(M.InterviewQuestion.sequence_number)
        .where(M.InterviewQuestion.org_id == org_id,
               M.InterviewQuestion.interview_id == interview_id)
        .order_by(M.InterviewQuestion.sequence_number.desc()).limit(1))
    return (res.scalar_one_or_none() or 0) + 1


async def ask(db: AsyncSession, *, org_id: uuid.UUID, interview_id: uuid.UUID,
              question_text: str, question_kind: str,
              competency_id: Optional[uuid.UUID] = None,
              provoking_claim_id: Optional[uuid.UUID] = None,
              parent_answer_id: Optional[uuid.UUID] = None,
              attempt_id: Optional[uuid.UUID] = None,
              probe_depth: int = 0, intent: Optional[str] = None,
              generated_by: str = "deterministic",
              model_name: Optional[str] = None,
              fallback_reason: Optional[str] = None) -> M.InterviewQuestion:
    row = M.InterviewQuestion(
        org_id=org_id, interview_id=interview_id, attempt_id=attempt_id,
        competency_id=competency_id, provoking_claim_id=provoking_claim_id,
        parent_answer_id=parent_answer_id,
        sequence_number=await next_sequence(db, org_id=org_id,
                                            interview_id=interview_id),
        probe_depth=probe_depth, question_kind=question_kind,
        question_text=question_text, intent=intent,
        generated_by=generated_by, model_name=model_name,
        fallback_reason=fallback_reason)
    db.add(row)
    await db.flush()
    return row


async def answer(db: AsyncSession, *, org_id: uuid.UUID,
                 interview_id: uuid.UUID, question_id: uuid.UUID,
                 answer_text: str, attempt_id: Optional[uuid.UUID] = None,
                 recording_start_ms: Optional[int] = None,
                 recording_end_ms: Optional[int] = None,
                 is_substantive: bool = True,
                 non_answer_kind: Optional[str] = None) -> M.InterviewAnswer:
    row = M.InterviewAnswer(
        org_id=org_id, interview_id=interview_id, attempt_id=attempt_id,
        question_id=question_id, answer_text=answer_text,
        recording_start_ms=recording_start_ms,
        recording_end_ms=recording_end_ms,
        is_substantive=is_substantive, non_answer_kind=non_answer_kind)
    db.add(row)
    await db.flush()
    return row


async def load_qa(db: AsyncSession, *, org_id: uuid.UUID,
                  interview_id: uuid.UUID) -> List[tuple]:
    """(question, answer|None) in asked order."""
    qres = await db.execute(
        select(M.InterviewQuestion)
        .where(M.InterviewQuestion.org_id == org_id,
               M.InterviewQuestion.interview_id == interview_id)
        .order_by(M.InterviewQuestion.sequence_number))
    questions = list(qres.scalars().all())

    ares = await db.execute(
        select(M.InterviewAnswer)
        .where(M.InterviewAnswer.org_id == org_id,
               M.InterviewAnswer.interview_id == interview_id))
    by_q = {a.question_id: a for a in ares.scalars().all()}
    return [(q, by_q.get(q.id)) for q in questions]


# ---------------------------------------------------------------------------
# Evidence + assessment
# ---------------------------------------------------------------------------

async def save_evidence(db: AsyncSession, *, org_id: uuid.UUID,
                        interview_id: uuid.UUID,
                        rows: Sequence[dict]) -> List[M.InterviewEvidence]:
    out: List[M.InterviewEvidence] = []
    for r in rows:
        ev = M.InterviewEvidence(org_id=org_id, interview_id=interview_id, **r)
        db.add(ev)
        out.append(ev)
    await db.flush()
    return out


async def load_evidence(db: AsyncSession, *, org_id: uuid.UUID,
                        interview_id: uuid.UUID,
                        competency_key: Optional[str] = None
                        ) -> List[M.InterviewEvidence]:
    q = select(M.InterviewEvidence).where(
        M.InterviewEvidence.org_id == org_id,
        M.InterviewEvidence.interview_id == interview_id)
    if competency_key:
        q = q.where(M.InterviewEvidence.competency_key == competency_key)
    res = await db.execute(q.order_by(M.InterviewEvidence.created_at))
    return list(res.scalars().all())
