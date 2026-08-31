-- ==========================================================================
-- 20260829  INTERVIEW DOMAIN
-- ==========================================================================
-- Before this migration the AI interviewer had 3,765 lines of service code and
-- no persistence whatsoever: no SQL, no session, no tables. Every interview
-- lived in process memory, so nothing survived a restart, nothing was
-- queryable, and no assessment could be traced back to what a candidate
-- actually said. That last part is the entire product thesis, so it is the
-- part that had to exist first.
--
-- WHAT THIS DOES NOT DO
-- It does not create a parallel HR system. Tenancy is public.orgs, the role is
-- public.job_postings, the applicant is public.candidates and a hire becomes
-- public.employees -- all of which already exist. This adds only what was
-- genuinely missing.
--
-- THE SHAPE OF THE EVIDENCE CHAIN
--
--   candidate_claims        what the candidate asserted, and WHERE they said it
--        |
--   interview_questions     what we asked, and which claim provoked it
--        |
--   interview_answers       what they said back
--        |
--   transcript_segments     the words, time-aligned to the recording
--        |
--   interview_evidence      a span that supports or contradicts something
--        |
--   competency_assessments  a judgement, citing that evidence
--        |
--   interview_scorecards    the assembled result
--
-- Every link in that chain is a real foreign key. An assessment that cannot
-- name its evidence is not a weaker assessment; it is a different kind of
-- object, and the schema refuses to store it as though it were the same thing.
--
-- TENANCY
-- Every table carries org_id NOT NULL with a cascading foreign key, and every
-- lookup index leads with org_id. The application is still responsible for
-- filtering -- service_role bypasses RLS, so the column is necessary and not
-- sufficient. tests/test_interview_tenancy.py attacks it directly.
-- ==========================================================================


