"""Three candidates, one job, a real database.

This is the acceptance test for the claim that the interviewer is not generic.
It runs against PostgreSQL rather than in-memory objects, because the thing
being asserted is that the plan and its provenance SURVIVE -- an interviewer
whose personalisation lives in a Python dict is a demo.

The candidates are deliberately the three shapes that break naive systems:

  A  senior domain expert, dense quantified evidence
  B  career switcher, adjacent experience, little that pattern-matches
  C  polished resume, confident phrasing, almost nothing concrete

C is the important one. A system that scores on how a resume READS will rate C
highly. A system that scores on evidence should find C has very little to hook
onto, and should say so rather than inventing depth.
"""
from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import claims as C
from app.interview import models as M
from app.interview import repository as R
from app.interview.planner import build_plan
from app.interview.rubrics import RUBRICS, rubric_for_title

from tests._interview_pg import DSN, SKIP_REASON  # noqa: E402

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")


# --- the three candidates --------------------------------------------------

RESUME_A = """Senior Platform Engineer, Acme Payments (2021-2025)
Reduced settlement failures by 40% during the Ledger migration.
Managed a team of 12 engineers across two time zones.
8 years of distributed systems experience.
Built services in Python and Go on AWS, backed by Postgres and Kafka.
Saved $1.2M in annual infrastructure spend by consolidating Kafka clusters.
"""

RESUME_B = """High school science teacher, Lincoln High (2018-2024).
Completed a part-time software bootcamp in 2024.
Built a small inventory tracker in Python for the school laboratory.
Led a department of 4 teachers through a curriculum change.
2 years of volunteer experience maintaining the district website.
"""

RESUME_C = """Results-driven senior technology leader with a proven track record of
delivering transformational outcomes at scale. Passionate about excellence,
innovation and building world-class high-performing teams. Recognised for
strategic vision and thought leadership across the enterprise. Adept at
navigating complex stakeholder landscapes and driving alignment.
Extensive experience across the full technology stack.
"""

JOB_TITLE = "Senior Software Engineer"


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
        await session.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def org(db):
    """A throwaway organisation, removed afterwards."""
    org_id = uuid.uuid4()
    await db.execute(
        text("INSERT INTO public.orgs (id, name) VALUES (:i, :n)"),
        {"i": org_id, "n": f"iv-test-{org_id.hex[:8]}"})
    await db.commit()
    yield org_id
    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": org_id})
    await db.commit()


@pytest_asyncio.fixture
async def job(db, org):
    job_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO public.job_postings (id, org_id, title, description, status)
        VALUES (:i, :o, :t, :d, 'open')"""),
        {"i": job_id, "o": org, "t": JOB_TITLE,
         "d": "Build and operate payment platform services."})
    await db.commit()
    return job_id


async def _make_candidate(db, org, job, name: str, email: str, resume: str):
    cand_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO public.candidates
            (id, org_id, job_posting_id, full_name, email, resume_text, status)
        VALUES (:i, :o, :j, :n, :e, :r, 'new')"""),
        {"i": cand_id, "o": org, "j": job, "n": name, "e": email, "r": resume})
    await db.commit()
    return cand_id


async def _plan_for(db, org, job, name, email, resume, *, role_config=None):
    """Extract -> persist claims -> plan -> persist plan. The real path."""
    cand_id = await _make_candidate(db, org, job, name, email, resume)
    extracted = C.extract_deterministic(
        resume, source_kind=C.RESUME, source_ref=f"resume:{cand_id}")
    claim_rows = await R.save_claims(
        db, org_id=org, candidate_id=cand_id, job_posting_id=job,
        claims=extracted)

    interview = await R.create_interview(
        db, org_id=org, job_posting_id=job, candidate_id=cand_id)
    plan = build_plan(job_title=JOB_TITLE,
                      candidate_claims=R.to_domain_claims(claim_rows),
                      role_config=role_config)
    plan_row = await R.save_plan(db, org_id=org, interview_id=interview.id,
                                 plan=plan, claim_rows=claim_rows)
    await db.commit()
    return {"candidate_id": cand_id, "interview": interview,
            "plan_row": plan_row, "plan": plan, "claims": claim_rows}


# ===========================================================================
# Persistence
# ===========================================================================

@pytest.mark.asyncio
async def test_the_plan_survives_the_process(db, org, job):
    """The point of the schema. Re-read everything from the database."""
    made = await _plan_for(db, org, job, "Ada Lovelace", "a@example.test", RESUME_A)

    plan = await R.load_plan(db, org_id=org, interview_id=made["interview"].id)
    assert plan is not None
    comps = await R.load_competencies(db, org_id=org, plan_id=plan.id)
    assert comps, "a persisted plan with no competencies is not a plan"

    hooked = [c for c in comps if c.hook_claim_id is not None]
    assert hooked, "no competency was bound to a claim row"

    # The hook is a real foreign key, so the claim it came from is readable.
    claim = (await db.execute(
        text("SELECT source_excerpt FROM public.candidate_claims WHERE id = :i"),
        {"i": hooked[0].hook_claim_id})).scalar_one()
    assert claim, "the hook points at a claim row that has no source excerpt"


@pytest.mark.asyncio
async def test_every_claim_keeps_its_source_span(db, org, job):
    made = await _plan_for(db, org, job, "Ada Lovelace", "a@example.test", RESUME_A)
    rows = await R.load_claims(db, org_id=org, candidate_id=made["candidate_id"])
    assert rows

    for r in rows:
        assert r.source_ref, f"{r.claim_type} claim has no source_ref"
        assert r.source_excerpt, f"{r.claim_type} claim has no excerpt"
        assert r.source_span_start is not None
        # The span must still hold against the original document.
        actual = RESUME_A[r.source_span_start:r.source_span_end].strip()
        assert actual == r.source_excerpt.strip(), (
            f"{r.claim_type} span drifted: document says {actual[:60]!r}, "
            f"claim says {r.source_excerpt[:60]!r}")


