"""
fintra_safety tests — prove the deterministic safety primitives without any network.

Run:
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=packages/shared-py \
        <api-venv>/bin/python -m pytest packages/shared-py/tests/test_fintra_safety.py -q
"""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fintra_safety import (
    screen_input,
    annotate_output,
    guard_completion,
    has_disclaimer,
    uncertainty_note,
    not_verified_evidence_note,
    SAFE_DISCLAIMER_MARKER,
    InputVerdict,
    GuardedResult,
)


# ── Crisis screening: TRUE positives ─────────────────────────────────────────
def test_crisis_kill_myself_detected_with_safe_response():
    v = screen_input("I don't know what to do anymore, I want to kill myself")
    assert isinstance(v, InputVerdict)
    assert v.crisis is True
    assert v.category == "self_harm"
    assert v.safe_response
    # The safe response must point at 988 and be explicit Fintra is not a crisis service.
    assert "988" in v.safe_response
    assert "crisis service" in v.safe_response.lower()


def test_crisis_various_intent_phrasings_detected():
    for text in (
        "i just want to end my life",
        "honestly there's no reason to live",
        "I've been having suicidal thoughts",
        "i feel like i should just hurt myself",
        "i'd be better off dead",
        "i don't want to be alive",
    ):
        assert screen_input(text).crisis is True, text


# ── Crisis screening: FALSE positives that must NOT fire ─────────────────────
def test_benign_kill_the_process_not_flagged():
    # The literal word "kill" in an ops/finance context is not a crisis.
    v = screen_input("Please kill the process that is stuck and then recompute the tax total")
    assert v.crisis is False
    assert v.safe_response is None
    assert v.category is None


def test_benign_finance_idioms_not_flagged():
    for text in (
        "Taking on that much debt would be financial suicide",
        "That pricing move is career suicide",
        "This tax deadline is killing me",
        "Ugh, just kill me now — the numbers still don't reconcile",
        "I want to end my life insurance policy and switch carriers",
        "We don't want to live in that office building anymore",
        "What is the ICD-10 code for suicidal ideation on this claim?",
    ):
        assert screen_input(text).crisis is False, text


def test_plain_tax_question_not_flagged():
    assert screen_input("How do I record a tax payment in the ledger?").crisis is False


# ── Output annotation: adds the right disclaimer once, idempotent ────────────
def test_annotate_adds_tax_disclaimer_once_and_is_idempotent():
    base = "You should set aside money for your quarterly taxes."
    once = annotate_output(base)
    assert once != base
    assert "not professional tax advice" in once
    assert has_disclaimer(once)
    assert SAFE_DISCLAIMER_MARKER in once
    # Idempotent: a second pass changes nothing and does not double-append.
    twice = annotate_output(once)
    assert twice == once
    assert once.count("not professional tax advice") == 1


def test_annotate_adds_legal_disclaimer():
    out = annotate_output("You may need to review the lawsuit with an attorney first.")
    assert "not legal advice" in out
    assert has_disclaimer(out)


def test_annotate_adds_financial_disclaimer_when_advice_like():
    out = annotate_output(
        "Here's some financial advice: I recommend building a 3-month emergency fund."
    )
    assert "not personalized financial advice" in out


def test_annotate_explicit_domains_override_detection():
    out = annotate_output("The current balance is $1,234.", domains=["investment"])
    assert "not investment advice" in out
    assert has_disclaimer(out)


def test_annotate_plain_text_unchanged():
    base = "The invoice total is $500.00 and it is due next Friday."
    assert annotate_output(base) == base
    assert not has_disclaimer(base)


def test_annotate_multiple_domains_stable_order():
    # tax comes before legal in display order.
    out = annotate_output(
        "You should file your taxes and also review the lawsuit with an attorney.",
    )
    assert "not professional tax advice" in out
    assert "not legal advice" in out
    assert out.index("tax advice") < out.index("legal advice")


# ── guard_completion: crisis replaces, benign annotates ──────────────────────
def test_guard_completion_replaces_on_crisis():
    r = guard_completion("i want to kill myself", "Here is your Q3 tax summary.")
    assert isinstance(r, GuardedResult)
    assert r.crisis is True
    assert r.replaced is True
    assert "988" in r.text
    assert "tax summary" not in r.text  # original completion was replaced


def test_guard_completion_annotates_when_benign():
    r = guard_completion(
        "kill the stuck job then help me",
        "You should file your estimated taxes this quarter.",
    )
    assert r.crisis is False
    assert r.replaced is False
    assert "not professional tax advice" in r.text


def test_guard_completion_handles_none_input():
    # Defensive: must not raise on None / empty.
    r = guard_completion(None, None)
    assert r.crisis is False
    assert isinstance(r.text, str)


# ── helper notes ─────────────────────────────────────────────────────────────
def test_helper_notes_are_nonempty_strings():
    assert isinstance(uncertainty_note(), str) and uncertainty_note()
    assert isinstance(not_verified_evidence_note(), str) and not_verified_evidence_note()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
