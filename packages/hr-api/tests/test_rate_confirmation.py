"""The rate confirmation, and the three things it refuses.

`build_settlement` used to read `load.carrier_rate_cents` -- a number in a
field -- and write the derivation note "carrier rate {rate} from the rate
confirmation". There was no rate confirmation. That note is the most expensive
kind of wrong statement a system can make: it is checkable, and the person
checking is the one being paid.

Each refusal below has a positive control beside it, because a control that
never fires and a control that was removed are the same thing from the outside.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.trucking import billing as B
from app.trucking import rate_confirmation as RC

ACCEPTED_AT = datetime(2026, 8, 20, 14, 3, tzinfo=timezone.utc)

DETENTION_TERM = {"kind": "DETENTION", "rate_cents": 5_000, "unit": "HOUR",
                  "free_time_minutes": 120, "cap_cents": 30_000}


def ratecon(**kw):
    base = dict(state=RC.ACCEPTED, load_id="L1", carrier_id="C1",
                confirmation_number="RC-1001",
                linehaul_cents=350_000, fuel_surcharge_cents=43_000,
                agreed_total_cents=393_000,
                approved_accessorials=[DETENTION_TERM],
                accepted_by="Delta Line dispatch", accepted_at=ACCEPTED_AT)
    base.update(kw)
    return type("R", (), base)()


def load(**kw):
    base = dict(id="L1", fulfilment_mode="BROKERED", carrier_id="C1",
                carrier_rate_cents=393_000, status="BOOKED")
    base.update(kw)
    return type("L", (), base)()


def acc(kind="DETENTION", amount=15_000, state="APPROVED",
        direction="CARRIER_PAYABLE"):
    return type("A", (), {"accessorial_kind": kind, "amount_cents": amount,
                          "state": state, "direction": direction})()


CARRIER = type("C", (), {"name": "Delta Line Transport"})()


# ===========================================================================
# Terms
# ===========================================================================

def test_a_term_keeps_its_free_time_and_cap():
    """"Detention at $50/hour" and "detention at $50/hour after two hours
    free" are different agreements, and the second is the one the industry
    writes down."""
    t = RC.parse_terms([DETENTION_TERM])[0]
    assert t.kind == "DETENTION"
    assert t.free_time_minutes == 120
    assert t.cap_cents == 30_000
    assert t.unit == "HOUR"


def test_a_term_with_no_accessorial_named_is_refused():
    with pytest.raises(RC.RateConRefused) as e:
        RC.parse_terms([{"rate_cents": 100}])
    assert e.value.code == "TERM_WITHOUT_KIND"


def test_an_unknown_unit_is_refused():
    with pytest.raises(RC.RateConRefused) as e:
        RC.parse_terms([{"kind": "DETENTION", "rate_cents": 100,
                         "unit": "PER_FORTNIGHT"}])
    assert e.value.code == "UNKNOWN_ACCESSORIAL_UNIT"


def test_the_same_accessorial_agreed_twice_is_refused():
    """A document that says two things about one charge is not an agreement."""
    with pytest.raises(RC.RateConRefused) as e:
        RC.parse_terms([DETENTION_TERM,
                        {**DETENTION_TERM, "rate_cents": 9_000}])
    assert e.value.code == "DUPLICATE_ACCESSORIAL_TERM"


def test_a_negative_agreed_rate_is_refused():
    with pytest.raises(RC.RateConRefused) as e:
        RC.parse_terms([{"kind": "LUMPER", "rate_cents": -100}])
    assert e.value.code == "NEGATIVE_TERM_RATE"


# ===========================================================================
# The document
# ===========================================================================

def _doc():
    return RC.render_document(
        confirmation_number="RC-1001", carrier_name="Delta Line Transport",
        load_number="L-24822", origin="Pharr TX", destination="Detroit MI",
        linehaul_cents=350_000, fuel_surcharge_cents=43_000,
        terms=RC.parse_terms([DETENTION_TERM]),
        equipment="REEFER", commodity="Romaine")


def test_the_document_states_the_terms_a_carrier_would_argue_about():
    d = _doc()
    assert "RC-1001" in d
    assert "3,500.00" in d and "430.00" in d and "3,930.00" in d
    assert "after 120 minutes free" in d
    assert "capped at 300.00" in d
    assert "not pre-approved" in d


def test_an_unaltered_document_verifies():
    d = _doc()
    r = RC.verify_document(document=d, recorded_sha256=RC.document_hash(d))
    assert r.intact and r.code == "INTACT"


def test_an_altered_document_is_detected():
    """A settlement may cite this months later. "The terms on file today" and
    "the terms the carrier accepted" are not the same claim."""
    original = _doc()
    recorded = RC.document_hash(original)
    tampered = original.replace("3,500.00", "3,100.00")
    r = RC.verify_document(document=tampered, recorded_sha256=recorded)
    assert not r.intact and r.code == "DOCUMENT_ALTERED"
    assert "citing a different document" in r.detail


def test_a_confirmation_with_no_recorded_hash_cannot_be_verified():
    r = RC.verify_document(document=_doc(), recorded_sha256=None)
    assert not r.intact and r.code == "NO_RECORDED_HASH"


def test_changing_a_term_changes_the_hash():
    """Control on the two above: a hash that did not move with the terms would
    make the tamper test pass for the wrong reason."""
    a = RC.document_hash(_doc())
    b = RC.document_hash(RC.render_document(
        confirmation_number="RC-1001", carrier_name="Delta Line Transport",
        load_number="L-24822", origin="Pharr TX", destination="Detroit MI",
        linehaul_cents=350_000, fuel_surcharge_cents=43_000,
        terms=RC.parse_terms([{**DETENTION_TERM, "cap_cents": 90_000}]),
        equipment="REEFER", commodity="Romaine"))
    assert a != b


# ===========================================================================
# The state machine
# ===========================================================================

@pytest.mark.parametrize("frm,to", [
    (RC.DRAFT, RC.ISSUED), (RC.DRAFT, RC.VOID),
    (RC.ISSUED, RC.ACCEPTED), (RC.ISSUED, RC.DECLINED), (RC.ISSUED, RC.VOID),
    (RC.ACCEPTED, RC.SUPERSEDED), (RC.DECLINED, RC.VOID),
])
def test_a_legitimate_transition_is_allowed(frm, to):
    RC.validate_transition(frm, to)


@pytest.mark.parametrize("frm,to", [
    (RC.DRAFT, RC.ACCEPTED),        # accepting something never sent
    (RC.ACCEPTED, RC.ISSUED),       # re-issuing an accepted rate
    (RC.ACCEPTED, RC.DECLINED),     # un-accepting it
    (RC.SUPERSEDED, RC.ACCEPTED),   # reviving a superseded rate
    (RC.VOID, RC.ACCEPTED),
    (RC.DECLINED, RC.ACCEPTED),
])
def test_an_illegal_transition_is_refused(frm, to):
    with pytest.raises(RC.RateConRefused) as e:
        RC.validate_transition(frm, to)
    assert e.value.code == "ILLEGAL_TRANSITION"


def test_an_accepted_confirmation_is_amended_not_edited():
    RC.validate_amendment(original_state=RC.ACCEPTED,
                          reason="carrier renegotiated after a re-power")


def test_an_amendment_records_why():
    """A superseding document changes what an existing settlement cites."""
    with pytest.raises(RC.RateConRefused) as e:
        RC.validate_amendment(original_state=RC.ACCEPTED, reason="  ")
    assert e.value.code == "AMENDMENT_WITHOUT_REASON"


def test_only_an_accepted_confirmation_is_amendable():
    with pytest.raises(RC.RateConRefused) as e:
        RC.validate_amendment(original_state=RC.ISSUED, reason="oops")
    assert e.value.code == "NOTHING_TO_AMEND"


# ===========================================================================
# Refusal 1: dispatch
# ===========================================================================

def test_a_brokered_load_does_not_dispatch_without_a_confirmation():
    d = RC.check_dispatch(load=load(), ratecon=None)
    assert not d.allowed
    assert "NO_RATE_CONFIRMATION" in d.refusal_codes
    assert "settlement time" in " ".join(d.reasons)


@pytest.mark.parametrize("state", [RC.DRAFT, RC.ISSUED, RC.DECLINED,
                                   RC.SUPERSEDED, RC.VOID])
def test_only_an_accepted_confirmation_authorises_a_tender(state):
    d = RC.check_dispatch(load=load(), ratecon=ratecon(state=state))
    assert not d.allowed
    assert "RATE_CONFIRMATION_NOT_ACCEPTED" in d.refusal_codes


def test_an_accepted_confirmation_authorises_the_tender():
    """Positive control. A gate that refused every state would pass the tests
    above and make brokerage impossible."""
    d = RC.check_dispatch(load=load(), ratecon=ratecon())
    assert d.allowed and d.refusal_codes == []


def test_a_confirmation_for_another_load_does_not_authorise_this_one():
    d = RC.check_dispatch(load=load(), ratecon=ratecon(load_id="L2"))
    assert not d.allowed
    assert "RATE_CONFIRMATION_WRONG_LOAD" in d.refusal_codes


def test_a_confirmation_agreed_with_another_carrier_is_refused():
    """Two carriers, one rate. The one hauling never agreed to it."""
    d = RC.check_dispatch(load=load(), ratecon=ratecon(carrier_id="C9"))
    assert not d.allowed
    assert "RATE_CONFIRMATION_WRONG_CARRIER" in d.refusal_codes


def test_an_own_fleet_load_needs_no_confirmation():
    """There is no counterparty to agree a rate with. `check_driver` is that
    flow's gate, and requiring a confirmation here would block every asset
    load in the system."""
    d = RC.check_dispatch(load=load(fulfilment_mode="OWN_FLEET"), ratecon=None)
    assert d.allowed


# ===========================================================================
# Refusal 2: the payable
# ===========================================================================

def test_the_payable_is_what_the_confirmation_authorises():
    c = RC.check_payable(ratecon=ratecon(), proposed_linehaul_cents=393_000,
                         accessorials=[acc(amount=15_000)])
    assert c.ok
    assert c.authorised_linehaul_cents == 393_000
    assert c.authorised_accessorial_cents == 15_000
    assert c.authorised_total_cents == 408_000


def test_paying_more_linehaul_than_was_agreed_is_refused():
    c = RC.check_payable(ratecon=ratecon(), proposed_linehaul_cents=450_000)
    assert not c.ok
    assert "LINEHAUL_EXCEEDS_CONFIRMATION" in c.refusal_codes
    assert "unreconciled payable" in " ".join(c.notes)


def test_paying_less_than_was_agreed_is_flagged_but_not_refused():
    """Underpaying is a dispute the carrier will raise. Refusing it would stop
    a legitimate deduction; saying nothing would let it become a phone call
    nobody was ready for."""
    c = RC.check_payable(ratecon=ratecon(), proposed_linehaul_cents=350_000)
    assert c.ok
    assert "owed the agreed figure" in " ".join(c.notes)


def test_an_accessorial_over_its_cap_is_refused():
    c = RC.check_payable(ratecon=ratecon(), proposed_linehaul_cents=393_000,
                         accessorials=[acc(amount=45_000)])
    assert not c.ok
    assert "ACCESSORIAL_OVER_CAP" in c.refusal_codes
    assert "the number both parties signed" in c.accessorials[0].detail


def test_an_accessorial_at_exactly_its_cap_is_payable():
    """Boundary. A cap that refused its own value would look like the test
    above passing."""
    c = RC.check_payable(ratecon=ratecon(), proposed_linehaul_cents=393_000,
                         accessorials=[acc(amount=30_000)])
    assert c.ok and c.authorised_accessorial_cents == 30_000


def test_an_unapproved_accessorial_is_not_paid():
    """EVENT is not CHARGE. Detention happening and detention being payable
    are different facts."""
    c = RC.check_payable(ratecon=ratecon(), proposed_linehaul_cents=393_000,
                         accessorials=[acc(amount=15_000, state="PROPOSED")])
    assert c.ok
    assert c.authorised_accessorial_cents == 0
    assert c.accessorials[0].code == "ACCESSORIAL_NOT_APPROVED"


def test_an_approved_accessorial_outside_the_confirmation_is_paid_but_flagged():
    """A human approved it, which is the separate control. It is still not
    something the carrier can point at the confirmation to justify, and the
    ops person settling it should know which of the two it is."""
    c = RC.check_payable(ratecon=ratecon(), proposed_linehaul_cents=393_000,
                         accessorials=[acc(kind="LUMPER", amount=9_000)])
    assert c.ok
    assert c.authorised_accessorial_cents == 9_000
    v = c.accessorials[0]
    assert v.payable and v.code == "APPROVED_OUTSIDE_CONFIRMATION"


def test_an_unaccepted_confirmation_authorises_no_payable():
    c = RC.check_payable(ratecon=ratecon(state=RC.ISSUED),
                         proposed_linehaul_cents=393_000)
    assert not c.ok
    assert "RATE_CONFIRMATION_NOT_ACCEPTED" in c.refusal_codes


# ===========================================================================
# The note the carrier reads
# ===========================================================================

def test_the_settlement_names_the_document_it_came_from():
    """The note used to cite a document that did not exist."""
    s = B.build_settlement(load=load(), carrier=CARRIER, ratecon=ratecon(),
                           accessorials=[acc(amount=15_000)])
    assert "RC-1001" in s.derivation_note
    assert "Delta Line dispatch" in s.derivation_note
    assert s.total_cents == 408_000

    # A CARRIER READS THIS. It used to carry an ISO-8601 timestamp and raw
    # cents under a settlement someone was questioning.
    assert "20 August 2026 at 14:03 UTC" in s.derivation_note
    assert "T14:03" not in s.derivation_note
    assert "$3,930.00" in s.derivation_note
    assert "393000" not in s.derivation_note


def test_a_separately_approved_accessorial_says_so_in_the_note():
    s = B.build_settlement(load=load(), carrier=CARRIER, ratecon=ratecon(),
                           accessorials=[acc(kind="LUMPER", amount=9_000)])
    assert "NOT covered by the confirmation" in s.derivation_note


def test_billing_refuses_a_brokered_settlement_with_no_confirmation():
    with pytest.raises(B.BillingRefused) as e:
        B.build_settlement(load=load(), carrier=CARRIER)
    assert e.value.code == "NO_RATE_CONFIRMATION"


def test_billing_refuses_an_over_cap_accessorial():
    with pytest.raises(B.BillingRefused) as e:
        B.build_settlement(load=load(), carrier=CARRIER, ratecon=ratecon(),
                           accessorials=[acc(amount=45_000)])
    assert e.value.code == "ACCESSORIAL_OVER_CAP"


def test_a_dispatcher_recorded_rate_above_the_confirmation_is_caught():
    """The reason the load's own figure is what gets proposed rather than the
    confirmation's: a dispatcher may have typed a different number, and the
    whole point of reconciling is to notice."""
    with pytest.raises(B.BillingRefused) as e:
        B.build_settlement(load=load(carrier_rate_cents=500_000),
                           carrier=CARRIER, ratecon=ratecon())
    assert e.value.code == "LINEHAUL_EXCEEDS_CONFIRMATION"


def test_the_rate_confirmation_does_not_replace_the_authority_check():
    """A signed confirmation from a revoked carrier is a signed document from
    a carrier who may not haul. The two controls are independent."""
    from datetime import date, timedelta
    from app.trucking import eligibility as E

    revoked = type("C", (), {
        "is_approved": True, "authority_status": "REVOKED",
        "authority_source": "FMCSA_LIVE",
        "authority_checked_at": datetime.now(timezone.utc),
        "insurance_expires_on": date.today() + timedelta(days=90)})()
    assert RC.check_dispatch(load=load(), ratecon=ratecon()).allowed
    assert not E.check_carrier(carrier=revoked, as_of=date.today()).eligible
