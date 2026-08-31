"""The rate-confirmation constraints, exercised against PostgreSQL.

`rate_confirmation.py` refuses these cases in Python. The database refuses them
too, because the Python path is not the only way a row gets written -- a
migration, a backfill script, a psql session at 2am. A constraint that lives
only in the application is a convention.

Every constraint here gets an attempted violation AND a legitimate row that
must still insert. A CHECK that rejected everything would pass half of this
file.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

NOW = datetime.now(timezone.utc)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def ctx(db):
    """An org with a load and a carrier for the confirmation to reference."""
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"rc-{org.hex[:6]}"})
    cust = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_customers
        (id,org_id,name,payment_terms_days) VALUES (:i,:o,'Shipper',30)"""),
        {"i": cust, "o": org})
    carrier = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_carriers
        (id,org_id,name,dot_number,authority_status,authority_source,
         authority_checked_at,is_approved)
        VALUES (:i,:o,'Delta Line','2194844','ACTIVE','FMCSA_LIVE',now(),true)"""),
        {"i": carrier, "o": org})
    load = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_loads
        (id,org_id,load_number,customer_id,status,fulfilment_mode,carrier_id,
         origin_city,origin_state,destination_city,destination_state,
         customer_rate_cents)
        VALUES (:i,:o,'L-RC-1',:c,'BOOKED','BROKERED',:car,
                'Pharr','TX','Detroit','MI',500000)"""),
        {"i": load, "o": org, "c": cust, "car": carrier})
    await db.commit()
    yield {"org": org, "load": load, "carrier": carrier}
    # A test that asserted on a constraint violation leaves the transaction
    # aborted, and the cleanup below would then fail with
    # InFailedSQLTransactionError -- turning every negative test into an error
    # even though the constraint did exactly what it should.
    await db.rollback()
    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": org})
    await db.commit()


async def _insert(db, ctx, **over):
    row = dict(
        i=uuid.uuid4(), o=ctx["org"], l=ctx["load"], c=ctx["carrier"],
        num=f"RC-{uuid.uuid4().hex[:8]}", lh=350_000, fsc=43_000,
        tot=393_000, state="DRAFT", issued=None, accepted=None, by=None,
        sha=None, sup=None, reason=None,
    )
    row.update(over)
    await db.execute(text("""INSERT INTO public.trucking_rate_confirmations
        (id,org_id,load_id,carrier_id,confirmation_number,
         linehaul_cents,fuel_surcharge_cents,agreed_total_cents,state,
         issued_at,accepted_at,accepted_by,document_sha256,
         supersedes_id,amendment_reason)
        VALUES (:i,:o,:l,:c,:num,:lh,:fsc,:tot,:state,
                :issued,:accepted,:by,:sha,:sup,:reason)"""), row)
    await db.commit()
    return row["i"]


# ===========================================================================
# The total is the sum of its parts
# ===========================================================================

@pytest.mark.asyncio
async def test_a_legitimate_draft_inserts(ctx, db):
    """Positive control for every test below."""
    assert await _insert(db, ctx) is not None


@pytest.mark.asyncio
async def test_a_total_that_is_not_its_parts_is_refused(ctx, db):
    """A document that says two different things about the money."""
    with pytest.raises(Exception) as e:
        await _insert(db, ctx, tot=999_999)
    assert "trucking_ratecon_total_ck" in str(e.value)


@pytest.mark.asyncio
async def test_a_negative_rate_is_refused(ctx, db):
    """A rate confirmation is not a credit memo."""
    with pytest.raises(Exception) as e:
        await _insert(db, ctx, lh=-1, tot=42_999)
    assert "nonneg" in str(e.value)


# ===========================================================================
# A state must carry its own evidence
# ===========================================================================

@pytest.mark.asyncio
async def test_accepted_without_a_counterparty_is_refused(ctx, db):
    """ACCEPTED is the state that authorises a payable. A row claiming
    acceptance with no time and no counterparty is the field it replaced."""
    with pytest.raises(Exception) as e:
        await _insert(db, ctx, state="ACCEPTED", issued=NOW, sha="a" * 64)
    assert "accepted_ck" in str(e.value)


@pytest.mark.asyncio
async def test_accepted_with_a_counterparty_and_a_time_inserts(ctx, db):
    assert await _insert(db, ctx, state="ACCEPTED", issued=NOW, sha="a" * 64,
                         accepted=NOW, by="Delta Line dispatch")


@pytest.mark.asyncio
async def test_issued_without_a_document_hash_is_refused(ctx, db):
    """ISSUED means it left the building. Without a hash there is nothing to
    detect a later edit against."""
    with pytest.raises(Exception) as e:
        await _insert(db, ctx, state="ISSUED", issued=NOW)
    assert "issued_ck" in str(e.value)


@pytest.mark.asyncio
async def test_an_unknown_state_is_refused(ctx, db):
    with pytest.raises(Exception) as e:
        await _insert(db, ctx, state="PROBABLY_FINE")
    assert "state_ck" in str(e.value)


# ===========================================================================
# Amendment
# ===========================================================================

