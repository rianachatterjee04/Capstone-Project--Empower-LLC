"""The tile and the list behind it are the same fact.

A drill-through that disagrees with its tile is worse than none: the operator
now has two numbers and no way to tell which is wrong. The tile ran one
hand-written query and the `drill` field was a PROSE DESCRIPTION of roughly
the same predicate -- so there was nothing to disagree with, and also nothing
to click.

These tests run against a real database with real rows, because the property
being tested is about SQL agreeing with SQL. A stub that returned what it was
told would pass every one of them and prove nothing.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.trucking import drilldown as DD
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

TODAY = date.today()


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest_asyncio.fixture
async def org(db):
    """An org with rows on BOTH sides of every predicate.

    Both sides matters. A fixture whose loads were all EXCEPTION would make
    the "active loads" reconciliation pass for the wrong reason, and
    `test_the_fixture_exercises_both_sides_of_each_predicate` is the control
    that keeps this honest.

    The inserts go through the real constraints -- fulfilment_mode,
    coverage, the settlement approval rule, the invoice total rule -- so a
    schema change that would break the drills breaks these first.
    """
    o = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": o, "n": f"drill-{o.hex[:6]}"})

    cust = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_customers
        (id,org_id,name,payment_terms_days) VALUES (:i,:o,'Acme Produce',30)"""),
        {"i": cust, "o": o})

    driver = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.trucking_drivers
        (id,org_id,driver_code,status,worker_classification,
         classification_source,classification_note,pay_model,pay_rate_cents,
         home_base)
        VALUES (:i,:o,'D-001','ACTIVE','W2_EMPLOYEE','ONBOARDING_FORM',
                'test fixture','PER_MILE',62,'Laredo TX')"""),
        {"i": driver, "o": o})

    # one credential expiring inside the window, one well outside it
    for ctype, days, ident in (("CDL_A", 12, "TX-9931"),
                               ("MEDICAL_CARD", 300, "MC-7781")):
        await db.execute(text("""INSERT INTO public.driver_credentials
            (id,org_id,driver_id,credential_type,identifier,issuing_authority,
             expires_on,verification_state)
            VALUES (:i,:o,:d,:t,:ident,'TX DPS',:e,'DOCUMENT_ON_FILE')"""),
            {"i": uuid.uuid4(), "o": o, "d": driver, "t": ctype,
             "ident": ident, "e": TODAY + timedelta(days=days)})

    # one carrier that cannot be used (stale check), one that can
    await db.execute(text("""INSERT INTO public.trucking_carriers
        (id,org_id,name,dot_number,mc_number,authority_status,authority_source,
         authority_checked_at,insurance_expires_on,is_approved)
        VALUES (:i,:o,'Stale Authority Trucking','2194844','MC-111','ACTIVE',
                'FMCSA_CACHED', now() - interval '90 days',
                :ins, true)"""),
        {"i": uuid.uuid4(), "o": o, "ins": TODAY + timedelta(days=180)})
    await db.execute(text("""INSERT INTO public.trucking_carriers
        (id,org_id,name,dot_number,mc_number,authority_status,authority_source,
         authority_checked_at,insurance_expires_on,is_approved)
        VALUES (:i,:o,'Good Standing Carriers','3311220','MC-222','ACTIVE',
                'FMCSA_LIVE', now() - interval '2 days', :ins, true)"""),
        {"i": uuid.uuid4(), "o": o, "ins": TODAY + timedelta(days=180)})

    async def load(n, status, *, pod=None, invoice=None, rate=250_000,
                   mode="OWN_FLEET"):
        lid = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_loads
            (id,org_id,load_number,customer_id,status,fulfilment_mode,driver_id,
             origin_city,origin_state,destination_city,destination_state,
             pickup_window_start,delivery_window_end,equipment_required,
             commodity,miles,customer_rate_cents,pod_id,invoice_id)
            VALUES (:i,:o,:n,:c,:s,:m,:drv,
                    'McAllen','TX','Chicago','IL',:p,:dd,'REEFER',
                    'Romaine',1420,:r,:pod,:inv)"""),
            {"i": lid, "o": o, "n": n, "c": cust, "s": status, "m": mode,
             "drv": driver, "p": TODAY, "dd": TODAY + timedelta(days=2),
             "r": rate, "pod": pod, "inv": invoice})
        return lid

    # active (4) and terminal (2), so "not terminal" is a real filter
    await load("L-ACT-1", "BOOKED")
    await load("L-ACT-2", "DISPATCHED")
    await load("L-ACT-3", "IN_TRANSIT")
    await load("L-ACT-4", "EXCEPTION")
    await load("L-DONE-1", "SETTLED")
    await load("L-CANC-1", "CANCELLED")

    # delivered without a POD -- cannot be invoiced
    await load("L-NOPOD-1", "DELIVERED")
    await load("L-NOPOD-2", "DELIVERED")

    # delivered WITH a POD and no invoice -> unbilled
    delivered = await load("L-UNBILLED-1", "POD_RECEIVED", rate=400_000)
    pod_id = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.proof_of_delivery
        (id,org_id,load_id,evidence_strength,received_at,receiver_name,
         signature_kind)
        VALUES (:i,:o,:l,'SIGNED_DOCUMENT', now(),'Dock 4','WET_SIGNATURE')"""),
        {"i": pod_id, "o": o, "l": delivered})
    await db.execute(text("UPDATE public.trucking_loads SET pod_id = :p "
                          "WHERE id = :l"), {"p": pod_id, "l": delivered})

    # invoices: open+current, open+overdue, and one already paid
    async def invoice(num, state, due, total, paid, load_id):
        iid = uuid.uuid4()
        await db.execute(text("""INSERT INTO public.trucking_invoices
            (id,org_id,invoice_number,customer_id,load_id,state,
             issued_on,due_on,linehaul_cents,accessorial_cents,
             total_cents,paid_cents,derivation_note)
            VALUES (:i,:o,:n,:c,:l,:s,:iss,:d,:t,0,:t,:p,'test fixture')"""),
            {"i": iid, "o": o, "n": num, "c": cust, "l": load_id, "s": state,
             "iss": due - timedelta(days=30), "d": due, "t": total, "p": paid})
        return iid

    await invoice("INV-CURRENT", "SENT", TODAY + timedelta(days=20),
                  300_000, 0, await load("L-INV-A", "INVOICED"))
    await invoice("INV-LATE", "SENT", TODAY - timedelta(days=10),
                  500_000, 100_000, await load("L-INV-B", "INVOICED"))
    await invoice("INV-PAID", "PAID", TODAY - timedelta(days=40),
                  200_000, 200_000, await load("L-INV-C", "SETTLED"))

    # settlements: carrier due (2), one already paid, one W-2 payroll input
    async def settlement(note, kind, state, total, load_id):
        approved = state in ("APPROVED", "PAID")
        await db.execute(text("""INSERT INTO public.trucking_settlements
            (id,org_id,load_id,payee_kind,state,linehaul_cents,total_cents,
             derivation_note,approved_by,approved_at)
            VALUES (:i,:o,:l,:k,:s,:t,:t,:n,:by,:at)"""),
            {"i": uuid.uuid4(), "o": o, "l": load_id, "k": kind, "s": state,
             "t": total, "n": note,
             "by": "fixture" if approved else None,
             "at": TODAY if approved else None})

    await settlement("S-CAR-1", "CARRIER", "APPROVED", 180_000,
                     await load("L-SET-A", "SETTLED"))
    await settlement("S-CAR-2", "CARRIER", "PROPOSED", 120_000,
                     await load("L-SET-B", "SETTLED"))
    await settlement("S-CAR-PAID", "CARRIER", "PAID", 999_000,
                     await load("L-SET-C", "SETTLED"))
    await settlement("S-W2-1", "DRIVER_W2", "PAYROLL_INPUT", 90_000,
                     await load("L-SET-D", "SETTLED"))

    await db.commit()
    yield o
    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": o})
    await db.commit()


def _binds(org):
    return {"o": org, "d": TODAY, "soon": TODAY + timedelta(days=30)}


# ===========================================================================
# The property
# ===========================================================================

@pytest.mark.parametrize("key", sorted(DD.DRILLS))
@pytest.mark.asyncio
async def test_the_rows_reconcile_with_the_tile(db, org, key):
    """For every drill: the tile's number and the rows behind it agree.

    Count drills: one row per unit counted.
    Money drills: the rows' own `amount_cents` sums to the tile.
    """
    spec = DD.DRILLS[key]
    binds = _binds(org)
    total = (await db.execute(text(spec.count_sql()), binds)).scalar_one()
    rows = (await db.execute(text(spec.rows_sql(500)), binds)).mappings().all()

    if spec.unit == DD.COUNT:
        assert len(rows) == int(total), (
            f"{key}: the tile says {total} and the drill returned {len(rows)}")
    else:
        assert "amount_cents" in (rows[0].keys() if rows else {"amount_cents"}), (
            f"{key} is a money drill and its rows expose no amount_cents, so "
            f"nothing on the screen can be reconciled against the tile")
        assert sum(int(r["amount_cents"] or 0) for r in rows) == int(total), (
            f"{key}: the tile says {total} and the rows sum to something else")


@pytest.mark.parametrize("key", sorted(DD.DRILLS))
@pytest.mark.asyncio
async def test_every_drill_returns_its_id_column(db, org, key):
    """A row you cannot open is a row you cannot act on."""
    spec = DD.DRILLS[key]
    rows = (await db.execute(text(spec.rows_sql(5)), _binds(org))).mappings().all()
    for r in rows:
        assert spec.id_column in r.keys(), f"{key} has no {spec.id_column}"


# ===========================================================================
# The fixture is not accidentally trivial
# ===========================================================================

@pytest.mark.asyncio
async def test_the_fixture_exercises_both_sides_of_each_predicate(db, org):
    """A reconciliation over an empty set is 0 == 0.

    This is the control on the tests above: if the fixture stopped producing
    rows, every reconciliation would still pass and the suite would be
    reporting on nothing.
    """
    binds = _binds(org)
    nonzero = {}
    for key, spec in DD.DRILLS.items():
        v = (await db.execute(text(spec.count_sql()), binds)).scalar_one()
        nonzero[key] = int(v or 0)

    for key in ("active_loads", "in_transit", "exceptions", "delivered_no_pod",
                "open_ar", "overdue_ar", "unbilled_delivered",
                "carrier_pay_due", "payroll_obligation",
                "expiring_credentials", "carrier_issues"):
        assert nonzero[key] > 0, f"{key} has no rows; its reconciliation is vacuous"


@pytest.mark.asyncio
async def test_terminal_loads_are_excluded_from_active(db, org):
    """The SETTLED and CANCELLED loads exist and must not be counted."""
    total = (await db.execute(text(
        "SELECT count(*) FROM public.trucking_loads WHERE org_id = :o"),
        {"o": org})).scalar_one()
    active = (await db.execute(
        text(DD.DRILLS["active_loads"].count_sql()), _binds(org))).scalar_one()
    assert int(active) < int(total)


@pytest.mark.asyncio
async def test_a_paid_invoice_is_not_open_ar(db, org):
    rows = (await db.execute(text(DD.DRILLS["open_ar"].rows_sql(50)),
                             _binds(org))).mappings().all()
    numbers = {r["invoice_number"] for r in rows}
    assert "INV-PAID" not in numbers
    assert {"INV-CURRENT", "INV-LATE"} <= numbers


@pytest.mark.asyncio
async def test_overdue_is_a_subset_of_open(db, org):
    binds = _binds(org)
    openr = (await db.execute(text(DD.DRILLS["open_ar"].rows_sql(50)),
                              binds)).mappings().all()
    late = (await db.execute(text(DD.DRILLS["overdue_ar"].rows_sql(50)),
                             binds)).mappings().all()
    assert {r["id"] for r in late} < {r["id"] for r in openr}


@pytest.mark.asyncio
async def test_a_paid_settlement_is_not_money_due(db, org):
    rows = (await db.execute(text(DD.DRILLS["carrier_pay_due"].rows_sql(50)),
                             _binds(org))).mappings().all()
    assert "S-CAR-PAID" not in {r["derivation_note"] for r in rows}
    assert {"S-CAR-1", "S-CAR-2"} == {r["derivation_note"] for r in rows}


# ===========================================================================
# Tenancy
# ===========================================================================

@pytest.mark.asyncio
async def test_no_drill_can_see_another_organisation(db, org):
    """Every predicate carries its own org filter. The drill endpoint takes a
    KEY, never a WHERE clause, and this is why."""
    other = uuid.uuid4()
    binds = {"o": other, "d": TODAY, "soon": TODAY + timedelta(days=30)}
    for key, spec in DD.DRILLS.items():
        rows = (await db.execute(text(spec.rows_sql(50)), binds)).mappings().all()
        assert rows == [], f"{key} returned rows for an unrelated org"


@pytest.mark.parametrize("key", sorted(DD.DRILLS))
def test_every_predicate_filters_by_org(key):
    """A structural control on the test above: it would pass for a predicate
    that happened to match nothing. This one reads the SQL."""
    spec = DD.DRILLS[key]
    assert "org_id = :o" in spec.where, (
        f"{key} does not filter by org_id in its own predicate")


# ===========================================================================
# The FMCSA disclosure
# ===========================================================================

@pytest.mark.asyncio
async def test_seeded_authority_does_not_make_fmcsa_connected(db, org):
    """"Do not let cached/demo authority become live compliance truth."

    The fixture's two carriers are FMCSA_CACHED and FMCSA_LIVE. Only a LIVE
    source inside the staleness window may flip the disclosure, and the query
    the board uses names that source explicitly -- so a seeded or cached row
    can never do it.
    """
    live = (await db.execute(text("""
        SELECT count(*) FROM public.trucking_carriers
        WHERE org_id = :o AND authority_source = 'FMCSA_LIVE'
          AND authority_checked_at IS NOT NULL
          AND authority_checked_at > now() - interval '30 days'"""),
        {"o": org})).scalar_one()
    cached = (await db.execute(text("""
        SELECT count(*) FROM public.trucking_carriers
        WHERE org_id = :o AND authority_source = 'FMCSA_CACHED'"""),
        {"o": org})).scalar_one()

    assert cached >= 1, "the fixture must contain a cached row to test against"
    assert live == 1, "only the genuinely-live carrier counts"


@pytest.mark.asyncio
async def test_a_stale_live_check_stops_counting(db, org):
    """A lookup that succeeded three months ago is not current authority.

    This is the same 30-day boundary `eligibility.check_carrier` refuses on.
    If the disclosure used a looser window than the control does, the board
    would say FMCSA is connected for carriers the system refuses to dispatch.
    """
    await db.execute(text("""
        UPDATE public.trucking_carriers
        SET authority_checked_at = now() - interval '31 days'
        WHERE org_id = :o AND authority_source = 'FMCSA_LIVE'"""), {"o": org})
    live = (await db.execute(text("""
        SELECT count(*) FROM public.trucking_carriers
        WHERE org_id = :o AND authority_source = 'FMCSA_LIVE'
          AND authority_checked_at > now() - interval '30 days'"""),
        {"o": org})).scalar_one()
    assert live == 0


def test_the_disclosure_reports_fmcsa_by_evidence():
    from app.api.routers.trucking import _unconnected_compliance_systems as U
    assert "FMCSA_LIVE" in U(fmcsa_evidenced=False)
    assert "FMCSA_LIVE" not in U(fmcsa_evidenced=True)
    # The two that genuinely are not wired up stay listed either way.
    for evidenced in (True, False):
        assert "ELD_HOS" in U(fmcsa_evidenced=evidenced)
        assert "DRUG_ALCOHOL_CONSORTIUM" in U(fmcsa_evidenced=evidenced)


# ===========================================================================
# One floor on the board, not two
# ===========================================================================

def test_the_margin_floor_is_defined_once():
    """The board carries a thin-margin TILE and a margin PANEL. A first version
    of the tile picked its own threshold, and the screen then read

        Loads at or under 8% margin: 1
        ...
        1 load below the 15% floor

    on the same page -- two numbers for one business rule, and no way for a
    buyer to tell which one the company actually runs on.
    """
    import re
    import pathlib
    router = (pathlib.Path(__file__).parent.parent / "app" / "api" / "routers"
              / "trucking.py").read_text(encoding="utf-8")

    assert "DD.MARGIN_FLOOR_PCT" in router, (
        "the margin panel no longer reads the shared floor")

    # No bare percentage literal sitting next to the word floor.
    for m in re.finditer(r'"floor_pct"\s*:\s*([^,\n]+)', router):
        value = m.group(1).strip()
        assert not re.fullmatch(r"[\d.]+", value), (
            f"floor_pct is hard-coded as {value}; it must come from "
            f"drilldown.MARGIN_FLOOR_PCT so the tile and the panel agree")


def test_the_thin_margin_drill_uses_the_same_floor():
    assert DD.THIN_MARGIN_PCT == DD.MARGIN_FLOOR_PCT
    assert f"{DD.MARGIN_FLOOR_PCT:g}" in DD.DRILLS["thin_margin"].label, (
        "the tile's label does not name the floor it filters on")


def test_an_already_expired_credential_is_not_called_expiring():
    """"Expiring within 30 days" and "expired three weeks ago" are different
    facts with different urgency: one is an appointment to book, the other is a
    driver who cannot legally take freight this morning. The predicate has no
    lower bound, so it has always returned both -- the label just did not say
    so, and on a compliance tile that distinction is the whole point.
    """
    spec = DD.DRILLS["expiring_credentials"]
    assert "expired" in spec.label.lower(), (
        f"the tile reads {spec.label!r}, which describes only half of what it "
        f"returns")
    assert "already refusing dispatch" in spec.action, (
        "the action text does not tell the operator that some of these rows "
        "are blocking dispatch right now")
    assert "already_expired" in spec.columns, (
        "the rows do not distinguish expired from expiring, so a reader has to "
        "compare dates by eye")


# ===========================================================================
# The board that consumes the drills
# ===========================================================================

class _Actor:
    """Minimal staff actor. The board is a staff surface (_require_ops)."""
    def __init__(self, org_id, role="owner"):
        self.org_id = org_id
        self.role = role
        self.user_id = None
        self.email = "ops@example.test"
        self.claims = {"email": "ops@example.test"}


@pytest.mark.asyncio
async def test_the_today_board_renders_with_every_section_populated(db, org):
    """NOTHING TESTED THE BOARD ITSELF. The drills each had reconciliation,
    ordering and org-filter coverage; the endpoint that assembles them into the
    screen a buyer looks at had none.

    So this line survived in it:

        {"driver": r["driver_code"], "driver_name": r["full_name"], ...}

    reading a column the drill has never selected, off a table that does not
    have one. It could not have worked. It never threw because the credentials
    drill had never returned a ROW in any environment anyone checked -- the
    comprehension ran zero times and the board looked healthy. The first
    expiring credential in the demo data turned the flagship trucking screen
    into a 500.

    The fixture deliberately seeds a credential inside the window, so this test
    only passes if the board survives a NON-EMPTY compliance section.
    """
    from app.api.routers import trucking as R

    board = await R.today(actor=_Actor(org), db=db)

    for section in ("operations", "money", "margin", "compliance"):
        assert section in board, f"the board has no {section} section"

    creds = board["compliance"]["expiring_credentials"]
    assert creds, (
        "the fixture seeds a credential expiring in 12 days and the board "
        "reported none — this test would pass vacuously, which is exactly how "
        "the crash it exists for went unnoticed")
    for c in creds:
        assert c["driver"], "a flagged credential with no driver to chase"
        assert c["credential"], "a flagged credential with no type"

    assert board["operations"], "no operations tiles"
    for tile in board["operations"]:
        assert tile.get("authority"), f"tile {tile.get('label')!r} has no authority label"
