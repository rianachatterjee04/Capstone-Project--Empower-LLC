"""Drive a whole interview, persisting everything as it goes.

This is the orchestration layer. It owns the loop:

    ask the planned question
      -> receive an answer
      -> analyse it
      -> extract evidence and persist it
      -> decide whether to probe again or move to the next competency

and then, at the end, verification -> assessment -> scorecard -> debrief.

WHY THE LOOP IS HERE AND NOT IN THE ROUTER
Because it has to be re-enterable. A candidate whose connection drops mid-
answer comes back to the same interview under a new attempt, and the loop
resumes from what is in the database rather than from anything held in memory.
`resume()` is the entry point for that, and it is the reason none of this state
lives in a service-level dict.

CONSENT IS CHECKED HERE, ONCE, AND IT FAILS CLOSED
`start()` refuses without a consent row that actually grants the interview. It
is checked at the point of starting rather than at the point of recording,
because an interview that has begun has already collected the candidate's words
whether or not a file was written.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.interview import analysis as A
from app.interview import claims as C
from app.interview import evidence as E
from app.interview import followup as F
from app.interview import models as M
from app.interview import repository as R
from app.interview import scoring as S
from app.interview import summary as SUM
from app.interview import verification as V
from app.interview.planner import build_plan
from app.interview.rubrics import (RUBRICS, domain_for_key,
                                   rubric_for_title)


#: Roughly how many substantive exchanges fit in a minute of interview,
#: derived from the demo runs: an opener plus its follow-ups averages a little
#: over two minutes once the candidate is actually talking.
QUESTIONS_PER_MINUTE = 0.45
MIN_QUESTIONS = 6


#: Every acknowledgement a probe can open with. Stored questions keep the
#: whole sentence, so recovering the body means stripping a known lead.
_ACK_LEADS = tuple(sorted(
    set(F._ACKS) | set(F._ACKS_LONG) | {"Let me make sure I've got this right."},
    key=len, reverse=True))


def _probe_body_of(question_text: str) -> str:
    """A stored question with its acknowledgement removed."""
    t = (question_text or "").strip()
    for lead in _ACK_LEADS:
        if t.startswith(lead):
            return t[len(lead):].strip()
    return t


def question_budget(target_minutes: int) -> int:
    """How many questions a target duration will bear.

    Floored at MIN_QUESTIONS: a very short interview still has to cover the
    required competencies, and the right answer to "we only have ten minutes"
    is a shorter interview, not an interview that skips the safety question.
    """
    return max(MIN_QUESTIONS, int(round(target_minutes * QUESTIONS_PER_MINUTE)))


class ConsentMissing(RuntimeError):
    """The interview cannot start without recorded consent."""


class InterviewNotFound(RuntimeError):
    """No such interview under this organisation.

    Separate from ConsentMissing on purpose. They were the same type, so
    "this is not your interview" and "the candidate withdrew consent" reached
    the client as the same 409 and no caller could tell a tenancy refusal from
    a consent problem. A dedicated type is what lets the router answer 404 for
    one and 409 for the other.
    """


@dataclass
class NextStep:
    """What the candidate is asked next, or that the interview is over."""

    question: Optional[M.InterviewQuestion] = None
    finished: bool = False
    reason: str = ""

    @property
    def has_question(self) -> bool:
        return self.question is not None


async def prepare(db: AsyncSession, *, org_id: uuid.UUID,
                  job_posting_id: uuid.UUID, candidate_id: uuid.UUID,
                  job_title: str, resume_text: str,
                  application_text: str = "",
                  role_config: Optional[dict] = None,
                  consent_id: Optional[uuid.UUID] = None) -> dict:
    """Extract claims, create the interview, build and persist the plan."""
    source_ref = f"resume:{candidate_id}"
    extracted = C.extract_deterministic(resume_text, source_kind=C.RESUME,
                                        source_ref=source_ref)
    if application_text.strip():
        extracted += C.extract_deterministic(
            application_text, source_kind=C.APPLICATION,
            source_ref=f"application:{candidate_id}")

    claim_rows = await R.save_claims(db, org_id=org_id,
                                     candidate_id=candidate_id,
                                     job_posting_id=job_posting_id,
                                     claims=extracted)

    interview = await R.create_interview(
        db, org_id=org_id, job_posting_id=job_posting_id,
        candidate_id=candidate_id, consent_id=consent_id,
        target_minutes=int((role_config or {}).get("target_minutes") or 30))

    plan = build_plan(job_title=job_title,
                      candidate_claims=R.to_domain_claims(claim_rows),
                      role_config=role_config)
    plan_row = await R.save_plan(db, org_id=org_id, interview_id=interview.id,
                                 plan=plan, claim_rows=claim_rows)

    interview.status = "PLANNED"
    await R.record_event(db, org_id=org_id, interview_id=interview.id,
                         event_type="PLAN_GENERATED", actor_kind="SYSTEM",
                         payload={"rubric": plan.rubric_key,
                                  "coverage": plan.coverage()})
    await db.flush()
    return {"interview": interview, "plan_row": plan_row, "plan": plan,
            "claims": claim_rows}


async def start(db: AsyncSession, *, org_id: uuid.UUID,
                interview_id: uuid.UUID,
                user_agent: Optional[str] = None) -> M.InterviewAttempt:
    """Open an attempt. Refuses without consent."""
    interview = await R.get_interview(db, org_id=org_id, interview_id=interview_id)
    if interview is None:
        raise InterviewNotFound("no such interview for this organisation")

    if interview.consent_id is None:
        raise ConsentMissing(
            "this interview has no consent record. An interview that has begun "
            "has already collected the candidate's words, so consent is "
            "checked before the first question rather than before recording.")

    res = await db.execute(
        select(M.InterviewConsent).where(
            M.InterviewConsent.org_id == org_id,
            M.InterviewConsent.id == interview.consent_id))
    consent = res.scalar_one_or_none()
    if consent is None or not consent.granted_at or consent.withdrawn_at:
        raise ConsentMissing("consent was never granted, or has been withdrawn")
    if not consent.consent_interview:
        raise ConsentMissing("the candidate did not consent to being interviewed")

    # The interview started when its first attempt did. Recording only the
    # ATTEMPT's time left `interviews.started_at` null forever, so a list
    # could show neither when an interview happened nor how long it took.
    if interview.started_at is None:
        interview.started_at = datetime.now(timezone.utc)

    attempt = await R.start_attempt(db, org_id=org_id, interview_id=interview_id,
                                    user_agent=user_agent)
    interview.status = "IN_PROGRESS"
    await R.record_event(db, org_id=org_id, interview_id=interview_id,
                         attempt_id=attempt.id, event_type="ATTEMPT_STARTED",
                         actor_kind="CANDIDATE",
                         payload={"attempt": attempt.attempt_number})
    await db.flush()
    return attempt


async def _competency_state(db: AsyncSession, *, org_id: uuid.UUID,
                            interview_id: uuid.UUID, plan_id: uuid.UUID) -> dict:
    comps = await R.load_competencies(db, org_id=org_id, plan_id=plan_id)
    qa = await R.load_qa(db, org_id=org_id, interview_id=interview_id)
    ev = await R.load_evidence(db, org_id=org_id, interview_id=interview_id)

    asked_by_comp: Dict[uuid.UUID, list] = {}
    for q, a in qa:
        asked_by_comp.setdefault(q.competency_id, []).append((q, a))

    ev_by_key: Dict[str, list] = {}
    for e in ev:
        ev_by_key.setdefault(e.competency_key, []).append(e)

    return {"competencies": comps, "asked": asked_by_comp,
            "evidence": ev_by_key, "qa": qa}


async def next_question(db: AsyncSession, *, org_id: uuid.UUID,
                        interview_id: uuid.UUID,
                        attempt_id: Optional[uuid.UUID] = None) -> NextStep:
    """The heart of the loop: probe again, or move to the next competency."""
    plan = await R.load_plan(db, org_id=org_id, interview_id=interview_id)
    if plan is None:
        return NextStep(finished=True, reason="no plan for this interview")

    st = await _competency_state(db, org_id=org_id, interview_id=interview_id,
                                 plan_id=plan.id)

    # TIME BUDGET.
    # A 30-minute interview is roughly a dozen substantive exchanges. Without a
    # bound the probe engine keeps finding gaps -- there is always another
    # thing that could be established -- and the candidate sits through forty
    # questions. The budget is spent on REQUIRED competencies first, so running
    # out of time drops optional depth rather than a required competency.
    asked_total = len(st["qa"])
    budget = question_budget(plan.target_minutes)
    over_budget = asked_total >= budget

    for comp in st["competencies"]:
        asked = st["asked"].get(comp.id, [])

        # Not started: ask the planned opener. Over budget, only REQUIRED
        # competencies still get one -- an optional competency is worth less
        # than finishing on time, and a required one is worth more.
        if not asked:
            if over_budget and not comp.is_required:
                continue
            q = await R.ask(
                db, org_id=org_id, interview_id=interview_id,
                attempt_id=attempt_id, competency_id=comp.id,
                provoking_claim_id=comp.hook_claim_id,
                question_text=comp.initial_question,
                question_kind="PLANNED_INITIAL", probe_depth=0,
                intent=comp.evidence_needed)
            await db.flush()
            return NextStep(question=q)

        last_q, last_a = asked[-1]
        if last_a is None:
            return NextStep(finished=False,
                            reason="waiting for the current answer")

        an = A.analyse(
            last_a.answer_text,
            prior_claims=R.to_domain_claims(
                await R.load_claims(
                    db, org_id=org_id,
                    candidate_id=(await R.get_interview(
                        db, org_id=org_id,
                        interview_id=interview_id)).candidate_id)),
            expects_metric=("metric" in (comp.evidence_needed or "").lower()
                            or "measur" in (comp.evidence_needed or "").lower()),
            expects_ownership=("personally" in (comp.evidence_needed or "").lower()
                               or "own" in comp.competency_key),
            expects_tradeoff=("alternative" in (comp.evidence_needed or "").lower()
                              or "tradeoff" in (comp.evidence_needed or "").lower()))

        decision = F.decide(
            an, probe_depth=last_q.probe_depth,
            max_probe_depth=comp.max_probe_depth,
            evidence_count=len([e for e in st["evidence"].get(comp.competency_key, [])
                                if e.polarity == "SUPPORTS"]),
            min_evidence=comp.min_evidence_count,
            expects_conflict=("conflict" in comp.competency_key
                              or "collaborat" in comp.competency_key),
            # The rubric decides the vocabulary the probes are written in, so
            # a driver is never asked what they "built".
            domain=domain_for_key(plan.rubric_key),
            competency_key=comp.competency_key)

        # Over budget, stop probing entirely and spend what is left opening
        # competencies that have not been touched.
        if decision.has_followup and over_budget:
            continue

        if decision.has_followup:
            # NEVER ASK THE SAME QUESTION TWICE.
            # If a candidate repeats themselves, the analysis reports the same
            # gaps and the engine generates the same probe. Asking it again
            # gathers nothing and makes the interviewer look like it is not
            # listening -- which is precisely the impression this product
            # exists to avoid. Move on to the next competency instead.
            # Compare the probe BODY, not the whole sentence. The
            # acknowledgement in front of it varies deliberately, so comparing
            # full text would let "Understood. Can you take me to..." and
            # "Thanks. Can you take me to..." both go out.
            body = decision.followup.probe_body or decision.followup.question_text
            already = {_probe_body_of(aq.question_text) for aq, _ in st["qa"]}
            if body in already:
                continue

            q = await R.ask(
                db, org_id=org_id, interview_id=interview_id,
                attempt_id=attempt_id, competency_id=comp.id,
                provoking_claim_id=comp.hook_claim_id,
                parent_answer_id=last_a.id,
                question_text=decision.followup.question_text,
                question_kind=decision.followup.question_kind,
                probe_depth=last_q.probe_depth + 1,
                intent=decision.followup.intent)
            await db.flush()
            return NextStep(question=q)
        # else: this competency is done; fall through to the next one.

    return NextStep(finished=True, reason="every planned competency was covered")


async def submit_answer(db: AsyncSession, *, org_id: uuid.UUID,
                        interview_id: uuid.UUID, question_id: uuid.UUID,
                        answer_text: str,
                        attempt_id: Optional[uuid.UUID] = None,
                        recording_start_ms: Optional[int] = None,
                        recording_end_ms: Optional[int] = None) -> dict:
    """Record an answer and the evidence it produced."""
    res = await db.execute(
        select(M.InterviewQuestion).where(
            M.InterviewQuestion.org_id == org_id,
            M.InterviewQuestion.id == question_id))
    question = res.scalar_one_or_none()
    if question is None:
        raise ValueError("no such question for this organisation")

    interview = await R.get_interview(db, org_id=org_id, interview_id=interview_id)
    claim_rows = await R.load_claims(db, org_id=org_id,
                                     candidate_id=interview.candidate_id)
    domain_claims = R.to_domain_claims(claim_rows)

    an = A.analyse(answer_text, prior_claims=domain_claims)

    ans = await R.answer(
        db, org_id=org_id, interview_id=interview_id, question_id=question_id,
        answer_text=answer_text, attempt_id=attempt_id,
        recording_start_ms=recording_start_ms,
        recording_end_ms=recording_end_ms,
        is_substantive=an.is_substantive, non_answer_kind=an.non_answer_kind)

    competency_key = "unassigned"
    if question.competency_id:
        cres = await db.execute(
            select(M.InterviewCompetency).where(
                M.InterviewCompetency.org_id == org_id,
                M.InterviewCompetency.id == question.competency_id))
        comp = cres.scalar_one_or_none()
        if comp is not None:
            competency_key = comp.competency_key

    extracted = E.extract(answer_text, an, competency_key=competency_key,
                          answer_start_ms=recording_start_ms,
                          answer_end_ms=recording_end_ms)
    rows = [e.as_row(answer_id=ans.id, question_id=question.id,
                     competency_id=question.competency_id) for e in extracted]
    saved = await R.save_evidence(db, org_id=org_id, interview_id=interview_id,
                                  rows=rows) if rows else []

    await R.record_event(db, org_id=org_id, interview_id=interview_id,
                         attempt_id=attempt_id, event_type="ANSWER_RECORDED",
                         actor_kind="CANDIDATE",
                         payload={"question_id": str(question_id),
                                  "evidence": len(saved),
                                  "substantive": an.is_substantive})
    await db.flush()
    return {"answer": ans, "analysis": an, "evidence": saved}


async def finalise(db: AsyncSession, *, org_id: uuid.UUID,
                   interview_id: uuid.UUID) -> dict:
    """Verification, assessments, scorecard and debrief -- all persisted."""
    plan = await R.load_plan(db, org_id=org_id, interview_id=interview_id)
    if plan is None:
        # No plan under THIS org: either the interview does not exist or it
        # belongs to someone else, and the query cannot tell those apart on
        # purpose. Taking .id off None here raised AttributeError, which
        # reached the client as a 500 -- an unhandled crash on a tenancy
        # boundary looks exactly like a broken server.
        raise InterviewNotFound(
            "no interview plan for this organisation")
    comps = await R.load_competencies(db, org_id=org_id, plan_id=plan.id)
    interview = await R.get_interview(db, org_id=org_id, interview_id=interview_id)
    qa = await R.load_qa(db, org_id=org_id, interview_id=interview_id)
    all_ev = await R.load_evidence(db, org_id=org_id, interview_id=interview_id)

    ev_by_key: Dict[str, list] = {}
    for e in all_ev:
        ev_by_key.setdefault(e.competency_key, []).append(e)

    # --- claim verification ------------------------------------------------
    claim_rows = await R.load_claims(db, org_id=org_id,
                                     candidate_id=interview.candidate_id)
    answers = [a.answer_text for _, a in qa if a is not None]
    verifications = []
    for claim in claim_rows:
        related = [e for e in all_ev if e.claim_id == claim.id]
        v = V.verify_claim(claim, answers, related)
        db.add(M.ClaimVerification(org_id=org_id, interview_id=interview_id,
                                   **v.as_row()))
        verifications.append(v)

    # --- assessments -------------------------------------------------------
    card = S.build_scorecard(
        rubric_key=plan.rubric_key, rubric_version=plan.rubric_version,
        planned=comps, evidence_by_competency=ev_by_key)

    by_key = {c.competency_key: c for c in comps}
    for a in card.assessments:
        comp = by_key.get(a.competency_key)
        row = M.CompetencyAssessment(
            org_id=org_id, interview_id=interview_id,
            competency_id=comp.id if comp else None,
            competency_key=a.competency_key, state=a.state, score=a.score,
            confidence=a.confidence, rationale=a.rationale,
            missing_evidence=a.missing_evidence,
            supporting_count=a.supporting_count,
            contradicting_count=a.contradicting_count,
            assessed_by=S.SCORING_VERSION)
        db.add(row)
        await db.flush()
        # assessment_evidence is a pure join table with no ORM model -- it
        # carries no org_id of its own because it is only reachable through
        # two tenant-bound parents. Inserted as SQL for that reason.
        for ev_id, role in ([(e, "SUPPORTING") for e in a.supporting_ids]
                            + [(e, "CONTRADICTING") for e in a.contradicting_ids]):
            if not ev_id:
                continue
            await db.execute(text(
                "INSERT INTO public.assessment_evidence "
                "(assessment_id, evidence_id, role) VALUES (:a, :e, :r) "
                "ON CONFLICT DO NOTHING"),
                {"a": row.id, "e": ev_id, "r": role})

    card_row = M.InterviewScorecard(
        org_id=org_id, interview_id=interview_id,
        rubric_key=card.rubric_key, rubric_version=card.rubric_version,
        overall_state=card.overall_state, overall_score=card.overall_score,
        overall_confidence=card.overall_confidence,
        completeness_state=card.completeness_state,
        uncovered_required=list(card.uncovered_required))
    db.add(card_row)
    await db.flush()

    # --- debrief -----------------------------------------------------------
    debrief = SUM.build_debrief(
        scorecard=card, evidence_by_competency=ev_by_key,
        competency_labels={c.competency_key: c.competency_label for c in comps},
        verifications=verifications)
    db.add(M.InterviewSummary(org_id=org_id, interview_id=interview_id,
                              scorecard_id=card_row.id, **debrief.as_rows()))

    interview.status = "COMPLETED"
    # AN INTERVIEW MARKED COMPLETED WITH NO END TIME IS A ROW THAT CONTRADICTS
    # ITSELF. The column existed and nothing wrote it, so every interview list
    # showed "finished: —" beside a COMPLETED badge, and no report could say
    # how long an interview took or when it happened.
    if interview.ended_at is None:
        interview.ended_at = datetime.now(timezone.utc)
    await R.record_event(db, org_id=org_id, interview_id=interview_id,
                         event_type="INTERVIEW_FINALISED", actor_kind="SYSTEM",
                         payload={"overall": str(card.overall_score),
                                  "completeness": card.completeness_state})
    await db.flush()
    return {"scorecard": card, "scorecard_row": card_row,
            "debrief": debrief, "verifications": verifications,
            "evidence_by_competency": ev_by_key}
