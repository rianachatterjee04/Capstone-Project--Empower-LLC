-- Migration: persist the flagship HR modules + make the 9-box real
-- Target: Postgres. Idempotent (safe to re-run). Additive only — no existing
-- table is altered or dropped.
--
-- Backs five services that were in-process `_store` dicts (data lost on every
-- deploy/restart) with real tables, keeping their public function signatures
-- unchanged (see app/services/_hr_persistence.py for the sync->async bridge):
--   * goals_service        -> objectives, key_results
--   * oneonone_service     -> one_on_one_series, one_on_one_meetings,
--                             agenda_items, action_items,
--                             one_on_one_talking_points
--   * recognition_service  -> recognitions, recognition_reactions
--   * engagement_service   -> engagement_surveys, survey_questions,
--                             survey_responses
--   * calibration_service  -> nine_box_placements  (performance axis is derived
--                             live from performance_reviews; managers store only
--                             potential + rationale here)

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =========================================================================
-- Goals / OKRs
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.objectives (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL,
  title      text NOT NULL,
  owner      text NOT NULL DEFAULT 'Org',
  team       text,
  cycle      text NOT NULL DEFAULT 'Q3 2026',
  status     text NOT NULL DEFAULT 'on_track',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_objectives_org ON public.objectives(org_id);

CREATE TABLE IF NOT EXISTS public.key_results (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  objective_id uuid NOT NULL REFERENCES public.objectives(id) ON DELETE CASCADE,
  title        text NOT NULL,
  metric_label text NOT NULL DEFAULT 'metric',
  target       double precision NOT NULL DEFAULT 0,
  current      double precision NOT NULL DEFAULT 0,
  direction    text NOT NULL DEFAULT 'up',
  owner        text,
  status       text NOT NULL DEFAULT 'on_track',
  position     integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_key_results_obj ON public.key_results(objective_id);

-- =========================================================================
-- 1:1s
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.one_on_one_series (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id           uuid NOT NULL,
  manager_user_id  text NOT NULL,
  report_user_id   text NOT NULL,
  cadence          text NOT NULL DEFAULT 'weekly',
  next_date        text,
  title            text NOT NULL DEFAULT '1:1',
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_1on1_series_org ON public.one_on_one_series(org_id);

CREATE TABLE IF NOT EXISTS public.one_on_one_meetings (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  series_id  uuid NOT NULL REFERENCES public.one_on_one_series(id) ON DELETE CASCADE,
  date       text NOT NULL,
  status     text NOT NULL DEFAULT 'scheduled',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_1on1_meetings_series ON public.one_on_one_meetings(series_id);

CREATE TABLE IF NOT EXISTS public.agenda_items (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id     uuid NOT NULL REFERENCES public.one_on_one_meetings(id) ON DELETE CASCADE,
  text           text NOT NULL,
  author_user_id text NOT NULL,
  author_role    text NOT NULL DEFAULT 'report',
  checked        boolean NOT NULL DEFAULT false,
  is_private     boolean NOT NULL DEFAULT false,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_agenda_items_meeting ON public.agenda_items(meeting_id);

CREATE TABLE IF NOT EXISTS public.action_items (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id       uuid NOT NULL REFERENCES public.one_on_one_meetings(id) ON DELETE CASCADE,
  text             text NOT NULL,
  assignee_user_id text,
  due              text,
  done             boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_action_items_meeting ON public.action_items(meeting_id);

CREATE TABLE IF NOT EXISTS public.one_on_one_talking_points (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  meeting_id     uuid NOT NULL REFERENCES public.one_on_one_meetings(id) ON DELETE CASCADE,
  text           text NOT NULL,
  author_user_id text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_1on1_tp_meeting ON public.one_on_one_talking_points(meeting_id);

-- =========================================================================
-- Recognition
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.recognitions (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL,
  from_name  text NOT NULL,
  to_name    text NOT NULL,
  body       text NOT NULL,
  value_tags jsonb NOT NULL DEFAULT '[]'::jsonb,   -- `values` is reserved; store tags here
  visibility text NOT NULL DEFAULT 'company',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recognitions_org ON public.recognitions(org_id);

CREATE TABLE IF NOT EXISTS public.recognition_reactions (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recognition_id uuid NOT NULL REFERENCES public.recognitions(id) ON DELETE CASCADE,
  emoji          text NOT NULL,
  by_name        text NOT NULL,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (recognition_id, emoji, by_name)
);
CREATE INDEX IF NOT EXISTS idx_recognition_reactions_rec ON public.recognition_reactions(recognition_id);

-- =========================================================================
-- Engagement / eNPS surveys
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.engagement_surveys (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL,
  title         text NOT NULL,
  type          text NOT NULL DEFAULT 'engagement',
  cadence       text NOT NULL DEFAULT 'quarterly',
  status        text NOT NULL DEFAULT 'draft',
  anonymous     boolean NOT NULL DEFAULT true,
  audience_size integer,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_engagement_surveys_org ON public.engagement_surveys(org_id);

CREATE TABLE IF NOT EXISTS public.survey_questions (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  survey_id uuid NOT NULL REFERENCES public.engagement_surveys(id) ON DELETE CASCADE,
  text      text NOT NULL,
  kind      text NOT NULL DEFAULT 'scale_1_5',
  category  text,
  options   jsonb NOT NULL DEFAULT '[]'::jsonb,
  position  integer NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_survey_questions_survey ON public.survey_questions(survey_id);

CREATE TABLE IF NOT EXISTS public.survey_responses (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  survey_id           uuid NOT NULL REFERENCES public.engagement_surveys(id) ON DELETE CASCADE,
  respondent_user_id  text NOT NULL,
  anonymous           boolean NOT NULL DEFAULT true,
  answers             jsonb NOT NULL DEFAULT '{}'::jsonb,
  submitted_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_survey_responses_survey ON public.survey_responses(survey_id);

-- =========================================================================
-- 9-box calibration
-- One row per (org, employee). `potential`, `rationale`, `risk_flags` and the
-- manager fields are the manager's inputs; the `performance` column is only a
-- snapshot fallback — calibration_service derives the live performance axis from
-- each employee's latest finalized performance_reviews.rating at read time.
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.nine_box_placements (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL,
  employee_id     text NOT NULL,                 -- text: real employee UUIDs and legacy demo ids both fit
  employee_name   text NOT NULL,
  team            text NOT NULL DEFAULT '',
  manager_id      text NOT NULL DEFAULT '',
  manager_name    text NOT NULL DEFAULT '',
  performance     integer NOT NULL DEFAULT 2,
  potential       integer NOT NULL DEFAULT 2,
  rationale       text NOT NULL DEFAULT '',
  risk_flags      jsonb NOT NULL DEFAULT '[]'::jsonb,
  promotion_ready boolean NOT NULL DEFAULT false,
  placed_at       timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, employee_id)
);
CREATE INDEX IF NOT EXISTS idx_nine_box_placements_org ON public.nine_box_placements(org_id);
