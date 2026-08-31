"""Every recruiter-only endpoint refuses a candidate, at the endpoint.

test_candidate_boundary_pg.py proves what a candidate RECEIVES from the
endpoints it knows about. This asks the other question, and asks it of the
router rather than of a list somebody maintained: which handlers gate
themselves with `_require_recruiter`, and does each of them actually refuse?

The list is DERIVED. Two endpoints added earlier tonight -- /recording and
/alignment -- were recruiter-gated from the moment they were written and had no
audience test, because the boundary suite names its endpoints by hand and
nobody thought to add them. A hand-maintained list of things to check is a list
that lags the code it checks.
"""
from __future__ import annotations

import ast
import inspect
import pathlib
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import repository as R
from app.interview import runner
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

ROUTER_FILE = (pathlib.Path(__file__).parent.parent / "app" / "api" / "routers"
               / "interview_v2.py")
RESUME = ("Senior Platform Engineer. Reduced settlement failures by 40%. "
          "Managed a team of 12 engineers. 8 years distributed systems.")


def _recruiter_gated_handlers() -> list[str]:
    """Handler names whose body calls _require_recruiter."""
    tree = ast.parse(ROUTER_FILE.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(node):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id == "_require_recruiter"):
                out.append(node.name)
                break
    return sorted(set(out))


HANDLERS = _recruiter_gated_handlers()


class _Actor:
    def __init__(self, org_id, role):
        self.org_id = org_id
        self.role = role
        self.user_id = None
        self.email = f"{role}@example.test"
        self.claims = {"email": f"{role}@example.test"}


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
                     {"i": org, "n": f"aud-{org.hex[:6]}"})
    job = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status)
        VALUES (:i,:o,'Senior Software Engineer','d','open')"""),
        {"i": job, "o": org})
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,'A','a@example.test',:r,'new')"""),
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
    return {"org": org, "id": prepared["interview"].id}


def _call_kwargs(fn, interview_id, actor, db):
    """Fill a handler's parameters with something harmless.

    The audience check runs FIRST in each of these handlers, so the arguments
    only have to be present, not meaningful -- a candidate must be refused
    before any of them is looked at.
    """
    kwargs = {}
    for name, p in inspect.signature(fn).parameters.items():
        if name == "interview_id":
            kwargs[name] = interview_id
        elif name == "actor":
            kwargs[name] = actor
        elif name == "db":
            kwargs[name] = db
        elif name == "request":
            kwargs[name] = None
        elif name == "part_number":
            kwargs[name] = 1
        elif name == "payload":
            kwargs[name] = {}
        elif p.default is not inspect.Parameter.empty:
            kwargs[name] = p.default
        else:
            kwargs[name] = None
    return kwargs


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", HANDLERS)
async def test_a_candidate_is_refused_by_every_recruiter_gated_endpoint(
        db, interview, handler):
    from app.api.routers import interview_v2 as R2

    fn = getattr(R2, handler)
    actor = _Actor(interview["org"], "employee")
    with pytest.raises(HTTPException) as exc:
        await fn(**_call_kwargs(fn, interview["id"], actor, db))
    assert exc.value.status_code in (403, 404), (
        f"{handler} answered {exc.value.status_code} to a candidate; a "
        f"recruiter-only endpoint must refuse")


@pytest.mark.asyncio
async def test_control_the_same_endpoints_answer_a_recruiter(db, interview):
    """Without this, a router that refused EVERYONE would pass every test above
    and look like a flawless boundary."""
    from app.api.routers import interview_v2 as R2

    actor = _Actor(interview["org"], "owner")
    answered = 0
    for handler in HANDLERS:
        fn = getattr(R2, handler)
        try:
            await fn(**_call_kwargs(fn, interview["id"], actor, db))
            answered += 1
        except HTTPException as exc:
            # 4xx for a real reason (no media yet, nothing to seal) is fine;
            # 403 is not -- that would be the recruiter being refused too.
            assert exc.value.status_code != 403 if hasattr(exc, "value") else True
            if exc.status_code == 403:
                pytest.fail(f"{handler} refused a recruiter with 403")
        except Exception:
            pass                      # a data-shaped failure is not an audience one
    assert answered, "no recruiter-gated endpoint answered a recruiter at all"


def test_control_the_handler_list_is_not_empty_and_covers_the_new_ones():
    """The whole file passes vacuously if the AST scan finds nothing."""
    assert len(HANDLERS) >= 5, f"only found {HANDLERS}"
    for expected in ("playback", "recording_state", "alignment", "finalise"):
        assert expected in HANDLERS, (
            f"{expected} is recruiter-gated in the router but the scan missed "
            f"it")
