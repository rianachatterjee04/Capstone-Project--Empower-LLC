"""Quality invariants over a WHOLE interview, not one generated question.

test_interview_conversation_quality.py covers question generation thoroughly:
phrasing, hooks, lexicon, and -- notably -- that a probe body is exposed "so the
runner can deduplicate". That the body is exposed is not the same claim as that
the runner deduplicates, and only one of those is what a candidate experiences.

So these run a full interview through the real runner and assert on the whole
transcript. The candidate is deliberately EVASIVE: generic, substantive-length
answers that establish nothing. That is the hardest case for repetition, because
every answer leaves the same gap and the obvious failure is to keep asking the
same question in the same words until the interview gives up.
"""
from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import repository as R
from app.interview import runner
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

RESUME = ("Senior Platform Engineer. Reduced settlement failures by 40%. "
          "Managed a team of 12 engineers. 8 years distributed systems.")

#: Substantive in length, empty in content. Cycled so no two consecutive
#: answers are identical -- a candidate repeating themselves verbatim would be
#: an easier case than this one.
EVASIVE = [
    "I always focus on delivering value and making sure the team is aligned "
    "around the outcome we care about most.",
    "I would say it comes back to leadership and vision. When you set the "
    "right direction and empower people, the outcomes follow.",
    "It really depends on the context, but generally I try to bring people "
    "together and keep everyone moving in the same direction.",
]

SPECIFIC = [
    "I rewrote the settlement reconciler. It was failing about 4% of "
    "settlements a day and I took that to 0.2% over six weeks.",
    "The baseline was 412 failures a day measured over the previous quarter, "
    "and after the rewrite it was 19 a day measured the same way.",
    "I chose write-ahead logging over a two-phase commit because the second "
    "would have added a network round trip to every settlement.",
]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _run_interview(db, answers, *, max_questions=40):
    """A full interview, driven the way the product drives one."""
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"q-{org.hex[:6]}"})
    job = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status)
        VALUES (:i,:o,'Senior Software Engineer','d','open')"""),
        {"i": job, "o": org})
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,'Q','q@example.test',:r,'new')"""),
        {"i": cand, "o": org, "j": job, "r": RESUME})
    await db.commit()

    consent = await R.create_consent(
        db, org_id=org, candidate_id=cand, disclosure_text="x" * 40,
        policy_version="2026.08", video=True, audio=True)
    await db.commit()
    prepared = await runner.prepare(
        db, org_id=org, job_posting_id=job, candidate_id=cand,
        job_title="Senior Software Engineer", resume_text=RESUME,
        consent_id=consent.id)
    await db.commit()
    iid = prepared["interview"].id
    await runner.start(db, org_id=org, interview_id=iid)
    await db.commit()

    asked = []
    for i in range(max_questions):
        step = await runner.next_question(db, org_id=org, interview_id=iid)
        await db.commit()
        if step.finished or not step.has_question:
            break
        q = step.question
        asked.append({
            "text": q.question_text,
            "kind": q.question_kind,
            "depth": q.probe_depth or 0,
            "competency_id": str(q.competency_id) if q.competency_id else None,
        })
        await runner.submit_answer(
            db, org_id=org, interview_id=iid, question_id=q.id,
            answer_text=answers[i % len(answers)])
        await db.commit()
    else:
        pytest.fail(
            f"the interview asked {max_questions} questions without finishing. "
            f"An evasive candidate must not be able to make it run forever.")
    return {"org": org, "interview_id": iid, "asked": asked}


# ── the invariants ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_evasive_candidate_is_never_asked_the_same_question_twice(db):
    run = await _run_interview(db, EVASIVE)
    texts = [a["text"] for a in run["asked"]]
    dupes = {t for t in texts if texts.count(t) > 1}
    assert not dupes, (
        "the interview repeated a question verbatim, which reads as the "
        f"interviewer not listening: {sorted(dupes)}")


@pytest.mark.asyncio
async def test_an_evasive_candidate_does_not_make_the_interview_run_forever(db):
    """The termination guarantee. Every answer leaves the same gap, so a
    follow-up rule keyed only on 'is there still a gap' never stops."""
    run = await _run_interview(db, EVASIVE)
    assert 7 <= len(run["asked"]) <= 25, (
        f"asked {len(run['asked'])} questions of a candidate who established "
        f"nothing")


@pytest.mark.asyncio
async def test_probe_depth_is_bounded(db):
    run = await _run_interview(db, EVASIVE)
    depths = [a["depth"] for a in run["asked"]]
    assert max(depths) <= 3, (
        f"probed to depth {max(depths)}. Past a point, asking again is not "
        f"interviewing -- it is telling the candidate they are failing.")


@pytest.mark.asyncio
async def test_every_competency_is_actually_put_to_the_candidate(db):
    """A competency assessed NOT_PROBED because the loop never got to it is a
    different failure from one the candidate could not evidence, and the
    scorecard's completeness claim depends on the difference."""
    run = await _run_interview(db, EVASIVE)
    plan = await R.load_plan(db, org_id=run["org"],
                             interview_id=run["interview_id"])
    comps = await R.load_competencies(db, org_id=run["org"], plan_id=plan.id)
    required = {str(c.id) for c in comps if getattr(c, "is_required", True)}
    asked_of = {a["competency_id"] for a in run["asked"]} - {None}
    missed = required - asked_of
    assert not missed, f"{len(missed)} required competencies were never asked"


@pytest.mark.asyncio
async def test_no_single_competency_monopolises_the_interview(db):
    run = await _run_interview(db, EVASIVE)
    counts = {}
    for a in run["asked"]:
        counts[a["competency_id"]] = counts.get(a["competency_id"], 0) + 1
    worst = max(counts.values())
    assert worst <= 4, (
        f"one competency took {worst} of {len(run['asked'])} questions, "
        f"which leaves the rest of the rubric unevidenced")


# ── control: the two candidates are treated differently ───────────────────

@pytest.mark.asyncio
async def test_control_a_specific_candidate_is_probed_less_than_an_evasive_one(db):
    """The adaptive claim, end to end. If both candidates got the same
    interview, every invariant above would still pass and the follow-up engine
    would be doing nothing.
    """
    evasive = await _run_interview(db, EVASIVE)
    specific = await _run_interview(db, SPECIFIC)

    e_depth = sum(a["depth"] for a in evasive["asked"])
    s_depth = sum(a["depth"] for a in specific["asked"])
    assert e_depth > s_depth, (
        f"the candidate who established nothing was probed no harder "
        f"(total depth {e_depth}) than the one who gave specifics ({s_depth}). "
        f"That is the adaptive behaviour not happening.")


@pytest.mark.asyncio
async def test_control_the_invariants_are_not_vacuously_true(db):
    """Each assertion above only means something if the interview actually
    exercises it: follow-ups must happen, several questions must share a
    competency, and enough questions must be asked for repetition to be
    possible at all.
    """
    run = await _run_interview(db, EVASIVE)
    asked = run["asked"]

    assert len(asked) >= 9, (
        f"only {len(asked)} questions asked — too few for 'never repeats' to "
        f"be a meaningful claim")
    assert max(a["depth"] for a in asked) >= 1, (
        "no follow-up was ever generated, so the depth bound is untested")
    counts = {}
    for a in asked:
        counts[a["competency_id"]] = counts.get(a["competency_id"], 0) + 1
    assert max(counts.values()) >= 2, (
        "no competency was asked about twice, so the monopoly bound and the "
        "de-duplication are both untested")
