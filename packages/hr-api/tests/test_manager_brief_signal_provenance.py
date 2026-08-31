"""
A manager's action feed counts only their own people.

WHY THIS IS A TEST
/app/manager is titled "Who needs my attention today" and describes its rows as
"every row is a decision you can make from here". The first row was:

    AC · RETAIN · Avery Chen · high attrition risk · URGENT
    Compa-ratio below 0.85 ...

Avery Chen is in _synthetic_features() — the same invented person as the risk
engine, the exec brief and the notification feed. Marked urgent, at the top of
a list a manager is asked to work through today, about somebody who is not on
their team and does not exist.

The headline counted her too: "2 signals on your team this week", when one of
the two was hers.
"""
from __future__ import annotations

import asyncio
import inspect

from app.services import manager_brief_service as M


def test_attrition_signals_are_marked_as_samples():
    src = inspect.getsource(M)
    body = src.split('"""', 2)[-1]
    # every BriefSignal built from a synthetic prediction carries the flag
    assert body.count("is_sample=True") >= 2, (
        "the attrition signals no longer declare that they come from the "
        "sample cohort")


def test_a_sample_signal_is_never_urgent():
    src = inspect.getsource(M)
    body = src.split('"""', 2)[-1]
    # the high-risk branch must not pair urgent with the sample flag
    for chunk in body.split("BriefSignal(")[1:]:
        head = chunk[:400]
        if "is_sample=True" in head:
            assert 'severity="urgent"' not in head, (
                "a sample signal is marked urgent — it asks a manager to act "
                "today on somebody who is not on their team")


def test_the_signal_dataclass_defaults_to_real():
    """CONTROL. A signal raised from the manager's own data must not be marked."""
    sig = M.BriefSignal(kind="review", severity="this_week", title="t",
                        detail="d", cta_label="Open", cta_href="/app")
    assert sig.is_sample is False


def test_the_headline_counts_only_real_signals():
    src = inspect.getsource(M)
    body = src.split('"""', 2)[-1]
    assert "real = [s for s in signals if not s.is_sample]" in body, (
        "the headline is counting sample signals as this manager's own again")
    assert "len(signals)} signal" not in body, (
        "the headline still reports the total signal count, which includes "
        "the sample rows")
