#!/usr/bin/env python3
"""Seed a complete, deterministic interview demo.

One command produces an organisation, a role, three candidates with genuinely
different resumes, and three FULLY RUN interviews -- plan, adaptive follow-ups,
evidence, claim verification, scorecard and debrief -- so the recruiter
playback page has real data the moment it loads.

DETERMINISTIC AND LABELLED
Every organisation this creates is named with the DEMO prefix, and the seeder
refuses to touch anything else. The interviews are real runs through
`app/interview/runner.py`, not fixtures: the questions are generated from the
resumes, the follow-ups are generated from the answers, and the scores come
from the evidence. Nothing here is a canned JSON blob dressed as a result --
which matters, because the demo's entire claim is that the assessment came
from what the candidate said.

WHAT IS SYNTHETIC
The candidates, their resumes and their answers. They are written to be
realistic and they are invented. No recording media is attached: the recording
rows would be DEMO_FIXTURE or NOT_CONNECTED, and the page says so rather than
implying a video exists.

    FINTRA_INTERVIEW_PG_DSN=postgresql+asyncpg:///fintra_iv_demo \
      python scripts/seed_interview_demo.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from sqlalchemy import text                                    # noqa: E402
from sqlalchemy.ext.asyncio import (async_sessionmaker,        # noqa: E402
                                    create_async_engine)

from app.interview import repository as R                      # noqa: E402
from app.interview import runner

#: How far apart the seeded answers sit on the recording timeline. Overridden
#: by FINTRA_DEMO_ANSWER_SECONDS so the seed can be matched to whatever media
#: is attached.
ANSWER_SPACING_MS = int(
    float(os.environ.get("FINTRA_DEMO_ANSWER_SECONDS", "8")) * 1000)                               # noqa: E402

DEMO_PREFIX = "DEMO —"
DEFAULT_ORG = f"{DEMO_PREFIX} Northwind Robotics"
JOB_TITLE = "Senior Platform Engineer"

DISCLOSURE = (
    "This interview is conducted by an AI interviewer and is recorded. Your "
    "answers are assessed against the competencies for this role, and a human "
    "recruiter makes the hiring decision. You can decline recording or stop at "
    "any time.")

# --- the three candidates --------------------------------------------------
# A: dense, quantified.  B: adjacent experience, honest about it.
# C: reads impressively, establishes nothing.

CANDIDATES = [
    {
        "name": "Ada Iwuchukwu",
        "email": "ada@example.test",
        "resume": """Senior Platform Engineer, Acme Payments (2021-2025)
