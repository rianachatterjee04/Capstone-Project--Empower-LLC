"""What reaches a candidate over the wire.

THE DEFECT THIS EXISTS FOR
The answer endpoint returned the full gap analysis to every caller, and the
candidate page "deliberately ignored" it in React. Anyone with DevTools open
therefore saw which competency was being probed, that their previous answer
read as vague, and how much evidence it produced -- enough to work out the
scoring strategy and game the remainder of the interview.

Hiding data in a component while shipping it over the wire is a disclosure.

So these tests read the ACTUAL RESPONSE BODY, walk it to arbitrary depth, and
assert the forbidden names are absent. A test that checked the React component
would have passed the entire time the leak existed.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import dto as DTO
from app.interview import repository as R
from app.interview import runner
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

RESUME = ("Senior Platform Engineer. Reduced settlement failures by 40% during "
          "the Ledger migration. Managed a team of 12 engineers. 8 years of "
          "distributed systems experience.")

ANSWER = ("I always try to make sure the team is aligned and we deliver value. "
          "My approach is to focus on communication.")


def _walk(payload: Any, path: str = "") -> list[str]:
    """Every key present in a payload, at any depth, with its path."""
    found = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            here = f"{path}.{k}" if path else k
            found.append(here)
            found.extend(_walk(v, here))
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            found.extend(_walk(v, f"{path}[{i}]"))
    return found


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def interview(db):
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"boundary-{org.hex[:6]}"})
    job = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status)
        VALUES (:i,:o,'Senior Software Engineer','d','open')"""),
        {"i": job, "o": org})
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,'Test Person','t@example.test',:r,'new')"""),
        {"i": cand, "o": org, "j": job, "r": RESUME})
    await db.commit()

    consent = await R.create_consent(
        db, org_id=org, candidate_id=cand,
        disclosure_text="x" * 40, policy_version="2026.08")
    await db.commit()
    prepared = await runner.prepare(
        db, org_id=org, job_posting_id=job, candidate_id=cand,
        job_title="Senior Software Engineer", resume_text=RESUME,
        consent_id=consent.id)
    await db.commit()
    attempt = await runner.start(db, org_id=org,
                                 interview_id=prepared["interview"].id)
    await db.commit()

    yield {"org": org, "interview_id": prepared["interview"].id,
           "attempt_id": attempt.id}

    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": org})
    await db.commit()


class _Actor:
    def __init__(self, org_id, role):
        self.org_id = org_id
        self.role = role
        self.user_id = None
        self.email = "x@example.test"
        self.claims = {"email": "x@example.test"}


# ===========================================================================
# The wire
# ===========================================================================

@pytest.mark.asyncio
async def test_the_candidate_next_response_carries_no_recruiter_data(
        db, interview):
    from app.api.routers import interview_v2 as R2

    body = await R2.next_question(
        interview["interview_id"], attempt_id=interview["attempt_id"],
        actor=_Actor(interview["org"], "employee"), db=db)

    keys = {k.rsplit(".", 1)[-1] for k in _walk(body)}
    leaked = keys & DTO.FORBIDDEN_KEYS
    assert not leaked, (
        f"the candidate response contains {sorted(leaked)}. These are "
        f"recruiter-only and must not be on the wire at all.")

    # And it still contains what the candidate actually needs.
    assert body["question"]["text"]
    assert "is_followup" in body["question"]


@pytest.mark.asyncio
async def test_staff_still_get_the_operational_detail(db, interview):
    """Positive control. If the boundary were implemented by removing the
    fields entirely, the recruiter live view would break and every test above
    would still pass."""
    from app.api.routers import interview_v2 as R2

    body = await R2.next_question(
        interview["interview_id"], attempt_id=interview["attempt_id"],
        actor=_Actor(interview["org"], "owner"), db=db)

    assert "probe_depth" in body["question"]
    assert "competency_id" in body["question"]
    assert "kind" in body["question"]


@pytest.mark.asyncio
async def test_the_candidate_answer_acknowledgement_reveals_nothing(
        db, interview):
    """The original leak. A vague answer is used on purpose: it produces the
    richest gap analysis, so if anything escapes it escapes here."""
    from app.api.routers import interview_v2 as R2

    step = await R2.next_question(
        interview["interview_id"], attempt_id=interview["attempt_id"],
        actor=_Actor(interview["org"], "owner"), db=db)
    qid = uuid.UUID(step["question"]["id"])

    body = await R2.answer(
        interview["interview_id"],
        R2.AnswerIn(question_id=qid, answer_text=ANSWER,
                    attempt_id=interview["attempt_id"]),
        actor=_Actor(interview["org"], "employee"), db=db)

    keys = {k.rsplit(".", 1)[-1] for k in _walk(body)}
    leaked = keys & DTO.FORBIDDEN_KEYS
    assert not leaked, (
        f"the candidate answer acknowledgement leaked {sorted(leaked)}")
    assert body == {"answer_id": body["answer_id"], "accepted": True}, (
        f"the acknowledgement should say only that the answer was stored; it "
        f"returned {sorted(body)}")


@pytest.mark.asyncio
async def test_the_recruiter_answer_response_still_carries_the_analysis(
        db, interview):
    """Positive control for the branch above."""
    from app.api.routers import interview_v2 as R2

    step = await R2.next_question(
        interview["interview_id"], attempt_id=interview["attempt_id"],
        actor=_Actor(interview["org"], "owner"), db=db)
    qid = uuid.UUID(step["question"]["id"])

    body = await R2.answer(
        interview["interview_id"],
        R2.AnswerIn(question_id=qid, answer_text=ANSWER,
                    attempt_id=interview["attempt_id"]),
        actor=_Actor(interview["org"], "owner"), db=db)

    assert "recruiter_view" in body
    assert "gaps" in body["recruiter_view"]


@pytest.mark.asyncio
async def test_a_candidate_cannot_reach_the_playback_endpoint(db, interview):
    """Everything about the assessment lives there."""
    from fastapi import HTTPException
    from app.api.routers import interview_v2 as R2

    with pytest.raises(HTTPException) as exc:
        await R2.playback(interview["interview_id"],
                          actor=_Actor(interview["org"], "employee"), db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_a_candidate_cannot_finalise_or_compare(db, interview):
    from fastapi import HTTPException
    from app.api.routers import interview_v2 as R2

    for call in (
        lambda: R2.finalise(interview["interview_id"],
                            actor=_Actor(interview["org"], "employee"), db=db),
        lambda: R2.compare(uuid.uuid4(),
                           actor=_Actor(interview["org"], "employee"), db=db),
    ):
        with pytest.raises(HTTPException) as exc:
            await call()
        assert exc.value.status_code == 403


# ===========================================================================
# The serialiser itself
# ===========================================================================

def test_the_serialiser_refuses_a_forbidden_field():
    """Deny by default, enforced on the way out rather than only in a test."""
    with pytest.raises(DTO.AudienceViolation):
        DTO.candidate_safe({"question": {"text": "x", "competency_key": "y"}})


def test_the_serialiser_walks_nested_structures():
    with pytest.raises(DTO.AudienceViolation):
        DTO.candidate_safe({"a": [{"b": {"score": 3.0}}]})


def test_the_serialiser_allows_a_clean_payload():
    """Positive control: it must not refuse everything."""
    out = DTO.candidate_safe({"finished": False,
                              "question": {"id": "1", "text": "hello",
                                           "sequence": 1, "is_followup": True}})
    assert out["question"]["text"] == "hello"


def test_probe_depth_is_on_the_forbidden_list():
    """It looks harmless and is not.

    A candidate who knows they are on the third follow-up about the same thing
    has been told the system is not satisfied -- mid-interview evaluative
    feedback delivered as an integer.
    """
    assert "probe_depth" in DTO.FORBIDDEN_KEYS
    assert "evidence_captured" in DTO.FORBIDDEN_KEYS
    assert "gaps" in DTO.FORBIDDEN_KEYS
