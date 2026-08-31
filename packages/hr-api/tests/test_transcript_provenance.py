"""How a transcript was obtained has to survive into the row.

An assessment cites transcript segments as its evidence. So "how do we know the
candidate said this" is part of the evidence, and it was being thrown away: both
ASR adapters wrote source='ASR', the adapter name went out in the HTTP response
and was never stored, and the two are not comparable evidence.

  browser-speech   the candidate's own browser recognised their speech and
                   POSTed the text. Tied to the recording by a shared clock,
                   not re-derived from it. We cannot confirm the wording.
  local-whisper    the server transcribed the stored media. Reproducible by
                   anyone holding the file.

The authority of a mixed transcript is its WEAKEST part. One client-reported
segment makes "this transcript was derived from the recording" false, so an
average or a best-of would be a more confident claim than the evidence supports.
"""
from __future__ import annotations

import pytest

from app.api.routers.interview_v2 import _transcript_provenance
from app.interview import media as MED


class _Seg:
    def __init__(self, adapter):
        self.asr_adapter = adapter


# ── the adapter stamps itself; the caller does not get a say ───────────────

def test_the_browser_adapter_names_itself_on_every_draft():
    drafts = MED.BrowserSpeechAdapter().transcribe(results=[
        {"text": "I led the migration", "start_ms": 0, "end_ms": 2000,
         "confidence": 0.91},
        {"text": "about eighteen months", "start_ms": 2000, "end_ms": 3500},
    ])
    assert len(drafts) == 2
    assert all(d.adapter == "browser-speech" for d in drafts)
    assert all(d.source == "ASR" for d in drafts)


def test_the_client_cannot_choose_its_own_provenance():
    """A provenance the client can set is not a provenance. The adapter stamps
    its own name, so a posted `adapter` or `source` field is ignored."""
    drafts = MED.BrowserSpeechAdapter().transcribe(results=[
        {"text": "hello", "start_ms": 0, "end_ms": 100,
         "adapter": "local-whisper", "source": "HUMAN"},
    ])
    assert drafts[0].adapter == "browser-speech"
    assert drafts[0].source == "ASR"


def test_the_server_side_adapter_refuses_rather_than_inventing():
    """It is not connected here. An adapter that returns an empty transcript
    when it cannot run is producing fabricated evidence."""
    ok, why = MED.LocalWhisperAdapter().available()
    assert ok is False and "NOT_CONNECTED" in why
    with pytest.raises(MED.MediaRefused):
        MED.LocalWhisperAdapter().transcribe(part=None)


# ── the summary reports the weakest link ──────────────────────────────────

def test_no_segments_is_its_own_answer_not_a_low_grade():
    p = _transcript_provenance([])
    assert p["authority"] == "NONE"
    assert p["adapters"] == []


def test_browser_only_transcript_is_client_reported():
    p = _transcript_provenance([_Seg("browser-speech")] * 3)
    assert p["authority"] == "CLIENT_REPORTED"
    assert p["adapters"] == ["browser-speech"]
    assert "cannot independently confirm" in p["detail"]


def test_server_derived_transcript_says_so():
    p = _transcript_provenance([_Seg("local-whisper")] * 2)
    assert p["authority"] == "SERVER_DERIVED"
    assert "reproducible" in p["detail"]


def test_a_mixed_transcript_takes_the_weakest_grade_not_the_average():
    """Nine server-derived segments and one from the browser is a transcript we
    cannot fully vouch for. Reporting SERVER_DERIVED here would be the more
    flattering answer and the wrong one."""
    segs = [_Seg("local-whisper")] * 9 + [_Seg("browser-speech")]
    p = _transcript_provenance(segs)
    assert p["authority"] == "CLIENT_REPORTED"
    assert p["adapters"] == ["browser-speech", "local-whisper"]


def test_an_unrecorded_adapter_is_unknown_not_assumed_good():
    """Segments written before the column existed do not know their adapter.
    Backfilling a guess would invent the provenance this records."""
    p = _transcript_provenance([_Seg("local-whisper"), _Seg(None)])
    assert p["authority"] == "UNKNOWN"
    assert "not assumed" in p["detail"]


def test_an_unrecognised_adapter_does_not_silently_rank_as_trustworthy():
    """A new adapter added without a ladder entry must degrade, not inherit."""
    p = _transcript_provenance([_Seg("some-new-thing")])
    assert p["authority"] == "UNKNOWN"


# ── control ───────────────────────────────────────────────────────────────

def test_control_the_grades_are_actually_distinguishable():
    """If every input produced the same answer, every test above would pass
    while the function reported nothing."""
    grades = {
        _transcript_provenance([])["authority"],
        _transcript_provenance([_Seg("browser-speech")])["authority"],
        _transcript_provenance([_Seg("local-whisper")])["authority"],
        _transcript_provenance([_Seg(None)])["authority"],
    }
    assert grades == {"NONE", "CLIENT_REPORTED", "SERVER_DERIVED", "UNKNOWN"}


# ── a demo fixture must never rank beside a real transcript ───────────────

def test_a_demo_fixture_is_graded_as_a_fixture():
    p = _transcript_provenance([_Seg("demo-fixture")] * 4)
    assert p["authority"] == "DEMO_FIXTURE"
    assert "No speech was recognised" in p["detail"]


def test_a_fixture_ranks_below_everything_including_unknown():
    """"We do not know how this was produced" still leaves open that a person
    said it. "This was seeded" closes that question the other way, so a fixture
    mixed with anything real must drag the whole transcript down to fixture."""
    for other in ("local-whisper", "browser-speech", None, "some-new-thing"):
        p = _transcript_provenance([_Seg(other), _Seg("demo-fixture")])
        assert p["authority"] == "DEMO_FIXTURE", (
            f"a demo fixture mixed with {other!r} graded as {p['authority']}. "
            f"A seeded transcript sitting quietly beside a real one is the "
            f"most misleading thing this ladder could allow.")
