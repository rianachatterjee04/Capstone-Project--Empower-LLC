"""Cross-tenant refusal at the ENDPOINT, for every interview-scoped route.

test_interview_tenancy_pg.py proves the REPOSITORY scopes by org. That is a
different claim from "the endpoints do", and evidence at one layer does not
inherit to the next: a handler that forgets to pass actor.org_id, or passes the
row's org instead of the caller's, sits above a perfectly correct repository.
The endpoint is the only thing an attacker can send a request to.

So org B calls every interview-scoped route with org A's interview id and must
be refused. The expected answer is 404, not 403: telling an outsider "that
exists but you may not have it" is itself a disclosure -- it confirms a
candidate is being interviewed by a competitor.

A COVERAGE GUARD RUNS WITH THEM. It reads the router's own route table and
fails if an interview-scoped route exists that this file does not exercise, so
a new endpoint cannot be added without either coverage or a deliberate,
visible exemption.
"""
from __future__ import annotations

import io
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import repository as R
from app.interview import runner
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

RESUME = ("Senior Platform Engineer. Reduced settlement failures by 40%. "
          "Managed a team of 12 engineers. 8 years distributed systems.")


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTRA_MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.delenv("FINTRA_MEDIA_OBJECT_STORE_URL", raising=False)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


class _Actor:
    def __init__(self, org_id, role="owner"):
        self.org_id = org_id
        self.role = role
        self.user_id = None
        self.email = "r@example.test"
        self.claims = {"email": "r@example.test"}


async def _tenant(db):
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"ten-{org.hex[:6]}"})
    job = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status)
        VALUES (:i,:o,'Senior Software Engineer','d','open')"""),
        {"i": job, "o": org})
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,'M','m@example.test',:r,'new')"""),
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
    return {"org": org, "interview_id": prepared["interview"].id}


def _upload():
    return UploadFile(filename="p.webm", file=io.BytesIO(b"\x1a\x45\xdf\xa3xx"),
                      headers={"content-type": "video/webm"})


#: Every interview-scoped route, and how to call it. The names are matched
#: against the router's own table by the coverage guard below.
def _calls(R2, iid, actor, db):
    from app.api.routers.interview_v2 import AnswerIn, TranscriptIn
    return {
        "start": lambda: R2.start(iid, actor=actor, db=db),
        "next_question": lambda: R2.next_question(iid, actor=actor, db=db),
        "answer": lambda: R2.answer(
            iid, AnswerIn(question_id=uuid.uuid4(), answer_text="hello there"),
            actor=actor, db=db),
        "finalise": lambda: R2.finalise(iid, actor=actor, db=db),
        "playback": lambda: R2.playback(iid, actor=actor, db=db),
        "upload_media": lambda: R2.upload_media(
            iid, file=_upload(), media_kind="VIDEO", part_number=1,
            actor=actor, db=db),
        "submit_transcript": lambda: R2.submit_transcript(
            iid, TranscriptIn(results=[{"text": "hi", "start_ms": 0,
                                        "end_ms": 10}]),
            actor=actor, db=db),
        "seal_recording": lambda: R2.seal_recording(
            iid, {"parts_expected": 1}, actor=actor, db=db),
        "recording_state": lambda: R2.recording_state(iid, actor=actor, db=db),
        "alignment": lambda: R2.alignment(iid, actor=actor, db=db),
        "stream_media": lambda: R2.stream_media(iid, 1, request=None,
                                                actor=actor, db=db),
    }


#: Routes that are deliberately NOT interview-scoped, with the reason. The
#: coverage guard requires an entry here for anything it cannot find a call for,
#: so an uncovered route is a visible decision rather than an omission.
_NOT_INTERVIEW_SCOPED = {
    "record_consent": "creates a consent row in the caller's own org",
    "prepare": "creates an interview in the caller's own org",
    "list_interviews": "lists the caller's own org; covered by the list tests",
    "compare": "job-scoped, not interview-scoped",
    "media_capability": "reports what this deployment can do; carries no data",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("route", sorted(_calls(
    __import__("app.api.routers.interview_v2", fromlist=["x"]),
    uuid.uuid4(), None, None).keys()))
async def test_another_tenant_is_refused_at_every_interview_route(db, route):
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    b = await _tenant(db)

    # A's interview is real and A can use it -- otherwise "refused" would be
    # indistinguishable from "this id does not exist".
    await R2.start(a["interview_id"], actor=_Actor(a["org"]), db=db)
    await db.commit()

    call = _calls(R2, a["interview_id"], _Actor(b["org"]), db)[route]
    with pytest.raises(HTTPException) as exc:
        await call()
    assert exc.value.status_code == 404, (
        f"{route} answered {exc.value.status_code} to another tenant. 404 is "
        f"the required answer: 403 confirms the interview exists, which tells "
        f"a competitor that this candidate is being interviewed.")


@pytest.mark.asyncio
async def test_positive_control_the_owning_org_is_not_refused(db):
    """Without this, a router that raised 404 for everyone would pass every
    test above and look like flawless tenancy."""
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    await R2.start(a["interview_id"], actor=_Actor(a["org"]), db=db)
    await db.commit()

    assert await R2.next_question(a["interview_id"],
                                  actor=_Actor(a["org"]), db=db)
    assert await R2.recording_state(a["interview_id"],
                                    actor=_Actor(a["org"]), db=db)


def test_coverage_guard_every_interview_scoped_route_is_exercised():
    """Reads the router's route table. A new /{interview_id}/... endpoint fails
    this until it is either covered above or listed as deliberately exempt."""
    from app.api.routers import interview_v2 as R2

    covered = set(_calls(R2, uuid.uuid4(), None, None).keys())
    scoped = set()
    for route in R2.router.routes:
        path = getattr(route, "path", "")
        name = getattr(route, "name", "")
        if "{interview_id}" in path:
            scoped.add(name)

    missing = scoped - covered - set(_NOT_INTERVIEW_SCOPED)
    assert not missing, (
        f"interview-scoped routes with no cross-tenant test: {sorted(missing)}. "
        f"Add them to _calls, or to _NOT_INTERVIEW_SCOPED with a reason.")
