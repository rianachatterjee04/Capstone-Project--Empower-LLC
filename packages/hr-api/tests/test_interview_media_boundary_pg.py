"""The media boundary, proven at the endpoint rather than at the helper.

`read_part` already has unit coverage: a ref from another tenant is refused and
so is a traversal. That proves the helper. It does NOT prove the ENDPOINT calls
it, calls it with the caller's org rather than the row's, or reaches it at all --
and the endpoint is the only thing an attacker can actually send a request to.

Two controls guard this file, and they are separate on purpose:

  LAYER 1  the row query is scoped to `actor.org_id`, so another tenant's part
           is simply not found.
  LAYER 2  the resolved path must sit inside the caller's media directory, which
           catches what LAYER 1 structurally cannot: a row in YOUR OWN org whose
           storage_ref points into someone else's directory.

Layer 2 is the one that is easy to believe is redundant. It is not: the test
below builds exactly that row, watches layer 1 pass it, and requires the read to
be refused anyway. Delete layer 2 and one org streams another org's video with
every tenancy filter in the request path still green.
"""
from __future__ import annotations

import io
import uuid

import pytest
import pytest_asyncio
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.interview import media as MED
from app.interview import models as M
from app.interview import repository as R
from app.interview import runner
from tests._interview_pg import DSN, SKIP_REASON

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")

WEBM = b"\x1a\x45\xdf\xa3" + bytes(range(256)) * 8      # known, checkable bytes
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


def _req(range_header: str | None = None) -> Request:
    headers = [(b"range", range_header.encode())] if range_header else []
    return Request({"type": "http", "method": "GET", "path": "/",
                    "query_string": b"", "headers": headers})


async def _tenant(db):
    """One org with a consented, prepared interview ready to receive media."""
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,:n)"),
                     {"i": org, "n": f"bnd-{org.hex[:6]}"})
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
        policy_version="2026.08", video=True, audio=True)
    await db.commit()
    prepared = await runner.prepare(
        db, org_id=org, job_posting_id=job, candidate_id=cand,
        job_title="Senior Software Engineer", resume_text=RESUME,
        consent_id=consent.id)
    await db.commit()
    return {"org": org, "interview_id": prepared["interview"].id}


async def _uploaded(db, tenant, part=1):
    from app.api.routers import interview_v2 as R2
    await R2.upload_media(tenant["interview_id"], file=_upload(),
                          media_kind="VIDEO", part_number=part,
                          actor=_Actor(tenant["org"]), db=db)
    await db.commit()
    row = (await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.interview_id == tenant["interview_id"],
        M.RecordingAsset.part_number == part))).scalar_one()
    return row


# ===========================================================================
# Positive control -- the owner CAN read their own media
# ===========================================================================

@pytest.mark.asyncio
async def test_positive_control_the_owning_recruiter_gets_the_bytes(db):
    """Without this, an endpoint that refused EVERYTHING would satisfy every
    refusal test below and look like flawless security."""
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    await _uploaded(db, a)

    resp = await R2.stream_media(a["interview_id"], 1, request=_req(),
                                 actor=_Actor(a["org"]), db=db)
    assert resp.status_code == 200
    assert resp.body == WEBM
    assert resp.headers.get("accept-ranges") == "bytes"


# ===========================================================================
# LAYER 1 -- another tenant's part is not found, and storage is never touched
# ===========================================================================

