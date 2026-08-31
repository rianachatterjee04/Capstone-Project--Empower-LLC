"""Does the interview actually feel role-specific, or just differently labelled?

Three trucking roles run end to end, and the assertions are about the
CONVERSATION rather than the score:

  robotic repetition            the same sentence twice in one interview
  generic follow-ups            every probe is "tell me more"
  redundant probing             a strong answer gets interrogated anyway
  vocabulary leakage            software words in a driver interview
  identical rhythm              two roles producing the same shape of question

The last one is the sharpest. A system that swaps a noun and keeps the
sentence has not personalised anything, and a diff of question TEXT would not
catch it -- the questions differ while the interview is the same. So the tests
compare the kinds of question asked and the claims they hook onto.
"""
from __future__ import annotations

import re
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import models as M
from app.interview import repository as R
from app.interview import runner
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")


ROLES = {
    "CDL Driver — Regional Reefer": {
        "resume": """Kenworth T680 / reefer, 6 years OTR and regional.
Class A CDL, clean MVR. Tanker endorsement.
Texas to the Midwest hauling refrigerated produce.
Averaged 2,800 miles a week with a 98% on-time record.
""",
        "answers": {
            "equipment_experience": (
                "Six years on reefer, mostly a Kenworth T680. McAllen up to "
                "Chicago about three times a month for four of those years."),
            "safety_judgement": (
                "Coming through Amarillo in February the road was glazing "
                "over. I shut down at a truck stop and called dispatch before "
                "they called me. We lost the appointment and ate a "
                "redelivery. I would do it again."),
            "exception_handling": (
                "A reefer unit failed outside Joplin with 42,000 pounds of "
                "lettuce. I pulled the temperature log, photographed the "
                "readout, called dispatch and the customer's after-hours "
                "line, and got to a shop inside ninety minutes."),
            "compliance_awareness": (
                "Level 2 in Oklahoma last year. They looked at my logs and my "
                "medical card. I had a marker light out I had missed on the "
                "pre-trip, so that went on the report."),
            "dispatch_communication": (
                "There is a receiver in Milwaukee that sits you four hours "
                "without a check call. I started calling the morning of and "
                "told dispatch to build it into the schedule."),
            "ownership": (
                "The reefer failure. Nobody told me to pull the temperature "
                "log; I did it because it was the only thing that would stop "
                "the load being rejected."),
            "evidence_specificity": (
                "McAllen to Elk Grove Village last March. 42,000 pounds of "
                "romaine, set point 34 degrees, picked up Tuesday night and "
                "delivered Thursday at 6am. I ran 2,800 miles that week and "
                "hit every appointment."),
        },
    },
    "Dispatcher": {
        "resume": """Dispatcher, 4 years at a 40-truck regional carrier.
Covered 60-80 loads a week across Texas and the Southeast.
Reduced empty miles by 18% by rebuilding the board around backhauls.
Managed 12 drivers day to day.
""",
        "answers": {
            "load_planning": (
                "We ran 40 trucks and the board was built by lane, not by "
                "driver. I rebuilt it around backhauls, which took empty "
                "miles from about 22% down to 18% over two quarters."),
            "exception_handling": (
                "A driver broke down outside Shreveport on a Friday with a "
                "Monday appointment. I moved the freight to a partner carrier "
                "at a loss of about $400 rather than miss the appointment, "
                "because that customer had already had one late delivery."),
            "driver_relationships": (
                "One of my drivers refused a load because he had been given "
                "the bad lane three weeks running. He was right. I had been "
                "assigning by who answered the phone fastest."),
            "problem_solving": (
                "The choice was a partner carrier at a loss or a late "
                "delivery. I took the loss because the account was already "
                "one strike down, and the load was worth less than the "
                "customer."),
            "ownership": (
                "A Laredo load tendered at 4pm on a Friday that nobody would "
                "take. I called four carriers off the board, then called a "
                "driver who was already home and offered him the Monday "
                "reset. It moved. Nobody asked me to do that."),
            "evidence_specificity": (
                "60 to 80 loads a week, 40 trucks, empty miles from 22% to "
                "18% between Q2 and Q4."),
            "communication": (
                "Telling a customer their load is going to be late is the "
                "job. I call before they call me, with a new time I can "
                "actually hit."),
        },
    },
    "Freight Broker": {
        "resume": """Freight broker, 5 years. Built a book of 22 shippers.
Grew a produce account from 4 loads a month to 30.
Held gross margin at 16% while the desk average was 11%.
""",
        "answers": {
            "carrier_sourcing": (
                "I check authority and insurance before anything else, then I "
                "call two references on the lane. I turned down a carrier "
                "last year whose authority was three weeks old and whose "
                "insurance certificate came from a broker I did not know."),
            "margin_discipline": (
                "A produce shipper wanted McAllen to Chicago at $3,900 when "
                "the lane was paying carriers $3,600. I walked. They came "
                "back in eleven days at $4,400 because nobody else covered "
                "it."),
            "shipper_relationships": (
                "The produce account went from 4 loads a month to 30. What "
                "changed is I started calling them on Thursday about the "
                "following week instead of waiting for the tender."),
            "problem_solving": (
                "Taking the load at $3,900 would have made the quarter and "
                "set the lane price for a year. The alternative was an empty "
                "week, which I could survive."),
            "ownership": (
                "The book was mine. 22 shippers, and I sourced 19 of them."),
            "evidence_specificity": (
                "16% gross margin against a desk average of 11%, on about 60 "
                "loads a month."),
            "communication": (
                "Explaining to a shipper why their rate went up is mostly "
                "about showing them what the lane actually paid last week."),
        },
    },
}

