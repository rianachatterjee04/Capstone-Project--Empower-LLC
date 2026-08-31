"""The commercial constraints, and the endpoints, against PostgreSQL.

`loop.py` refuses these in Python. The database refuses them too, because the
Python path is not the only way a row gets written -- a backfill, an import, a
psql session. A constraint that lives only in the application is a convention.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import Actor, db_session, require_org
from app.main import app as fastapi_app
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

TODAY = date.today()


@pytest_asyncio.fixture
async def env():
    import os
    os.environ["DATABASE_URL"] = DSN
    os.environ.setdefault("ENV", "development")

    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _session():
        async with maker() as s:
            yield s

    org, other = uuid.uuid4(), uuid.uuid4()
    async with maker() as db:
        for o, n in ((org, "com"), (other, "com-other")):
            await db.execute(
                text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                {"i": o, "n": f"{n}-{o.hex[:6]}"})

        register = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.commercial_sources
            (id,org_id,name,kind,permits_direct_marketing,licence_note)
            VALUES (:i,:o,'FMCSA carrier register','PUBLIC_REGISTER',false,
                    'read-only public register; no outreach licence')"""),
            {"i": register, "o": org})
        licensed = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.commercial_sources
            (id,org_id,name,kind,permits_direct_marketing,licence_note)
            VALUES (:i,:o,'Trade show list','SELF_SOURCED',true,
                    'collected at our own booth with consent')"""),
            {"i": licensed, "o": org})

        observed = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.commercial_prospects
            (id,org_id,source_id,name,stage)
            VALUES (:i,:o,:s,'Charles David Martin Jr','OBSERVED')"""),
            {"i": observed, "o": org, "s": register})
        saved = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.commercial_prospects
            (id,org_id,source_id,name,stage,saved_by,saved_at)
            VALUES (:i,:o,:s,'Rio Grande Produce','SAVED',
                    'dana.ruiz@example.test',now())"""),
            {"i": saved, "o": org, "s": licensed})
        await db.commit()

    fastapi_app.dependency_overrides[db_session] = _session
    fastapi_app.dependency_overrides[require_org] = lambda: Actor(
        org_id=str(org), user_id="t", role="admin", claims={})

    async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=fastapi_app),
            base_url="http://t") as client:
        yield {"c": client, "db_maker": maker, "org": org, "other": other,
               "register": register, "licensed": licensed,
               "observed": observed, "saved": saved}

    fastapi_app.dependency_overrides.pop(db_session, None)
    fastapi_app.dependency_overrides.pop(require_org, None)
    async with maker() as db:
        for o in (org, other):
            await db.execute(text("DELETE FROM public.orgs WHERE id = :i"),
                             {"i": o})
        await db.commit()
    await engine.dispose()


# ===========================================================================
# Schema
# ===========================================================================

@pytest.mark.asyncio
async def test_a_source_permitting_outreach_must_state_the_basis(env):
    """"true" with no note is the field that gets set by whoever is in a
    hurry."""
    async with env["db_maker"]() as db:
        with pytest.raises(Exception) as e:
            await db.execute(text("""INSERT INTO public.commercial_sources
                (id,org_id,name,kind,permits_direct_marketing,licence_note)
                VALUES (:i,:o,'Careless list','PURCHASED_LIST',true,'ok')"""),
                {"i": uuid.uuid4(), "o": env["org"]})
            await db.commit()
        assert "licence_ck" in str(e.value)


@pytest.mark.asyncio
async def test_a_prospect_past_observed_needs_a_human(env):
    async with env["db_maker"]() as db:
        with pytest.raises(Exception) as e:
            await db.execute(text("""INSERT INTO public.commercial_prospects
                (id,org_id,source_id,name,stage)
                VALUES (:i,:o,:s,'Nobody saved me','CONTACTED')"""),
                {"i": uuid.uuid4(), "o": env["org"], "s": env["licensed"]})
            await db.commit()
        assert "human_ck" in str(e.value)


@pytest.mark.asyncio
async def test_an_observed_prospect_needs_nobody(env):
    """Positive control: the gate is on ADVANCING, not on observing."""
    async with env["db_maker"]() as db:
        await db.execute(text("""INSERT INTO public.commercial_prospects
            (id,org_id,source_id,name,stage)
            VALUES (:i,:o,:s,'Just a name','OBSERVED')"""),
            {"i": uuid.uuid4(), "o": env["org"], "s": env["licensed"]})
        await db.commit()


@pytest.mark.asyncio
async def test_an_attribution_cannot_claim_realised_without_cash(env):
    async with env["db_maker"]() as db:
        with pytest.raises(Exception) as e:
            await db.execute(text("""INSERT INTO public.commercial_attributions
                (id,org_id,prospect_id,spend_cents,revenue_cents,
                 cash_collected_cents,verdict,grade,basis,note)
                VALUES (:i,:o,:p,180000,800000,0,'WORKED','MODELED',
                        'REALISED','no cash at all')"""),
                {"i": uuid.uuid4(), "o": env["org"], "p": env["saved"]})
            await db.commit()
        assert "cash_ck" in str(e.value)


@pytest.mark.asyncio
async def test_an_actual_spend_must_cite_something(env):
    async with env["db_maker"]() as db:
        with pytest.raises(Exception) as e:
            await db.execute(text("""INSERT INTO public.commercial_actions
                (id,org_id,prospect_id,action_kind,description,occurred_on,
                 spend_cents,spend_authority)
                VALUES (:i,:o,:p,'CONTENT','a campaign',:d,180000,
                        'FINANCIAL_ACTUAL')"""),
                {"i": uuid.uuid4(), "o": env["org"], "p": env["saved"],
                 "d": TODAY})
            await db.commit()
        assert "actual_ck" in str(e.value)


@pytest.mark.asyncio
async def test_deleting_a_source_takes_its_prospects_but_not_its_customers(env):
    """A prospect whose licence basis no longer exists must not survive as an
    unattributed name. A CUSTOMER must survive: the account exists
    independently of how it was sourced."""
    async with env["db_maker"]() as db:
        cust = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_customers
            (id,org_id,name,payment_terms_days,prospect_id)
            VALUES (:i,:o,'Rio Grande Produce',30,:p)"""),
            {"i": cust, "o": env["org"], "p": env["saved"]})
        await db.commit()

        await db.execute(text("DELETE FROM public.commercial_sources "
                              "WHERE id = :i"), {"i": env["licensed"]})
        await db.commit()

        gone = (await db.execute(text("""
            SELECT count(*) FROM public.commercial_prospects
            WHERE id = :i"""), {"i": env["saved"]})).scalar_one()
        assert gone == 0

        row = (await db.execute(text("""
            SELECT name, prospect_id FROM public.trucking_customers
            WHERE id = :i"""), {"i": cust})).first()
        assert row is not None, "the customer must survive"
        assert row[1] is None, "and its origin is now unknown, not invented"


