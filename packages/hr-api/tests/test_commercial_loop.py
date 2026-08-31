"""The commercial loop's three refusals, each with its positive control.

The loop existed only inside a demo script: it printed a convincing story and
persisted nothing. These test the rules that make the persisted version worth
having, and every one of them has a case beside it proving the rule still
allows the thing it is supposed to allow.
"""
from __future__ import annotations

import pytest

from app.commercial import loop as L


def source(*, name="a list", kind="SELF_SOURCED", permits=True,
           note="collected at our own booth with consent"):
    return type("S", (), {"name": name, "kind": kind,
                          "permits_direct_marketing": permits,
                          "licence_note": note})()


def action(cents, authority="MODELED", kind="OUTBOUND_EMAIL"):
    return type("A", (), {"spend_cents": cents, "spend_authority": authority,
                          "action_kind": kind})()


def invoice(total, paid):
    return type("I", (), {"total_cents": total, "paid_cents": paid})()


def cost(cents, authority="MODELED", kind="CARRIER_PAY"):
    return type("C", (), {"amount_cents": cents, "authority": authority,
                          "cost_type": kind})()


# ===========================================================================
# 1. The rights gate
# ===========================================================================

def test_a_public_register_does_not_licence_outreach():
    """FMCSA publishes a register of carriers. Being able to read it is not
    permission to run a campaign against the businesses in it, and the fact
    that the data is public is exactly what makes the mistake easy."""
    d = L.check_marketing_allowed(
        source=source(name="FMCSA carrier register", kind="PUBLIC_REGISTER",
                      permits=False, note=""))
    assert not d.allowed
    assert d.refusal_code == "SOURCE_DOES_NOT_LICENCE_OUTREACH"
    assert "not permission to run a campaign" in d.reason


def test_the_refusal_says_what_the_source_IS_good_for():
    """A refusal that only says no teaches people to route around it."""
    d = L.check_marketing_allowed(
        source=source(kind="PUBLIC_REGISTER", permits=False, note=""))
    assert "CARRIER network" in d.alternative


def test_a_self_sourced_prospect_may_be_marketed_to():
    """Positive control. A gate that refused everything would pass the two
    tests above and make the product useless."""
    assert L.check_marketing_allowed(source=source()).allowed


def test_the_licence_is_the_test_not_the_kind():
    """A public register that DID carry an outreach licence would pass. The
    rule is about the licence, not about a category we disapprove of."""
    d = L.check_marketing_allowed(
        source=source(kind="PUBLIC_REGISTER", permits=True,
                      note="licensed for outreach under our data agreement"))
    assert d.allowed


def test_an_unattributed_source_is_refused():
    d = L.check_marketing_allowed(
        source=source(name="a spreadsheet", kind="UNATTRIBUTED",
                      permits=False, note=""))
    assert not d.allowed
    assert "no licence" in d.reason


# ===========================================================================
# 2. The human gate
# ===========================================================================

def test_an_observed_prospect_cannot_skip_being_saved():
    with pytest.raises(L.LoopRefused) as e:
        L.check_stage_change(current=L.OBSERVED, target=L.CONTACTED,
                             saved_by="someone")
    assert e.value.code == "ILLEGAL_STAGE_CHANGE"


def test_nothing_advances_without_a_human():
    """"The system found 400 leads" means "the system copied 400 rows"."""
    with pytest.raises(L.LoopRefused) as e:
        L.check_stage_change(current=L.OBSERVED, target=L.SAVED, saved_by="  ")
    assert e.value.code == "NO_HUMAN_SAVED_THIS"


def test_a_human_can_save_it():
    L.check_stage_change(current=L.OBSERVED, target=L.SAVED,
                         saved_by="dana.ruiz@example.test")


@pytest.mark.parametrize("frm,to", [
    (L.SAVED, L.CONTACTED), (L.CONTACTED, L.QUALIFIED),
    (L.QUALIFIED, L.CUSTOMER), (L.SAVED, L.DISQUALIFIED),
    (L.CUSTOMER, L.DISQUALIFIED),
])
def test_the_normal_path_is_allowed(frm, to):
    L.check_stage_change(current=frm, target=to, saved_by="dana")


@pytest.mark.parametrize("frm,to", [
    (L.CUSTOMER, L.QUALIFIED),      # un-winning a deal
    (L.DISQUALIFIED, L.SAVED),      # reviving without a new record
    (L.QUALIFIED, L.CONTACTED),
    (L.SAVED, L.CUSTOMER),          # skipping qualification
])
def test_a_stage_cannot_go_backwards_or_skip(frm, to):
    with pytest.raises(L.LoopRefused) as e:
        L.check_stage_change(current=frm, target=to, saved_by="dana")
    assert e.value.code == "ILLEGAL_STAGE_CHANGE"


