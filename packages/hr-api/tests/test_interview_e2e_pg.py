"""A whole interview, end to end, through PostgreSQL.

This is the test that says the product exists: consent, plan, adaptive
questioning driven by real answers, evidence persisted with its links,
verification, scorecard, debrief -- and a recruiter able to get from a score
back to the moment the candidate said the thing.

Three candidates run the same job. The interviews DIVERGE because the answers
diverge, and the assertions are about that divergence rather than about any
particular score.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import models as M
from app.interview import repository as R
from app.interview import runner
from app.interview import scoring as S
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

JOB_TITLE = "Senior Software Engineer"

RESUME_A = """Senior Platform Engineer, Acme Payments (2021-2025)
Reduced settlement failures by 40% during the Ledger migration.
Managed a team of 12 engineers across two time zones.
8 years of distributed systems experience. Built services in Python and Go on AWS.
"""

RESUME_C = """Results-driven senior technology leader with a proven track record of
delivering transformational outcomes at scale. Passionate about excellence and
building world-class high-performing teams. Extensive experience across the
full technology stack.
"""

# What each candidate says. A answers concretely; C answers in adjectives.
ANSWERS_A = [
    ("I rewrote the settlement reconciler. Before that we were failing about "
     "4% of settlements a day, mostly duplicate submissions after a timeout. "
     "I added an idempotency key on the ledger write and changed the retry to "
     "check state first. Over the following quarter that dropped to 0.2%. We "
     "knew it was the change because we held volume constant and it was the "
     "only thing we shipped that sprint. The downside is the ledger write got "
     "slower, which we accepted instead of caching because stale reads would "
     "be worse. In hindsight I underestimated the migration effort."),
    ("I had 3 engineers reporting to me directly. The cross-functional group "
     "for the migration was 12 people across two teams. I owned hiring and "
     "performance for my 3 and drove the technical direction for the wider "
     "group."),
]

ANSWERS_C = [
    ("I always focus on delivering value and making sure the team is aligned. "
     "My approach is to drive excellence through clear communication."),
    ("I've led many high-performing teams throughout my career and I'm "
     "passionate about developing talent and driving transformational "
     "outcomes."),
]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def org(db):
    org_id = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org_id, "n": f"e2e-{org_id.hex[:8]}"})
    await db.commit()
    yield org_id
    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": org_id})
    await db.commit()


@pytest_asyncio.fixture
async def job(db, org):
    job_id = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status) VALUES (:i,:o,:t,:d,'open')"""),
        {"i": job_id, "o": org, "t": JOB_TITLE, "d": "Payments platform."})
    await db.commit()
    return job_id


