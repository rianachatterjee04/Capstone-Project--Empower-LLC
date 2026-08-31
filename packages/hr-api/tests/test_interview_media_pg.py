"""The recording path, end to end, through the database and the API layer.

capture -> upload -> durable file -> recording row -> transcript segments
bound to that recording -> alignment verified against the media -> recruiter
can stream it back.

The consent tests are the ones that matter most. Consenting to be interviewed
and consenting to be recorded are separate grants on the consent row, and that
separation is only real if the upload endpoint actually refuses.
"""
from __future__ import annotations

import io
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview import media as MED
from app.interview import models as M
from app.interview import repository as R
from app.interview import runner
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

WEBM = b"\x1a\x45\xdf\xa3" + b"captured" * 256
RESUME = ("Senior Platform Engineer. Reduced settlement failures by 40%. "
          "Managed a team of 12 engineers. 8 years distributed systems.")


@pytest.fixture(autouse=True)
def media_root(tmp_path, monkeypatch):
    monkeypatch.setenv("FINTRA_MEDIA_ROOT", str(tmp_path / "media"))
    monkeypatch.delenv("FINTRA_MEDIA_OBJECT_STORE_URL", raising=False)


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


class _Actor:
    def __init__(self, org_id, role="owner"):
        self.org_id = org_id
        self.role = role
        self.user_id = None
        self.email = "r@example.test"
        self.claims = {"email": "r@example.test"}


def _upload(data=WEBM, name="part.webm", mime="video/webm") -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data),
                      headers={"content-type": mime})


async def _make(db, *, video=True, audio=True):
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"media-{org.hex[:6]}"})
    job = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status)
        VALUES (:i,:o,'Senior Software Engineer','d','open')"""),
        {"i": job, "o": org})
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,resume_text,status)
        VALUES (:i,:o,:j,'M','m@example.test',:r,'new')"""),
        {"i": cand, "o": org, "j": job, "r": RESUME})
    await db.commit()

    consent = await R.create_consent(
        db, org_id=org, candidate_id=cand, disclosure_text="x" * 40,
        policy_version="2026.08", video=video, audio=audio)
    await db.commit()
    prepared = await runner.prepare(
        db, org_id=org, job_posting_id=job, candidate_id=cand,
        job_title="Senior Software Engineer", resume_text=RESUME,
        consent_id=consent.id)
    await db.commit()
    return {"org": org, "interview_id": prepared["interview"].id,
            "candidate": cand, "consent": consent}


# ===========================================================================
# Capability, reported honestly
# ===========================================================================

@pytest.mark.asyncio
async def test_capability_reports_what_this_deployment_can_really_do(db):
    from app.api.routers import interview_v2 as R2
    cap = await R2.media_capability(actor=_Actor(uuid.uuid4()))

    assert cap["storage_kind"] == MED.LOCAL_FILE
    assert cap["storage_is_durable"] is True
    assert "video/webm" in cap["accepted_containers"]
    # The server-side model is absent here and must say so.
    assert cap["asr"]["local-whisper"]["available"] is False
    assert "NOT_CONNECTED" in cap["asr"]["local-whisper"]["detail"]


# ===========================================================================
# Consent gates the recording, separately from the interview
# ===========================================================================

@pytest.mark.asyncio
async def test_recording_is_refused_without_recording_consent(db):
    """The separation made real.

    This candidate consented to the interview and to neither camera nor
    microphone. The interview may proceed; the upload may not.
    """
    from app.api.routers import interview_v2 as R2
    made = await _make(db, video=False, audio=False)

    with pytest.raises(HTTPException) as exc:
        await R2.upload_media(made["interview_id"], file=_upload(),
                              media_kind="VIDEO", part_number=1,
                              actor=_Actor(made["org"]), db=db)
    assert exc.value.status_code == 409
    assert "consent" in str(exc.value.detail).lower()


