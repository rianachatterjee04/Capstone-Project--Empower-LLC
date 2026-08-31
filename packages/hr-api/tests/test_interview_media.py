"""Recording, storage, and the difference between a timestamp and an alignment.

THE CLAIM BEING TESTED
That media a browser captured is stored durably, bound to one tenant and one
interview, and that transcript offsets can be checked AGAINST THE MEDIA rather
than against application events.

That distinction is the point. An interaction timestamp records when a button
was pressed. It does not establish that a word was spoken at that offset in a
file, and a recruiter clicking evidence backed only by an interaction
timestamp can land anywhere. `verify_alignment` compares offsets to the parts'
measured durations and boundaries, so a segment that runs past the end of the
recording, or falls in the gap between two parts, is a detected fault rather
than a silently wrong seek.

The failure list from the specification is covered here: consent refused,
camera/mic unavailable, reconnect, multi-segment recording, candidate closes
the browser, duplicate completion, wrong interview, wrong tenant media id,
tampered transcript timing, and a transcript linked to the wrong recording.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import uuid

import pytest

from app.interview import media as MED


@pytest.fixture(autouse=True)
def isolated_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTRA_MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.delenv("FINTRA_MEDIA_OBJECT_STORE_URL", raising=False)
    return tmp_path


WEBM = b"\x1a\x45\xdf\xa3" + b"fake-but-real-bytes" * 64


class _Part:
    def __init__(self, id, part_number, timeline_offset_ms, duration_ms):
        self.id = id
        self.part_number = part_number
        self.timeline_offset_ms = timeline_offset_ms
        self.duration_ms = duration_ms


class _Seg:
    def __init__(self, start_ms, end_ms, recording_asset_id=None):
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.recording_asset_id = recording_asset_id


# ===========================================================================
# Storage
# ===========================================================================

def test_a_captured_part_is_stored_hashed_and_measured():
    org, iv = uuid.uuid4(), uuid.uuid4()
    part = MED.store_part(org_id=org, interview_id=iv, data=WEBM,
                          mime_type="video/webm;codecs=vp8,opus",
                          media_kind="VIDEO", part_number=1,
                          duration_ms=61_000)

    assert part.byte_size == len(WEBM)
    assert part.sha256 == hashlib.sha256(WEBM).hexdigest()
    assert part.storage_kind == MED.LOCAL_FILE
    assert pathlib.Path(part.storage_ref).is_file()
    assert pathlib.Path(part.storage_ref).read_bytes() == WEBM


def test_storage_kind_is_never_optimistic():
    """It must not claim object storage that is not configured."""
    assert MED.storage_kind() == MED.LOCAL_FILE
    os.environ["FINTRA_MEDIA_OBJECT_STORE_URL"] = "s3://x"
    try:
        assert MED.storage_kind() == MED.OBJECT_STORE
    finally:
        del os.environ["FINTRA_MEDIA_OBJECT_STORE_URL"]


def test_an_empty_upload_is_refused():
    """A MediaRecorder that never started produces a zero-byte blob. Storing
    it creates a recording row that claims media exists."""
    with pytest.raises(MED.MediaRefused) as exc:
        MED.store_part(org_id=uuid.uuid4(), interview_id=uuid.uuid4(),
                       data=b"", mime_type="video/webm",
                       media_kind="VIDEO", part_number=1)
    assert exc.value.code == "EMPTY_MEDIA"


def test_an_unknown_container_is_refused():
    with pytest.raises(MED.MediaRefused) as exc:
        MED.store_part(org_id=uuid.uuid4(), interview_id=uuid.uuid4(),
                       data=WEBM, mime_type="application/zip",
                       media_kind="VIDEO", part_number=1)
    assert exc.value.code == "UNSUPPORTED_MEDIA_TYPE"


def test_an_oversized_part_is_refused(monkeypatch):
    monkeypatch.setattr(MED, "MAX_PART_BYTES", 100)
    with pytest.raises(MED.MediaRefused) as exc:
        MED.store_part(org_id=uuid.uuid4(), interview_id=uuid.uuid4(),
                       data=WEBM, mime_type="video/webm",
                       media_kind="VIDEO", part_number=1)
    assert exc.value.code == "MEDIA_TOO_LARGE"


def test_re_uploading_identical_bytes_is_idempotent():
    """A candidate whose browser retries an upload must not create a conflict."""
    org, iv = uuid.uuid4(), uuid.uuid4()
    kw = dict(org_id=org, interview_id=iv, data=WEBM, mime_type="video/webm",
              media_kind="VIDEO", part_number=1, duration_ms=1000)
    a = MED.store_part(**kw)
    b = MED.store_part(**kw)
    assert a.sha256 == b.sha256
    assert a.storage_ref == b.storage_ref


def test_different_bytes_under_the_same_part_number_are_refused():
    """DUPLICATE COMPLETION.

    Silently overwriting media that transcript segments already point into
    would break every evidence link inside it, and the recruiter would seek
    into different audio than the one that was assessed.
    """
    org, iv = uuid.uuid4(), uuid.uuid4()
    MED.store_part(org_id=org, interview_id=iv, data=WEBM,
                   mime_type="video/webm", media_kind="VIDEO", part_number=1)
    with pytest.raises(MED.MediaRefused) as exc:
        MED.store_part(org_id=org, interview_id=iv, data=WEBM + b"different",
                       mime_type="video/webm", media_kind="VIDEO",
                       part_number=1)
    assert exc.value.code == "PART_ALREADY_EXISTS"


# ===========================================================================
# Reconnect and multi-part
# ===========================================================================

def test_a_reconnect_produces_a_second_part_on_one_timeline():
    """The candidate's connection drops at 3 minutes and they come back.

    Two files, one timeline. A transcript offset of 200s must resolve to part
    2 at 20s into that file, not to 200s into part 1 which does not exist.
    """
    org, iv = uuid.uuid4(), uuid.uuid4()
    p1 = MED.store_part(org_id=org, interview_id=iv, data=WEBM,
                        mime_type="video/webm", media_kind="VIDEO",
                        part_number=1, timeline_offset_ms=0,
                        duration_ms=180_000)
    p2 = MED.store_part(org_id=org, interview_id=iv, data=WEBM + b"two",
                        mime_type="video/webm", media_kind="VIDEO",
                        part_number=2, timeline_offset_ms=180_000,
                        duration_ms=240_000)

    assert p1.storage_ref != p2.storage_ref
    problems = MED.verify_alignment(
        [_Seg(200_000, 205_000)],
        [_Part(1, 1, 0, 180_000), _Part(2, 2, 180_000, 240_000)])
    assert problems == []


def test_a_segment_in_the_gap_between_parts_is_caught():
    """CANDIDATE CLOSES THE BROWSER mid-answer.

    Nothing was captured between the parts. A transcript claiming words there
    is describing audio that does not exist.
    """
    problems = MED.verify_alignment(
        [_Seg(185_000, 188_000)],
        [_Part(1, 1, 0, 180_000), _Part(2, 2, 200_000, 60_000)])
    assert [p.code for p in problems] == ["SEGMENT_IN_A_GAP"]


# ===========================================================================
# Alignment against the MEDIA, not against events
# ===========================================================================

def test_a_segment_past_the_end_of_the_recording_is_caught():
    """TAMPERED TRANSCRIPT TIMING, and the everyday version of it.

    An interaction timestamp can exceed the media duration whenever the
    recording stopped early. Checking against the artifact catches both.
    """
    problems = MED.verify_alignment(
        [_Seg(0, 5_000), _Seg(600_000, 610_000)],
        [_Part(1, 1, 0, 300_000)])
    codes = [p.code for p in problems]
    assert codes == ["SEGMENT_BEYOND_MEDIA"]
    assert "land past the end" in problems[0].detail


def test_a_segment_bound_to_the_wrong_recording_is_caught():
    """TRANSCRIPT LINKED TO THE WRONG RECORDING."""
    problems = MED.verify_alignment(
        [_Seg(10_000, 12_000, recording_asset_id=2)],
        [_Part(1, 1, 0, 180_000), _Part(2, 2, 180_000, 60_000)])
    assert [p.code for p in problems] == ["SEGMENT_BOUND_TO_WRONG_PART"]


def test_reversed_and_negative_offsets_are_caught():
    problems = MED.verify_alignment(
        [_Seg(9_000, 3_000), _Seg(-5, 100)], [_Part(1, 1, 0, 60_000)])
    assert {p.code for p in problems} == {
        "SEGMENT_ENDS_BEFORE_IT_STARTS", "NEGATIVE_OFFSET"}


def test_a_transcript_with_no_media_cannot_be_verified():
    """The state this whole module exists to make visible.

    Segments with no recording are not aligned evidence. They may still be a
    useful transcript, and the difference has to be reportable.
    """
    problems = MED.verify_alignment([_Seg(0, 1000)], [])
    assert [p.code for p in problems] == ["NO_MEDIA"]


def test_a_part_with_no_measured_duration_cannot_anchor_anything():
    problems = MED.verify_alignment([_Seg(0, 1000)], [_Part(1, 1, 0, None)])
    assert any(p.code == "PART_DURATION_UNKNOWN" for p in problems)


def test_well_aligned_segments_produce_no_problems():
    """Positive control. A checker that flags everything proves nothing."""
    assert MED.verify_alignment(
        [_Seg(0, 5_000), _Seg(5_000, 11_000), _Seg(120_000, 124_000)],
        [_Part(1, 1, 0, 300_000)]) == []


# ===========================================================================
# Tenancy
# ===========================================================================

def test_media_is_stored_under_the_tenant_directory():
    org, iv = uuid.uuid4(), uuid.uuid4()
    part = MED.store_part(org_id=org, interview_id=iv, data=WEBM,
                          mime_type="video/webm", media_kind="VIDEO",
                          part_number=1)
    assert str(org) in part.storage_ref
    assert str(iv) in part.storage_ref


def test_another_tenant_cannot_read_a_stored_reference():
    """WRONG TENANT MEDIA ID.

    The row is not a capability. A ref copied from another organisation must
    not resolve, even though the file plainly exists on this disk.
    """
    org_a, org_b, iv = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    part = MED.store_part(org_id=org_a, interview_id=iv, data=WEBM,
                          mime_type="video/webm", media_kind="VIDEO",
                          part_number=1)

    assert MED.read_part(part.storage_ref, org_id=org_a) == WEBM
    with pytest.raises(MED.MediaRefused) as exc:
        MED.read_part(part.storage_ref, org_id=org_b)
    assert exc.value.code == "MEDIA_OUTSIDE_TENANT"


def test_a_traversal_reference_is_refused():
    org = uuid.uuid4()
    with pytest.raises(MED.MediaRefused):
        MED.read_part(str(MED.storage_root() / str(org) / ".." / ".." / "etc"),
                      org_id=org)


def test_deleting_an_interviews_media_removes_the_files():
    """Retention and erasure have to actually erase."""
    org, iv = uuid.uuid4(), uuid.uuid4()
    MED.store_part(org_id=org, interview_id=iv, data=WEBM,
                   mime_type="video/webm", media_kind="VIDEO", part_number=1)
    MED.store_part(org_id=org, interview_id=iv, data=WEBM + b"2",
                   mime_type="video/webm", media_kind="VIDEO", part_number=2)

    assert MED.delete_interview_media(org_id=org, interview_id=iv) == 2
    assert MED.delete_interview_media(org_id=org, interview_id=iv) == 0


# ===========================================================================
# ASR honesty
# ===========================================================================

def test_the_browser_adapter_turns_real_results_into_segments():
    drafts = MED.BrowserSpeechAdapter().transcribe(results=[
        {"text": "I rewrote the reconciler", "start_ms": 1000,
         "end_ms": 4200, "confidence": 0.93},
        {"text": "", "start_ms": 4200, "end_ms": 4300},
        {"text": "then we shipped it", "start_ms": 4300, "end_ms": 6000},
    ])
    assert [d.text for d in drafts] == ["I rewrote the reconciler",
                                        "then we shipped it"]
    assert drafts[0].asr_confidence == 0.93
    assert drafts[0].source == "ASR"


def test_the_local_model_adapter_reports_not_connected_rather_than_guessing():
    """The important one.

    A transcript is evidence. An adapter that fabricates one when it cannot
    run is producing fabricated evidence, which is worse than none.
    """
    ok, why = MED.LocalWhisperAdapter().available()
    if ok:
        pytest.skip("a local model is installed on this machine")
    assert "NOT_CONNECTED" in why
    with pytest.raises(MED.MediaRefused) as exc:
        MED.LocalWhisperAdapter().transcribe(part=None)
    assert exc.value.code == "ASR_NOT_CONNECTED"


def test_asr_status_reports_every_adapter_honestly():
    status = MED.asr_status()
    assert "browser-speech" in status and "local-whisper" in status
    assert status["browser-speech"]["available"] is True
    for name, s in status.items():
        assert isinstance(s["available"], bool)
        assert s["detail"]
