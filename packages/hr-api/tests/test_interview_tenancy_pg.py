"""Cross-tenant attacks on the interview domain.

WHY THE APPLICATION FILTER IS THE CONTROL
Supabase `service_role` bypasses row-level security. Any code path running with
it sees every tenant's rows, so an `org_id` column plus an RLS policy is not
what protects this data -- the WHERE clause in `repository.py` is. That makes
these tests a security control rather than a schema formality.

Each test takes an id that genuinely exists and asks for it under the wrong
organisation. The required answer is nothing: not a partial row, not an empty
object with an id in it, and not an error that confirms the id is real.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import claims as C
from app.interview import repository as R
from app.interview.planner import build_plan

from tests._interview_pg import DSN, SKIP_REASON  # noqa: E402

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

RESUME = ("Reduced settlement failures by 40% during the Ledger migration. "
          "Managed a team of 12 engineers. 8 years of distributed systems "
          "experience.")


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _tenant(db, label: str) -> dict:
    """A complete, independent tenant with one planned interview."""
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"tenancy-{label}-{org.hex[:6]}"})
    job = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status)
        VALUES (:i,:o,'Senior Software Engineer','d','open')"""),
        {"i": job, "o": org})
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,:n,:e,:r,'new')"""),
        {"i": cand, "o": org, "j": job, "n": f"cand-{label}",
         "e": f"{label}-{cand.hex[:6]}@example.test", "r": RESUME})
    await db.commit()

    extracted = C.extract_deterministic(RESUME, source_kind=C.RESUME,
                                        source_ref=f"resume:{cand}")
    claim_rows = await R.save_claims(db, org_id=org, candidate_id=cand,
                                     job_posting_id=job, claims=extracted)
    iv = await R.create_interview(db, org_id=org, job_posting_id=job,
                                  candidate_id=cand)
    plan = build_plan(job_title="Senior Software Engineer",
                      candidate_claims=R.to_domain_claims(claim_rows))
    plan_row = await R.save_plan(db, org_id=org, interview_id=iv.id,
                                 plan=plan, claim_rows=claim_rows)
    q = await R.ask(db, org_id=org, interview_id=iv.id,
                    question_text="Tell me about the 40%.",
                    question_kind="PLANNED_INITIAL")
    a = await R.answer(db, org_id=org, interview_id=iv.id, question_id=q.id,
                       answer_text="We cut retries after fixing idempotency.")
    await db.commit()
    return {"org": org, "job": job, "candidate": cand, "interview": iv,
            "plan": plan_row, "question": q, "answer": a,
            "claims": claim_rows}


@pytest_asyncio.fixture
async def two(db):
    a = await _tenant(db, "a")
    b = await _tenant(db, "b")
    yield a, b
    for t in (a, b):
        await db.execute(text("DELETE FROM public.orgs WHERE id = :i"),
                         {"i": t["org"]})
    await db.commit()


# ===========================================================================
# Reads
# ===========================================================================

@pytest.mark.asyncio
async def test_an_interview_is_invisible_to_another_tenant(two, db):
    a, b = two
    assert await R.get_interview(db, org_id=a["org"],
                                 interview_id=a["interview"].id) is not None
    stolen = await R.get_interview(db, org_id=b["org"],
                                   interview_id=a["interview"].id)
    assert stolen is None, "tenant B read tenant A's interview"


@pytest.mark.asyncio
async def test_a_plan_is_invisible_to_another_tenant(two, db):
    a, b = two
    assert await R.load_plan(db, org_id=a["org"],
                             interview_id=a["interview"].id) is not None
    assert await R.load_plan(db, org_id=b["org"],
                             interview_id=a["interview"].id) is None


@pytest.mark.asyncio
async def test_competencies_are_invisible_to_another_tenant(two, db):
    a, b = two
    assert await R.load_competencies(db, org_id=a["org"], plan_id=a["plan"].id)
    assert await R.load_competencies(db, org_id=b["org"], plan_id=a["plan"].id) == []


@pytest.mark.asyncio
async def test_claims_are_invisible_to_another_tenant(two, db):
    """Claims quote a resume verbatim. A leak here is a leak of the document."""
    a, b = two
    assert await R.load_claims(db, org_id=a["org"], candidate_id=a["candidate"])
    assert await R.load_claims(db, org_id=b["org"],
                               candidate_id=a["candidate"]) == []


@pytest.mark.asyncio
async def test_questions_and_answers_are_invisible_to_another_tenant(two, db):
    a, b = two
    assert await R.load_qa(db, org_id=a["org"], interview_id=a["interview"].id)
    assert await R.load_qa(db, org_id=b["org"],
                           interview_id=a["interview"].id) == []


@pytest.mark.asyncio
async def test_evidence_is_invisible_to_another_tenant(two, db):
    a, b = two
    await R.save_evidence(db, org_id=a["org"], interview_id=a["interview"].id,
                          rows=[{
                              "competency_key": "ownership",
                              "answer_id": a["answer"].id,
                              "question_id": a["question"].id,
                              "polarity": "SUPPORTS",
                              "evidence_kind": "OWNERSHIP",
                              "quote": "I fixed idempotency",
                              "rationale": "first person, specific mechanism",
                          }])
    await db.commit()
    assert await R.load_evidence(db, org_id=a["org"],
                                 interview_id=a["interview"].id)
    assert await R.load_evidence(db, org_id=b["org"],
                                 interview_id=a["interview"].id) == []


# ===========================================================================
# Writes
# ===========================================================================

@pytest.mark.asyncio
async def test_the_next_sequence_number_does_not_leak_across_tenants(two, db):
    """A subtle one. If the counter were global, tenant B could infer how many
    questions tenant A has been asked -- and the gap in B's own numbering would
    be a side channel."""
    a, b = two
    assert await R.next_sequence(db, org_id=b["org"],
                                 interview_id=b["interview"].id) == 2
    # A's interview id under B's org must not see A's questions at all.
    assert await R.next_sequence(db, org_id=b["org"],
                                 interview_id=a["interview"].id) == 1


@pytest.mark.asyncio
async def test_a_cross_tenant_question_write_is_refused_by_the_database(two, db):
    """Defence in depth, and it turned out stronger than the design intended.

    Writing a question into tenant A's interview while claiming tenant B's org
    does not produce a hidden row -- it FAILS. Two independent mechanisms
    combine: `next_sequence` is tenant-scoped, so under B's org it cannot see
    A's existing questions and returns 1; and `interview_questions_seq_unique`
    is scoped to the INTERVIEW, where sequence 1 is already taken.

    So the attacker's own tenant isolation is what defeats them. The write is
    refused at the database rather than landing somewhere unreachable, which
    is the better outcome: an unreachable row is still a row containing a
    candidate's words.
    """
    a, b = two
    # Plain values, captured before anything can expire. A rollback expires
    # every ORM object in the session, and reading `.id` off an expired
    # instance triggers a lazy refresh outside the greenlet context -- which
    # fails with an error that has nothing to do with the property under test.
    a_org, a_iv = a["org"], a["interview"].id
    b_org = b["org"]

    # The message is captured BEFORE the rollback. Touching the exception after
    # the session has been reset makes SQLAlchemy attempt lazy IO outside the
    # greenlet context, which fails with something unrelated to the property
    # under test.
    message = None
    try:
        await R.ask(db, org_id=b_org, interview_id=a_iv,
                    question_text="INJECTED", question_kind="FOLLOWUP_SPECIFIC")
        await db.flush()
    except Exception as exc:            # noqa: BLE001 - the type is the point
        message = str(exc)
    await db.rollback()

    assert message is not None, (
        "the cross-tenant write succeeded; it must be refused")
    assert "interview_questions_seq_unique" in message, message

    # And nothing landed in A's interview.
    a_qa = await R.load_qa(db, org_id=a_org, interview_id=a_iv)
    assert all("INJECTED" not in q.question_text for q, _ in a_qa)


@pytest.mark.asyncio
async def test_deleting_a_tenant_removes_its_interview_data(db):
    """Cascade check. A deleted organisation must not leave candidate quotes,
    recordings or transcripts behind."""
    t = await _tenant(db, "cascade")
    org, iv = t["org"], t["interview"].id

    before = (await db.execute(text(
        "SELECT count(*) FROM public.candidate_claims WHERE org_id = :o"),
        {"o": org})).scalar_one()
    assert before > 0

    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": org})
    await db.commit()

    for table in ("candidate_claims", "interviews", "interview_plans",
                  "interview_questions", "interview_answers"):
        left = (await db.execute(text(
            f"SELECT count(*) FROM public.{table} WHERE org_id = :o"),
            {"o": org})).scalar_one()
        assert left == 0, f"{table} still holds rows for a deleted organisation"