@pytest.mark.asyncio
async def test_audio_consent_alone_refuses_video(db):
    """A candidate may agree to be heard and not seen."""
    from app.api.routers import interview_v2 as R2
    made = await _make(db, video=False, audio=True)

    ok = await R2.upload_media(made["interview_id"],
                               file=_upload(mime="audio/webm"),
                               media_kind="AUDIO", part_number=1,
                               actor=_Actor(made["org"]), db=db)
    assert ok["byte_size"] == len(WEBM)

    with pytest.raises(HTTPException) as exc:
        await R2.upload_media(made["interview_id"], file=_upload(),
                              media_kind="VIDEO", part_number=2,
                              actor=_Actor(made["org"]), db=db)
    assert exc.value.status_code == 409


# ===========================================================================
# The chain
# ===========================================================================

@pytest.mark.asyncio
async def test_upload_transcribe_align_and_stream_back(db):
    """The whole path, and the claim the product rests on."""
    from app.api.routers import interview_v2 as R2
    made = await _make(db)
    org, iv = made["org"], made["interview_id"]

    stored = await R2.upload_media(iv, file=_upload(), media_kind="VIDEO",
                                   part_number=1, timeline_offset_ms=0,
                                   duration_ms=300_000,
                                   actor=_Actor(org), db=db)
    assert stored["sha256"]
    assert stored["storage_kind"] == MED.LOCAL_FILE

    got = await R2.submit_transcript(
        iv, R2.TranscriptIn(recording_part=1, results=[
            {"text": "I rewrote the settlement reconciler",
             "start_ms": 12_000, "end_ms": 18_400, "confidence": 0.91},
            {"text": "failures went from four percent to point two",
             "start_ms": 18_400, "end_ms": 25_000, "confidence": 0.88},
        ]), actor=_Actor(org), db=db)
    assert got["segments"] == 2
    assert got["bound_to_recording"] == stored["recording_id"]

    report = await R2.alignment(iv, actor=_Actor(org), db=db)
    assert report["aligned"] is True, report["problems"]
    assert report["recording_parts"] == 1
    assert "not application event timestamps" in report["verified_against"]

    resp = await R2.stream_media(iv, 1, actor=_Actor(org), db=db)
    assert resp.body == WEBM


@pytest.mark.asyncio
async def test_a_transcript_beyond_the_media_is_reported_as_misaligned(db):
    """TAMPERED TRANSCRIPT TIMING, through the real API.

    The recording is 30 seconds. A segment claiming ten minutes in cannot be
    evidence, and the report has to say so rather than letting the recruiter
    click into nothing.
    """
    from app.api.routers import interview_v2 as R2
    made = await _make(db)
    org, iv = made["org"], made["interview_id"]

    await R2.upload_media(iv, file=_upload(), media_kind="VIDEO",
                          part_number=1, duration_ms=30_000,
                          actor=_Actor(org), db=db)
    await R2.submit_transcript(
        iv, R2.TranscriptIn(recording_part=1, results=[
            {"text": "spoken much later", "start_ms": 600_000,
             "end_ms": 601_000}]),
        actor=_Actor(org), db=db)

    report = await R2.alignment(iv, actor=_Actor(org), db=db)
    assert report["aligned"] is False
    assert report["problems"][0]["code"] == "SEGMENT_BEYOND_MEDIA"


@pytest.mark.asyncio
async def test_a_transcript_with_no_media_is_not_aligned_evidence(db):
    """The state the product must not paper over.

    Text without media is a transcript. It is not evidence a recruiter can
    seek into, and the two have to be distinguishable.
    """
    from app.api.routers import interview_v2 as R2
    made = await _make(db)
    org, iv = made["org"], made["interview_id"]

    out = await R2.submit_transcript(
        iv, R2.TranscriptIn(results=[
            {"text": "no media was captured", "start_ms": 0, "end_ms": 2_000}]),
        actor=_Actor(org), db=db)
    assert out["bound_to_recording"] is None

    report = await R2.alignment(iv, actor=_Actor(org), db=db)
    assert report["aligned"] is False
    assert report["problems"][0]["code"] == "NO_MEDIA"


