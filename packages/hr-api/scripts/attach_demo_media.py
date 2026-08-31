#!/usr/bin/env python3
"""Attach the demo recording to a seeded interview.

WHY THE DEMO SHIPS A RECORDING AT ALL
The recruiter debrief's headline interaction is "click any assessment and the
recording seeks to the moment the candidate said it". A seeded demo with no
media demonstrates the empty state, which is honest and sells nothing.

WHAT THIS MEDIA IS, EXACTLY
Real `MediaRecorder` output -- three WebM parts on one timeline, produced by
recording a canvas in a browser. It is SYNTHETIC: no camera, no microphone, no
person. Every byte of the path AFTER `getUserMedia` is the same code a real
capture takes: the recorder, the container, the upload, the duration repair,
the storage, the range serving and the player. `getUserMedia` itself is the one
link this does not exercise, and the demo says so rather than implying
otherwise.

The parts are 24 seconds each and the seeded answer boundaries are 8 seconds
apart. This attaches AS MANY parts as the interview needs, cycling the fixture
files, so every evidence timecode lands inside the media -- which is the point.
A boundary past the end of the recording makes the player refuse to seek and
say why. That refusal is correct behaviour, and a demo should not be the thing
constantly triggering it: at a fixed three parts it did, on 10 of 36 evidence
items, because a twelve-answer interview runs to 88s and three parts cover 72s.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import os
import pathlib
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "dummy")

from sqlalchemy import select, text                              # noqa: E402
from sqlalchemy.ext.asyncio import (async_sessionmaker,          # noqa: E402
                                    create_async_engine)

from app.interview import media as MED                           # noqa: E402
from app.interview import models as M                            # noqa: E402

MEDIA_DIR = pathlib.Path(__file__).parent.parent / "demo" / "media"
PART_MS = 24_000


async def attach(dsn: str, org_id: str, candidate: str) -> int:
    engine = create_async_engine(dsn, future=True)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        org = uuid.UUID(org_id)
        row = (await db.execute(text("""
            SELECT i.id, i.consent_id
            FROM public.interviews i
            JOIN public.candidates c ON c.id = i.candidate_id
            WHERE i.org_id = :o AND c.full_name = :n
            ORDER BY i.created_at DESC LIMIT 1"""),
            {"o": org, "n": candidate})).first()
        if row is None:
            print(f"  no interview for {candidate!r}; nothing to attach")
            return 0
        interview_id, consent_id = row

        # Consent is checked at upload in the API for good reason; this writes
        # directly, so it checks here rather than skipping the question.
        if consent_id:
            c = (await db.execute(text("""
                SELECT consent_video, consent_audio
                FROM public.interview_consents WHERE id = :i"""),
                {"i": consent_id})).first()
            if not (c and (c[0] or c[1])):
                print("  the candidate did not consent to recording; "
                      "nothing attached")
                return 0

        fixtures = sorted(MEDIA_DIR.glob("part-*.webm"))
        if not fixtures:
            print(f"  no demo media in {MEDIA_DIR}")
            return 0

        # HOW MUCH MEDIA THIS INTERVIEW ACTUALLY NEEDS.
        #
        # This used to attach exactly one part per fixture file -- three parts,
        # 72 seconds -- on the reasoning quoted at the top of this file: the
        # boundaries are 8 seconds apart, so everything lands inside the media.
        # That is true up to nine answers. The seeder produces twelve, whose
        # boundaries run to 88s, so the last three sat past the end of the
        # recording and 10 of 36 evidence items refused to seek: 28% of the
        # clicks in the demo whose headline is "click any assessment and the
        # recording plays that moment".
        #
        # The refusal was correct -- a player sent past the end would show the
        # wrong moment -- and the demo should not be the thing provoking it.
        # So the media is sized from the interview instead of assumed: cover
        # the last boundary, plus one part of headroom so the final answer has
        # somewhere to play rather than starting on the last frame.
        last_ms = (await db.execute(text("""
            SELECT COALESCE(MAX(GREATEST(COALESCE(recording_start_ms, 0),
                                         COALESCE(recording_end_ms, 0))), 0)
            FROM public.interview_answers
            WHERE org_id = :o AND interview_id = :i"""),
            {"o": org, "i": interview_id})).scalar() or 0
        needed = max(len(fixtures), math.ceil((last_ms + PART_MS) / PART_MS))

        # The fixture files cycle. They are synthetic canvas recordings with no
        # person in them, so reusing one as a later part invents nothing that
        # was not already invented -- and the alternative, a demo that trips its
        # own refusal path on a quarter of its clicks, sells the opposite of
        # what it is meant to show.
        parts = [fixtures[i % len(fixtures)] for i in range(needed)]

        # Idempotent: clear whatever is there, then write this set.
        #
        # The FILES have to go too, not just the rows. store_part refuses to
        # overwrite a part whose bytes differ -- correctly, because transcript
        # segments may already point into it -- so deleting only the rows made
        # this script work when re-run with the SAME media and fail with
        # PART_ALREADY_EXISTS the moment the demo footage changed. The seeder
        # owns this interview's media end to end, which is exactly the case
        # where clearing it is safe and the guard is not.
        await db.execute(text("""DELETE FROM public.recording_assets
            WHERE org_id = :o AND interview_id = :i"""),
            {"o": org, "i": interview_id})
        await db.commit()
        removed = MED.delete_interview_media(org_id=org, interview_id=interview_id)
        if removed:
            print(f"  cleared {removed} previously stored file(s)")

        attached = 0
        for n, path in enumerate(parts, start=1):
            data = path.read_bytes()
            # THE DURATION REPAIR, the same call the upload endpoint makes.
            #
            # This script stored the fixture bytes raw, which meant the demo did
            # NOT take "the same code a real capture takes" the way the header
            # of this file claims. It went unnoticed only because the committed
            # fixtures happened to already carry a Duration. The moment the
            # footage was regenerated -- live MediaRecorder output, unknown-size
            # Segment, no Duration, as a real capture produces -- the player
            # reported duration Infinity and refused to seek at all.
            repair = MED.ensure_webm_duration(data, PART_MS)
            data = repair.data
            # `store_part` only refuses when the bytes on disk DIFFER, so
            # re-attaching the same demo media is idempotent by construction
            # and the duplicate guard stays load-bearing for real captures.
            stored = MED.store_part(
                org_id=org, interview_id=interview_id, data=data,
                mime_type="video/webm", media_kind="VIDEO",
                part_number=n, timeline_offset_ms=(n - 1) * PART_MS,
                duration_ms=PART_MS)
            db.add(M.RecordingAsset(org_id=org, interview_id=interview_id,
                                    **stored.as_row()))
            attached += 1
        await db.commit()
        # THE TRANSCRIPT, LABELLED AS WHAT IT IS.
        #
        # Without segments the demo shows record -> (nothing) -> assess ->
        # click -> watch, the alignment endpoint reports aligned=false because
        # there is nothing to align, and the transcript panel is empty on the
        # page whose whole argument is that the assessment came from what the
        # candidate said.
        #
        # These are NOT ASR output and must not claim to be. `source` has a
        # DEMO_FIXTURE value for exactly this, and the adapter is recorded as
        # `demo-fixture`, which the provenance summary grades as a fixture
        # rather than quietly ranking it beside a real transcription. The text
        # is the seeded answer verbatim and the offsets are the seeded answer
        # boundaries -- the same numbers the evidence cites -- so the alignment
        # check has something real to verify and can still fail.
        await db.execute(text("""DELETE FROM public.transcript_segments
            WHERE org_id = :o AND interview_id = :i"""),
            {"o": org, "i": interview_id})

        answers = (await db.execute(text("""
            SELECT id, answer_text, recording_start_ms, recording_end_ms
            FROM public.interview_answers
            WHERE org_id = :o AND interview_id = :i
              AND recording_start_ms IS NOT NULL
            ORDER BY recording_start_ms"""),
            {"o": org, "i": interview_id})).mappings().all()

        by_part = {r.part_number: r.id for r in (await db.execute(
            select(M.RecordingAsset).where(
                M.RecordingAsset.org_id == org,
                M.RecordingAsset.interview_id == interview_id))).scalars().all()}

        segments = 0
        for n, a in enumerate(answers, start=1):
            start = int(a["recording_start_ms"])
            end = int(a["recording_end_ms"] or start)
            part_no = start // PART_MS + 1
            db.add(M.TranscriptSegment(
                org_id=org, interview_id=interview_id, answer_id=a["id"],
                recording_asset_id=by_part.get(part_no),
                speaker="CANDIDATE", sequence_number=n,
                start_ms=start, end_ms=end, text=a["answer_text"],
                source="DEMO_FIXTURE", asr_adapter="demo-fixture"))
            segments += 1
        await db.commit()

        # SEAL IT. The recruiter page otherwise shows "This recording was never
        # sealed -- 5 part(s) received and the client has not said how many it
        # produced", which is the honest answer to a genuinely unsealed
        # recording and the wrong thing for a demo to be demonstrating. This
        # script IS the client for these parts and knows exactly how many it
        # wrote, so it says so, the same way a real capture does at finalize.
        await db.execute(text("""UPDATE public.interviews
            SET recording_parts_expected = :n
            WHERE org_id = :o AND id = :i"""),
            {"n": attached, "o": org, "i": interview_id})
        await db.commit()

        covered = attached * PART_MS
        print(f"  attached {attached} part(s), {covered // 1000}s, to "
              f"{candidate}'s interview")
        if last_ms:
            print(f"  last answer boundary {last_ms // 1000}s — "
                  f"{'covered' if last_ms < covered else 'NOT COVERED'}")
        print(f"  sealed at {attached} part(s) — the recruiter page will "
              f"report the recording as complete")
        print(f"  {segments} transcript segment(s), source=DEMO_FIXTURE "
              f"(not ASR, and reported as such)")
        if len(parts) > len(fixtures):
            print(f"  ({len(fixtures)} fixture file(s) cycled to fill "
                  f"{attached} parts)")
        print(f"  {interview_id}")
    await engine.dispose()
    return attached


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dsn", default=(os.environ.get("FINTRA_INTERVIEW_PG_DSN")
                                      or os.environ.get("FINTRA_HR_PG_DSN", "")))
    ap.add_argument("--org", default="11111111-1111-1111-1111-111111111111")
    ap.add_argument("--candidate", default="Marcus Delgado")
    args = ap.parse_args()
    if not args.dsn:
        raise SystemExit("set FINTRA_INTERVIEW_PG_DSN")
    attached = asyncio.run(attach(args.dsn, args.org, args.candidate))
    if not attached:
        # LOUD, because seed_demo.sh runs this as a step and then prints READY.
        # Returning 0 here meant a candidate rename in either seeder silently
        # stripped the recording out of the demo while the build still
        # announced "the demo media, so the debrief's click has somewhere to
        # go" -- and the five-minute path ends on "click any assessment, the
        # recording seeks to that moment".
        print(f"  NOTHING WAS ATTACHED for {args.candidate!r}. The demo has no "
              f"recording, so the debrief's click has nowhere to go.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
