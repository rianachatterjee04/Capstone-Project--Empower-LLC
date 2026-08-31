"""The container repair, against a real MediaRecorder file.

WHY THE FIXTURE IS A REAL RECORDING
`tests/fixtures/mediarecorder-live.webm` came out of an actual `MediaRecorder`
in a browser. A hand-built EBML fixture would be exactly the file this code was
written to handle, which proves nothing: the whole defect is that a real
recorder writes a LIVE container -- unknown-size Segment, no SeekHead, no Cues
and no Duration -- and every one of those has to be tolerated.

WHAT WAS BROKEN, MEASURED IN A BROWSER
    before   video.duration === Infinity, seekable.end(0) === undefined
    after    video.duration === 5,        seekable.end(0) === 5
             and seeks to 3.0s, 1.0s and 4.2s all landed exactly

That is the recruiter debrief's entire interaction -- "click any assessment and
the recording seeks to the moment the candidate said it". It did not work, and
nothing said so: the RecordingAsset row existed, the bytes were real WebM with
the right magic, and a <video> element accepted `currentTime = 90` without
complaint. It simply never went there.
"""
from __future__ import annotations

import pathlib
import struct

import pytest

from app.interview import media as MED

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mediarecorder-live.webm"

ID_DURATION = b"\x44\x89"
ID_SEGMENT = b"\x18\x53\x80\x67"
UNKNOWN_SIZE = b"\x01\xff\xff\xff\xff\xff\xff\xff"


@pytest.fixture
def live() -> bytes:
    return FIXTURE.read_bytes()


# ===========================================================================
# The fixture is the thing we think it is
# ===========================================================================

def test_the_fixture_is_a_live_webm_with_no_duration(live):
    """The control on every test below. If the fixture ever gained a Duration,
    the repair tests would pass while testing nothing."""
    assert live[:4] == b"\x1a\x45\xdf\xa3", "not an EBML container"
    assert ID_DURATION not in live, "the fixture already has a Duration"
    assert ID_SEGMENT + UNKNOWN_SIZE in live, (
        "the fixture does not have the unknown-size Segment a live recorder "
        "writes, so it is not the case this code exists for")
    assert b"\x1c\x53\xbb\x6b" not in live, "the fixture unexpectedly has Cues"


# ===========================================================================
# The repair
# ===========================================================================

def test_a_duration_is_written(live):
    r = MED.ensure_webm_duration(live, 2500)
    assert r.changed
    assert r.duration_is_authoritative
    assert ID_DURATION in r.data
    assert len(r.data) > len(live)


def test_the_written_duration_is_the_one_that_was_measured(live):
    r = MED.ensure_webm_duration(live, 2500)
    idx = r.data.find(ID_DURATION)
    assert idx > 0
    assert r.data[idx + 2] == 0x88, "Duration should be an 8-byte float"
    value = struct.unpack(">d", r.data[idx + 3:idx + 11])[0]
    # Default TimecodeScale is 1ms, so the stored value is in milliseconds.
    assert abs(value - 2500) < 0.001


def test_the_segment_size_is_left_alone(live):
    """The first version rewrote this too, and it was actively harmful.

    A declared Segment size is a claim about how many bytes follow, and
    nothing here can verify that claim for a live container -- the truncation
    test below caught the repair writing a size describing bytes that were
    never received, producing a file that looks complete and is not.

    Measured in a browser, the Duration element ALONE is sufficient: with the
    Segment left unknown, duration is 2.5, seekable.end(0) is 2.5, and seeks
    land exactly. So the repair writes the fact it was told and never one it
    would be inferring.
    """
    r = MED.ensure_webm_duration(live, 2500)
    assert r.changed
    assert ID_SEGMENT + UNKNOWN_SIZE in r.data


def test_only_the_info_element_grows(live):
    """The size difference is exactly one Duration element: the 2-byte id, the
    1-byte length, an 8-byte float, and the widened Info length."""
    r = MED.ensure_webm_duration(live, 2500)
    assert 11 <= len(r.data) - len(live) <= 18


def test_the_media_bytes_after_the_header_are_untouched(live):
    """The repair edits the Info element and the Segment length. Every cluster
    -- the actual video -- has to come through byte for byte."""
    r = MED.ensure_webm_duration(live, 2500)
    cluster = live.find(b"\x1f\x43\xb6\x75")
    assert cluster > 0, "the fixture has no Cluster to compare"
    assert live[cluster:] in r.data


def test_the_repair_is_idempotent(live):
    once = MED.ensure_webm_duration(live, 2500)
    twice = MED.ensure_webm_duration(once.data, 2500)
    assert not twice.changed
    assert twice.duration_is_authoritative
    assert twice.data == once.data


# ===========================================================================
# It refuses rather than guesses
# ===========================================================================

@pytest.mark.parametrize("duration", [None, 0, -1])
def test_no_measured_duration_means_no_change(live, duration):
    """The browser is the only thing that knows how long the part was. Making
    one up would be worse than a missing scrubber."""
    r = MED.ensure_webm_duration(live, duration)
    assert not r.changed
    assert r.data == live
    assert not r.duration_is_authoritative