FOLLOWUP = ("To be specific about that: the numbers came off our own board, "
            "and I can walk you through the week it changed.")

SOFTWARE_WORDS = re.compile(
    r"\b(architecture|codebase|deploy|API|latency|refactor|repository|"
    r"microservice|database|schema|throughput|sprint|merge|commit)\b",
    re.IGNORECASE)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _run_role(db, org, title: str, spec: dict) -> dict:
    from sqlalchemy import select

    job = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status) VALUES (:i,:o,:t,'d','open')"""),
        {"i": job, "o": org, "t": title})
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,:n,:e,:r,'new')"""),
        {"i": cand, "o": org, "j": job, "n": f"C-{title[:12]}",
         "e": f"{cand.hex[:8]}@example.test", "r": spec["resume"]})
    await db.commit()

    consent = await R.create_consent(db, org_id=org, candidate_id=cand,
                                     disclosure_text="x" * 40,
                                     policy_version="2026.08")
    await db.commit()
    prepared = await runner.prepare(
        db, org_id=org, job_posting_id=job, candidate_id=cand,
        job_title=title, resume_text=spec["resume"], consent_id=consent.id)
    await db.commit()
    iv = prepared["interview"].id
    attempt = await runner.start(db, org_id=org, interview_id=iv)
    await db.commit()

    asked = []
    for _ in range(20):
        step = await runner.next_question(db, org_id=org, interview_id=iv,
                                          attempt_id=attempt.id)
        if step.finished or not step.has_question:
            break
        q = step.question
        key = None
        if q.competency_id:
            res = await db.execute(select(M.InterviewCompetency).where(
                M.InterviewCompetency.org_id == org,
                M.InterviewCompetency.id == q.competency_id))
            comp = res.scalar_one_or_none()
            key = comp.competency_key if comp else None
        answer = (FOLLOWUP if q.probe_depth > 0
                  else spec["answers"].get(key, spec["answers"][
                      list(spec["answers"])[0]]))
        asked.append({"text": q.question_text, "kind": q.question_kind,
                      "depth": q.probe_depth, "competency": key})
        await runner.submit_answer(db, org_id=org, interview_id=iv,
                                   question_id=q.id, answer_text=answer,
                                   attempt_id=attempt.id,
                                   recording_start_ms=len(asked) * 90_000,
                                   recording_end_ms=len(asked) * 90_000 + 70_000)
        await db.commit()

    final = await runner.finalise(db, org_id=org, interview_id=iv)
    await db.commit()
    return {"title": title, "asked": asked, "plan": prepared["plan"], **final}


@pytest_asyncio.fixture(scope="function")
async def three(db):
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"roles-{org.hex[:6]}"})
    await db.commit()
    out = {}
    for title, spec in ROLES.items():
        out[title] = await _run_role(db, org, title, spec)
    yield out
    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": org})
    await db.commit()


# ===========================================================================
# Role specificity
# ===========================================================================

def test_each_role_gets_its_own_rubric(three):
    keys = {t: r["plan"].rubric_key for t, r in three.items()}
    assert keys["CDL Driver — Regional Reefer"] == "cdl_driver"
    assert keys["Dispatcher"] == "dispatcher"
    assert keys["Freight Broker"] == "freight_broker"