@pytest.mark.asyncio
async def test_an_amendment_without_a_reason_is_refused(ctx, db):
    original = await _insert(db, ctx, state="ACCEPTED", issued=NOW,
                             sha="a" * 64, accepted=NOW, by="dispatch")
    await db.execute(text("""UPDATE public.trucking_rate_confirmations
        SET state = 'SUPERSEDED', superseded_at = now() WHERE id = :i"""),
        {"i": original})
    await db.commit()
    with pytest.raises(Exception) as e:
        await _insert(db, ctx, sup=original)
    assert "amendment_ck" in str(e.value)


@pytest.mark.asyncio
async def test_an_amendment_with_a_reason_inserts(ctx, db):
    original = await _insert(db, ctx, state="ACCEPTED", issued=NOW,
                             sha="a" * 64, accepted=NOW, by="dispatch")
    await db.execute(text("""UPDATE public.trucking_rate_confirmations
        SET state = 'SUPERSEDED', superseded_at = now() WHERE id = :i"""),
        {"i": original})
    await db.commit()
    assert await _insert(db, ctx, sup=original,
                         reason="carrier renegotiated after a re-power")


# ===========================================================================
# One live confirmation per load
# ===========================================================================

@pytest.mark.asyncio
async def test_a_load_cannot_have_two_live_confirmations(ctx, db):
    """Two live rates for one load means the settlement picks one, and which
    one it picks is not a decision anybody made."""
    await _insert(db, ctx, state="ACCEPTED", issued=NOW, sha="a" * 64,
                  accepted=NOW, by="dispatch")
    with pytest.raises(Exception) as e:
        await _insert(db, ctx, state="DRAFT")
    assert "uq_ratecon_live_per_load" in str(e.value)


@pytest.mark.asyncio
async def test_a_superseded_confirmation_leaves_room_for_the_next(ctx, db):
    """Superseding rather than updating is what keeps the original, and the
    partial index is what makes that possible."""
    first = await _insert(db, ctx, state="ACCEPTED", issued=NOW, sha="a" * 64,
                          accepted=NOW, by="dispatch")
    await db.execute(text("""UPDATE public.trucking_rate_confirmations
        SET state = 'SUPERSEDED', superseded_at = now() WHERE id = :i"""),
        {"i": first})
    await db.commit()
    second = await _insert(db, ctx, sup=first, reason="re-power",
                           state="ACCEPTED", issued=NOW, sha="b" * 64,
                           accepted=NOW, by="dispatch")
    rows = (await db.execute(text("""
        SELECT state FROM public.trucking_rate_confirmations
        WHERE load_id = :l ORDER BY created_at"""),
        {"l": ctx["load"]})).scalars().all()
    assert rows == ["SUPERSEDED", "ACCEPTED"], (
        "the original must still be there; a settlement may cite it")
    assert second != first


@pytest.mark.asyncio
async def test_a_declined_confirmation_leaves_room_for_the_next(ctx, db):
    await _insert(db, ctx, state="ISSUED", issued=NOW, sha="a" * 64)
    await db.execute(text("""UPDATE public.trucking_rate_confirmations
        SET state = 'DECLINED' WHERE load_id = :l"""), {"l": ctx["load"]})
    await db.commit()
    assert await _insert(db, ctx, state="DRAFT")


@pytest.mark.asyncio
async def test_confirmation_numbers_are_unique_within_an_org(ctx, db):
    await _insert(db, ctx, num="RC-SAME")
    # A second load, so the live-per-load index is not what refuses it.
    other = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_loads
        (id,org_id,load_number,customer_id,status,fulfilment_mode,
         origin_city,origin_state,destination_city,destination_state,
         customer_rate_cents)
        SELECT :i,:o,'L-RC-2',customer_id,'BOOKED','BROKERED',
               'Pharr','TX','Detroit','MI',400000
        FROM public.trucking_loads WHERE id = :l"""),
        {"i": other, "o": ctx["org"], "l": ctx["load"]})
    await db.commit()
    with pytest.raises(Exception) as e:
        await _insert(db, ctx, num="RC-SAME", l=other)
    assert "uq_ratecon_number" in str(e.value)


# ===========================================================================
# The links a settlement is traced through
# ===========================================================================

@pytest.mark.asyncio
async def test_a_settlement_records_which_confirmation_authorised_it(ctx, db):
    """A carrier payable with no confirmation behind it must be traceable as
    such, rather than indistinguishable from one that has one."""
    rc = await _insert(db, ctx, state="ACCEPTED", issued=NOW, sha="a" * 64,
                       accepted=NOW, by="dispatch")
    sid = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_settlements
        (id,org_id,load_id,payee_kind,state,linehaul_cents,total_cents,
         derivation_note,rate_confirmation_id)
        VALUES (:i,:o,:l,'CARRIER','PROPOSED',393000,393000,
                'from RC',:rc)"""),
        {"i": sid, "o": ctx["org"], "l": ctx["load"], "rc": rc})
    await db.commit()
    got = (await db.execute(text("""
        SELECT rate_confirmation_id FROM public.trucking_settlements
        WHERE id = :i"""), {"i": sid})).scalar_one()
    assert got == rc


@pytest.mark.asyncio
async def test_deleting_the_org_takes_its_confirmations(ctx, db):
    """Tenant deletion must not strand a document naming a carrier and a rate."""
    await _insert(db, ctx)
    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"),
                     {"i": ctx["org"]})
    await db.commit()
    left = (await db.execute(text("""
        SELECT count(*) FROM public.trucking_rate_confirmations
        WHERE org_id = :o"""), {"o": ctx["org"]})).scalar_one()
    assert left == 0