def test_a_non_webm_file_is_returned_untouched():
    data = b"%PDF-1.4\nthis is not a recording"
    r = MED.ensure_webm_duration(data, 2500)
    assert not r.changed and r.data == data


@pytest.mark.parametrize("cut", [4, 12, 40])
def test_a_truncated_file_is_returned_untouched(live, cut):
    """A recording corrupted by a hopeful muxer is a lost interview. Anything
    it cannot parse comes back exactly as it arrived."""
    truncated = live[:cut]
    r = MED.ensure_webm_duration(truncated, 2500)
    assert r.data == truncated
    assert not r.changed


@pytest.mark.parametrize("cut", [100, 200, 500, 1000, 1900])
def test_a_truncated_upload_never_gains_a_claim_it_cannot_back(live, cut):
    """A file cut after a complete Info header still parses, and is
    indistinguishable from a short valid recording. What matters is that
    nothing is written that DESCRIBES the missing bytes -- the media that is
    present survives byte for byte, and the Segment still says its size is
    unknown, which is the truth.
    """
    truncated = live[:cut]
    r = MED.ensure_webm_duration(truncated, 2500)
    assert ID_SEGMENT + UNKNOWN_SIZE in r.data, (
        "a truncated upload must not be given a size it cannot back")

    # The MEDIA survives byte for byte. The Duration is inserted inside the
    # Info element, so a window spanning that boundary is legitimately split;
    # what must not change is everything from the first Cluster onwards.
    cluster = truncated.find(b"\x1f\x43\xb6\x75")
    if cluster > 0:
        assert truncated[cluster:] in r.data

    # Nothing beyond one Duration element and a widened Info length.
    assert 0 <= len(r.data) - len(truncated) <= 18


def test_garbage_after_the_header_is_returned_untouched(live):
    mangled = live[:20] + bytes([0x00] * 200) + live[220:]
    r = MED.ensure_webm_duration(mangled, 2500)
    assert r.data == mangled or r.changed is False


# ===========================================================================
# The varint codec the repair depends on
# ===========================================================================

@pytest.mark.parametrize("value", [0, 1, 126, 127, 128, 16_382, 100_000,
                                   2 ** 28, 2 ** 40])
def test_a_length_survives_a_round_trip(value):
    encoded = MED._encode_vint(value)
    decoded, _, width = MED._read_vint(encoded, 0, keep_marker=False)
    assert decoded == value
    assert width == len(encoded)


def test_a_fixed_width_length_uses_that_width():
    """Rewriting the Segment size in place depends on being able to encode a
    known value at the original width -- otherwise every offset after it
    moves."""
    encoded = MED._encode_vint(1916, width=8)
    assert len(encoded) == 8
    decoded, _, _ = MED._read_vint(encoded, 0, keep_marker=False)
    assert decoded == 1916


# ===========================================================================
# Range serving — the other half of a seek
# ===========================================================================

@pytest.mark.parametrize("header,size,expected", [
    ("bytes=0-99", 1000, (0, 99)),
    ("bytes=100-", 1000, (100, 999)),
    ("bytes=-50", 1000, (950, 999)),
    ("bytes=999-1500", 1000, (999, 999)),      # clamped to the end
    ("bytes=0-99, 200-299", 1000, (0, 99)),    # first range only
])
def test_a_range_header_is_parsed(header, size, expected):
    from app.api.routers.interview_v2 import _parse_range
    assert _parse_range(header, size) == expected


@pytest.mark.parametrize("header,size", [
    ("bytes=1000-", 1000),      # starts past the end
    ("bytes=-0", 1000),         # a suffix of nothing
    ("bytes=500-499", 1000),    # backwards
])
def test_an_impossible_range_is_unsatisfiable(header, size):
    from app.api.routers.interview_v2 import _parse_range
    assert _parse_range(header, size) == "unsatisfiable"


@pytest.mark.parametrize("header", [None, "", "items=0-1", "bytes=abc",
                                    "bytes=", "bytes=0"])
def test_a_header_that_is_not_a_byte_range_is_ignored(header):
    """Ignored, not refused: RFC 9110 says an unparseable Range is served as
    a normal 200."""
    from app.api.routers.interview_v2 import _parse_range
    assert _parse_range(header, 1000) is None


def test_the_playback_payload_does_not_ship_a_server_path():
    """`storage_ref` was in the recruiter's playback response, so every
    browser received an absolute server filesystem path: the media root, the
    organisation's UUID and the interview's UUID as a directory tree.

    Read as source rather than exercised, because the shape of the payload is
    the thing being asserted and a running database is not needed to see it.
    """
    src = (pathlib.Path(__file__).parent.parent / "app" / "api" / "routers"
           / "interview_v2.py").read_text()
    start = src.index('"recordings": [{')
    block = src[start:start + 600]
    assert '"storage_ref"' not in block, (
        "the playback payload is shipping a server filesystem path again")
    assert '"href"' in block, (
        "the client needs a URL it can fetch in place of the path")