async def _run(db, org, job, *, name, email, resume, answers, consent=True):
    """The whole journey for one candidate."""
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,:n,:e,:r,'new')"""),
        {"i": cand, "o": org, "j": job, "n": name, "e": email, "r": resume})
    await db.commit()

    consent_id = None
    if consent:
        c = await R.create_consent(
            db, org_id=org, candidate_id=cand,
            disclosure_text=("This interview is conducted by an AI system and "
                             "is recorded. Your answers are assessed against "
                             "the role's competencies by a human recruiter."),
            policy_version="2026.08")
        consent_id = c.id
        await db.commit()

    prepared = await runner.prepare(
        db, org_id=org, job_posting_id=job, candidate_id=cand,
        job_title=JOB_TITLE, resume_text=resume, consent_id=consent_id)
    await db.commit()

    interview_id = prepared["interview"].id
    attempt = await runner.start(db, org_id=org, interview_id=interview_id)
    await db.commit()

    asked = []
    for i in range(14):                       # bounded: a loop, not a promise
        step = await runner.next_question(db, org_id=org,
                                          interview_id=interview_id,
                                          attempt_id=attempt.id)
        if step.finished:
            break
        assert step.has_question
        asked.append(step.question)
        await runner.submit_answer(
            db, org_id=org, interview_id=interview_id,
            question_id=step.question.id,
            answer_text=answers[len(asked) % len(answers)],
            attempt_id=attempt.id,
            recording_start_ms=len(asked) * 60_000,
            recording_end_ms=len(asked) * 60_000 + 45_000)
        await db.commit()

    final = await runner.finalise(db, org_id=org, interview_id=interview_id)
    await db.commit()
    return {"candidate_id": cand, "interview_id": interview_id,
            "asked": asked, **final}


# ===========================================================================
# The journey
# ===========================================================================

@pytest.mark.asyncio
async def test_a_whole_interview_runs_and_persists(db, org, job):
    out = await _run(db, org, job, name="Ada", email="a@example.test",
                     resume=RESUME_A, answers=ANSWERS_A)

    assert len(out["asked"]) >= 4, "the interview asked almost nothing"

    card = out["scorecard"]
    assert card.overall_state == S.SCORED
    assert card.decision_authority == "RECRUITER_DECISION_SUPPORT"

    # Everything is readable back out of the database.
    row = (await db.execute(text(
        "SELECT overall_score, completeness_state FROM public.interview_scorecards "
        "WHERE interview_id = :i"), {"i": out["interview_id"]})).first()
    assert row is not None and row[0] is not None

    summary = (await db.execute(text(
        "SELECT headline, strengths FROM public.interview_summaries "
        "WHERE interview_id = :i"), {"i": out["interview_id"]})).first()
    assert summary is not None and summary[0]


@pytest.mark.asyncio
async def test_consent_is_required_before_the_first_question(db, org, job):
    """Fails closed. An interview that has begun has already taken the
    candidate's words, whether or not a file was written."""
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,'NoConsent','nc@example.test',:r,'new')"""),
        {"i": cand, "o": org, "j": job, "r": RESUME_A})
    await db.commit()

    prepared = await runner.prepare(
        db, org_id=org, job_posting_id=job, candidate_id=cand,
        job_title=JOB_TITLE, resume_text=RESUME_A, consent_id=None)
    await db.commit()

    with pytest.raises(runner.ConsentMissing):
        await runner.start(db, org_id=org,
                           interview_id=prepared["interview"].id)


@pytest.mark.asyncio
async def test_every_score_can_be_traced_to_a_quote_and_a_timecode(db, org, job):
    """THE PRODUCT CLAIM.

    For each scored competency, walk assessment -> assessment_evidence ->
    interview_evidence and require a quote and a recording offset. This is what
    makes the recruiter's click work, and it is the thing a generic AI
    interviewer cannot do.
    """
    out = await _run(db, org, job, name="Ada", email="a@example.test",
                     resume=RESUME_A, answers=ANSWERS_A)

    rows = (await db.execute(text("""
        SELECT ca.competency_key, ca.score, ie.quote, ie.quote_start_ms
        FROM public.competency_assessments ca
        JOIN public.assessment_evidence ae ON ae.assessment_id = ca.id
        JOIN public.interview_evidence ie ON ie.id = ae.evidence_id
        WHERE ca.interview_id = :i AND ca.state = 'SCORED'
          AND ae.role = 'SUPPORTING'
    """), {"i": out["interview_id"]})).all()

    assert rows, "no scored competency cited any supporting evidence"
    for key, score, quote, start_ms in rows:
        assert quote and quote.strip(), f"{key} cites evidence with no quote"
        assert start_ms is not None, (
            f"{key} cites evidence with no recording offset; the recruiter "
            f"cannot jump to it")


@pytest.mark.asyncio
async def test_the_managed_twelve_case_is_partially_supported(db, org, job):
    """The specification's own example, end to end through the database."""
    out = await _run(db, org, job, name="Ada", email="a@example.test",
                     resume=RESUME_A, answers=ANSWERS_A)

    rows = (await db.execute(text("""
        SELECT cv.verdict, cv.established_text, cv.rationale, cc.claim_text
        FROM public.claim_verifications cv
        JOIN public.candidate_claims cc ON cc.id = cv.claim_id
        WHERE cv.interview_id = :i AND cc.claim_type = 'LEADERSHIP'
    """), {"i": out["interview_id"]})).all()

    assert rows, "the team-size claim was never verified"
    verdict, established, rationale, claim_text = rows[0]
    assert verdict == "PARTIALLY_SUPPORTED", (
        f"'managed 12' with 3 direct reports and a 12-person project group "
        f"came out as {verdict}; both statements are true and the verdict must "
        f"say so without calling it a contradiction")
    assert "3" in (established or "")
    assert "not a discrepancy" in rationale or "Both can be true" in rationale