def test_spending_against_an_unlicensed_source_is_refused_before_the_spend():
    """A spend row against a prospect we may not contact is a RECORD of having
    done it. The refusal has to come first."""
    with pytest.raises(L.LoopRefused) as e:
        L.check_action(source=source(kind="PUBLIC_REGISTER", permits=False,
                                     note=""),
                       prospect_stage=L.SAVED)
    assert e.value.code == "SOURCE_DOES_NOT_LICENCE_OUTREACH"


def test_spending_against_a_merely_observed_prospect_is_refused():
    with pytest.raises(L.LoopRefused) as e:
        L.check_action(source=source(), prospect_stage=L.OBSERVED)
    assert e.value.code == "NO_HUMAN_SAVED_THIS"


def test_spending_against_a_saved_prospect_from_a_licensed_source_is_fine():
    L.check_action(source=source(), prospect_stage=L.SAVED)


# ===========================================================================
# 3. Attribution
# ===========================================================================

def test_the_grade_is_the_weakest_input_never_the_average():
    """One paid invoice does not make a page of estimates measured."""
    a = L.attribute(
        actions=[action(180_000, "FINANCIAL_ACTUAL")],
        invoices=[invoice(838_336, 838_336)],
        costs=[cost(500_000, "FINANCIAL_ACTUAL"),
               cost(8_900, "MODELED", "INSURANCE_ALLOCATION")])
    assert a.grade == "MODELED"
    assert a.limiting_input == "INSURANCE_ALLOCATION cost"


def test_realised_requires_cash():
    """"Did it work" is a question about money that moved."""
    a = L.attribute(actions=[action(180_000, "FINANCIAL_ACTUAL")],
                    invoices=[invoice(838_336, 0)],
                    costs=[cost(500_000, "FINANCIAL_ACTUAL")])
    assert a.basis == "MODELED"
    assert any("No cash has been collected" in c for c in a.caveats)


def test_cash_makes_it_realised():
    a = L.attribute(actions=[action(180_000, "FINANCIAL_ACTUAL")],
                    invoices=[invoice(838_336, 838_336)],
                    costs=[cost(500_000, "FINANCIAL_ACTUAL")])
    assert a.basis == "REALISED"


def test_partial_collection_is_called_a_receivable():
    a = L.attribute(actions=[action(180_000, "FINANCIAL_ACTUAL")],
                    invoices=[invoice(436_336, 436_336), invoice(402_000, 0)],
                    costs=[cost(500_000, "FINANCIAL_ACTUAL")])
    assert a.basis == "REALISED"
    assert any("a receivable, not a result" in c for c in a.caveats)


def test_grade_and_basis_are_independent():
    """Strong inputs with no cash: FINANCIAL_ACTUAL grade, MODELED basis.
    Conflating them is how "we have receipts" becomes "we got paid"."""
    a = L.attribute(actions=[action(180_000, "FINANCIAL_ACTUAL")],
                    invoices=[invoice(400_000, 0)],
                    costs=[cost(100_000, "FINANCIAL_ACTUAL")])
    assert a.grade == "FINANCIAL_ACTUAL"
    assert a.basis == "MODELED"


def test_spend_with_no_invoice_is_too_early_not_a_failure():
    a = L.attribute(actions=[action(180_000, "FINANCIAL_ACTUAL")],
                    invoices=[], costs=[])
    assert a.verdict == "TOO_EARLY"
    assert "not a failure" in a.note


def test_no_action_means_there_is_nothing_to_attribute():
    a = L.attribute(actions=[], invoices=[invoice(400_000, 400_000)],
                    costs=[cost(100_000)])
    assert a.verdict == "INSUFFICIENT_EVIDENCE"


def test_losing_money_says_so_without_editorialising():
    a = L.attribute(actions=[action(900_000, "FINANCIAL_ACTUAL")],
                    invoices=[invoice(400_000, 400_000)],
                    costs=[cost(350_000, "FINANCIAL_ACTUAL")])
    assert a.verdict == "DID_NOT_WORK"
    assert "not a judgement about the channel" in a.note


def test_it_never_claims_causation():
    a = L.attribute(actions=[action(180_000, "FINANCIAL_ACTUAL")],
                    invoices=[invoice(838_336, 838_336)],
                    costs=[cost(500_000, "FINANCIAL_ACTUAL")])
    joined = " ".join(a.caveats)
    assert "not a controlled experiment" in joined
    assert "not proof of what caused it" in joined


def test_margin_per_dollar_is_none_rather_than_infinite():
    a = L.attribute(actions=[action(0)], invoices=[invoice(400_000, 400_000)],
                    costs=[cost(100_000)])
    assert a.margin_per_dollar is None