def test_the_competencies_actually_differ_between_roles(three):
    sets = {t: {c.competency_key for c in r["plan"].competencies}
            for t, r in three.items()}
    driver = sets["CDL Driver — Regional Reefer"]
    broker = sets["Freight Broker"]
    assert "safety_judgement" in driver and "safety_judgement" not in broker
    assert "margin_discipline" in broker and "margin_discipline" not in driver
    assert len(driver ^ broker) >= 4, (
        "the two roles share almost every competency; they are the same "
        "interview with a different title")


def test_no_software_vocabulary_reaches_a_driver_interview(three):
    """The fairness defect that scored a CDL driver 0.79 came from software
    vocabulary in the analysis. This checks the QUESTIONS too."""
    joined = " ".join(q["text"] for q in
                      three["CDL Driver — Regional Reefer"]["asked"])
    leaked = SOFTWARE_WORDS.findall(joined)
    assert not leaked, f"a driver was asked about {sorted(set(leaked))}"


def test_the_driver_is_asked_about_equipment_they_actually_ran(three):
    joined = " ".join(q["text"] for q in
                      three["CDL Driver — Regional Reefer"]["asked"]).lower()
    assert "reefer" in joined, (
        "the resume says reefer six times and the interview never mentions it")


def test_the_broker_is_asked_about_margin_not_equipment(three):
    joined = " ".join(q["text"] for q in three["Freight Broker"]["asked"]).lower()
    assert "reefer" not in joined and "cdl" not in joined


# ===========================================================================
# Conversational quality
# ===========================================================================

def test_no_interview_asks_the_same_question_twice(three):
    for title, r in three.items():
        texts = [q["text"] for q in r["asked"]]
        dupes = {t for t in texts if texts.count(t) > 1}
        assert not dupes, (
            f"{title} asked {len(dupes)} question(s) twice. An interviewer "
            f"that repeats itself is not listening: {list(dupes)[:1]}")


def test_follow_ups_are_not_all_the_same_kind(three):
    """"Tell me more" four times is not adaptive questioning."""
    for title, r in three.items():
        kinds = [q["kind"] for q in r["asked"] if q["depth"] > 0]
        if len(kinds) < 3:
            continue
        assert len(set(kinds)) >= 2, (
            f"{title}'s follow-ups are all {kinds[0]}; the engine is not "
            f"responding to what each answer contained")


def test_two_roles_do_not_produce_an_identical_rhythm(three):
    """The sharpest test.

    A system that swaps a noun and keeps the sentence has personalised
    nothing, and comparing question TEXT would not catch it. This compares the
    SHAPE: the sequence of question kinds.
    """
    shapes = {t: tuple(q["kind"] for q in r["asked"]) for t, r in three.items()}
    driver = shapes["CDL Driver — Regional Reefer"]
    broker = shapes["Freight Broker"]
    assert driver != broker, (
        "the driver and the broker interviews have an identical sequence of "
        "question kinds; the conversation is the same shape with different "
        "nouns")


def test_a_strong_answer_is_not_probed_to_the_maximum_depth(three):
    """Every candidate here gives specific, owned, quantified answers. If the
    engine still drove every competency to max depth it would be grinding
    rather than listening."""
    for title, r in three.items():
        depths = [q["depth"] for q in r["asked"]]
        assert max(depths, default=0) <= 3
        deep = sum(1 for d in depths if d >= 2)
        assert deep <= len(depths) // 2, (
            f"{title}: {deep} of {len(depths)} questions were depth 2+ on "
            f"answers that were already specific")


def test_every_interview_covers_its_required_competencies(three):
    for title, r in three.items():
        card = r["scorecard"]
        assert card.completeness_state == "COMPLETE", (
            f"{title} left {card.uncovered_required} uncovered")


def test_every_role_produces_a_usable_scorecard(three):
    for title, r in three.items():
        card = r["scorecard"]
        assert card.overall_state == "SCORED", title
        scored = [a for a in card.assessments if a.state == "SCORED"]
        assert len(scored) >= 4, (
            f"{title} only established {len(scored)} competencies from "
            f"answers that were deliberately specific")


def test_the_interviewer_never_evaluates_out_loud(three):
    """Mid-interview praise tells a candidate how they are scoring."""
    banned = ("great answer", "excellent", "well done", "perfect",
              "impressive", "good job", "that's exactly right")
    for title, r in three.items():
        joined = " ".join(q["text"] for q in r["asked"]).lower()
        for phrase in banned:
            assert phrase not in joined, f"{title} said {phrase!r}"
