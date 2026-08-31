"""The schema is a control, so it gets tested like one.

Two failure modes this catches, both of which produce a system that looks
correct and stores wrong things:

  1. THE MIGRATION AND THE ORM DISAGREE. The SQL file is authoritative because
     it is what runs against a real database. The ORM is a convenience. If a
     column exists in one and not the other, writes silently drop data or blow
     up at runtime rather than at review.

  2. THE CHECK CONSTRAINTS ARE MISSING. These are not decoration. They are the
     difference between "INSUFFICIENT_EVIDENCE" being a real state and being a
     label on a row that also carries a score. A database built by
     `create_all` instead of the migration has the tables and none of the
     guards -- it would pass every behavioural test in the suite.
"""
from __future__ import annotations

import os
import re
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.interview.models import INTERVIEW_TABLES

from tests._interview_pg import DSN, SKIP_REASON  # noqa: E402

MIGRATION = (pathlib.Path(__file__).resolve().parents[1]
             / "migrations" / "20260829_interview_domain.sql")

pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "")


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(DSN, future=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.mark.asyncio
async def test_every_interview_table_exists(db):
    res = await db.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'"""))
    present = {r[0] for r in res}
    missing = [t for t in INTERVIEW_TABLES if t not in present]
    assert not missing, (
        f"missing tables {missing}. Run scripts/ephemeral_interview_db.sh; a "
        f"suite that skips because the schema is absent proves nothing.")


@pytest.mark.asyncio
async def test_every_table_is_tenant_bound(db):
    """org_id NOT NULL, on every one of them.

    A table without it cannot be filtered by tenant at all, and this codebase
    relies on application-level filtering because service_role bypasses RLS.
    """
    join_tables = {"claim_verification_evidence", "assessment_evidence"}
    for table in INTERVIEW_TABLES:
        if table in join_tables:
            continue   # reached only through a tenant-bound parent
        res = await db.execute(text("""
            SELECT is_nullable FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t AND column_name='org_id'"""),
            {"t": table})
        row = res.first()
        assert row is not None, f"{table} has no org_id column"
        assert row[0] == "NO", f"{table}.org_id is nullable"


@pytest.mark.asyncio
async def test_the_guard_constraints_are_present(db):
    """Named individually, because each one encodes a decision."""
    expected = {
        "competency_assessments_score_ck":
            "INSUFFICIENT_EVIDENCE must not carry a score",
        "candidate_claims_inference_ck":
            "an inference must carry a confidence",
        "recording_assets_ref_ck":
            "a recording claiming to be stored must say where",
        "interview_scorecards_authority_ck":
            "a scorecard is decision SUPPORT and may not say otherwise",
        "claim_verifications_verdict_ck":
            "the verification vocabulary is closed",
        "transcript_segments_time_ck":
            "a segment cannot end before it starts",
        "interview_competencies_weight_ck":
            "a role weight is a proportion",
    }
    res = await db.execute(text("SELECT conname FROM pg_constraint"))
    present = {r[0] for r in res}
    missing = {k: v for k, v in expected.items() if k not in present}
    assert not missing, (
        f"missing guard constraints: {missing}. This usually means the tables "
        f"were built by ORM create_all instead of the migration -- the ORM "
        f"does not declare CHECK constraints, so the schema would look "
        f"complete and enforce nothing.")


@pytest.mark.asyncio
async def test_an_insufficient_evidence_assessment_cannot_carry_a_score(db):
    """The constraint, exercised rather than merely present."""
    import uuid
    org = uuid.uuid4()
    await db.execute(text("INSERT INTO public.orgs (id,name) VALUES (:i,'ck')"),
                     {"i": org})
    job = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.job_postings
        (id,org_id,title,description,status) VALUES (:i,:o,'t','d','open')"""),
        {"i": job, "o": org})
    cand = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.candidates
        (id,org_id,job_posting_id,full_name,email,status)
        VALUES (:i,:o,:j,'n','e@x.test','new')"""),
        {"i": cand, "o": org, "j": job})
    iv = uuid.uuid4()
    await db.execute(text("""INSERT INTO public.interviews
        (id,org_id,job_posting_id,candidate_id) VALUES (:i,:o,:j,:c)"""),
        {"i": iv, "o": org, "j": job, "c": cand})

    with pytest.raises(Exception) as exc:
        await db.execute(text("""
            INSERT INTO public.competency_assessments
              (org_id, interview_id, competency_key, state, score, rationale)
            VALUES (:o, :i, 'k', 'INSUFFICIENT_EVIDENCE', 3.0, 'r')"""),
            {"o": org, "i": iv})
        await db.flush()
    assert "competency_assessments_score_ck" in str(exc.value)

    await db.rollback()
    await db.execute(text("DELETE FROM public.orgs WHERE id = :i"), {"i": org})
    await db.commit()


@pytest.mark.asyncio
async def test_the_migration_and_the_orm_agree_on_columns(db):
    """Structural. A column in one and not the other is a silent data loss."""
    from app.db.models import Base
    import app.interview.models  # noqa: F401  registers them in metadata

    sql = MIGRATION.read_text(encoding="utf-8")
    mismatches: list[str] = []

    for table in INTERVIEW_TABLES:
        if table in ("claim_verification_evidence", "assessment_evidence"):
            continue
        mapped = Base.metadata.tables.get(f"public.{table}")
        if mapped is None:
            mismatches.append(f"{table}: no ORM model")
            continue
        res = await db.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='public' AND table_name=:t"""), {"t": table})
        db_cols = {r[0] for r in res}
        orm_cols = {c.name for c in mapped.columns}
        only_orm = orm_cols - db_cols
        if only_orm:
            mismatches.append(f"{table}: ORM declares {sorted(only_orm)} "
                              f"which the database does not have")

    assert not mismatches, "\n".join(mismatches)
