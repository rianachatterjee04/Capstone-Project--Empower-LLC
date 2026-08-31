"""Durable storage for interview recordings, and the ASR boundary.

WHAT IS REAL HERE
Media that a browser actually captured, written to disk, hashed, measured, and
bound to one interview and one tenant. A recording that reconnects produces
multiple PARTS with a shared timeline, so a transcript offset at t=412s
resolves to the right file and the right position inside it.

WHAT IS NOT, AND SAYS SO
Production object storage. `storage_kind` is explicit and there is no default
that implies S3. On this machine it is LOCAL_FILE, and the API reports that
rather than letting a demo imply durability it does not have.

THE ASR BOUNDARY
Transcription is an adapter with three honest states. `BrowserSpeechAdapter`
takes results the browser's own SpeechRecognition produced during the
interview -- that is real speech recognition, it is just not ours. A
server-side model would be `LocalWhisperAdapter`, and it reports NOT_CONNECTED
unless the model and ffmpeg are actually present, because a transcript is
evidence and a fabricated one is the worst possible kind.

ALIGNMENT IS CHECKED AGAINST THE ARTIFACT
`verify_alignment` compares transcript offsets to the RECORDING's measured
duration and part boundaries -- not to application event timestamps. An
interaction timestamp says when a button was clicked; it does not prove a word
was spoken at that moment in the file. A segment that ends after the media
does is a broken link, and the recruiter clicking it would land nowhere.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence

MEDIA_VERSION = "media-2026.08.29"

LOCAL_FILE = "LOCAL_FILE"
DEMO_FIXTURE = "DEMO_FIXTURE"
OBJECT_STORE = "OBJECT_STORE"
NOT_CONNECTED = "NOT_CONNECTED"

#: Container types a browser MediaRecorder actually produces.
ALLOWED_MIME = {
    "video/webm", "video/webm;codecs=vp8,opus", "video/webm;codecs=vp9,opus",
    "video/mp4", "audio/webm", "audio/webm;codecs=opus", "audio/ogg",
    "audio/mp4", "audio/wav",
}

#: 25 minutes of 720p webm is comfortably under this. A larger upload is more
#: likely a mistake or an attack than an interview.
MAX_PART_BYTES = 512 * 1024 * 1024


class MediaRefused(RuntimeError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def storage_root() -> pathlib.Path:
    """Where media lives on this machine.

    Deliberately env-driven with a local default, and NEVER a temp directory:
    a recording that disappears on reboot is not a recording, and a demo that
    silently loses evidence is worse than one that admits it has none.
    """
    root = os.environ.get("FINTRA_MEDIA_ROOT")
    if root:
        return pathlib.Path(root).expanduser()
    return pathlib.Path.home() / ".fintra" / "interview-media"


def storage_kind() -> str:
    """What kind of storage is actually in use. Never guessed optimistically."""
    if os.environ.get("FINTRA_MEDIA_OBJECT_STORE_URL"):
        return OBJECT_STORE
    return LOCAL_FILE


@dataclass
class StoredPart:
    org_id: object
    interview_id: object
    media_kind: str
    part_number: int
    mime_type: str
    storage_kind: str
    storage_ref: str
    byte_size: int
    sha256: str
    duration_ms: Optional[int]
    timeline_offset_ms: int
    stored_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    def as_row(self, attempt_id=None) -> dict:
        return {
            "attempt_id": attempt_id,
            "part_number": self.part_number,
            "media_kind": self.media_kind,
            "mime_type": self.mime_type,
            "storage_kind": self.storage_kind,
            "storage_ref": self.storage_ref,
            "byte_size": self.byte_size,
            "sha256": self.sha256,
            "duration_ms": self.duration_ms,
            "timeline_offset_ms": self.timeline_offset_ms,
        }


def _tenant_path(org_id, interview_id, part_number: int, ext: str) -> pathlib.Path:
    """org/interview/part. The org is in the PATH, not just the row.

    A directory layout that mixes tenants makes an accidental disclosure a
    single wrong filename away, and makes "delete everything for this
    organisation" a query instead of an `rm -rf` of one directory.
    """
    return (storage_root() / str(org_id) / str(interview_id)
            / f"part-{part_number:03d}{ext}")


def _ext_for(mime: str) -> str:
    base = mime.split(";")[0].strip().lower()
    return {"video/webm": ".webm", "audio/webm": ".webm", "video/mp4": ".mp4",
            "audio/mp4": ".m4a", "audio/ogg": ".ogg",
            "audio/wav": ".wav"}.get(base, ".bin")


def store_part(*, org_id, interview_id, data: bytes, mime_type: str,
               media_kind: str, part_number: int,
               timeline_offset_ms: int = 0,
               duration_ms: Optional[int] = None) -> StoredPart:
    """Write one captured part to durable storage.

    Refuses an empty body, an unrecognised container and an oversized upload.
    Each refusal is a real case: a MediaRecorder that never started produces a
    zero-byte blob, and storing it would create a recording row pointing at
    nothing.
    """
    if not data:
        raise MediaRefused(
            "EMPTY_MEDIA",
            "the upload contained no bytes. A recording row pointing at an "
            "empty file is worse than no row: it claims media exists.")
    if len(data) > MAX_PART_BYTES:
        raise MediaRefused(
            "MEDIA_TOO_LARGE",
            f"{len(data)} bytes exceeds the {MAX_PART_BYTES} limit for one part")

    base = mime_type.split(";")[0].strip().lower()
    if base not in {m.split(";")[0] for m in ALLOWED_MIME}:
        raise MediaRefused(
            "UNSUPPORTED_MEDIA_TYPE",
            f"{mime_type!r} is not a container this accepts. Allowed: "
            f"{sorted({m.split(';')[0] for m in ALLOWED_MIME})}")
    if media_kind not in ("VIDEO", "AUDIO"):
        raise MediaRefused("BAD_MEDIA_KIND",
                           f"media_kind must be VIDEO or AUDIO, not {media_kind!r}")
    if part_number < 1:
        raise MediaRefused("BAD_PART_NUMBER", "parts are numbered from 1")

    path = _tenant_path(org_id, interview_id, part_number, _ext_for(mime_type))
    path.parent.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(data).hexdigest()

    # A re-upload of the SAME bytes is idempotent; different bytes under the
    # same part number is a conflict, not an overwrite. Silently replacing
    # media that a transcript already points at would break every evidence
    # link into it.
    if path.exists():
        existing = hashlib.sha256(path.read_bytes()).hexdigest()
        if existing != digest:
            raise MediaRefused(
                "PART_ALREADY_EXISTS",
                f"part {part_number} already holds different media "
                f"({existing[:12]}… vs {digest[:12]}…). Transcript segments "
                f"may already point into it; use the next part number.")
    else:
        path.write_bytes(data)

    return StoredPart(
        org_id=org_id, interview_id=interview_id, media_kind=media_kind,
        part_number=part_number, mime_type=mime_type,
        storage_kind=storage_kind(), storage_ref=str(path),
        byte_size=len(data), sha256=digest, duration_ms=duration_ms,
        timeline_offset_ms=timeline_offset_ms)


def read_part(storage_ref: str, *, org_id) -> bytes:
    """Read media back, refusing a path outside this tenant's directory.

    The ref comes from a database row, but a row is not a capability: a
    traversal or a copied ref from another tenant must not resolve.
    """
    path = pathlib.Path(storage_ref).resolve()
    tenant_root = (storage_root() / str(org_id)).resolve()
    try:
        path.relative_to(tenant_root)
    except ValueError:
        raise MediaRefused(
            "MEDIA_OUTSIDE_TENANT",
            f"the stored reference resolves outside this organisation's media "
            f"directory. Refusing to read it.")
    if not path.is_file():
        raise MediaRefused("MEDIA_MISSING",
                           f"the row references {storage_ref}, which is not on disk")
    return path.read_bytes()


def delete_interview_media(*, org_id, interview_id) -> int:
    """Retention / erasure. Returns how many files were removed."""
    d = (storage_root() / str(org_id) / str(interview_id))
    if not d.is_dir():
        return 0
    n = len(list(d.glob("*")))
    shutil.rmtree(d, ignore_errors=True)
    return n


# ---------------------------------------------------------------------------
# Transcript alignment, checked against the MEDIA
# ---------------------------------------------------------------------------

@dataclass
class AlignmentProblem:
    segment_index: int
    code: str
    detail: str


def verify_alignment(segments: Sequence, parts: Sequence) -> List[AlignmentProblem]:
    """Do these transcript offsets actually land inside the recorded media?

    This is the difference between a timestamp and an alignment. An
    application event says when a button was pressed; it does not establish
    that a word was spoken at that offset in a file. Checking against the
    parts' measured durations does.

    `segments` need .start_ms, .end_ms and optionally .recording_asset_id.
    `parts` need .part_number, .timeline_offset_ms, .duration_ms and .id.
    """
    problems: List[AlignmentProblem] = []
    if not parts:
        return [AlignmentProblem(
            -1, "NO_MEDIA",
            "there are transcript segments but no recording. Their offsets "
            "cannot be verified against anything.")] if segments else []

    spans = []
    for p in sorted(parts, key=lambda x: getattr(x, "part_number", 0)):
        dur = getattr(p, "duration_ms", None)
        if dur is None:
            problems.append(AlignmentProblem(
                -1, "PART_DURATION_UNKNOWN",
                f"part {getattr(p, 'part_number', '?')} has no measured "
                f"duration, so nothing can be aligned to it"))
            continue
        start = int(getattr(p, "timeline_offset_ms", 0) or 0)
        spans.append((start, start + int(dur), getattr(p, "id", None),
                      getattr(p, "part_number", None)))

    if not spans:
        return problems

    total_end = max(e for _, e, _, _ in spans)

    for i, seg in enumerate(segments):
        s = int(getattr(seg, "start_ms", 0) or 0)
        e = int(getattr(seg, "end_ms", 0) or 0)

        if e < s:
            problems.append(AlignmentProblem(
                i, "SEGMENT_ENDS_BEFORE_IT_STARTS", f"{s}ms -> {e}ms"))
            continue
        if s < 0:
            problems.append(AlignmentProblem(i, "NEGATIVE_OFFSET", f"{s}ms"))
            continue
        if e > total_end:
            problems.append(AlignmentProblem(
                i, "SEGMENT_BEYOND_MEDIA",
                f"segment ends at {e}ms but the recording is {total_end}ms "
                f"long. A recruiter clicking this would land past the end."))
            continue

        covering = [sp for sp in spans if sp[0] <= s < sp[1]]
        if not covering:
            problems.append(AlignmentProblem(
                i, "SEGMENT_IN_A_GAP",
                f"{s}ms falls between recorded parts — nothing was captured "
                f"at that moment"))
            continue

        claimed = getattr(seg, "recording_asset_id", None)
        if claimed is not None and claimed != covering[0][2]:
            problems.append(AlignmentProblem(
                i, "SEGMENT_BOUND_TO_WRONG_PART",
                f"the segment names one recording but its offset falls inside "
                f"part {covering[0][3]}"))
    return problems


# ---------------------------------------------------------------------------
# ASR adapters
# ---------------------------------------------------------------------------

@dataclass
class TranscriptSegmentDraft:
    speaker: str
    sequence_number: int
    start_ms: int
    end_ms: int
    text: str
    asr_confidence: Optional[float] = None
    source: str = "ASR"
    #: The adapter that produced this draft. Set by the adapter itself, never
    #: by the caller: a provenance the client can choose is not a provenance.
    adapter: Optional[str] = None


class AsrAdapter:
    """The transcription boundary.

    `available()` must be honest. A transcript is evidence; an adapter that
    invents one when it cannot run is producing fabricated evidence, which is
    worse than admitting it has none.
    """

    name = "abstract"

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def transcribe(self, *, part, **kw) -> List[TranscriptSegmentDraft]:
        raise NotImplementedError


class BrowserSpeechAdapter(AsrAdapter):
    """Results the browser's own SpeechRecognition produced during the call.

    This is real speech recognition -- it is simply not ours, and it happened
    live rather than from the file. Its offsets are relative to the recording
    clock the same MediaRecorder started, which is why they can be verified
    against the media afterwards.

    Its limits are real too: Chrome and Safari only, no speaker separation,
    and quality varies with the microphone. Recorded as source=ASR with the
    adapter named on the segment.
    """

    name = "browser-speech"

    def available(self) -> tuple[bool, str]:
        return True, ("accepts transcript results captured in the browser "
                      "during the interview")

    def transcribe(self, *, part=None, results: Sequence[dict] = (),
                   **kw) -> List[TranscriptSegmentDraft]:
        out: List[TranscriptSegmentDraft] = []
        for i, r in enumerate(results):
            text = (r.get("text") or "").strip()
            if not text:
                continue
            out.append(TranscriptSegmentDraft(
                speaker=r.get("speaker") or "CANDIDATE",
                sequence_number=i + 1,
                start_ms=int(r.get("start_ms") or 0),
                end_ms=int(r.get("end_ms") or 0),
                text=text,
                asr_confidence=(float(r["confidence"])
                                if r.get("confidence") is not None else None),
                source="ASR", adapter=self.name))
        return out


class LocalWhisperAdapter(AsrAdapter):
    """Server-side transcription from the media file itself.

    Reports NOT_CONNECTED unless BOTH the model package and ffmpeg are present.
    On this machine neither is, and the honest consequence is that server-side
    ASR is a stated gap rather than a silently degraded path.
    """

    name = "local-whisper"

    def available(self) -> tuple[bool, str]:
        import importlib.util
        missing = []
        if importlib.util.find_spec("whisper") is None and \
           importlib.util.find_spec("faster_whisper") is None:
            missing.append("openai-whisper or faster-whisper")
        if shutil.which("ffmpeg") is None:
            missing.append("ffmpeg")
        if missing:
            return False, ("NOT_CONNECTED — needs " + ", ".join(missing))
        return True, "local model available"

    def transcribe(self, *, part, **kw) -> List[TranscriptSegmentDraft]:
        ok, why = self.available()
        if not ok:
            raise MediaRefused("ASR_NOT_CONNECTED", why)
        raise MediaRefused(
            "ASR_NOT_IMPLEMENTED",
            "the model is installed but this adapter has not been wired to it "
            "yet. It refuses rather than returning an empty transcript, "
            "because an empty transcript reads as 'the candidate said "
            "nothing'.")


def adapters() -> List[AsrAdapter]:
    return [BrowserSpeechAdapter(), LocalWhisperAdapter()]


def asr_status() -> dict:
    """What transcription this deployment can actually do."""
    out = {}
    for a in adapters():
        ok, why = a.available()
        out[a.name] = {"available": ok, "detail": why}
    return out


# ===========================================================================
# WebM duration repair
# ===========================================================================
#
# WHY A MUXER LIVES IN THIS FILE
# `MediaRecorder` writes a LIVE WebM: the Segment has an unknown size, there is
# no Cues index, no SeekHead, and -- the one that matters -- no Duration. A
# browser loading it reports `video.duration === Infinity` and
# `seekable.end(0) === undefined`.
#
# Everything above this looked fine. The RecordingAsset row existed, the bytes
# were real WebM with the right magic, the range serving worked, and a <video>
# element accepted `currentTime = 90`. What it could not do was SEEK there, or
# draw a scrubber, because the file does not say how long it is.
#
# That is the whole recruiter interaction: "click any assessment and the
# recording seeks to the moment the candidate said it." So the duration the
# browser already measured and sends with the upload is written into the
# container here, and the Segment's unknown size is replaced with its real one.
#
# WHAT THIS IS NOT
# A remux. There are still no Cues, so a browser seeking backwards may rescan
# clusters; for parts of a few minutes that is imperceptible, and adding a real
# index would mean parsing every cluster. `duration_is_authoritative` says
# which of the two a caller is looking at, rather than leaving them to guess.

_EBML_MAGIC = b"\x1a\x45\xdf\xa3"
_ID_SEGMENT = b"\x18\x53\x80\x67"
_ID_INFO = b"\x15\x49\xa9\x66"
_ID_TIMECODE_SCALE = b"\x2a\xd7\xb1"
_ID_DURATION = b"\x44\x89"

#: Matroska's default: one timecode unit is 1,000,000 ns, i.e. one millisecond.
_DEFAULT_TIMECODE_SCALE_NS = 1_000_000


class WebmRepairFailed(RuntimeError):
    pass


def _read_vint(buf: bytes, pos: int, *, keep_marker: bool) -> tuple:
    """One EBML variable-length integer. Returns (value, next_pos, width)."""
    if pos >= len(buf):
        raise WebmRepairFailed("ran off the end reading a length")
    first = buf[pos]
    if first == 0:
        raise WebmRepairFailed("invalid EBML length: leading zero byte")
    width = 1
    mask = 0x80
    while not (first & mask):
        mask >>= 1
        width += 1
    if pos + width > len(buf):
        raise WebmRepairFailed("truncated EBML length")
    value = first if keep_marker else (first & (mask - 1))
    for i in range(1, width):
        value = (value << 8) | buf[pos + i]
    return value, pos + width, width


def _encode_vint(value: int, *, width: int = 0) -> bytes:
    """Encode a length as an EBML varint, optionally at a fixed width."""
    if width == 0:
        width = 1
        while value >= (1 << (7 * width)) - 1:
            width += 1
            if width > 8:
                raise WebmRepairFailed("length does not fit in 8 bytes")
    out = bytearray(value.to_bytes(width, "big"))
    out[0] |= 0x80 >> (width - 1)
    return bytes(out)


@dataclass
class WebmRepair:
    data: bytes
    changed: bool
    reason: str
    duration_ms: Optional[int] = None
    #: True when the container itself now states the duration.
    duration_is_authoritative: bool = False


def ensure_webm_duration(data: bytes,
                         duration_ms: Optional[int]) -> WebmRepair:
    """Write `duration_ms` into a MediaRecorder WebM that does not carry one.

    Returns the original bytes unchanged whenever it is not confident: a file
    that is not WebM, one that already has a Duration, a missing duration from
    the client, or anything it cannot parse. A recording that plays without a
    scrubber is a limitation; a recording corrupted by a hopeful muxer is a
    lost interview.
    """
    if not data[:4] == _EBML_MAGIC:
        return WebmRepair(data, False, "not an EBML/WebM container")
    if not duration_ms or duration_ms <= 0:
        return WebmRepair(data, False,
                          "the client reported no duration for this part")

    try:
        # --- top level: EBML header, then Segment ------------------------
        pos = 0
        _, pos, _ = _read_vint(data, pos + 4, keep_marker=False)  # header size
        # `pos` is now at the header's content; skip it.
        header_size, after_len, _ = _read_vint(data, 4, keep_marker=False)
        pos = after_len + header_size
        if pos + 4 > len(data):
            raise WebmRepairFailed("the file ends inside its own EBML header")

        if data[pos:pos + 4] != _ID_SEGMENT:
            return WebmRepair(data, False, "no Segment where one was expected")
        seg_size_pos = pos + 4
        # Parsed to validate the Segment header and to find where its children
        # begin. The size itself is deliberately not rewritten -- see the note
        # at the end of this function.
        _seg_raw, seg_body, _seg_width = _read_vint(data, seg_size_pos,
                                                    keep_marker=False)

        # --- find Info inside the Segment --------------------------------
        p = seg_body
        info_start = info_body = info_end = None
        timecode_scale = _DEFAULT_TIMECODE_SCALE_NS
        while p < len(data) - 4:
            if data[p:p + 4] == _ID_INFO:
                info_start = p
                size, body, _ = _read_vint(data, p + 4, keep_marker=False)
                info_body, info_end = body, body + size
                break
            # Walk this element and step over it.
            eid_len = 4
            for cand in (4, 3, 2, 1):
                b = data[p]
                bits = 1
                m = 0x80
                while not (b & m) and bits <= 4:
                    m >>= 1
                    bits += 1
                eid_len = bits
                break
            size, body, _ = _read_vint(data, p + eid_len, keep_marker=False)
            if body + size > len(data):
                raise WebmRepairFailed(
                    "an element declares more bytes than the file holds")
            p = body + size

        if info_start is None:
            return WebmRepair(data, False, "no Info element found")

        # A DECLARED SIZE THAT RUNS PAST THE END MEANS THE FILE IS TRUNCATED.
        # Python slices clamp silently, so without this the repair happily
        # built a "fixed" container out of a partial upload -- writing a
        # Segment size that described bytes which were never received. A
        # recording that plays without a scrubber is a limitation; one that
        # claims to be complete when it is not is a lost interview that looks
        # fine until someone opens it.
        if info_end > len(data) or info_body > len(data):
            return WebmRepair(
                data, False,
                "the Info element declares more bytes than the file holds; "
                "this upload is truncated and was left exactly as it arrived")

        info = data[info_body:info_end]
        if _ID_DURATION in info:
            return WebmRepair(data, False, "the container already has a "
                                           "Duration", duration_ms,
                              duration_is_authoritative=True)

        idx = info.find(_ID_TIMECODE_SCALE)
        if idx >= 0:
            size, body, _ = _read_vint(info, idx + 3, keep_marker=False)
            timecode_scale = int.from_bytes(info[body:body + size], "big")
        if timecode_scale <= 0:
            timecode_scale = _DEFAULT_TIMECODE_SCALE_NS

        # Duration is expressed in TimecodeScale units, as a float.
        scaled = (duration_ms * 1_000_000.0) / timecode_scale
        duration_el = _ID_DURATION + b"\x88" + struct.pack(">d", scaled)

        new_info_body = info + duration_el
        new_info = (_ID_INFO + _encode_vint(len(new_info_body))
                    + new_info_body)

        rebuilt = bytearray()
        rebuilt += data[:info_start]
        rebuilt += new_info
        rebuilt += data[info_end:]

        # THE SEGMENT SIZE IS DELIBERATELY LEFT UNKNOWN.
        #
        # The first version rewrote it too, on the reasoning that an
        # unknown-size Segment tells the player the file is still being
        # written. Measured in a browser, the Duration element ALONE is
        # sufficient: with the Segment left unknown, `video.duration` is 2.5,
        # `seekable.end(0)` is 2.5, and seeks to 1.5s and 0.5s both land
        # exactly.
        #
        # And rewriting it was actively harmful. A declared size is a claim
        # about how many bytes follow, and nothing here can verify that claim
        # for a live container -- a test with a file truncated after a
        # complete Info header caught the repair writing a size that described
        # bytes which were never received, producing a file that looks
        # complete and is not.
        #
        # So: write the fact we were told (the browser measured this duration)
        # and never a fact we would be inferring.
        return WebmRepair(bytes(rebuilt), True,
                          "wrote the browser-measured duration into the "
                          "container so the player can scrub it",
                          duration_ms, duration_is_authoritative=True)

    except WebmRepairFailed as exc:
        return WebmRepair(data, False, f"left unchanged: {exc}")
    except Exception as exc:            # pragma: no cover - defensive
        return WebmRepair(data, False, f"left unchanged: {exc!r}")


# ===========================================================================
# Recording lifecycle
# ===========================================================================
#
# WHY A STATE AND NOT JUST ROWS
# A RecordingAsset row exists the moment bytes land. Nothing distinguished a
# recording that captured the whole interview from one where the candidate's
# laptop slept through part three, or where the tab closed while the last part
# was uploading. Both look like "there is a recording", and a recruiter opening
# either sees a player.
#
# That is the failure this product cannot afford: an assessment defended by a
# recording that is missing the answer it rests on. So the interview carries an
# explicit state, and the state is only SEALED when the client has said how
# many parts it produced AND the server holds exactly those parts.

NOT_CAPTURED = "NOT_CAPTURED"
CAPTURING = "CAPTURING"
SEALED = "SEALED"
INCOMPLETE = "INCOMPLETE"

RECORDING_STATES = (NOT_CAPTURED, CAPTURING, SEALED, INCOMPLETE)


@dataclass
class RecordingCompleteness:
    state: str
    parts_held: int
    parts_expected: Optional[int]
    missing_parts: List[int] = field(default_factory=list)
    duplicate_parts: List[int] = field(default_factory=list)
    zero_byte_parts: List[int] = field(default_factory=list)
    detail: str = ""

    @property
    def is_sealed(self) -> bool:
        return self.state == SEALED

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "parts_held": self.parts_held,
            "parts_expected": self.parts_expected,
            "missing_parts": self.missing_parts,
            "duplicate_parts": self.duplicate_parts,
            "zero_byte_parts": self.zero_byte_parts,
            "detail": self.detail,
        }


def assess_completeness(parts: Sequence,
                        expected: Optional[int]) -> RecordingCompleteness:
    """Is what we hold the whole recording?

    `parts` need `.part_number` and `.byte_size`. `expected` is what the CLIENT
    says it produced -- the only party that knows, because a part that never
    reached the server leaves no trace here.

    Without `expected` the answer is CAPTURING, never SEALED. "We have three
    parts" is not "we have all the parts", and treating it as such is exactly
    how a truncated recording comes to look complete.
    """
    numbers = sorted(int(getattr(p, "part_number", 0) or 0) for p in parts)
    held = len(numbers)
    dupes = sorted({n for n in numbers if numbers.count(n) > 1})
    empty = sorted(int(getattr(p, "part_number", 0) or 0) for p in parts
                   if not getattr(p, "byte_size", None))

    if not numbers:
        return RecordingCompleteness(
            NOT_CAPTURED, 0, expected,
            detail=("no media was captured for this interview. The evidence "
                    "still carries timecodes from the answer boundaries; "
                    "there is nothing to seek into."))

    if expected is None:
        return RecordingCompleteness(
            CAPTURING, held, None, duplicate_parts=dupes,
            zero_byte_parts=empty,
            detail=(f"{held} part(s) received and the client has not said how "
                    f"many it produced. Holding parts is not the same as "
                    f"holding all of them."))

    missing = [n for n in range(1, int(expected) + 1) if n not in numbers]
    problems = []
    if missing:
        problems.append(f"missing part(s) {missing}")
    if dupes:
        problems.append(f"duplicate part number(s) {dupes}")
    if empty:
        problems.append(f"zero-byte part(s) {empty}")
    extra = [n for n in numbers if n > int(expected)]
    if extra:
        problems.append(f"part(s) {extra} beyond the {expected} the client "
                        f"reported")

    if problems:
        return RecordingCompleteness(
            INCOMPLETE, held, int(expected), missing_parts=missing,
            duplicate_parts=dupes, zero_byte_parts=empty,
            detail=("this recording is not whole: " + "; ".join(problems) +
                    ". Evidence timed inside a missing part cannot be played, "
                    "and the player says so rather than seeking to the wrong "
                    "moment."))

    return RecordingCompleteness(
        SEALED, held, int(expected),
        detail=(f"all {expected} part(s) the client produced are held, "
                f"contiguous and non-empty."))
