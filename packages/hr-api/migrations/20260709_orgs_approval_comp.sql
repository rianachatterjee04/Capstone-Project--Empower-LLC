-- Migration: wire the dead company-creation + approval + comp-cycle paths.
-- Target: Postgres (Supabase). Idempotent (every statement is IF NOT EXISTS).
--
-- The audit found routers referenced in code but whose backing tables had NO
-- migration, so these paths 500'd / were left unmounted:
--   * orgs.py         -> org_nodes, approval_authority, performance_cycles,
--                        onboarding_templates, user_profiles  (company bootstrap)
--   * approvals.py    -> approval_authority, approval_requests, approval_actions
--                        (amount-tier approval — e.g. $50M spend sign-off)
--   * comp_cycle.py   -> comp_cycles, comp_proposals  (merit/comp cycle)
--   * security.py     -> user_profiles (SCIM provisioning)
--
-- performance_cycles is already created by init_db_fixed.init_models(); it is
-- re-declared here IF NOT EXISTS so this file is self-contained and safe to
-- apply on any environment.

-- =========================================================================
-- USER PROFILES (org membership / directory)
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.user_profiles (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id          uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  user_id         uuid,
  external_id     text,
  email           text,
  display_name    text,
  first_name      text,
  last_name       text,
  role            text NOT NULL DEFAULT 'employee',
  manager_user_id uuid,
  active          boolean NOT NULL DEFAULT true,
  last_login_at   timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_user_profiles_org  ON public.user_profiles(org_id);
CREATE INDEX IF NOT EXISTS idx_user_profiles_user ON public.user_profiles(user_id);

-- =========================================================================
-- ORG NODES (org-chart bootstrap for a new company)
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.org_nodes (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  name       text NOT NULL,
  type       text NOT NULL DEFAULT 'department',   -- root | department | team
  parent_id  uuid REFERENCES public.org_nodes(id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_org_nodes_org ON public.org_nodes(org_id);

-- =========================================================================
-- APPROVAL AUTHORITY (amount-tier sign-off matrix)
--   The approver for a spend/action resolves by amount tier: a request of
--   `amount` is authorized by a role/user whose [min_amount, max_amount]
--   window contains it. Enables the $50M spend-approval path in approvals.py.
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.approval_authority (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  role        text,                                  -- role tier (manager, director, vp, cfo, owner)
  user_id     uuid,                                  -- optional per-user override (NULL = role-level)
  min_amount  numeric(20,2) NOT NULL DEFAULT 0,      -- inclusive lower bound
  max_amount  numeric(20,2) NOT NULL,                -- inclusive upper bound (authority ceiling)
  active      boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  CHECK (min_amount <= max_amount),
  CHECK (role IS NOT NULL OR user_id IS NOT NULL)    -- must bind to a role or a user
);
CREATE INDEX IF NOT EXISTS idx_approval_authority_org  ON public.approval_authority(org_id);
CREATE INDEX IF NOT EXISTS idx_approval_authority_role ON public.approval_authority(org_id, role);
CREATE INDEX IF NOT EXISTS idx_approval_authority_user ON public.approval_authority(org_id, user_id);

-- =========================================================================
-- APPROVAL REQUESTS + ACTIONS (workflow used by every module via
-- approvals.py POST /approvals/request)
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.approval_requests (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  title         text,
  type          text,
  amount        numeric(20,2),
  status        text NOT NULL DEFAULT 'pending',     -- pending | approved | rejected
  requested_by  uuid,
  approved_by   uuid,
  approved_role text,
  approved_at   timestamptz,
  rejected_at   timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_approval_requests_org    ON public.approval_requests(org_id);
CREATE INDEX IF NOT EXISTS idx_approval_requests_status ON public.approval_requests(org_id, status);

CREATE TABLE IF NOT EXISTS public.approval_actions (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  approval_request_id uuid NOT NULL REFERENCES public.approval_requests(id) ON DELETE CASCADE,
  actor_user_id       uuid,
  actor_role          text,
  action              text NOT NULL,                 -- approved | rejected
  notes               text,
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_approval_actions_req ON public.approval_actions(approval_request_id);

-- =========================================================================
-- COMP CYCLES + PROPOSALS (merit/compensation cycle — comp_cycle.py)
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.comp_cycles (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  name       text,
  budget     numeric(20,2),
  status     text NOT NULL DEFAULT 'planning',       -- planning | approval | closed
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_comp_cycles_org ON public.comp_cycles(org_id);

CREATE TABLE IF NOT EXISTS public.comp_proposals (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id           uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  cycle_id         uuid NOT NULL REFERENCES public.comp_cycles(id) ON DELETE CASCADE,
  employee_id      uuid,
  proposed_salary  numeric(20,2),
  proposed_bonus   numeric(20,2),
  approved_salary  numeric(20,2),
  approved_bonus   numeric(20,2),
  justification    text,
  status           text NOT NULL DEFAULT 'proposed', -- proposed | hr_adjusted
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_comp_proposals_cycle ON public.comp_proposals(org_id, cycle_id);

-- =========================================================================
-- PERFORMANCE CYCLES (also created by init_db_fixed; re-declared for
-- self-containment) + ONBOARDING TEMPLATES (org bootstrap default)
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.performance_cycles (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL,
  name       text NOT NULL,
  status     text NOT NULL DEFAULT 'closed',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_performance_cycles_org ON public.performance_cycles(org_id);

CREATE TABLE IF NOT EXISTS public.onboarding_templates (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL REFERENCES public.orgs(id) ON DELETE CASCADE,
  name       text NOT NULL,
  checklist  jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_onboarding_templates_org ON public.onboarding_templates(org_id);