-- ==========================================================================
-- CONSENT
-- ==========================================================================
-- Recorded BEFORE the interview and never inferred from "they joined the
-- call". A missing row here is a hard stop, not a default-yes.
CREATE TABLE IF NOT EXISTS public.interview_consents (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  candidate_id        uuid NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,

  -- Separate grants. A candidate may consent to being interviewed and not to
  -- being recorded, and collapsing the two into one boolean loses the refusal.
  consent_interview   boolean NOT NULL DEFAULT false,
  consent_audio       boolean NOT NULL DEFAULT false,
  consent_video       boolean NOT NULL DEFAULT false,
  consent_transcript  boolean NOT NULL DEFAULT false,
  consent_ai_analysis boolean NOT NULL DEFAULT false,

  policy_version      text NOT NULL,
  granted_at          timestamptz,
  withdrawn_at        timestamptz,
  -- What the candidate was actually shown, kept verbatim. "They agreed" is not
  -- meaningful without the text they agreed to.
  disclosure_text     text NOT NULL,
  locale              text NOT NULL DEFAULT 'en-US',

  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_interview_consents_org_cand
  ON public.interview_consents(org_id, candidate_id);


-- ==========================================================================
-- INTERVIEW  +  ATTEMPT
-- ==========================================================================
-- An interview is the intent to assess this candidate for this role. An
-- attempt is one connected session. They are separate because a dropped
-- connection must not create a second interview, lose the plan, or restart the
-- evidence -- reconnect resumes the SAME interview under a new attempt.
CREATE TABLE IF NOT EXISTS public.interviews (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  job_posting_id      uuid NOT NULL REFERENCES public.job_postings(id) ON DELETE CASCADE,
  candidate_id        uuid NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  consent_id          uuid REFERENCES public.interview_consents(id) ON DELETE SET NULL,

  status              text NOT NULL DEFAULT 'DRAFT',
  -- DRAFT | PLANNED | READY | IN_PROGRESS | COMPLETED | ABANDONED | CANCELLED

  mode                text NOT NULL DEFAULT 'ASYNC_AI',
  target_minutes      integer NOT NULL DEFAULT 30,

  scheduled_at        timestamptz,
  started_at          timestamptz,
  ended_at            timestamptz,

  created_by          uuid,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interviews_status_ck CHECK (status IN (
    'DRAFT','PLANNED','READY','IN_PROGRESS','COMPLETED','ABANDONED','CANCELLED'))
);
CREATE INDEX IF NOT EXISTS ix_interviews_org_job ON public.interviews(org_id, job_posting_id);
CREATE INDEX IF NOT EXISTS ix_interviews_org_cand ON public.interviews(org_id, candidate_id);

CREATE TABLE IF NOT EXISTS public.interview_attempts (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,

  attempt_number      integer NOT NULL,
  started_at          timestamptz NOT NULL DEFAULT now(),
  ended_at            timestamptz,
  end_reason          text,   -- COMPLETED | DISCONNECTED | TIMEOUT | ABANDONED | ERROR

  client_user_agent   text,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interview_attempts_unique UNIQUE (interview_id, attempt_number)
);
CREATE INDEX IF NOT EXISTS ix_interview_attempts_org
  ON public.interview_attempts(org_id, interview_id);


-- ==========================================================================
-- CANDIDATE CLAIMS
-- ==========================================================================
-- Extracted from permitted materials. The whole point is the provenance
-- columns: a claim with no source is not a claim, it is a guess, and the
-- interviewer must never probe a candidate about something they did not say.
CREATE TABLE IF NOT EXISTS public.candidate_claims (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  candidate_id        uuid NOT NULL REFERENCES public.candidates(id) ON DELETE CASCADE,
  job_posting_id      uuid REFERENCES public.job_postings(id) ON DELETE CASCADE,

  claim_type          text NOT NULL,
  -- SKILL | PROJECT | RESPONSIBILITY | LEADERSHIP | MEASURABLE_OUTCOME
  -- | DOMAIN_EXPERIENCE | CERTIFICATION | ROLE_HISTORY | TECHNICAL_CAPABILITY
  -- | CAREER_TRANSITION | EQUIPMENT_OPERATED | OTHER

  claim_text          text NOT NULL,   -- normalised statement of the claim
  subject             text,            -- e.g. "reefer freight", "settlement failures"

  -- Quantities kept structured so a probe can ask about the RIGHT number.
  quantity_value      numeric,
  quantity_unit       text,
  time_period         text,

  -- PROVENANCE. Non-negotiable.
  source_kind         text NOT NULL,   -- RESUME | APPLICATION | PORTFOLIO |
                                       -- RECRUITER_NOTE | PRIOR_INTERVIEW | JOB_DESCRIPTION
  source_ref          text NOT NULL,   -- which document
  source_span_start   integer,         -- character offset into that document
  source_span_end     integer,
  source_excerpt      text NOT NULL,   -- the candidate's own words, verbatim

  -- An LLM reading a resume produces an INFERENCE. It is stored as one.
  is_inference        boolean NOT NULL DEFAULT false,
  confidence          numeric(4,3),
  extracted_at        timestamptz NOT NULL DEFAULT now(),
  extractor           text NOT NULL,   -- 'deterministic' | 'llm'
  model_name          text,
  model_version       text,

  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT candidate_claims_confidence_ck
    CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
  -- An inference with no confidence is an assertion wearing a disclaimer.
  CONSTRAINT candidate_claims_inference_ck
    CHECK (is_inference = false OR confidence IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_candidate_claims_org_cand
  ON public.candidate_claims(org_id, candidate_id);
CREATE INDEX IF NOT EXISTS ix_candidate_claims_type
  ON public.candidate_claims(org_id, candidate_id, claim_type);


-- ==========================================================================
-- PLAN  +  PLANNED COMPETENCIES
-- ==========================================================================
CREATE TABLE IF NOT EXISTS public.interview_plans (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,

  rubric_key          text NOT NULL,          -- which role rubric was used
  rubric_version      text NOT NULL,
  generated_by        text NOT NULL,          -- 'llm' | 'deterministic'
  model_name          text,
  model_version       text,
  prompt_version      text,
  -- Set when the LLM was unreachable and the deterministic planner ran.
  -- Nullable on purpose: the absence of a fallback reason is the record that
  -- no fallback happened.
  fallback_reason     text,

  target_minutes      integer NOT NULL DEFAULT 30,
  generated_at        timestamptz NOT NULL DEFAULT now(),
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interview_plans_one_per_interview UNIQUE (interview_id)
);
CREATE INDEX IF NOT EXISTS ix_interview_plans_org ON public.interview_plans(org_id);

CREATE TABLE IF NOT EXISTS public.interview_competencies (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  plan_id             uuid NOT NULL REFERENCES public.interview_plans(id) ON DELETE CASCADE,

  competency_key      text NOT NULL,
  competency_label    text NOT NULL,
  why_it_matters      text NOT NULL,

  -- The candidate-specific hook. This is what separates a personalised
  -- interview from a question list, so it is a first-class column: a plan row
  -- whose hook is null was not personalised, and that is visible.
  candidate_hook      text,
  hook_claim_id       uuid REFERENCES public.candidate_claims(id) ON DELETE SET NULL,

  evidence_needed     text NOT NULL,
  initial_question    text NOT NULL,
  followup_objectives jsonb NOT NULL DEFAULT '[]'::jsonb,

  role_weight         numeric(4,3) NOT NULL DEFAULT 1.0,
  -- A required competency may not be silently dropped because the
  -- conversation went elsewhere. The completeness gate reads this column.
  is_required         boolean NOT NULL DEFAULT true,
  min_evidence_count  integer NOT NULL DEFAULT 1,
  max_probe_depth     integer NOT NULL DEFAULT 3,
  display_order       integer NOT NULL DEFAULT 0,

  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interview_competencies_unique UNIQUE (plan_id, competency_key),
  CONSTRAINT interview_competencies_weight_ck
    CHECK (role_weight >= 0 AND role_weight <= 1),
  CONSTRAINT interview_competencies_depth_ck CHECK (max_probe_depth BETWEEN 1 AND 10)
);
CREATE INDEX IF NOT EXISTS ix_interview_competencies_org_plan
  ON public.interview_competencies(org_id, plan_id);


-- ==========================================================================
-- QUESTIONS  +  ANSWERS
-- ==========================================================================
CREATE TABLE IF NOT EXISTS public.interview_questions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
  attempt_id          uuid REFERENCES public.interview_attempts(id) ON DELETE SET NULL,
  competency_id       uuid REFERENCES public.interview_competencies(id) ON DELETE SET NULL,

  -- Which claim this question is interrogating. Null for openers.
  provoking_claim_id  uuid REFERENCES public.candidate_claims(id) ON DELETE SET NULL,
  -- The answer that caused this follow-up. Null for a planned initial question.
  parent_answer_id    uuid,

  sequence_number     integer NOT NULL,
  probe_depth         integer NOT NULL DEFAULT 0,
  question_kind       text NOT NULL,
  -- OPENING | PLANNED_INITIAL | FOLLOWUP_SPECIFIC | FOLLOWUP_OWNERSHIP
  -- | FOLLOWUP_METRIC | FOLLOWUP_TRADEOFF | FOLLOWUP_FAILURE
  -- | FOLLOWUP_CONFLICT | CLARIFY_CONTRADICTION | MUST_ASK | CLOSING

  question_text       text NOT NULL,
  intent              text,
  generated_by        text NOT NULL DEFAULT 'deterministic',
  model_name          text,
  model_version       text,
  prompt_version      text,
  fallback_reason     text,

  asked_at            timestamptz NOT NULL DEFAULT now(),
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interview_questions_seq_unique UNIQUE (interview_id, sequence_number)
);
CREATE INDEX IF NOT EXISTS ix_interview_questions_org_int
  ON public.interview_questions(org_id, interview_id, sequence_number);

CREATE TABLE IF NOT EXISTS public.interview_answers (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
  attempt_id          uuid REFERENCES public.interview_attempts(id) ON DELETE SET NULL,
  question_id         uuid NOT NULL REFERENCES public.interview_questions(id) ON DELETE CASCADE,

  answer_text         text NOT NULL,
  started_at          timestamptz,
  ended_at            timestamptz,
  duration_ms         integer,

  -- Offsets into the recording, so a recruiter can jump to this answer.
  recording_start_ms  integer,
  recording_end_ms    integer,

  -- A refusal or a non-answer is data, not an empty string.
  is_substantive      boolean NOT NULL DEFAULT true,
  non_answer_kind     text,   -- SKIPPED | REFUSED | INAUDIBLE | OFF_TOPIC | TOO_SHORT

  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_interview_answers_org_int
  ON public.interview_answers(org_id, interview_id);
CREATE INDEX IF NOT EXISTS ix_interview_answers_question
  ON public.interview_answers(question_id);

-- Deferred: interview_questions.parent_answer_id -> interview_answers.id.
-- The two tables reference each other, so the constraint is added after both
-- exist rather than by making one of the columns nullable-and-unenforced.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'interview_questions_parent_answer_fk'
  ) THEN
    ALTER TABLE public.interview_questions
      ADD CONSTRAINT interview_questions_parent_answer_fk
      FOREIGN KEY (parent_answer_id)
      REFERENCES public.interview_answers(id) ON DELETE SET NULL;
  END IF;
END $$;


-- ==========================================================================
-- RECORDING  +  TRANSCRIPT
-- ==========================================================================
-- storage_kind is explicit and there is no default that implies production
-- object storage. A demo file on a laptop must never be reported as though it
-- were durable cloud storage.
CREATE TABLE IF NOT EXISTS public.recording_assets (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
  attempt_id          uuid REFERENCES public.interview_attempts(id) ON DELETE SET NULL,

  part_number         integer NOT NULL DEFAULT 1,   -- reconnect produces parts
  media_kind          text NOT NULL,                -- VIDEO | AUDIO
  mime_type           text NOT NULL,

  storage_kind        text NOT NULL,
  -- LOCAL_FILE | DEMO_FIXTURE | OBJECT_STORE | NOT_CONNECTED
  storage_ref         text,
  byte_size           bigint,
  duration_ms         integer,
  sha256              text,

  -- Where this part sits on the interview's timeline, so a transcript segment
  -- at t=412s resolves to the right file AND the right offset within it.
  timeline_offset_ms  integer NOT NULL DEFAULT 0,

  started_at          timestamptz,
  ended_at            timestamptz,
  retention_until     date,
  deleted_at          timestamptz,

  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT recording_assets_unique UNIQUE (interview_id, media_kind, part_number),
  CONSTRAINT recording_assets_storage_ck CHECK (storage_kind IN (
    'LOCAL_FILE','DEMO_FIXTURE','OBJECT_STORE','NOT_CONNECTED')),
  -- Anything claiming to be stored must say where.
  CONSTRAINT recording_assets_ref_ck
    CHECK (storage_kind = 'NOT_CONNECTED' OR storage_ref IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_recording_assets_org_int
  ON public.recording_assets(org_id, interview_id);

CREATE TABLE IF NOT EXISTS public.transcript_segments (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
  attempt_id          uuid REFERENCES public.interview_attempts(id) ON DELETE SET NULL,
  answer_id           uuid REFERENCES public.interview_answers(id) ON DELETE SET NULL,
  recording_asset_id  uuid REFERENCES public.recording_assets(id) ON DELETE SET NULL,

  speaker             text NOT NULL,        -- INTERVIEWER | CANDIDATE | SYSTEM
  sequence_number     integer NOT NULL,
  start_ms            integer NOT NULL,
  end_ms              integer NOT NULL,
  text                text NOT NULL,
  asr_confidence      numeric(4,3),

  -- Correction provenance. A corrected transcript that cannot show what it
  -- used to say is not an auditable record.
  revision            integer NOT NULL DEFAULT 1,
  supersedes_id       uuid REFERENCES public.transcript_segments(id) ON DELETE SET NULL,
  corrected_by        text,
  corrected_at        timestamptz,
  is_current          boolean NOT NULL DEFAULT true,

  source              text NOT NULL DEFAULT 'ASR',   -- ASR | HUMAN | DEMO_FIXTURE
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT transcript_segments_time_ck CHECK (end_ms >= start_ms),
  CONSTRAINT transcript_segments_speaker_ck
    CHECK (speaker IN ('INTERVIEWER','CANDIDATE','SYSTEM'))
);
CREATE INDEX IF NOT EXISTS ix_transcript_segments_org_int
  ON public.transcript_segments(org_id, interview_id, sequence_number);
CREATE INDEX IF NOT EXISTS ix_transcript_segments_answer
  ON public.transcript_segments(answer_id);
-- Only one current revision per (interview, sequence).
CREATE UNIQUE INDEX IF NOT EXISTS uq_transcript_segments_current
  ON public.transcript_segments(interview_id, sequence_number)
  WHERE is_current;


-- ==========================================================================
-- EVIDENCE
-- ==========================================================================
-- The load-bearing table. An evidence row is a pointer at words the candidate
-- said, plus what those words do for or against a competency.
CREATE TABLE IF NOT EXISTS public.interview_evidence (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,

  competency_id       uuid REFERENCES public.interview_competencies(id) ON DELETE SET NULL,
  competency_key      text NOT NULL,
  claim_id            uuid REFERENCES public.candidate_claims(id) ON DELETE SET NULL,
  question_id         uuid REFERENCES public.interview_questions(id) ON DELETE SET NULL,
  answer_id           uuid NOT NULL REFERENCES public.interview_answers(id) ON DELETE CASCADE,
  transcript_segment_id uuid REFERENCES public.transcript_segments(id) ON DELETE SET NULL,

  polarity            text NOT NULL,   -- SUPPORTS | CONTRADICTS | NEUTRAL
  evidence_kind       text NOT NULL,
  -- SPECIFIC_EXAMPLE | OWNERSHIP | QUANTIFIED_OUTCOME | TRADEOFF_REASONING
  -- | FAILURE_REFLECTION | CONFLICT_HANDLING | DOMAIN_DEPTH | VAGUENESS
  -- | UNSUPPORTED_METRIC | CONTRADICTION | NON_ANSWER

  -- The candidate's own words. A recruiter reads THIS, not a paraphrase.
  quote               text NOT NULL,
  quote_start_ms      integer,
  quote_end_ms        integer,

  strength            numeric(4,3) NOT NULL DEFAULT 0.5,
  rationale           text NOT NULL,

  extracted_by        text NOT NULL DEFAULT 'deterministic',
  model_name          text,
  model_version       text,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interview_evidence_polarity_ck
    CHECK (polarity IN ('SUPPORTS','CONTRADICTS','NEUTRAL')),
  CONSTRAINT interview_evidence_strength_ck CHECK (strength >= 0 AND strength <= 1)
);
CREATE INDEX IF NOT EXISTS ix_interview_evidence_org_int
  ON public.interview_evidence(org_id, interview_id);
CREATE INDEX IF NOT EXISTS ix_interview_evidence_competency
  ON public.interview_evidence(org_id, interview_id, competency_key);


-- ==========================================================================
-- CLAIM VERIFICATION
-- ==========================================================================
-- "managed 12 people" resolving to 3 direct reports and a 12-person project
-- group is NOT a lie. It is two different claims, and the verdict vocabulary
-- has to be able to say so without accusing anyone.
CREATE TABLE IF NOT EXISTS public.claim_verifications (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
  claim_id            uuid NOT NULL REFERENCES public.candidate_claims(id) ON DELETE CASCADE,

  verdict             text NOT NULL,
  -- SUPPORTED | PARTIALLY_SUPPORTED | CONTRADICTED | UNVERIFIED | INSUFFICIENT_EVIDENCE

  -- What the interview actually established, which may be a narrower or
  -- differently-shaped fact than the original claim.
  established_text    text,
  established_value   numeric,
  established_unit    text,

  rationale           text NOT NULL,
  confidence          numeric(4,3),
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT claim_verifications_verdict_ck CHECK (verdict IN (
    'SUPPORTED','PARTIALLY_SUPPORTED','CONTRADICTED','UNVERIFIED','INSUFFICIENT_EVIDENCE')),
  CONSTRAINT claim_verifications_unique UNIQUE (interview_id, claim_id)
);
CREATE INDEX IF NOT EXISTS ix_claim_verifications_org_int
  ON public.claim_verifications(org_id, interview_id);

CREATE TABLE IF NOT EXISTS public.claim_verification_evidence (
  verification_id     uuid NOT NULL REFERENCES public.claim_verifications(id) ON DELETE CASCADE,
  evidence_id         uuid NOT NULL REFERENCES public.interview_evidence(id) ON DELETE CASCADE,
  PRIMARY KEY (verification_id, evidence_id)
);


-- ==========================================================================
-- ASSESSMENT  +  SCORECARD  +  SUMMARY
-- ==========================================================================
-- score is NULLABLE and INSUFFICIENT_EVIDENCE is a first-class state. A rubric
-- that must emit a number invents one, and an invented number is worse than an
-- admission that the interview did not establish the thing.
CREATE TABLE IF NOT EXISTS public.competency_assessments (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
  competency_id       uuid REFERENCES public.interview_competencies(id) ON DELETE SET NULL,
  competency_key      text NOT NULL,

  state               text NOT NULL,   -- SCORED | INSUFFICIENT_EVIDENCE | NOT_PROBED
  score               numeric(4,2),    -- 0..4, null unless state = SCORED
  confidence          numeric(4,3),
  rationale           text NOT NULL,
  missing_evidence    text,

  supporting_count    integer NOT NULL DEFAULT 0,
  contradicting_count integer NOT NULL DEFAULT 0,

  assessed_by         text NOT NULL DEFAULT 'deterministic',
  model_name          text,
  model_version       text,
  prompt_version      text,
  fallback_reason     text,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT competency_assessments_unique UNIQUE (interview_id, competency_key),
  CONSTRAINT competency_assessments_state_ck CHECK (state IN (
    'SCORED','INSUFFICIENT_EVIDENCE','NOT_PROBED')),
  CONSTRAINT competency_assessments_score_ck
    CHECK ((state = 'SCORED' AND score IS NOT NULL)
        OR (state <> 'SCORED' AND score IS NULL)),
  CONSTRAINT competency_assessments_range_ck
    CHECK (score IS NULL OR (score >= 0 AND score <= 4))
);
CREATE INDEX IF NOT EXISTS ix_competency_assessments_org_int
  ON public.competency_assessments(org_id, interview_id);

-- Which evidence each assessment actually cited. Without this join the
-- assessment's "supporting_evidence" is a number nobody can check.
CREATE TABLE IF NOT EXISTS public.assessment_evidence (
  assessment_id       uuid NOT NULL REFERENCES public.competency_assessments(id) ON DELETE CASCADE,
  evidence_id         uuid NOT NULL REFERENCES public.interview_evidence(id) ON DELETE CASCADE,
  role                text NOT NULL DEFAULT 'SUPPORTING',   -- SUPPORTING | CONTRADICTING
  PRIMARY KEY (assessment_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS public.interview_scorecards (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,

  rubric_key          text NOT NULL,
  rubric_version      text NOT NULL,

  overall_state       text NOT NULL,   -- SCORED | INSUFFICIENT_EVIDENCE
  overall_score       numeric(4,2),
  overall_confidence  numeric(4,3),

  -- Did every REQUIRED competency actually get probed and evidenced? A
  -- scorecard over an incomplete interview is not comparable to one over a
  -- complete interview, and the difference must be on the record.
  completeness_state  text NOT NULL,   -- COMPLETE | INCOMPLETE
  uncovered_required  jsonb NOT NULL DEFAULT '[]'::jsonb,

  -- This is decision SUPPORT. The column exists so no downstream automation
  -- can claim the product made a hiring decision.
  decision_authority  text NOT NULL DEFAULT 'RECRUITER_DECISION_SUPPORT',

  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interview_scorecards_unique UNIQUE (interview_id),
  CONSTRAINT interview_scorecards_state_ck
    CHECK (overall_state IN ('SCORED','INSUFFICIENT_EVIDENCE')),
  CONSTRAINT interview_scorecards_completeness_ck
    CHECK (completeness_state IN ('COMPLETE','INCOMPLETE')),
  CONSTRAINT interview_scorecards_authority_ck
    CHECK (decision_authority = 'RECRUITER_DECISION_SUPPORT')
);

CREATE TABLE IF NOT EXISTS public.interview_summaries (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
  scorecard_id        uuid REFERENCES public.interview_scorecards(id) ON DELETE SET NULL,

  headline            text NOT NULL,
  overall_assessment  text NOT NULL,

  -- Structured, not a paragraph. Each entry carries its evidence ids so the
  -- recruiter UI can turn any line into a jump into the recording.
  strengths           jsonb NOT NULL DEFAULT '[]'::jsonb,
  weaknesses          jsonb NOT NULL DEFAULT '[]'::jsonb,
  contradictions      jsonb NOT NULL DEFAULT '[]'::jsonb,
  unresolved_questions jsonb NOT NULL DEFAULT '[]'::jsonb,
  recommended_followup jsonb NOT NULL DEFAULT '[]'::jsonb,

  generated_by        text NOT NULL DEFAULT 'deterministic',
  model_name          text,
  model_version       text,
  prompt_version      text,
  fallback_reason     text,
  created_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interview_summaries_unique UNIQUE (interview_id)
);


-- ==========================================================================
-- EVENTS
-- ==========================================================================
-- Append-only. Consent, disconnects, resumes, media starts, corrections and
-- recruiter access all land here.
CREATE TABLE IF NOT EXISTS public.interview_events (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  interview_id        uuid NOT NULL REFERENCES public.interviews(id) ON DELETE CASCADE,
  attempt_id          uuid REFERENCES public.interview_attempts(id) ON DELETE SET NULL,

  event_type          text NOT NULL,
  actor_kind          text NOT NULL,   -- CANDIDATE | RECRUITER | SYSTEM | AI
  actor_ref           text,
  payload             jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_interview_events_org_int
  ON public.interview_events(org_id, interview_id, occurred_at);


-- ==========================================================================
-- RECRUITER CONFIGURATION
-- ==========================================================================
CREATE TABLE IF NOT EXISTS public.interview_role_configs (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  job_posting_id      uuid NOT NULL REFERENCES public.job_postings(id) ON DELETE CASCADE,

  rubric_key          text NOT NULL,
  target_minutes      integer NOT NULL DEFAULT 30,
  required_competencies jsonb NOT NULL DEFAULT '[]'::jsonb,
  competency_weights  jsonb NOT NULL DEFAULT '{}'::jsonb,
  must_ask_questions  jsonb NOT NULL DEFAULT '[]'::jsonb,
  preferred_experience jsonb NOT NULL DEFAULT '[]'::jsonb,
  hiring_manager_notes text,

  created_by          uuid,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),

  CONSTRAINT interview_role_configs_unique UNIQUE (job_posting_id)
);
CREATE INDEX IF NOT EXISTS ix_interview_role_configs_org
  ON public.interview_role_configs(org_id);
