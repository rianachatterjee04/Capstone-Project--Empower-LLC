"""The rate-confirmation endpoints, over HTTP, against a real database.

The module and the schema are tested elsewhere. What is left is the seam: that
the endpoint refuses the same things the module does, that it does not let one
tenant reach another's documents, and that issuing twice is a conflict rather
than a second live rate.
"""
from __future__ import annotations

import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# IMPORTED AT MODULE SCOPE ON PURPOSE.
# `app.dependency_overrides` is keyed by function IDENTITY, and the routes
# captured these objects when the app was built. Importing them inside the
# fixture instead would pick up whatever `sys.modules` holds at call time,
# which another test's `importlib.reload` can have replaced.
from app.api.deps import Actor, db_session, require_org
from app.main import app as fastapi_app
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

TERMS = [{"kind": "DETENTION", "rate_cents": 5_000, "unit": "HOUR",
          "free_time_minutes": 120, "cap_cents": 30_000}]


@pytest_asyncio.fixture
async def env():
    """An app wired to the test database, with two orgs and a brokered load."""
    import os
    os.environ["DATABASE_URL"] = DSN
    os.environ.setdefault("ENV", "development")
    app = fastapi_app

    # ONE ENGINE PER TEST, AND THE APP USES IT.
    # `app.db.session` builds its engine at import time, so its connection
    # pool binds to whichever event loop touches it first. pytest-asyncio gives
    # each test a fresh loop, so from the second test onward the app was
    # handing out connections that belonged to a loop that had closed --
    # "coroutine 'Connection._cancel' was never awaited", and six failures
    # that all passed when run alone.
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _session():
        async with maker() as s:
            yield s

    app.dependency_overrides[db_session] = _session

    org, other = uuid.uuid4(), uuid.uuid4()
    async with maker() as db:
        for o, n in ((org, "rc-api"), (other, "rc-api-other")):
            await db.execute(
                text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                {"i": o, "n": f"{n}-{o.hex[:6]}"})
        cust = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_customers
            (id,org_id,name,payment_terms_days) VALUES (:i,:o,'Shipper',30)"""),
            {"i": cust, "o": org})
        carrier = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_carriers
            (id,org_id,name,dot_number,authority_status,authority_source,
             authority_checked_at,is_approved)
            VALUES (:i,:o,'Delta Line','2194844','ACTIVE','FMCSA_LIVE',
                    now(),true)"""), {"i": carrier, "o": org})

        async def load(num, mode):
            lid = uuid.uuid4()
            await db.execute(text("""INSERT INTO public.trucking_loads
                (id,org_id,load_number,customer_id,status,fulfilment_mode,
                 carrier_id,origin_city,origin_state,destination_city,
                 destination_state,equipment_required,commodity,
                 customer_rate_cents)
                VALUES (:i,:o,:n,:c,'BOOKED',:m,:car,'Pharr','TX',
                        'Detroit','MI','REEFER','Romaine',500000)"""),
                {"i": lid, "o": org, "n": num, "c": cust, "m": mode,
                 "car": carrier if mode == "BROKERED" else None})
            return lid

        brokered = await load("L-API-1", "BROKERED")
        own = await load("L-API-2", "OWN_FLEET")
        await db.commit()

    app.dependency_overrides[require_org] = lambda: Actor(
        org_id=str(org), user_id="t", role="admin", claims={})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://t") as client:
        yield {"c": client, "org": org, "other": other, "app": app,
               "require_org": require_org, "Actor": Actor,
               "brokered": brokered, "own": own, "carrier": carrier,
               "maker": maker}

    app.dependency_overrides.pop(require_org, None)
    app.dependency_overrides.pop(db_session, None)
    async with maker() as db:
        for o in (org, other):
            await db.execute(text("DELETE FROM public.orgs WHERE id = :i"),
                             {"i": o})
        await db.commit()
    await engine.dispose()


def _issue_body(**kw):
    body = {"linehaul_cents": 385_000, "fuel_surcharge_cents": 44_000,
            "approved_accessorials": TERMS}
    body.update(kw)
    return body


# ===========================================================================
# Issue
# ===========================================================================

@pytest.mark.asyncio
async def test_issuing_returns_the_document_and_its_hash(env):
    r = await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "ISSUED"
    assert "3,850.00" in body["document"]
    assert "after 120 minutes free" in body["document"]
    assert len(body["document_sha256"]) == 64
    assert "will not dispatch" in body["note"]


@pytest.mark.asyncio
async def test_an_own_fleet_load_has_no_rate_to_agree(env):
    r = await env["c"].post(
        f"/api/trucking/loads/{env['own']}/rate-confirmation",
        json=_issue_body())
    assert r.status_code == 409
    assert "own-fleet" in r.json()["detail"]


