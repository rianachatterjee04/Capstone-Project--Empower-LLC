"""Cross-tenant attacks on the trucking objects.

Same reasoning as the interview tenancy suite: service_role bypasses RLS, so
the application's WHERE clause is the control rather than a backstop behind
one. What is different here is the CONSEQUENCE. An interview leak exposes a
candidate's words; a load leak exposes a customer's freight, their rate, and
who is hauling it -- and a settlement leak moves money.

The attacks that matter most are the WRITE ones, because a cross-tenant read
is a disclosure and a cross-tenant write is a payment.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

TODAY = date.today()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


async def _tenant(db, label: str) -> dict:
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"truck-{label}-{org.hex[:6]}"})
    cust = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_customers
        (id,org_id,name) VALUES (:i,:o,:n)"""),
        {"i": cust, "o": org, "n": f"Shipper {label}"})
    drv = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_drivers
        (id,org_id,driver_code,worker_classification,pay_model,pay_rate_cents)
        VALUES (:i,:o,:c,'W2_EMPLOYEE','PER_MILE',60)"""),
        {"i": drv, "o": org, "c": f"D-{label}"})
    await db.execute(text("""INSERT INTO public.driver_credentials
        (org_id,driver_id,credential_type,expires_on,verification_state)
        VALUES (:o,:d,'CDL_A',:e,'DOCUMENT_ON_FILE')"""),
        {"o": org, "d": drv, "e": TODAY + timedelta(days=365)})
    load = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_loads
        (id,org_id,customer_id,load_number,status,fulfilment_mode,driver_id,
         origin_city,origin_state,destination_city,destination_state,
         customer_rate_cents,miles)
        VALUES (:i,:o,:c,:n,'DISPATCHED','OWN_FLEET',:d,
                'Dallas','TX','Chicago','IL',400000,1000)"""),
        {"i": load, "o": org, "c": cust, "n": f"L-{label}", "d": drv})
    await db.commit()
    return {"org": org, "customer": cust, "driver": drv, "load": load,
            "label": label}


@pytest_asyncio.fixture
async def two(db):
    a = await _tenant(db, "aaa")
    b = await _tenant(db, "bbb")
    yield a, b
    for t in (a, b):
        await db.execute(text("DELETE FROM public.orgs WHERE id = :i"),
                         {"i": t["org"]})
    await db.commit()


# ===========================================================================
# Reads
# ===========================================================================

@pytest.mark.parametrize("table,column", [
    ("trucking_loads", "id"),
    ("trucking_customers", "id"),
    ("trucking_drivers", "id"),
])
@pytest.mark.asyncio
async def test_an_object_is_invisible_under_the_wrong_org(two, db, table, column):
    a, b = two
    key = {"trucking_loads": "load", "trucking_customers": "customer",
           "trucking_drivers": "driver"}[table]

    mine = (await db.execute(text(
        f"SELECT count(*) FROM public.{table} WHERE org_id=:o AND {column}=:i"),
        {"o": a["org"], "i": a[key]})).scalar_one()
    assert mine == 1

    stolen = (await db.execute(text(
        f"SELECT count(*) FROM public.{table} WHERE org_id=:o AND {column}=:i"),
        {"o": b["org"], "i": a[key]})).scalar_one()
    assert stolen == 0, f"tenant B could read tenant A's {table}"


@pytest.mark.asyncio
async def test_a_driver_credential_does_not_leak(two, db):
    """A licence number and expiry are personal data about an employee."""
    a, b = two
    assert (await db.execute(text(
        "SELECT count(*) FROM public.driver_credentials "
        "WHERE org_id=:o AND driver_id=:d"),
        {"o": b["org"], "d": a["driver"]})).scalar_one() == 0


@pytest.mark.asyncio
async def test_a_customer_rate_does_not_leak(two, db):
    """What one shipper pays is commercially sensitive to the other."""
    a, b = two
    assert (await db.execute(text(
        "SELECT customer_rate_cents FROM public.trucking_loads "
        "WHERE org_id=:o AND id=:l"),
        {"o": b["org"], "l": a["load"]})).first() is None


# ===========================================================================
# Writes -- where a leak becomes a payment
# ===========================================================================

@pytest.mark.asyncio
async def test_a_load_cannot_be_assigned_another_tenants_driver(two, db):
    """The attack that matters: put MY driver on YOUR load, and the settlement
    follows the driver.

    The database does not enforce this by itself -- driver_id has no composite
    key with org_id -- so the application filter is what stops it. This test
    documents that the row CAN be written and asserts the query that any
    read path must use.
    """
    a, b = two
    await db.execute(text(
        "UPDATE public.trucking_loads SET driver_id=:d WHERE id=:l"),
        {"d": b["driver"], "l": a["load"]})
    await db.commit()

    # The read path must join on org_id, and then the driver disappears.
    row = (await db.execute(text("""
        SELECT d.driver_code
        FROM public.trucking_loads l
        JOIN public.trucking_drivers d
          ON d.id = l.driver_id AND d.org_id = l.org_id
        WHERE l.org_id = :o AND l.id = :l"""),
        {"o": a["org"], "l": a["load"]})).first()
    assert row is None, (
        "a driver from another tenant resolved through a load. Every join to "
        "trucking_drivers must carry org_id, or a cross-tenant assignment "
        "reads as valid.")