Reduced settlement failures by 40% during the Ledger migration.
Managed a team of 12 engineers across two time zones.
8 years of distributed systems experience.
Built services in Python and Go on AWS, backed by Postgres and Kafka.
Saved $1.2M in annual infrastructure spend by consolidating Kafka clusters.
""",
        "by_competency": {
            "technical_depth": (
                "I rewrote the settlement reconciler. Before that we were "
                "failing about 4% of settlements a day, almost all of them "
                "duplicate submissions after a gateway timeout. I added an "
                "idempotency key on the ledger write and changed the retry "
                "path to check state before resubmitting. Over the following "
                "quarter that dropped to 0.2%. We knew it was the change "
                "because we held the volume constant and it was the only "
                "thing we shipped that sprint."),
            "system_design": (
                "The choice was between an idempotency key on the write and a "
                "dedupe cache in front of the gateway. I went with the key "
                "because the cache only helps if the duplicate arrives inside "
                "the TTL, and our duplicates were arriving minutes apart after "
                "a client retry. The cost is that the ledger write got slower, "
                "which we accepted because a stale read would have been worse."),
            "problem_solving": (
                "The Kafka consolidation. We were running nine clusters "
                "because every team had spun up their own. I measured actual "
                "throughput and found seven were under 5% utilised, so we "
                "moved them onto two. That was the $1.2M. What did not go well "
                "is that I migrated cluster by cluster without a rollback plan "
                "for the third one, and we had a four hour outage on a "
                "Saturday because of it."),
            "ownership": (
                "I had 3 engineers reporting to me directly. The "
                "cross-functional group for the migration was 12 people across "
                "two teams. I owned hiring and performance for my 3, and I "
                "drove the technical direction for the wider group without "
                "managing them."),
            "evidence_specificity": (
                "The clearest one is the reconciler rewrite. Settlement "
                "failures went from 4% a day to 0.2% over the quarter after I "
                "shipped the idempotency key. I can show you the dashboard; we "
                "tracked it as duplicate_submission_rate."),
            "communication": (
                "I had to explain to the finance team why settlements were "
                "going to look wrong for two days during the cutover. I "
                "stopped talking about idempotency and framed it as: the same "
                "payment may appear twice in your export, here is the query "
                "that collapses them, and it stops on Thursday. They needed to "
                "act on it, not understand it."),
            "collaboration": (
                "Our staff engineer wanted to do the migration in one cutover "
                "and I wanted it incremental. We disagreed for about a week. I "
                "eventually agreed to his approach for the read path because "
                "he was right that the dual-read window would be worse, and "
                "kept mine for the writes. Splitting it was not a compromise "
                "for its own sake -- the two halves had different risks."),
        },
        "followup": (
            "To be specific about that: the baseline was 4.1% measured over "
            "the preceding 30 days, the after number was 0.2% over the "
            "following quarter, and I personally wrote the idempotency key "
            "and the retry state check. The rest of the team did the client "
            "migration."),
        "answers": [
            ("I rewrote the settlement reconciler. Before that we were failing "
             "about 4% of settlements a day, almost all of them duplicate "
             "submissions after a gateway timeout. I added an idempotency key "
             "on the ledger write and changed the retry path to check state "
             "before resubmitting. Over the following quarter that dropped to "
             "0.2%. We knew it was the change because we held the volume "
             "constant and it was the only thing we shipped that sprint. The "
             "downside is the ledger write got slower, which we accepted "
             "instead of caching because a stale read would have been worse. "
             "In hindsight I underestimated how long the migration would take."),
            ("I had 3 engineers reporting to me directly. The cross-functional "
             "group for the migration was 12 people across two teams. I owned "
             "hiring and performance for my 3, and I drove the technical "
             "direction for the wider group without managing them."),
            ("The Kafka consolidation is the one I'd point to. We were running "
             "nine clusters because every team had spun up their own. I "
             "measured the actual throughput, found seven were under 5% "
             "utilised, and moved them onto two. That was the $1.2M. What "
             "didn't go well is that I did the migration cluster by cluster "
             "without a rollback plan for the third one, and we had a four "
             "hour outage on a Saturday because of it."),
        ],
    },
    {
        "name": "Ben Castellanos",
        "email": "ben@example.test",
        "resume": """High school physics teacher, Lincoln High (2018-2024).
Completed a part-time software engineering bootcamp in 2024.
Built an inventory tracker in Python for the school science laboratory.
Led a department of 4 teachers through a state curriculum change.
2 years of volunteer experience maintaining the district website.
""",
        "by_competency": {
            "technical_depth": (
                "The inventory tracker is the main thing I have built. The lab "
                "had about 400 items on a paper sheet and things went missing "
                "every term. I wrote it in Python with SQLite and a small "
                "Flask front end. I know SQLite would not survive concurrent "
                "writes from more than a handful of people; there were twelve "
                "teachers using it, so it did not need to."),
            "system_design": (
                "I did consider a shared Google Sheet, which is what the "
                "school actually wanted. I went with the app because the sheet "
                "had no way to stop two people editing the same row and that "
                "was the exact failure we were trying to fix. The cost is that "
                "I am now the only person who can maintain it, which is a real "
                "problem I did not think about at the time."),
            "problem_solving": (
                "The hard part was not the code. It was that people would not "
                "use it if it took longer than the paper sheet. So I timed "
                "myself doing a checkout on paper -- about eleven seconds -- "
                "and made that the budget. That is why it is one screen with "
                "no login."),
            "ownership": (
                "I led the department through the curriculum change. There "
                "were 4 of us and I was the department head. Two of them had "
                "taught the old syllabus for fifteen years and did not want to "
                "change. I sat with each of them and worked out which parts of "
                "their existing material still mapped, because starting from "
                "nothing was the thing they were actually afraid of."),
            "evidence_specificity": (
                "Honestly the limit is that I have not worked on anything with "
                "real traffic. I understand the concepts from the bootcamp but "
                "I would not claim to have operated a distributed system. What "
                "I do have is six years of explaining hard things to people "
                "who do not want to hear them."),
            "communication": (
                "Every day, for six years, to sixteen-year-olds who did not "
                "choose to be there. The specific one I would give you is "
                "explaining to a parent why their child's grade was going to "
                "drop under the new syllabus -- that is a technical "
                "explanation with someone who is upset, and you do not get to "
                "retry it."),
            "collaboration": (
                "The two teachers who resisted the curriculum change. One of "
                "them filed a complaint about me. We ended up co-teaching a "
                "unit so I could see what she was actually worried about, "
                "which turned out to be the assessment format rather than the "
                "content."),
        },
        "followup": (
            "I want to be careful not to overstate that. The tracker had "
            "twelve users and no uptime requirement. I have not been on call "
            "and I have not debugged a production incident."),
        "answers": [
            ("The inventory tracker is the main thing I've built. The lab had "
             "about 400 items on a paper sheet and things went missing every "
             "term. I wrote it in Python with a SQLite database and a small "
             "Flask front end. I'm aware that doesn't scale, but there were "
             "twelve teachers using it, so it didn't need to."),
            ("I led the department through the curriculum change. There were 4 "
             "of us and I was the department head. Two of them had taught the "
             "old syllabus for fifteen years and did not want to change. I sat "
             "with each of them and worked out which parts of their existing "
             "material still mapped, because starting from nothing was the "
             "thing they were actually afraid of."),
            ("Honestly the limit is that I have not worked on anything with "
             "real traffic. I understand the concepts from the bootcamp but I "
             "would not claim to have operated a distributed system. What I do "
             "have is six years of explaining hard things to people who don't "
             "want to hear them."),
        ],
    },
    {
        "name": "Cara Lindqvist",
        "email": "cara@example.test",
        "resume": """Results-driven senior technology leader with a proven track record of
