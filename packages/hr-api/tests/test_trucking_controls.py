"""The trucking controls, each tested by making it fail.

From the specification: expired driver credential, wrong carrier, duplicate
invoice, wrong rate, missing POD, duplicate payment and wrong tenant must all
fail appropriately. Each block below plants the defect and asserts the refusal,
and each has a positive control beside it -- a refusal that fires on everything
is not a control, it is an outage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pytest

from app.trucking import billing as B
from app.trucking import eligibility as E

TODAY = date(2026, 8, 29)
NEXT_WEEK = TODAY + timedelta(days=7)


# --- lightweight stand-ins, so the control logic is testable without a DB ---

@dataclass
class Cred:
    credential_type: str
    expires_on: Optional[date] = None
    verification_state: str = "DOCUMENT_ON_FILE"


@dataclass
class Driver:
    status: str = "ACTIVE"
    worker_classification: str = "W2_EMPLOYEE"
    pay_model: str = "PER_MILE"
    pay_rate_cents: int = 65


@dataclass
class Carrier:
    is_approved: bool = True
    authority_status: str = "ACTIVE"
    authority_source: str = "FMCSA_LIVE"
    authority_checked_at: Optional[datetime] = None
    insurance_expires_on: Optional[date] = None


@dataclass
class Load:
    customer_rate_cents: int = 250_000
    carrier_rate_cents: int = 190_000
    fulfilment_mode: str = "OWN_FLEET"
    miles: int = 1_200
    status: str = "DELIVERED"
    id: str = "load-1"
    carrier_id: str = "carrier-1"


@dataclass
class RateCon:
    """An accepted rate confirmation, agreeing the load's carrier rate.

    A brokered settlement is now derived from this document rather than from a
    field on the load, so every brokered case in this file has to supply one.
    """
    state: str = "ACCEPTED"
    load_id: str = "load-1"
    carrier_id: str = "carrier-1"
    confirmation_number: str = "RC-1001"
    linehaul_cents: int = 190_000
    fuel_surcharge_cents: int = 0
    agreed_total_cents: int = 190_000
    approved_accessorials: tuple = ()
    accepted_by: str = "carrier dispatch"
    accepted_at: Optional[datetime] = None


@dataclass
class Pod:
    evidence_strength: str = "SIGNED_DOCUMENT"


@dataclass
class Acc:
    id: str = "acc-1"
    accessorial_type: str = "DETENTION"
    direction: str = "CUSTOMER_BILLABLE"
    state: str = "APPROVED"
    amount_cents: int = 15_000
    approved_by: str = "dispatcher@example.test"


@dataclass
class Cost:
    cost_type: str
    amount_cents: int
    authority: str = "MODELED"


def _full_credentials(**over) -> list:
    base = {"CDL_A": Cred("CDL_A", TODAY + timedelta(days=400)),
            "MEDICAL_CARD": Cred("MEDICAL_CARD", TODAY + timedelta(days=200))}
    base.update(over)
    return list(base.values())


# ===========================================================================
# 1. Driver credentials
# ===========================================================================

def test_a_fully_credentialled_driver_is_eligible():
    """Positive control. Everything below is meaningless without it."""
    d = E.check_driver(driver=Driver(), credentials=_full_credentials(),
                       equipment="DRY_VAN", as_of=TODAY, delivery_by=NEXT_WEEK)
    assert d.eligible, d.refusal_codes


def test_an_expired_medical_card_refuses_the_assignment():
    d = E.check_driver(
        driver=Driver(),
        credentials=_full_credentials(
            MEDICAL_CARD=Cred("MEDICAL_CARD", TODAY - timedelta(days=1))),
        equipment="DRY_VAN", as_of=TODAY, delivery_by=NEXT_WEEK)
    assert not d.eligible
    assert "CREDENTIAL_EXPIRED" in d.refusal_codes


def test_a_credential_expiring_mid_load_refuses_the_assignment():
    """The one that is easy to miss.

    Valid at dispatch, expired at delivery: the driver is unlicensed on the
    road, and a check that only asks "valid today" produces a violation that
    looks compliant in the log.
    """
    d = E.check_driver(
        driver=Driver(),
        credentials=_full_credentials(
            CDL_A=Cred("CDL_A", TODAY + timedelta(days=2))),
        equipment="DRY_VAN", as_of=TODAY, delivery_by=NEXT_WEEK)
    assert not d.eligible
    assert "CREDENTIAL_EXPIRES_IN_TRANSIT" in d.refusal_codes


def test_a_self_reported_credential_is_not_enough_to_dispatch():
    d = E.check_driver(
        driver=Driver(),
        credentials=_full_credentials(
            CDL_A=Cred("CDL_A", TODAY + timedelta(days=400), "SELF_REPORTED")),
        equipment="DRY_VAN", as_of=TODAY)
    assert not d.eligible
    assert "CREDENTIAL_NOT_VERIFIED" in d.refusal_codes


def test_hazmat_freight_requires_the_hazmat_endorsement():
    without = E.check_driver(driver=Driver(), credentials=_full_credentials(),
                             equipment="DRY_VAN", hazmat=True, as_of=TODAY)
    assert not without.eligible
    assert "CREDENTIAL_MISSING" in without.refusal_codes

    with_it = E.check_driver(
        driver=Driver(),
        credentials=_full_credentials(
            HAZMAT=Cred("HAZMAT", TODAY + timedelta(days=300))),
        equipment="DRY_VAN", hazmat=True, as_of=TODAY)
    assert with_it.eligible, with_it.refusal_codes


def test_unknown_equipment_does_not_disable_the_check():
    """A typo in a load record must not silently switch the control off."""
    d = E.check_driver(driver=Driver(), credentials=[],
                       equipment="ZZ_TYPO", as_of=TODAY)
    assert not d.eligible
    assert E.required_credentials(equipment="ZZ_TYPO"), (
        "an unrecognised equipment type returned no requirements, which means "
        "a typo disables credential checking entirely")


def test_an_inactive_driver_is_refused_even_with_perfect_credentials():
    d = E.check_driver(driver=Driver(status="TERMINATED"),
                       credentials=_full_credentials(),
                       equipment="DRY_VAN", as_of=TODAY)
    assert not d.eligible
    assert "DRIVER_NOT_ACTIVE" in d.refusal_codes


def test_the_write_path_raises_rather_than_returning_false():
    """A boolean is easy not to check, and the failure mode of not checking is
    an unlicensed driver on a load."""
    with pytest.raises(E.AssignmentRefused):
        E.assert_driver_eligible(
            driver=Driver(), credentials=[], equipment="DRY_VAN", as_of=TODAY)


def test_hours_of_service_is_reported_as_not_connected():
    """Claiming an ELD integration that does not exist is how a carrier gets
    shut down. The gap must be visible, not assumed away."""
    d = E.check_driver(driver=Driver(), credentials=_full_credentials(),
                       equipment="DRY_VAN", as_of=TODAY)
    assert "ELD_HOS" in d.not_connected


# ===========================================================================
# 2. Carrier — the wrong-carrier control
# ===========================================================================

def _good_carrier() -> Carrier:
    return Carrier(
        authority_checked_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        insurance_expires_on=TODAY + timedelta(days=180))


def test_an_approved_current_carrier_is_eligible():
    assert E.check_carrier(carrier=_good_carrier(), as_of=TODAY).eligible


def test_an_unapproved_carrier_is_refused():
    c = _good_carrier()
    c.is_approved = False
    d = E.check_carrier(carrier=c, as_of=TODAY)
    assert not d.eligible
    assert "CARRIER_NOT_APPROVED" in d.refusal_codes


def test_stale_authority_is_refused_even_when_it_says_active():
    """The subtle one. A cached ACTIVE from eight months ago is not evidence
    of current authority -- revocation is exactly what happens in between."""
    c = _good_carrier()
    c.authority_source = "FMCSA_CACHED"
    c.authority_checked_at = datetime(2026, 1, 5, tzinfo=timezone.utc)
    d = E.check_carrier(carrier=c, as_of=TODAY)
    assert not d.eligible
    assert "CARRIER_AUTHORITY_STALE" in d.refusal_codes


def test_unknown_authority_is_refused_like_a_revoked_one():
    c = _good_carrier()
    c.authority_status = "UNKNOWN"
    d = E.check_carrier(carrier=c, as_of=TODAY)
    assert not d.eligible
    assert "CARRIER_AUTHORITY_NOT_ACTIVE" in d.refusal_codes


def test_expired_carrier_insurance_is_refused():
    c = _good_carrier()
    c.insurance_expires_on = TODAY - timedelta(days=3)
    d = E.check_carrier(carrier=c, as_of=TODAY)
    assert not d.eligible
    assert "CARRIER_INSURANCE_EXPIRED" in d.refusal_codes


# ===========================================================================
# 3. Billing — POD, rate, and unapproved accessorials
# ===========================================================================

def test_a_load_with_a_signed_pod_invoices():
    """Positive control."""
    inv = B.build_invoice(load=Load(), pod=Pod(), accessorials=[Acc()])
    assert inv.linehaul_cents == 250_000
    assert inv.accessorial_cents == 15_000
    assert inv.total_cents == 265_000


def test_no_pod_means_no_invoice():
    with pytest.raises(B.BillingRefused) as exc:
        B.build_invoice(load=Load(), pod=None, accessorials=[])
    assert exc.value.code == "POD_MISSING"


def test_a_driver_asserted_delivery_is_not_a_pod():
    """The distinction the schema exists to preserve: this is the same claim
    as the status field, recorded in a different table."""
    with pytest.raises(B.BillingRefused) as exc:
        B.build_invoice(load=Load(), pod=Pod("ASSERTED_BY_DRIVER"),
                        accessorials=[])
    assert exc.value.code == "POD_TOO_WEAK"


def test_a_load_with_no_contract_rate_cannot_be_invoiced():
    with pytest.raises(B.BillingRefused) as exc:
        B.build_invoice(load=Load(customer_rate_cents=0), pod=Pod(),
                        accessorials=[])
    assert exc.value.code == "NO_CONTRACT_RATE"


def test_an_unapproved_accessorial_never_reaches_the_total():
    proposed = Acc(state="PROPOSED", approved_by=None)
    inv = B.build_invoice(load=Load(), pod=Pod(), accessorials=[proposed])
    assert inv.accessorial_cents == 0
    assert inv.total_cents == 250_000
    assert "not approved" in inv.derivation_note


def test_the_invoice_says_how_it_was_derived():
    """A total nobody can reconstruct is a typed number with an audit trail
    bolted on.

    The note is printed under an invoice a shipper is disputing, so the
    amounts are written the way money is written. It used to say "linehaul
    250000", which nobody outside this repository reads as $2,500.
    """
    inv = B.build_invoice(load=Load(), pod=Pod(), accessorials=[Acc()])
    assert "$2,500.00" in inv.derivation_note
    assert "$150.00" in inv.derivation_note
    assert "dispatcher@example.test" in inv.derivation_note
    assert "signed document" in inv.derivation_note
    # And no raw cents anywhere in it.
    assert "250000" not in inv.derivation_note
    assert "15000" not in inv.derivation_note


# ===========================================================================
# 4. Settlement — classification and the wrong-rate control
# ===========================================================================

def test_a_w2_driver_routes_to_payroll_and_is_never_paid_directly():
    s = B.build_settlement(load=Load(), driver=Driver(), accessorials=[])
    assert s.payee_kind == "DRIVER_W2"
    assert s.routes_to_payroll is True
    assert "PAYROLL INPUT" in s.derivation_note
    assert s.total_cents == 65 * 1_200


def test_a_contractor_driver_settles_directly():
    """Positive control for the branch above: the two must not collapse."""
    s = B.build_settlement(
        load=Load(), driver=Driver(worker_classification="OWNER_OPERATOR"),
        accessorials=[])
    assert s.payee_kind == "DRIVER_CONTRACTOR"
    assert s.routes_to_payroll is False


def test_a_brokered_load_with_no_rate_confirmation_is_refused():
    """Paying an amount nobody agreed to.

    This used to check for a zero `carrier_rate_cents`, which is the weaker
    version of the same worry: a field being empty. The stronger refusal is
    that there is no DOCUMENT, and it fires first because a payable with no
    confirmation behind it cannot be defended at any amount.
    """
    with pytest.raises(B.BillingRefused) as exc:
        B.build_settlement(load=Load(fulfilment_mode="BROKERED",
                                     carrier_rate_cents=0),
                           carrier=_good_carrier())
    assert exc.value.code == "NO_RATE_CONFIRMATION"


def test_a_rate_confirmation_agreeing_nothing_is_refused():
    with pytest.raises(B.BillingRefused) as exc:
        B.build_settlement(
            load=Load(fulfilment_mode="BROKERED", carrier_rate_cents=0),
            carrier=_good_carrier(),
            ratecon=RateCon(linehaul_cents=0, agreed_total_cents=0))
    assert exc.value.code == "NO_CARRIER_RATE"


def test_a_brokered_load_with_no_carrier_is_refused():
    with pytest.raises(B.BillingRefused) as exc:
        B.build_settlement(load=Load(fulfilment_mode="BROKERED"), carrier=None)
    assert exc.value.code == "NO_CARRIER"


def test_a_customer_billable_accessorial_does_not_leak_into_carrier_pay():
    """Detention billed to the customer at one rate and owed to the carrier at
    another are two rows. Paying the customer's rate to the carrier is the
    error this separation prevents."""
    customer_side = Acc(direction="CUSTOMER_BILLABLE", amount_cents=15_000)
    s = B.build_settlement(load=Load(fulfilment_mode="BROKERED"),
                           carrier=_good_carrier(),
                           ratecon=RateCon(),
                           accessorials=[customer_side])
    assert s.accessorial_cents == 0
    assert s.total_cents == 190_000


# ===========================================================================
# 5. Margin
# ===========================================================================

def test_margin_is_revenue_less_direct_costs():
    inv = B.build_invoice(load=Load(), pod=Pod(), accessorials=[Acc()])
    m = B.load_margin(invoice=inv, costs=[
        Cost("CARRIER_PAY", 190_000, "FINANCIAL_ACTUAL"),
        Cost("FUEL", 42_000, "FINANCIAL_ACTUAL"),
        Cost("TOLLS", 3_500, "FINANCIAL_ACTUAL"),
    ])
    assert m.revenue_cents == 265_000
    assert m.direct_cost_cents == 235_500
    assert m.contribution_margin_cents == 29_500
    assert m.cost_authority == "FINANCIAL_ACTUAL"


def test_one_modelled_cost_downgrades_the_whole_margin():
    """The minimum, never the average. Otherwise a single receipt makes a page
    of estimates look measured."""
    inv = B.build_invoice(load=Load(), pod=Pod(), accessorials=[])
    m = B.load_margin(invoice=inv, costs=[
        Cost("CARRIER_PAY", 190_000, "FINANCIAL_ACTUAL"),
        Cost("INSURANCE_ALLOCATION", 5_000, "MODELED"),
    ])
    assert m.cost_authority == "MODELED"
    assert m.limiting_cost == "INSURANCE_ALLOCATION"


def test_a_load_with_no_costs_reports_revenue_not_margin():
    inv = B.build_invoice(load=Load(), pod=Pod(), accessorials=[])
    m = B.load_margin(invoice=inv, costs=[])
    assert "revenue, not margin" in m.note


def test_margin_never_calls_itself_profit():
    """'Margin' next to a big number is read as profit by everyone who is not
    an accountant, so the note has to say what it excludes."""
    inv = B.build_invoice(load=Load(), pod=Pod(), accessorials=[])
    m = B.load_margin(invoice=inv, costs=[Cost("FUEL", 1_000, "MODELED")])
    assert "Not profit" in m.note
    assert "overhead" in m.note


def test_a_negative_margin_is_reported_as_negative():
    """A load can lose money and the system must say so plainly."""
    inv = B.build_invoice(load=Load(customer_rate_cents=100_000), pod=Pod(),
                          accessorials=[])
    m = B.load_margin(invoice=inv, costs=[
        Cost("CARRIER_PAY", 190_000, "FINANCIAL_ACTUAL")])
    assert m.contribution_margin_cents == -90_000
    assert m.margin_pct is not None and m.margin_pct < 0


# ===========================================================================
# 6. Modeled margin is not realised margin
# ===========================================================================
# The overclaim this closes: reporting one number and calling it margin.
# A contribution margin from an invoice and some cost rows is what we EXPECT
# to have made. Realised margin counts only money that actually moved.

def _pair(cash, costs):
    inv = B.InvoiceDraft(linehaul_cents=412_500, accessorial_cents=23_836,
                         total_cents=436_336, derivation_note="test")
    return B.margin_pair(invoice=inv, costs=costs, cash_collected_cents=cash)


def test_an_unpaid_load_has_no_realised_margin():
    """A delivered, invoiced, unpaid load has spent money and earned a
    receivable. Calling that margin is how a cash crisis hides behind a
    healthy-looking P&L."""
    mp = _pair(0, [Cost("FUEL", 47_600, "FINANCIAL_ACTUAL")])
    assert mp.realised_state == "AWAITING_CASH"
    assert mp.realised_margin_cents is None
    assert mp.modeled.contribution_margin_cents > 0, (
        "the modelled figure should still exist; it is the expectation")


def test_cash_with_no_actual_costs_is_not_realised_either():
    """Otherwise realised margin would be revenue minus estimates, which is
    the modelled figure wearing a stronger label."""
    mp = _pair(436_336, [Cost("FUEL", 47_600, "MODELED")])
    assert mp.realised_state == "AWAITING_COSTS"
    assert mp.realised_margin_cents is None


def test_realised_margin_counts_only_money_that_moved():
    mp = _pair(436_336, [
        Cost("DRIVER_LABOR", 79_608, "FINANCIAL_ACTUAL"),
        Cost("FUEL", 47_600, "FINANCIAL_ACTUAL"),
        Cost("INSURANCE_ALLOCATION", 8_900, "MODELED"),
    ])
    assert mp.realised_state == "REALISED"
    # Collected minus the two real costs. The modelled allocation is excluded.
    assert mp.realised_margin_cents == 436_336 - 127_208
    assert mp.actual_cost_cents == 127_208
    assert mp.modeled_cost_cents == 8_900


def test_the_variance_is_explainable():
    """A variance a CFO cannot account for is worse than no variance.

    Here it is exactly the modelled cost excluded from the realised figure,
    and the note says so.
    """
    mp = _pair(436_336, [
        Cost("DRIVER_LABOR", 79_608, "FINANCIAL_ACTUAL"),
        Cost("FUEL", 47_600, "FINANCIAL_ACTUAL"),
        Cost("INSURANCE_ALLOCATION", 8_900, "MODELED"),
    ])
    assert mp.variance_cents == mp.modeled_cost_cents == 8_900
    assert "EXCLUDED" in mp.note


def test_a_fully_actual_load_has_no_variance():
    """Positive control: when every cost is real, the two agree."""
    mp = _pair(436_336, [
        Cost("DRIVER_LABOR", 79_608, "FINANCIAL_ACTUAL"),
        Cost("FUEL", 47_600, "FINANCIAL_ACTUAL"),
    ])
    assert mp.variance_cents == 0
    assert "every cost on this load is a real payment" in mp.note.lower()


def test_a_load_with_neither_cash_nor_actuals_realises_nothing():
    mp = _pair(0, [Cost("FUEL", 47_600, "MODELED")])
    assert mp.realised_state == "NONE"
    assert "expectation, not a result" in mp.note


# ===========================================================================
# Controls on these controls
# ===========================================================================
#
# Thirty-seven tests assert that eligibility refuses the right things. Not one
# of them establishes that they would NOTICE if the rule stopped refusing --
# and a compliance check is exactly the kind of code that gets "simplified"
# during a refactor by someone who does not know why a branch is there.
#
# Each control below plants a specific, plausible defect and requires the
# suite to go red. A planted defect that leaves the suite green is a test
# suite that would have shipped the defect.

def _expect_failures(*tests):
    """Run the given test functions; return which ones failed."""
    failed = []
    for fn in tests:
        try:
            fn()
        except AssertionError:
            failed.append(fn.__name__)
    return failed


def test_mutation_control_an_expired_credential_that_stops_refusing_is_caught(
        monkeypatch):
    """The plainest defect: `expires < as_of` becomes `expires <= as_of - 1y`,
    the kind of thing a "fix the off-by-one" commit produces."""
    import datetime as _dt

    real = E.check_driver

    def permissive(*, driver, credentials, equipment, as_of=None,
                   delivery_by=None, **kw):
        # Pretend today is a year ago: an expired card looks current.
        shifted = (as_of or _dt.date.today()) - _dt.timedelta(days=365)
        return real(driver=driver, credentials=credentials,
                    equipment=equipment, as_of=shifted,
                    delivery_by=None, **kw)

    monkeypatch.setattr(E, "check_driver", permissive)
    failed = _expect_failures(
        test_an_expired_medical_card_refuses_the_assignment,
        test_a_credential_expiring_mid_load_refuses_the_assignment)
    assert len(failed) == 2, (
        f"a permissive expiry rule was caught by only {failed}; the other "
        f"refusal test would have passed over a driver dispatched on an "
        f"expired credential")


def test_mutation_control_dropping_the_mid_load_check_is_caught(monkeypatch):
    """The subtle one. Valid at dispatch and expired at delivery is a driver
    unlicensed on the road, and a check that only asks "valid today" produces a
    violation that looks compliant in the log. Removing `delivery_by` is a
    one-argument change."""
    real = E.check_driver

    def today_only(*, driver, credentials, equipment, as_of=None,
                   delivery_by=None, **kw):
        return real(driver=driver, credentials=credentials,
                    equipment=equipment, as_of=as_of, delivery_by=None, **kw)

    monkeypatch.setattr(E, "check_driver", today_only)
    failed = _expect_failures(test_a_credential_expiring_mid_load_refuses_the_assignment)
    assert failed, (
        "the mid-load expiry check was removed and every test still passed")


def test_mutation_control_the_positive_control_still_holds_under_no_mutation():
    """And the counterpart: with nothing mutated, the refusal tests must PASS.
    Otherwise the two controls above would be satisfied by a suite that fails
    all the time."""
    assert not _expect_failures(
        test_a_fully_credentialled_driver_is_eligible,
        test_an_expired_medical_card_refuses_the_assignment,
        test_a_credential_expiring_mid_load_refuses_the_assignment)