# ===========================================================================
# The endpoints
# ===========================================================================

@pytest.mark.asyncio
async def test_spending_against_an_unlicensed_prospect_is_refused(env):
    r = await env["c"].post(
        f"/api/commercial/prospects/{env['observed']}/actions",
        json={"action_kind": "OUTBOUND_EMAIL", "spend_cents": 50_000,
              "description": "a campaign"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "SOURCE_DOES_NOT_LICENCE_OUTREACH"

    async with env["db_maker"]() as db:
        n = (await db.execute(text("""
            SELECT count(*) FROM public.commercial_actions
            WHERE prospect_id = :p"""), {"p": env["observed"]})).scalar_one()
    assert n == 0, "a refused action must not leave a spend row behind"


@pytest.mark.asyncio
async def test_spending_against_a_saved_licensed_prospect_is_recorded(env):
    r = await env["c"].post(
        f"/api/commercial/prospects/{env['saved']}/actions",
        json={"action_kind": "CONTENT", "spend_cents": 180_000,
              "description": "lane page for McAllen to Chicago reefer",
              "spend_authority": "FINANCIAL_ACTUAL",
              "spend_source_ref": "AP invoice 2026-0431"})
    assert r.status_code == 200, r.text
    assert r.json()["spend_cents"] == 180_000


@pytest.mark.asyncio
async def test_an_actual_spend_with_no_reference_is_refused_by_the_api(env):
    r = await env["c"].post(
        f"/api/commercial/prospects/{env['saved']}/actions",
        json={"action_kind": "CONTENT", "spend_cents": 180_000,
              "spend_authority": "FINANCIAL_ACTUAL", "description": "x"})
    assert r.status_code == 422
    assert "cite the invoice" in r.json()["detail"]


@pytest.mark.asyncio
async def test_the_loop_reports_too_early_before_any_freight(env):
    await env["c"].post(
        f"/api/commercial/prospects/{env['saved']}/actions",
        json={"action_kind": "CONTENT", "spend_cents": 180_000,
              "description": "lane page"})
    r = await env["c"].get(f"/api/commercial/loop/{env['saved']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["attribution"]["verdict"] == "TOO_EARLY"
    assert body["marketing_rights"]["allowed"] is True


@pytest.mark.asyncio
async def test_the_loop_shows_the_refusal_on_an_unlicensed_prospect(env):
    r = await env["c"].get(f"/api/commercial/loop/{env['observed']}")
    assert r.status_code == 200
    rights = r.json()["marketing_rights"]
    assert rights["allowed"] is False
    assert "CARRIER network" in rights["alternative"]


@pytest.mark.asyncio
async def test_advancing_a_prospect_records_who_decided(env):
    r = await env["c"].post(
        f"/api/commercial/prospects/{env['observed']}/stage",
        json={"stage": "SAVED", "saved_by": "dana.ruiz@example.test"})
    assert r.status_code == 200, r.text
    r2 = await env["c"].get(f"/api/commercial/loop/{env['observed']}")
    assert r2.json()["prospect"]["saved_by"] == "dana.ruiz@example.test"


@pytest.mark.asyncio
async def test_advancing_without_a_human_is_refused(env):
    r = await env["c"].post(
        f"/api/commercial/prospects/{env['observed']}/stage",
        json={"stage": "SAVED"})
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "NO_HUMAN_SAVED_THIS"


@pytest.mark.asyncio
async def test_the_index_only_shows_this_organisations_prospects(env):
    r = await env["c"].get("/api/commercial/loop")
    names = {p["name"] for p in r.json()["prospects"]}
    assert names == {"Charles David Martin Jr", "Rio Grande Produce"}

    fastapi_app.dependency_overrides[require_org] = lambda: Actor(
        org_id=str(env["other"]), user_id="t", role="admin", claims={})
    try:
        r2 = await env["c"].get("/api/commercial/loop")
        assert r2.json()["prospects"] == []
        r3 = await env["c"].get(f"/api/commercial/loop/{env['saved']}")
        assert r3.status_code == 404
    finally:
        fastapi_app.dependency_overrides[require_org] = lambda: Actor(
            org_id=str(env["org"]), user_id="t", role="admin", claims={})


@pytest.mark.asyncio
async def test_a_non_staff_role_is_refused(env):
    fastapi_app.dependency_overrides[require_org] = lambda: Actor(
        org_id=str(env["org"]), user_id="t", role="employee", claims={})
    try:
        r = await env["c"].get("/api/commercial/loop")
        assert r.status_code == 403
    finally:
        fastapi_app.dependency_overrides[require_org] = lambda: Actor(
            org_id=str(env["org"]), user_id="t", role="admin", claims={})
