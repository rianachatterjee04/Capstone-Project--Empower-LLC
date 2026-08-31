"""ORM for the interview domain.

These map migrations/20260829_interview_domain.sql. The SQL file is
authoritative -- it is what runs against a real database, and
tests/test_interview_schema.py asserts the two agree rather than trusting that
they do.

They reuse `app.db.models.Base` on purpose. A second declarative base would
give the interview tables their own metadata, and `create_all` would then
produce a schema that silently disagrees with the rest of HR.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, ForeignKey, Integer, Numeric,
                        String, Text, UniqueConstraint, func)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _org() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.orgs.id", ondelete="CASCADE"), nullable=False)


class InterviewConsent(Base):
    __tablename__ = "interview_consents"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False)

    consent_interview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_audio: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_video: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_transcript: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consent_ai_analysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disclosure_text: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="en-US")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    @property
    def permits_recording(self) -> bool:
        """Consent to be interviewed is not consent to be recorded."""
        return bool(self.granted_at and not self.withdrawn_at
                    and self.consent_interview
                    and (self.consent_audio or self.consent_video))


class Interview(Base):
    __tablename__ = "interviews"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    job_posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.job_postings.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False)
    consent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_consents.id", ondelete="SET NULL"))

    status: Mapped[str] = mapped_column(Text, nullable=False, default="DRAFT")
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="ASYNC_AI")
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Whether the media held for this interview is the WHOLE recording.
    #: NOT_CAPTURED / CAPTURING / SEALED / INCOMPLETE -- see
    #: `media.assess_completeness`. A RecordingAsset row existing is not the
    #: same as a recording being complete, and only SEALED says it is.
    recording_state: Mapped[str] = mapped_column(
        Text, nullable=False, default="NOT_CAPTURED")
    #: How many parts the CLIENT says it produced. The server cannot know: a
    #: part that never arrived leaves no trace here.
    recording_parts_expected: Mapped[int | None] = mapped_column(Integer)
    recording_sealed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True))
    recording_state_detail: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewAttempt(Base):
    __tablename__ = "interview_attempts"
    __table_args__ = (
        UniqueConstraint("interview_id", "attempt_number",
                         name="interview_attempts_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(Text)
    client_user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class CandidateClaim(Base):
    __tablename__ = "candidate_claims"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.candidates.id", ondelete="CASCADE"), nullable=False)
    job_posting_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.job_postings.id", ondelete="CASCADE"))

    claim_type: Mapped[str] = mapped_column(Text, nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str | None] = mapped_column(Text)

    quantity_value: Mapped[float | None] = mapped_column(Numeric)
    quantity_unit: Mapped[str | None] = mapped_column(Text)
    time_period: Mapped[str | None] = mapped_column(Text)

    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    source_ref: Mapped[str] = mapped_column(Text, nullable=False)
    source_span_start: Mapped[int | None] = mapped_column(Integer)
    source_span_end: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False)

    is_inference: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    extracted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    extractor: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewPlan(Base):
    __tablename__ = "interview_plans"
    __table_args__ = (
        UniqueConstraint("interview_id", name="interview_plans_one_per_interview"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)

    rubric_key: Mapped[str] = mapped_column(Text, nullable=False)
    rubric_version: Mapped[str] = mapped_column(Text, nullable=False)
    generated_by: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    fallback_reason: Mapped[str | None] = mapped_column(Text)

    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewCompetency(Base):
    __tablename__ = "interview_competencies"
    __table_args__ = (
        UniqueConstraint("plan_id", "competency_key",
                         name="interview_competencies_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_plans.id", ondelete="CASCADE"), nullable=False)

    competency_key: Mapped[str] = mapped_column(Text, nullable=False)
    competency_label: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)

    candidate_hook: Mapped[str | None] = mapped_column(Text)
    hook_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.candidate_claims.id", ondelete="SET NULL"))

    evidence_needed: Mapped[str] = mapped_column(Text, nullable=False)
    initial_question: Mapped[str] = mapped_column(Text, nullable=False)
    followup_objectives: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list)

    role_weight: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=1.0)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    min_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_probe_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint("interview_id", "sequence_number",
                         name="interview_questions_seq_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_attempts.id", ondelete="SET NULL"))
    competency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_competencies.id", ondelete="SET NULL"))
    provoking_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.candidate_claims.id", ondelete="SET NULL"))
    parent_answer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    probe_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_kind: Mapped[str] = mapped_column(Text, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(Text)

    generated_by: Mapped[str] = mapped_column(Text, nullable=False, default="deterministic")
    model_name: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    fallback_reason: Mapped[str | None] = mapped_column(Text)

    asked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewAnswer(Base):
    __tablename__ = "interview_answers"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_attempts.id", ondelete="SET NULL"))
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_questions.id", ondelete="CASCADE"), nullable=False)

    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    recording_start_ms: Mapped[int | None] = mapped_column(Integer)
    recording_end_ms: Mapped[int | None] = mapped_column(Integer)

    is_substantive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    non_answer_kind: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class RecordingAsset(Base):
    __tablename__ = "recording_assets"
    __table_args__ = (
        UniqueConstraint("interview_id", "media_kind", "part_number",
                         name="recording_assets_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_attempts.id", ondelete="SET NULL"))

    part_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    media_kind: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)

    storage_kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_ref: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(Text)
    timeline_offset_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_until: Mapped[date | None] = mapped_column(Date)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_attempts.id", ondelete="SET NULL"))
    answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_answers.id", ondelete="SET NULL"))
    recording_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.recording_assets.id", ondelete="SET NULL"))

    speaker: Mapped[str] = mapped_column(Text, nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    asr_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.transcript_segments.id", ondelete="SET NULL"))
    corrected_by: Mapped[str | None] = mapped_column(Text)
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    source: Mapped[str] = mapped_column(Text, nullable=False, default="ASR")
    #: WHICH instrument produced it. `source` says the kind (ASR/HUMAN);
    #: this says whether the text came from the candidate's browser or from
    #: the server reading the media. NULL means unrecorded -- never "assume
    #: the trustworthy one".
    asr_adapter: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewEvidence(Base):
    __tablename__ = "interview_evidence"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)

    competency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_competencies.id", ondelete="SET NULL"))
    competency_key: Mapped[str] = mapped_column(Text, nullable=False)
    claim_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.candidate_claims.id", ondelete="SET NULL"))
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_questions.id", ondelete="SET NULL"))
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_answers.id", ondelete="CASCADE"), nullable=False)
    transcript_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.transcript_segments.id", ondelete="SET NULL"))

    polarity: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_kind: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_start_ms: Mapped[int | None] = mapped_column(Integer)
    quote_end_ms: Mapped[int | None] = mapped_column(Integer)

    strength: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False, default=0.5)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)

    extracted_by: Mapped[str] = mapped_column(Text, nullable=False, default="deterministic")
    model_name: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class ClaimVerification(Base):
    __tablename__ = "claim_verifications"
    __table_args__ = (
        UniqueConstraint("interview_id", "claim_id",
                         name="claim_verifications_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.candidate_claims.id", ondelete="CASCADE"), nullable=False)

    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    established_text: Mapped[str | None] = mapped_column(Text)
    established_value: Mapped[float | None] = mapped_column(Numeric)
    established_unit: Mapped[str | None] = mapped_column(Text)

    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class CompetencyAssessment(Base):
    __tablename__ = "competency_assessments"
    __table_args__ = (
        UniqueConstraint("interview_id", "competency_key",
                         name="competency_assessments_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)
    competency_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_competencies.id", ondelete="SET NULL"))
    competency_key: Mapped[str] = mapped_column(Text, nullable=False)

    state: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(Numeric(4, 2))
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    missing_evidence: Mapped[str | None] = mapped_column(Text)

    supporting_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradicting_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    assessed_by: Mapped[str] = mapped_column(Text, nullable=False, default="deterministic")
    model_name: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewScorecard(Base):
    __tablename__ = "interview_scorecards"
    __table_args__ = (
        UniqueConstraint("interview_id", name="interview_scorecards_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)

    rubric_key: Mapped[str] = mapped_column(Text, nullable=False)
    rubric_version: Mapped[str] = mapped_column(Text, nullable=False)

    overall_state: Mapped[str] = mapped_column(Text, nullable=False)
    overall_score: Mapped[float | None] = mapped_column(Numeric(4, 2))
    overall_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))

    completeness_state: Mapped[str] = mapped_column(Text, nullable=False)
    uncovered_required: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    decision_authority: Mapped[str] = mapped_column(
        Text, nullable=False, default="RECRUITER_DECISION_SUPPORT")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewSummary(Base):
    __tablename__ = "interview_summaries"
    __table_args__ = (
        UniqueConstraint("interview_id", name="interview_summaries_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)
    scorecard_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_scorecards.id", ondelete="SET NULL"))

    headline: Mapped[str] = mapped_column(Text, nullable=False)
    overall_assessment: Mapped[str] = mapped_column(Text, nullable=False)

    strengths: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    weaknesses: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: Scored, at the bar, and not among the strongest four. Without this the
    #: fifth-best competency was assessed and then absent from the summary.
    also_assessed: Mapped[list] = mapped_column(JSONB, nullable=False,
                                                default=list)
    contradictions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    unresolved_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    recommended_followup: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    generated_by: Mapped[str] = mapped_column(Text, nullable=False, default="deterministic")
    model_name: Mapped[str | None] = mapped_column(Text)
    model_version: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewEvent(Base):
    __tablename__ = "interview_events"
    __table_args__ = {"schema": "public"}

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    interview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interviews.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.interview_attempts.id", ondelete="SET NULL"))

    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_kind: Mapped[str] = mapped_column(Text, nullable=False)
    actor_ref: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class InterviewRoleConfig(Base):
    __tablename__ = "interview_role_configs"
    __table_args__ = (
        UniqueConstraint("job_posting_id", name="interview_role_configs_unique"),
        {"schema": "public"},
    )

    id: Mapped[uuid.UUID] = _pk()
    org_id: Mapped[uuid.UUID] = _org()
    job_posting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("public.job_postings.id", ondelete="CASCADE"), nullable=False)

    rubric_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    required_competencies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    competency_weights: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    must_ask_questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    preferred_experience: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    hiring_manager_notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


#: Every interview-domain table, for the schema-conformance test.
INTERVIEW_TABLES = (
    "interview_consents", "interviews", "interview_attempts", "candidate_claims",
    "interview_plans", "interview_competencies", "interview_questions",
    "interview_answers", "recording_assets", "transcript_segments",
    "interview_evidence", "claim_verifications", "claim_verification_evidence",
    "competency_assessments", "assessment_evidence", "interview_scorecards",
    "interview_summaries", "interview_events", "interview_role_configs",
)