@pytest.mark.asyncio
async def test_layer1_cross_tenant_request_is_404_at_the_endpoint(db):
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    b = await _tenant(db)
    await _uploaded(db, a)

    with pytest.raises(HTTPException) as exc:
        await R2.stream_media(a["interview_id"], 1, request=_req(),
                              actor=_Actor(b["org"]), db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_layer1_refuses_before_storage_is_consulted(db, monkeypatch):
    """Attribution: layer 1 must stop this on its own. If the refusal only
    happens because layer 2 later objects, then layer 1 is not doing the work
    this test claims it does, and the two layers are not independent."""
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    b = await _tenant(db)
    await _uploaded(db, a)

    def _boom(*args, **kwargs):
        raise AssertionError("storage was read for a row outside the caller's org")
    monkeypatch.setattr(MED, "read_part", _boom)

    with pytest.raises(HTTPException) as exc:
        await R2.stream_media(a["interview_id"], 1, request=_req(),
                              actor=_Actor(b["org"]), db=db)
    assert exc.value.status_code == 404


# ===========================================================================
# LAYER 2 -- the case layer 1 structurally cannot catch
# ===========================================================================

@pytest.mark.asyncio
async def test_layer2_own_row_pointing_at_another_tenants_file_is_refused(db):
    """B owns this row. The org filter passes. The bytes are A's.

    This is the whole reason the path check exists, and the only test in the
    suite where its absence is visible: every tenancy filter in the request
    path is satisfied here.
    """
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    b = await _tenant(db)
    a_row = await _uploaded(db, a)

    # A row legitimately owned by B, deliberately referencing A's file.
    stolen = M.RecordingAsset(
        id=uuid.uuid4(), org_id=b["org"], interview_id=b["interview_id"],
        part_number=1, media_kind="VIDEO", mime_type="video/webm",
        storage_kind=a_row.storage_kind,
        storage_ref=a_row.storage_ref,          # <-- A's path
        byte_size=a_row.byte_size, timeline_offset_ms=0)
    db.add(stolen)
    await db.commit()

    # Layer 1 finds it: same org, same interview, same part.
    found = (await db.execute(select(M.RecordingAsset).where(
        M.RecordingAsset.org_id == b["org"],
        M.RecordingAsset.interview_id == b["interview_id"],
        M.RecordingAsset.part_number == 1))).scalar_one()
    assert found.storage_ref == a_row.storage_ref, "setup did not build the case"

    with pytest.raises(HTTPException) as exc:
        await R2.stream_media(b["interview_id"], 1, request=_req(),
                              actor=_Actor(b["org"]), db=db)
    assert exc.value.status_code == 404
    detail = exc.value.detail
    assert isinstance(detail, dict) and detail.get("code") == "MEDIA_OUTSIDE_TENANT"


@pytest.mark.asyncio
async def test_layer2_is_load_bearing_not_redundant(db, monkeypatch):
    """Mutation control. Neuter ONLY the path check; the previous test's case
    must then leak A's bytes to B. If it does not, the refusal above was coming
    from somewhere else and layer 2 has not been shown to do anything."""
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    b = await _tenant(db)
    a_row = await _uploaded(db, a)

    stolen = M.RecordingAsset(
        id=uuid.uuid4(), org_id=b["org"], interview_id=b["interview_id"],
        part_number=1, media_kind="VIDEO", mime_type="video/webm",
        storage_kind=a_row.storage_kind, storage_ref=a_row.storage_ref,
        byte_size=a_row.byte_size, timeline_offset_ms=0)
    db.add(stolen)
    await db.commit()

    import pathlib
    monkeypatch.setattr(
        MED, "read_part",
        lambda ref, *, org_id: pathlib.Path(ref).read_bytes())   # the mutant

    resp = await R2.stream_media(b["interview_id"], 1, request=_req(),
                                 actor=_Actor(b["org"]), db=db)
    assert resp.body == WEBM, (
        "with the tenant path check removed, B received A's recording. That is "
        "what layer 2 is preventing, and it is not something the org filter on "
        "the row can prevent.")


# ===========================================================================
# Seeking -- requested byte range vs the range actually served
# ===========================================================================

@pytest.mark.asyncio
async def test_a_range_request_serves_exactly_the_requested_bytes(db):
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    await _uploaded(db, a)
    total = len(WEBM)

    for start, end in [(0, 9), (100, 199), (total - 5, total - 1)]:
        resp = await R2.stream_media(
            a["interview_id"], 1, request=_req(f"bytes={start}-{end}"),
            actor=_Actor(a["org"]), db=db)
        assert resp.status_code == 206, f"range {start}-{end} was not partial"
        assert resp.body == WEBM[start:end + 1], (
            f"asked for bytes {start}-{end} and got different bytes: a player "
            f"seeking here would land somewhere else")
        assert resp.headers["content-range"] == f"bytes {start}-{end}/{total}"
        assert int(resp.headers["content-length"]) == end - start + 1


@pytest.mark.asyncio
async def test_an_open_ended_range_runs_to_the_end(db):
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    await _uploaded(db, a)
    total = len(WEBM)
    resp = await R2.stream_media(a["interview_id"], 1,
                                 request=_req("bytes=64-"),
                                 actor=_Actor(a["org"]), db=db)
    assert resp.status_code == 206
    assert resp.body == WEBM[64:]
    assert resp.headers["content-range"] == f"bytes 64-{total - 1}/{total}"


@pytest.mark.asyncio
async def test_an_unsatisfiable_range_is_416_not_a_silent_full_body(db):
    """A player that asks past the end must be told, not handed the whole file
    and left to believe it seeked."""
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    await _uploaded(db, a)
    total = len(WEBM)
    resp = await R2.stream_media(a["interview_id"], 1,
                                 request=_req(f"bytes={total + 50}-{total + 99}"),
                                 actor=_Actor(a["org"]), db=db)
    assert resp.status_code == 416
    assert resp.headers["content-range"] == f"bytes */{total}"


@pytest.mark.asyncio
async def test_an_unparseable_range_is_ignored_and_the_whole_body_is_served(db):
    """RFC 9110 permits a server to IGNORE or to REJECT an invalid range, so
    both answers are conformant and the point of this test is to pin down which
    one this server gives -- a player's behaviour depends on it.

    The contract here is a coherent split: a header this server cannot parse at
    all is ignored (200, whole body, as if no Range had been sent), while a
    well-formed range that cannot be satisfied gets 416. Garbage is not treated
    as a request for nothing.
    """
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    await _uploaded(db, a)
    for bad in ["bytes=abc-def", "chunks=0-10", "bytes=", "not-a-range"]:
        resp = await R2.stream_media(a["interview_id"], 1, request=_req(bad),
                                     actor=_Actor(a["org"]), db=db)
        assert resp.status_code == 200, f"{bad!r} should be ignored, not fatal"
        assert resp.body == WEBM


@pytest.mark.asyncio
async def test_an_inverted_range_is_rejected_rather_than_ignored(db):
    """`bytes=5-2` parses but describes nothing. This server rejects it, which
    is the stricter of the two conformant options; asserted so the choice is a
    decision on the record rather than an accident.
    """
    from app.api.routers import interview_v2 as R2
    a = await _tenant(db)
    await _uploaded(db, a)
    resp = await R2.stream_media(a["interview_id"], 1, request=_req("bytes=5-2"),
                                 actor=_Actor(a["org"]), db=db)
    assert resp.status_code == 416
    assert resp.headers["content-range"] == f"bytes */{len(WEBM)}"