@pytest.mark.asyncio
async def test_two_tenants_may_use_the_same_load_number(two, db):
    """Uniqueness is per organisation. If load numbers were globally unique,
    one tenant could probe another's numbering -- and worse, a legitimate
    'L-1001' would be refused because a stranger already used it."""
    a, b = two
    dup = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_loads
        (id,org_id,customer_id,load_number,origin_city,origin_state,
         destination_city,destination_state)
        VALUES (:i,:o,:c,:n,'X','TX','Y','IL')"""),
        {"i": dup, "o": b["org"], "c": b["customer"], "n": "L-aaa"})
    await db.commit()
    assert (await db.execute(text(
        "SELECT count(*) FROM public.trucking_loads WHERE load_number='L-aaa'"
    ))).scalar_one() == 2


@pytest.mark.asyncio
async def test_an_invoice_is_one_per_load(two, db):
    """The duplicate-invoice control, at the database.

    Billing the same load twice is the most common revenue-integrity failure
    in freight, and it is usually a retry rather than fraud -- which is why it
    has to be a constraint rather than a procedure.
    """
    a, _ = two
    for n in ("INV-1", "INV-2"):
        stmt = text("""INSERT INTO public.trucking_invoices
            (org_id,customer_id,load_id,invoice_number,linehaul_cents,
             accessorial_cents,total_cents,derivation_note)
            VALUES (:o,:c,:l,:n,400000,0,400000,'test')""")
        params = {"o": a["org"], "c": a["customer"], "l": a["load"], "n": n}
        if n == "INV-1":
            await db.execute(stmt, params)
            await db.commit()
        else:
            message = None
            try:
                await db.execute(stmt, params)
                await db.flush()
            except Exception as exc:      # noqa: BLE001
                message = str(exc)
            await db.rollback()
            assert message and "trucking_invoices_one_per_load" in message, (
                "a second invoice was accepted for the same load")


@pytest.mark.asyncio
async def test_an_invoice_total_must_equal_its_parts(two, db):
    """A typed total is exactly what the derivation is meant to prevent."""
    a, _ = two
    message = None
    try:
        await db.execute(text("""INSERT INTO public.trucking_invoices
            (org_id,customer_id,load_id,invoice_number,linehaul_cents,
             accessorial_cents,total_cents,derivation_note)
            VALUES (:o,:c,:l,'INV-BAD',400000,0,999999,'typed')"""),
            {"o": a["org"], "c": a["customer"], "l": a["load"]})
        await db.flush()
    except Exception as exc:              # noqa: BLE001
        message = str(exc)
    await db.rollback()
    assert message and "trucking_invoices_total_ck" in message


@pytest.mark.asyncio
async def test_a_w2_settlement_cannot_be_marked_paid(two, db):
    """Worker classification, enforced by the database rather than by a code
    path somebody can route around."""
    a, _ = two
    message = None
    try:
        await db.execute(text("""INSERT INTO public.trucking_settlements
            (org_id,load_id,payee_kind,driver_id,linehaul_cents,total_cents,
             derivation_note,state,approved_by,approved_at)
            VALUES (:o,:l,'DRIVER_W2',:d,60000,60000,'x','PAID','me',now())"""),
            {"o": a["org"], "l": a["load"], "d": a["driver"]})
        await db.flush()
    except Exception as exc:              # noqa: BLE001
        message = str(exc)
    await db.rollback()
    assert message and "trucking_settlements_w2_ck" in message, (
        "a W-2 driver's pay was marked PAID from settlement, bypassing "
        "withholding and employer contributions")


@pytest.mark.asyncio
async def test_an_approved_accessorial_needs_a_named_approver(two, db):
    a, _ = two
    message = None
    try:
        await db.execute(text("""INSERT INTO public.trucking_accessorials
            (org_id,load_id,accessorial_type,amount_cents,state,direction)
            VALUES (:o,:l,'DETENTION',25000,'APPROVED','CUSTOMER_BILLABLE')"""),
            {"o": a["org"], "l": a["load"]})
        await db.flush()
    except Exception as exc:              # noqa: BLE001
        message = str(exc)
    await db.rollback()
    assert message and "trucking_accessorials_approval_ck" in message


@pytest.mark.asyncio
async def test_a_carrier_claiming_a_source_must_say_when_it_was_checked(two, db):
    """A stale ACTIVE is how a revoked carrier keeps getting loads."""
    a, _ = two
    message = None
    try:
        await db.execute(text("""INSERT INTO public.trucking_carriers
            (org_id,name,authority_status,authority_source)
            VALUES (:o,'Ghost Trucking','ACTIVE','FMCSA_CACHED')"""),
            {"o": a["org"]})
        await db.flush()
    except Exception as exc:              # noqa: BLE001
        message = str(exc)
    await db.rollback()
    assert message and "trucking_carriers_checked_ck" in message


@pytest.mark.asyncio
async def test_deleting_a_tenant_removes_its_freight_data(db):
    t = await _tenant(db, "cascade")
    org = t["org"]
    assert (await db.execute(text(
        "SELECT count(*) FROM public.trucking_loads WHERE org_id=:o"),
        {"o": org})).scalar_one() == 1

    await db.execute(text("DELETE FROM public.orgs WHERE id=:i"), {"i": org})
    await db.commit()

    for table in ("trucking_loads", "trucking_drivers", "driver_credentials",
                  "trucking_customers"):
        left = (await db.execute(text(
            f"SELECT count(*) FROM public.{table} WHERE org_id=:o"),
            {"o": org})).scalar_one()
        assert left == 0, f"{table} still holds rows for a deleted organisation"