@pytest.mark.asyncio
async def test_issuing_twice_is_a_conflict(env):
    await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())
    r = await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())
    assert r.status_code == 409
    assert "not a decision anybody made" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_malformed_accessorial_term_is_refused(env):
    r = await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body(approved_accessorials=[{"rate_cents": 100}]))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "TERM_WITHOUT_KIND"


@pytest.mark.asyncio
async def test_a_negative_rate_is_refused(env):
    r = await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body(linehaul_cents=-1))
    assert r.status_code == 422


# ===========================================================================
# Accept
# ===========================================================================

@pytest.mark.asyncio
async def test_accepting_authorises_dispatch(env):
    issued = (await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())).json()

    before = (await env["c"].get(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation")).json()
    assert before["dispatch"]["allowed"] is False
    assert "RATE_CONFIRMATION_NOT_ACCEPTED" in before["dispatch"]["refusal_codes"]

    r = await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/accept",
        json={"accepted_by": "Marisol Vega, Delta Line", "channel": "EMAIL"})
    assert r.status_code == 200, r.text

    after = (await env["c"].get(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation")).json()
    assert after["dispatch"]["allowed"] is True
    assert after["current"]["accepted_by"] == "Marisol Vega, Delta Line"


@pytest.mark.asyncio
async def test_accepting_without_naming_the_counterparty_is_refused(env):
    issued = (await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())).json()
    r = await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/accept",
        json={"accepted_by": "   "})
    assert r.status_code == 422
    assert "no counterparty named" in r.json()["detail"]


@pytest.mark.asyncio
async def test_accepting_twice_is_refused(env):
    issued = (await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())).json()
    await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/accept",
        json={"accepted_by": "Delta Line"})
    r = await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/accept",
        json={"accepted_by": "Delta Line again"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ILLEGAL_TRANSITION"


# ===========================================================================
# Amend
# ===========================================================================

@pytest.mark.asyncio
async def test_an_amendment_keeps_the_original(env):
    """A settlement already citing the original still has to be defensible."""
    issued = (await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())).json()
    await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/accept",
        json={"accepted_by": "Delta Line"})

    r = await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/amend",
        json={"reason": "re-power after a breakdown",
              "linehaul_cents": 410_000})
    assert r.status_code == 200, r.text
    amended = r.json()
    assert amended["supersedes"] == issued["id"]

    chain = (await env["c"].get(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation")).json()
    states = [h["state"] for h in chain["history"]]
    assert states == ["SUPERSEDED", "ISSUED"]
    assert chain["dispatch"]["allowed"] is False, (
        "an amendment has to be accepted before the load moves again")


@pytest.mark.asyncio
async def test_an_amendment_without_a_reason_is_refused(env):
    issued = (await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())).json()
    await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/accept",
        json={"accepted_by": "Delta Line"})
    r = await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/amend", json={})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "AMENDMENT_WITHOUT_REASON"


@pytest.mark.asyncio
async def test_an_unaccepted_confirmation_is_not_amended(env):
    issued = (await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())).json()
    r = await env["c"].post(
        f"/api/trucking/rate-confirmations/{issued['id']}/amend",
        json={"reason": "typo"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NOTHING_TO_AMEND"


# ===========================================================================
# Tenancy
# ===========================================================================

@pytest.mark.asyncio
async def test_another_tenant_cannot_read_the_confirmation(env):
    """A rate confirmation names a carrier, a lane and a price. It is one of
    the more commercially sensitive rows in the system."""
    issued = (await env["c"].post(
        f"/api/trucking/loads/{env['brokered']}/rate-confirmation",
        json=_issue_body())).json()

    env["app"].dependency_overrides[env["require_org"]] = lambda: env["Actor"](
        org_id=str(env["other"]), user_id="t", role="admin", claims={})
    try:
        r = await env["c"].get(
            f"/api/trucking/loads/{env['brokered']}/rate-confirmation")
        assert r.status_code == 404
        r = await env["c"].post(
            f"/api/trucking/rate-confirmations/{issued['id']}/accept",
            json={"accepted_by": "someone else"})
        assert r.status_code == 404
    finally:
        env["app"].dependency_overrides[env["require_org"]] = \
            lambda: env["Actor"](org_id=str(env["org"]), user_id="t",
                                 role="admin", claims={})


@pytest.mark.asyncio
async def test_a_non_ops_role_is_refused(env):
    env["app"].dependency_overrides[env["require_org"]] = lambda: env["Actor"](
        org_id=str(env["org"]), user_id="t", role="employee", claims={})
    try:
        r = await env["c"].get(
            f"/api/trucking/loads/{env['brokered']}/rate-confirmation")
        assert r.status_code == 403
    finally:
        env["app"].dependency_overrides[env["require_org"]] = \
            lambda: env["Actor"](org_id=str(env["org"]), user_id="t",
                                 role="admin", claims={})
