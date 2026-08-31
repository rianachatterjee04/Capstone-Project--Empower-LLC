"""A partially persisted recording must never look complete.

A RecordingAsset row exists the moment bytes land. Before this, nothing
distinguished a recording that captured the whole interview from one where the
candidate's laptop slept through part three, or where the tab closed while the
last part was uploading. Both look like "there is a recording", and a recruiter
opening either sees a player.

That is the failure this product cannot afford: an assessment defended by a
recording that is missing the answer it rests on.

The pure cases live here because they are a function of what is held versus
what the client says it produced -- no database needed to state that holding
three parts is not holding all the parts.
"""
from __future__ import annotations

import pytest

from app.interview import media as MED


def part(n, byte_size=1024, duration_ms=24_000, offset=None):
    return type("P", (), {
        "part_number": n, "byte_size": byte_size,
        "duration_ms": duration_ms,
        "timeline_offset_ms": (n - 1) * 24_000 if offset is None else offset,
    })()


# ===========================================================================
# The states
# ===========================================================================

def test_nothing_captured_is_its_own_state():
    """Distinct from INCOMPLETE. A candidate who declined the camera has no
    recording; that is a choice, not a fault, and the debrief says the
    evidence still carries timecodes from the answer boundaries."""
    v = MED.assess_completeness([], None)
    assert v.state == MED.NOT_CAPTURED
    assert not v.is_sealed
    assert "nothing to seek into" in v.detail


def test_parts_without_a_seal_are_never_complete():
    """The load-bearing case. A part that never reached the server leaves no
    trace on the server, so absent an explicit count the honest answer is
    CAPTURING -- not "we have three, that must be all of them"."""
    v = MED.assess_completeness([part(1), part(2), part(3)], None)
    assert v.state == MED.CAPTURING
    assert not v.is_sealed
    assert "not the same as holding all of them" in v.detail


def test_a_matching_count_seals():
    v = MED.assess_completeness([part(1), part(2), part(3)], 3)
    assert v.state == MED.SEALED
    assert v.is_sealed
    assert v.missing_parts == []


def test_parts_arriving_out_of_order_still_seal():
    """Uploads race. Order of arrival says nothing about completeness."""
    v = MED.assess_completeness([part(3), part(1), part(2)], 3)
    assert v.state == MED.SEALED


# ===========================================================================
# Every way it is not whole
# ===========================================================================

def test_a_missing_middle_part_is_named():
    v = MED.assess_completeness([part(1), part(3)], 3)
    assert v.state == MED.INCOMPLETE
    assert v.missing_parts == [2]
    assert "missing part(s) [2]" in v.detail


def test_a_missing_last_part_is_caught():
    """The one that matters most: the last part holds the answer to the final
    question, and losing it is the failure mode of a tab closed too early."""
    v = MED.assess_completeness([part(1), part(2)], 3)
    assert v.state == MED.INCOMPLETE
    assert v.missing_parts == [3]


def test_a_zero_byte_part_is_not_a_part():
    """A MediaRecorder that never started produces an empty blob. A row
    pointing at nothing is worse than a missing row, because it counts."""
    v = MED.assess_completeness([part(1), part(2, byte_size=0)], 2)
    assert v.state == MED.INCOMPLETE
    assert v.zero_byte_parts == [2]


def test_a_duplicate_part_number_is_caught():
    v = MED.assess_completeness([part(1), part(2), part(2)], 2)
    assert v.state == MED.INCOMPLETE
    assert v.duplicate_parts == [2]


def test_more_parts_than_the_client_reported_is_suspicious():
    """Not obviously benign: either the seal was wrong or something wrote a
    part that did not come from this recorder. Both need a human."""
    v = MED.assess_completeness([part(1), part(2), part(3)], 2)
    assert v.state == MED.INCOMPLETE
    assert "beyond the 2" in v.detail


def test_sealing_with_zero_when_parts_exist_is_incomplete():
    v = MED.assess_completeness([part(1)], 0)
    assert v.state == MED.INCOMPLETE


def test_sealing_with_zero_and_no_parts_is_not_captured():
    """A candidate who declined the camera seals with nothing, and that is a
    complete and honest outcome rather than a fault."""
    v = MED.assess_completeness([], 0)
    assert v.state == MED.NOT_CAPTURED


# ===========================================================================
# The detail is usable, not a shrug
# ===========================================================================

def test_an_incomplete_recording_always_says_what_is_wrong():
    """"INCOMPLETE" with no explanation is a shrug in a column. The database
    constraint requires a detail; this is the code side of the same rule."""
    for parts, expected in [([part(1)], 2), ([part(1), part(1)], 1),
                            ([part(1, byte_size=0)], 1), ([part(1)], 0)]:
        v = MED.assess_completeness(parts, expected)
        assert v.state == MED.INCOMPLETE
        assert len(v.detail) >= 12, v


def test_the_detail_explains_the_consequence_not_just_the_fault():
    """A recruiter reading this has to know what it means for them."""
    v = MED.assess_completeness([part(1), part(3)], 3)
    assert "cannot be played" in v.detail
    assert "seeking to the wrong moment" in v.detail


def test_every_state_is_one_the_schema_accepts():
    """The column has a CHECK constraint; a state this code can produce and
    the database refuses would fail at the worst moment."""
    seen = {
        MED.assess_completeness([], None).state,
        MED.assess_completeness([part(1)], None).state,
        MED.assess_completeness([part(1)], 1).state,
        MED.assess_completeness([part(1)], 2).state,
    }
    assert seen <= set(MED.RECORDING_STATES)
    assert seen == {MED.NOT_CAPTURED, MED.CAPTURING, MED.SEALED,
                    MED.INCOMPLETE}