@pytest.mark.asyncio
async def test_reconnect_stores_a_second_part_on_the_same_interview(db):
    """RECONNECT and MULTI-SEGMENT RECORDING."""
    from app.api.routers import interview_v2 as R2
    made = await _make(db)
    org, iv = made["org"], made["interview_id"]

    await R2.upload_media(iv, file=_upload(WEBM), media_kind="VIDEO",
                          part_number=1, timeline_offset_ms=0,
                          duration_ms=180_000, actor=_Actor(org), db=db)
    await R2.upload_media(iv, file=_upload(WEBM + b"second"),
                          media_kind="VIDEO", part_number=2,
                          timeline_offset_ms=180_000, duration_ms=120_000,
                          actor=_Actor(org), db=db)

    rows = list((await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.org_id == org,
        M.RecordingAsset.interview_id == iv))).scalars().all())
    assert len(rows) == 2
    assert {r.part_number for r in rows} == {1, 2}

    # An offset inside part 2 must verify.
    await R2.submit_transcript(
        iv, R2.TranscriptIn(recording_part=2, results=[
            {"text": "after the reconnect", "start_ms": 200_000,
             "end_ms": 204_000}]), actor=_Actor(org), db=db)
    report = await R2.alignment(iv, actor=_Actor(org), db=db)
    assert report["aligned"] is True, report["problems"]


@pytest.mark.asyncio
async def test_re_uploading_a_part_with_different_bytes_is_a_conflict(db):
    """DUPLICATE COMPLETION. Overwriting media a transcript points into
    would make every evidence link inside it seek to different audio."""
    from app.api.routers import interview_v2 as R2
    made = await _make(db)
    org, iv = made["org"], made["interview_id"]

    await R2.upload_media(iv, file=_upload(WEBM), media_kind="VIDEO",
                          part_number=1, duration_ms=1000,
                          actor=_Actor(org), db=db)
    with pytest.raises(HTTPException) as exc:
        await R2.upload_media(iv, file=_upload(WEBM + b"x"), media_kind="VIDEO",
                              part_number=1, duration_ms=1000,
                              actor=_Actor(org), db=db)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "PART_ALREADY_EXISTS"


@pytest.mark.asyncio
async def test_an_empty_capture_is_refused(db):
    """CAMERA/MIC UNAVAILABLE produces a zero-byte blob."""
    from app.api.routers import interview_v2 as R2
    made = await _make(db)

    with pytest.raises(HTTPException) as exc:
        await R2.upload_media(made["interview_id"], file=_upload(b""),
                              media_kind="VIDEO", part_number=1,
                              actor=_Actor(made["org"]), db=db)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "EMPTY_MEDIA"


# ===========================================================================
# Tenancy and audience
# ===========================================================================

@pytest.mark.asyncio
async def test_media_cannot_be_uploaded_to_another_tenants_interview(db):
    """WRONG INTERVIEW / WRONG TENANT."""
    from app.api.routers import interview_v2 as R2
    a = await _make(db)
    b = await _make(db)

    with pytest.raises(HTTPException) as exc:
        await R2.upload_media(a["interview_id"], file=_upload(),
                              media_kind="VIDEO", part_number=1,
                              actor=_Actor(b["org"]), db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_a_candidate_cannot_stream_the_recording_back(db):
    """The media is the assessment material. Staff only."""
    from app.api.routers import interview_v2 as R2
    made = await _make(db)
    org, iv = made["org"], made["interview_id"]
    await R2.upload_media(iv, file=_upload(), media_kind="VIDEO",
                          part_number=1, duration_ms=1000,
                          actor=_Actor(org), db=db)

    with pytest.raises(HTTPException) as exc:
        await R2.stream_media(iv, 1, actor=_Actor(org, "employee"), db=db)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_another_tenant_cannot_stream_the_file(db):
    from app.api.routers import interview_v2 as R2
    a = await _make(db)
    b = await _make(db)
    await R2.upload_media(a["interview_id"], file=_upload(), media_kind="VIDEO",
                          part_number=1, duration_ms=1000,
                          actor=_Actor(a["org"]), db=db)

    with pytest.raises(HTTPException) as exc:
        await R2.stream_media(a["interview_id"], 1,
                              actor=_Actor(b["org"]), db=db)
    assert exc.value.status_code == 404