@pytest.mark.asyncio
async def test_the_vague_candidate_is_not_scored_on_adjectives(db, org, job):
    """Candidate C reads impressively and establishes nothing.

    The required outcome is INSUFFICIENT_EVIDENCE on most competencies -- not
    a middling score. A middling score would be a finding about C that the
    interview did not support.
    """
    a = await _run(db, org, job, name="Ada", email="a2@example.test",
                   resume=RESUME_A, answers=ANSWERS_A)
    c = await _run(db, org, job, name="Cara", email="c@example.test",
                   resume=RESUME_C, answers=ANSWERS_C)

    def states(out):
        return [x.state for x in out["scorecard"].assessments]

    a_scored = sum(1 for s in states(a) if s == S.SCORED)
    c_scored = sum(1 for s in states(c) if s == S.SCORED)

    assert c_scored < a_scored, (
        f"the evidence-free candidate had {c_scored} competencies scored "
        f"against {a_scored} for the specific one; the instrument is reading "
        f"tone rather than evidence")

    c_insufficient = sum(1 for s in states(c)
                         if s in (S.INSUFFICIENT_EVIDENCE, S.NOT_PROBED))
    assert c_insufficient >= 1


@pytest.mark.asyncio
async def test_two_candidates_are_asked_different_questions(db, org, job):
    a = await _run(db, org, job, name="Ada", email="a3@example.test",
                   resume=RESUME_A, answers=ANSWERS_A)
    c = await _run(db, org, job, name="Cara", email="c3@example.test",
                   resume=RESUME_C, answers=ANSWERS_C)

    qa = {q.question_text for q in a["asked"]}
    qc = {q.question_text for q in c["asked"]}
    assert len(qa - qc) >= 2, (
        "the two interviews asked substantially the same questions despite "
        "different resumes and different answers")


@pytest.mark.asyncio
async def test_a_reconnect_resumes_the_same_interview(db, org, job):
    """A dropped connection must not fork the evidence into two half
    assessments."""
    out = await _run(db, org, job, name="Ada", email="a4@example.test",
                     resume=RESUME_A, answers=ANSWERS_A)

    second = await R.start_attempt(db, org_id=org,
                                   interview_id=out["interview_id"])
    await db.commit()
    assert second.attempt_number == 2

    count = (await db.execute(text(
        "SELECT count(*) FROM public.interviews WHERE candidate_id = :c"),
        {"c": out["candidate_id"]})).scalar_one()
    assert count == 1, "reconnecting created a second interview"

    # The plan and the evidence are still attached to the original.
    qa = await R.load_qa(db, org_id=org, interview_id=out["interview_id"])
    assert len(qa) == len(out["asked"])


@pytest.mark.asyncio
async def test_the_debrief_names_what_was_not_established(db, org, job):
    """The section most tools omit and the one that changes a decision."""
    out = await _run(db, org, job, name="Cara", email="c5@example.test",
                     resume=RESUME_C, answers=ANSWERS_C)

    debrief = out["debrief"]
    assert debrief.unresolved_questions or debrief.recommended_followup, (
        "the debrief said nothing about what the interview failed to establish")
    assert "decision support" in debrief.overall_assessment.lower()


@pytest.mark.asyncio
async def test_every_strength_in_the_debrief_carries_evidence(db, org, job):
    """A claim in the debrief with no evidence id cannot be rendered as a
    clickable jump, so it must not exist."""
    out = await _run(db, org, job, name="Ada", email="a6@example.test",
                     resume=RESUME_A, answers=ANSWERS_A)

    for item in out["debrief"].strengths:
        assert item.evidence_ids, f"strength {item.text[:60]!r} cites nothing"
        assert item.quote, f"strength {item.text[:60]!r} has no quote"