delivering transformational outcomes at scale. Passionate about excellence,
innovation and building world-class high-performing teams. Recognised for
strategic vision and thought leadership across the enterprise.
Extensive experience across the full technology stack.
""",
        "by_competency": {},
        "followup": (
            "I would say it comes back to leadership and vision. When you set "
            "the right direction and empower people, the outcomes follow."),
        "answers": [
            ("I always focus on delivering value and making sure the team is "
             "aligned around the outcome. My approach is to drive excellence "
             "through clear communication and setting a high bar."),
            ("I've led many high-performing teams throughout my career. I'm "
             "passionate about developing talent and driving transformational "
             "outcomes for the business."),
            ("I would say my greatest strength is strategic vision. I'm able to "
             "see the big picture and bring people along with me on the "
             "journey."),
        ],
    },
]


async def _answer_for(db, org_id, question, spec) -> str:
    """The answer this candidate gives to THIS competency.

    Falls back to a generic follow-up reply, because a follow-up probes deeper
    into the same competency and a candidate does not restart their story.
    """
    from sqlalchemy import select
    from app.interview import models as IM

    key = None
    if question.competency_id:
        res = await db.execute(select(IM.InterviewCompetency).where(
            IM.InterviewCompetency.org_id == org_id,
            IM.InterviewCompetency.id == question.competency_id))
        comp = res.scalar_one_or_none()
        key = comp.competency_key if comp else None

    # Probe depth is checked FIRST. A candidate answering a follow-up adds
    # detail; they do not repeat the answer they just gave. Checking the
    # competency map first made the demo replay identical text at depth 1 and
    # depth 2, which reads as a broken interviewer.
    if question.probe_depth > 0 and spec.get("followup"):
        return spec["followup"]

    by_key = spec.get("by_competency", {})
    if key and key in by_key:
        return by_key[key]
    return spec["answers"][0]


async def _wipe(db, org_id) -> None:
    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": org_id})
    await db.commit()


async def seed(dsn: str, org_name: str) -> dict:
    engine = create_async_engine(dsn, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    if not org_name.startswith(DEMO_PREFIX):
        raise SystemExit(
            f"refusing to seed {org_name!r}: this seeder only manages "
            f"organisations named {DEMO_PREFIX!r}... so it cannot be pointed "
            f"at real data by accident")

    async with maker() as db:
        existing = (await db.execute(
            text("SELECT id FROM public.orgs WHERE name = :n"),
            {"n": org_name})).first()
        if existing:
            await _wipe(db, existing[0])

        # Fixed id so the employer web app -- which sends a hard-coded demo
        # org -- lands on this data without configuration.
        org_id = uuid.UUID(os.environ.get(
            'FINTRA_DEMO_ORG_ID', '11111111-1111-1111-1111-111111111111'))
        await db.execute(
            text("INSERT INTO public.orgs (id, name) VALUES (:i, :n)"),
            {"i": org_id, "n": org_name})

        job_id = uuid.uuid4()
        await db.execute(text("""
            INSERT INTO public.job_postings
                (id, org_id, title, description, status)
            VALUES (:i, :o, :t, :d, 'open')"""),
            {"i": job_id, "o": org_id, "t": JOB_TITLE,
             "d": ("Own the payment platform's settlement and ledger services. "
                   "You will be responsible for correctness under concurrency, "
                   "the on-call rotation for the settlement path, and "
                   "mentoring two mid-level engineers.")})
        await db.commit()

        results = []
        for spec in CANDIDATES:
            cand_id = uuid.uuid4()
            await db.execute(text("""
                INSERT INTO public.candidates
                    (id, org_id, job_posting_id, full_name, email,
                     resume_text, status)
                VALUES (:i, :o, :j, :n, :e, :r, 'interviewing')"""),
                {"i": cand_id, "o": org_id, "j": job_id, "n": spec["name"],
                 "e": spec["email"], "r": spec["resume"]})
            await db.commit()

            consent = await R.create_consent(
                db, org_id=org_id, candidate_id=cand_id,
                disclosure_text=DISCLOSURE, policy_version="2026.08")
            await db.commit()

            prepared = await runner.prepare(
                db, org_id=org_id, job_posting_id=job_id, candidate_id=cand_id,
                job_title=JOB_TITLE, resume_text=spec["resume"],
                consent_id=consent.id)
            await db.commit()

            iv_id = prepared["interview"].id
            attempt = await runner.start(db, org_id=org_id, interview_id=iv_id)
            await db.commit()

            asked = 0
            answers = spec["answers"]
            while asked < 16:
                step = await runner.next_question(
                    db, org_id=org_id, interview_id=iv_id,
                    attempt_id=attempt.id)
                if step.finished:
                    break
                if not step.has_question:
                    break
                # Pick the answer that belongs to the competency being asked
                # about. Cycling a short list instead produced a demo where
                # five competencies quoted the same sentence and scored
                # identically -- which reads as a broken product, and hides
                # the thing the demo exists to show.
                answer_text = await _answer_for(
                    db, org_id, step.question, spec)
                await runner.submit_answer(
                    db, org_id=org_id, interview_id=iv_id,
                    question_id=step.question.id,
                    answer_text=answer_text,
                    attempt_id=attempt.id,
                    # ANSWER BOUNDARIES ON THE SAME SCALE AS THE DEMO MEDIA.
                    # These were 95 seconds apart, so an eleven-question
                    # interview spanned seventeen minutes -- against a demo
                    # recording that is ninety seconds long. Every click in
                    # the debrief then landed past the end of the media and
                    # the player correctly refused to move, which is the right
                    # behaviour and a terrible demonstration of it.
                    #
                    # A real interview's boundaries come from the recorder's
                    # own clock and need no adjustment; this is a property of
                    # the SEED, and `--answer-seconds` keeps it explicit.
                    recording_start_ms=asked * ANSWER_SPACING_MS,
                    recording_end_ms=(asked * ANSWER_SPACING_MS
                                      + ANSWER_SPACING_MS - 1_000))
                await db.commit()
                asked += 1

            final = await runner.finalise(db, org_id=org_id, interview_id=iv_id)
            await db.commit()

            card = final["scorecard"]
            results.append({
                "name": spec["name"], "interview_id": str(iv_id),
                "questions": asked,
                "overall": card.overall_score,
                "confidence": card.overall_confidence,
                "completeness": card.completeness_state,
                "scored": sum(1 for a in card.assessments if a.state == "SCORED"),
                "total": len(card.assessments),
            })

    await engine.dispose()
    return {"org_id": str(org_id), "job_id": str(job_id),
            "org_name": org_name, "candidates": results}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--org-name", default=DEFAULT_ORG)
    ap.add_argument("--dsn", default=(os.environ.get("FINTRA_INTERVIEW_PG_DSN")
                                      or os.environ.get("FINTRA_HR_PG_DSN", "")))
    args = ap.parse_args()
    if not args.dsn:
        raise SystemExit("set FINTRA_INTERVIEW_PG_DSN")

    out = asyncio.run(seed(args.dsn, args.org_name))

    print(f"\nseeded {out['org_name']}   (DEMO / SYNTHETIC data)")
    print(f"org  {out['org_id']}")
    print(f"job  {out['job_id']}  {JOB_TITLE}\n")
    print(f"{'CANDIDATE':<22}{'Qs':>4}{'OVERALL':>10}{'CONF':>7}"
          f"{'SCORED':>9}  COMPLETENESS")
    print("-" * 74)
    for c in out["candidates"]:
        scored_of_total = f"{c['scored']}/{c['total']}"
        print(f"{c['name']:<22}{c['questions']:>4}"
              f"{str(c['overall']):>10}{str(c['confidence']):>7}"
              f"{scored_of_total:>9}  {c['completeness']}")
    print("-" * 74)
    print("\nrecruiter playback:")
    for c in out["candidates"]:
        print(f"  /app/interview-review/{c['interview_id']}   {c['name']}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
