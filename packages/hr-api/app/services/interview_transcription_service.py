"""Interview Transcription service — STUB-FIRST.

What's real:
  - In-process append-only transcript store, per-interview.
  - Speaker, timestamp, text, confidence dataclasses.
  - Consent gating: an interview must have consent_status=granted before
    a single transcript line is accepted.

What's stubbed (clearly marked):
  - Real-time STT.  Currently the browser pushes Web Speech transcript
    lines to this store.  A production wiring would swap in Whisper /
    Deepgram / AssemblyAI on the server side and consume the audio
    stream from Zoom / Meet / Teams / Daily / Twilio.
  - Speaker diarisation.  Today the client tags each line with
    speaker='interviewer' | 'candidate' | 'unknown'.  Production should
    diarise on the audio side.
  - PII redaction.  Hook is exposed but no-op in the demo.

This deliberately keeps the surface explicit so the rest of the copilot
layer can be wired against a real transcript stream without rewriting.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class TranscriptLine:
    id: str
    interview_id: str
    speaker: str            # "interviewer" | "candidate" | "unknown"
    speaker_name: Optional[str]
    text: str
    timestamp: str          # ISO 8601
    confidence: float = 0.85  # 0..1; client-supplied for WebSpeech, server for STT

    def to_dict(self) -> dict:
        return self.__dict__


# Consent statuses recognised across the platform
CONSENT_STATES = {"not_collected", "requested", "granted", "denied"}


@dataclass
class ConsentRecord:
    interview_id: str
    candidate_consent_status: str = "not_collected"
    interviewer_consent_status: str = "not_collected"
    consent_recorded_at: Optional[str] = None
    consent_recorded_by: Optional[str] = None
    policy_version: str = "v1.0"
    recording_enabled: bool = False  # explicit user choice

    def to_dict(self) -> dict:
        return self.__dict__


# ---------------------------------------------------------------------------
# In-process store
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_transcripts: dict[str, list[TranscriptLine]] = {}     # interview_id -> lines
_consent: dict[str, ConsentRecord] = {}                # interview_id -> consent


def get_consent(interview_id: str) -> ConsentRecord:
    """Return the consent record, creating an empty one if missing."""
    with _lock:
        rec = _consent.get(interview_id)
        if not rec:
            rec = ConsentRecord(interview_id=interview_id)
            _consent[interview_id] = rec
        return rec


def record_consent(
    interview_id: str,
    *,
    candidate_consent_status: Optional[str] = None,
    interviewer_consent_status: Optional[str] = None,
    recording_enabled: Optional[bool] = None,
    recorded_by: Optional[str] = None,
) -> ConsentRecord:
    """Update consent state. All status fields validated against CONSENT_STATES."""
    with _lock:
        rec = get_consent(interview_id)
        if candidate_consent_status:
            if candidate_consent_status not in CONSENT_STATES:
                raise ValueError("Invalid candidate_consent_status")
            rec.candidate_consent_status = candidate_consent_status
        if interviewer_consent_status:
            if interviewer_consent_status not in CONSENT_STATES:
                raise ValueError("Invalid interviewer_consent_status")
            rec.interviewer_consent_status = interviewer_consent_status
        if recording_enabled is not None:
            rec.recording_enabled = bool(recording_enabled)
        rec.consent_recorded_at = datetime.now(timezone.utc).isoformat()
        rec.consent_recorded_by = recorded_by
        return rec


def can_capture(interview_id: str) -> tuple[bool, str]:
    """Gating check: only allow capture once *both* parties have granted."""
    rec = get_consent(interview_id)
    if rec.candidate_consent_status != "granted":
        return False, "Candidate has not granted consent to capture transcript."
    if rec.interviewer_consent_status != "granted":
        return False, "Interviewer-side consent not granted."
    return True, ""


def append_line(
    interview_id: str,
    *,
    speaker: str,
    speaker_name: Optional[str],
    text: str,
    confidence: float = 0.85,
) -> Optional[TranscriptLine]:
    """Append a transcript line *only* when consent is granted."""
    ok, _ = can_capture(interview_id)
    if not ok:
        return None
    if speaker not in ("interviewer", "candidate", "unknown"):
        speaker = "unknown"
    line = TranscriptLine(
        id=str(uuid.uuid4()),
        interview_id=interview_id,
        speaker=speaker,
        speaker_name=speaker_name,
        text=text.strip(),
        timestamp=datetime.now(timezone.utc).isoformat(),
        confidence=max(0.0, min(1.0, float(confidence))),
    )
    with _lock:
        _transcripts.setdefault(interview_id, []).append(line)
    return line


def list_lines(interview_id: str, *, since_iso: Optional[str] = None) -> list[TranscriptLine]:
    with _lock:
        lines = list(_transcripts.get(interview_id, []))
    if since_iso:
        lines = [l for l in lines if l.timestamp > since_iso]
    return lines


def full_transcript(interview_id: str) -> str:
    """Render the transcript as readable plain text (for summarisation)."""
    lines = list_lines(interview_id)
    rendered: list[str] = []
    for l in lines:
        who = l.speaker_name or l.speaker.title()
        rendered.append(f"{who}: {l.text}")
    return "\n".join(rendered)


def clear(interview_id: str) -> None:
    """Wipe transcript — invoked when the candidate revokes consent."""
    with _lock:
        _transcripts.pop(interview_id, None)


# ---------------------------------------------------------------------------
# Hooks for future wiring (no-ops in demo)
# ---------------------------------------------------------------------------
def redact_pii_stub(text: str) -> str:
    """Placeholder for PII redaction. Currently a passthrough.

    Production: route through Presidio / spaCy NER / your DLP layer.
    """
    return text