# ===========================================================================
# Personalisation
# ===========================================================================

@pytest.mark.asyncio
async def test_three_candidates_get_materially_different_questions(db, org, job):
    a = await _plan_for(db, org, job, "Ada", "a@example.test", RESUME_A)
    b = await _plan_for(db, org, job, "Ben", "b@example.test", RESUME_B)
    c = await _plan_for(db, org, job, "Cara", "c@example.test", RESUME_C)

    qa, qb, qc = (set(x["plan"].question_texts()) for x in (a, b, c))

    assert qa != qb and qa != qc and qb != qc, "two candidates got identical plans"

    # Not just "different" -- materially so. A one-word difference would pass a
    # set comparison while being a template substitution.
    assert len(qa - qb) >= 2, (
        f"only {len(qa - qb)} of A's questions differ from B's; that is "
        f"template substitution, not personalisation")


@pytest.mark.asyncio
async def test_the_dense_resume_is_probed_on_its_own_numbers(db, org, job):
    a = await _plan_for(db, org, job, "Ada", "a@example.test", RESUME_A)
    joined = " ".join(a["plan"].question_texts())

    assert "40" in joined, "the 40% claim was never put to the candidate"
    assert "settlement failures" in joined.lower()
    assert "12" in joined, "the team-of-12 claim was never probed"


@pytest.mark.asyncio
async def test_the_vague_resume_yields_few_hooks_rather_than_invented_depth(
        db, org, job):
    """Candidate C reads impressively and claims almost nothing checkable.

    The right behaviour is a mostly-generic plan. A system that produced a
    confidently personalised plan for C would be pattern-matching on tone.
    """
    a = await _plan_for(db, org, job, "Ada", "a@example.test", RESUME_A)
    c = await _plan_for(db, org, job, "Cara", "c@example.test", RESUME_C)

    ca, cc = a["plan"].coverage(), c["plan"].coverage()
    assert cc["personalised"] < ca["personalised"], (
        f"the vague resume produced {cc['personalised']} personalised "
        f"competencies against the dense resume's {ca['personalised']}. If "
        f"they match, the planner is hooking onto adjectives.")

    # And it must not have quietly invented a quantity.
    joined = " ".join(c["plan"].question_texts())
    assert "Your resume says" not in joined or "%" not in joined, (
        "a quantified probe was generated for a resume with no quantities")


@pytest.mark.asyncio
async def test_required_competencies_survive_a_thin_resume(db, org, job):
    """The fairness property: a sparse resume must not shrink the interview."""
    rubric = rubric_for_title(JOB_TITLE)
    required = set(rubric.required_keys())

    for name, email, resume in (("Ada", "a@example.test", RESUME_A),
                                ("Ben", "b@example.test", RESUME_B),
                                ("Cara", "c@example.test", RESUME_C)):
        made = await _plan_for(db, org, job, name, email, resume)
        plan = await R.load_plan(db, org_id=org, interview_id=made["interview"].id)
        comps = await R.load_competencies(db, org_id=org, plan_id=plan.id)
        planned = {c.competency_key for c in comps}
        missing = required - planned
        assert not missing, (
            f"{name} was not planned for required competencies {sorted(missing)}. "
            f"A thin resume must not shrink what the candidate is assessed on.")


@pytest.mark.asyncio
async def test_changing_only_the_name_changes_nothing(db, org, job):
    """Fairness control. The name is not a claim and must not reach the plan."""
    one = await _plan_for(db, org, job, "Ada Lovelace", "a1@example.test", RESUME_A)
    two = await _plan_for(db, org, job, "Rajesh Patel", "a2@example.test", RESUME_A)

    assert one["plan"].question_texts() == two["plan"].question_texts(), (
        "the candidate's name altered the interview plan")
    assert one["plan"].coverage() == two["plan"].coverage()


# ===========================================================================
# Recruiter configuration
# ===========================================================================

@pytest.mark.asyncio
async def test_a_must_ask_question_is_planned_and_required(db, org, job):
    made = await _plan_for(
        db, org, job, "Ada", "a@example.test", RESUME_A,
        role_config={"must_ask_questions": [
            "Are you able to work on-call one week in six?"]})

    plan = await R.load_plan(db, org_id=org, interview_id=made["interview"].id)
    comps = await R.load_competencies(db, org_id=org, plan_id=plan.id)
    must = [c for c in comps if c.competency_key.startswith("must_ask_")]
    assert len(must) == 1
    assert must[0].is_required is True
    assert "on-call" in must[0].initial_question


@pytest.mark.asyncio
async def test_config_cannot_switch_off_a_rubric_required_competency(db, org, job):
    """The one edit a hiring manager may not make.

    Weights and extra requirements are theirs. Removing a competency the rubric
    marks required would let a role quietly stop being assessed on the thing
    the rubric exists to protect.
    """
    rubric = rubric_for_title(JOB_TITLE)
    victim = rubric.required_keys()[0]

    made = await _plan_for(
        db, org, job, "Ada", "a@example.test", RESUME_A,
        role_config={"required_competencies": [],
                     "competency_weights": {victim: 0.0}})

    plan = await R.load_plan(db, org_id=org, interview_id=made["interview"].id)
    comps = await R.load_competencies(db, org_id=org, plan_id=plan.id)
    row = next(c for c in comps if c.competency_key == victim)
    assert row.is_required is True, (
        f"role config switched off rubric-required competency {victim!r}")
    # The weight IS the recruiter's to set, including to zero.
    assert float(row.role_weight) == 0.0
