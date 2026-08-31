-- Migration: SMB HR core gaps (BambooHR-parity pass)
-- Target: Postgres (Supabase). Idempotent.
--
-- Adds:
--   1. Time-off engine: policies, per-employee assignments, signed hours ledger
--      (accrual / usage / adjustment / carryover) so balances are auditable.
--   2. Onboarding/offboarding checklists: templates + per-employee instances + tasks.
--   3. Effective-dated employee records (PeopleSoft pattern): comp_history,
--      job_history, plus emergency_contacts.
--
-- The existing pto_requests table is untouched; approved requests write usage
-- entries into time_off_ledger (fail-soft when no policy is assigned).

-- =========================================================================
-- 1. TIME OFF
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.time_off_policies (
  id                       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id                   uuid NOT NULL,
  name                     text NOT NULL,
  accrual_hours_per_period numeric(8,2) NOT NULL DEFAULT 6.67,  -- ~10 d/yr monthly
  accrual_period           text NOT NULL DEFAULT 'monthly',     -- monthly | biweekly | annual
  max_balance_hours        numeric(8,2),                        -- accrual cap (NULL = uncapped)
  carryover_max_hours      numeric(8,2),                        -- year-end carryover cap (NULL = all)
  hours_per_day            numeric(4,2) NOT NULL DEFAULT 8,
  is_default               boolean NOT NULL DEFAULT false,
  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, name)
);
CREATE INDEX IF NOT EXISTS idx_top_org ON public.time_off_policies(org_id);

CREATE TABLE IF NOT EXISTS public.time_off_policy_assignments (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL,
  employee_id    uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  policy_id      uuid NOT NULL REFERENCES public.time_off_policies(id) ON DELETE CASCADE,
  effective_date date NOT NULL DEFAULT current_date,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, employee_id)          -- one active policy per employee (SMB-simple)
);
CREATE INDEX IF NOT EXISTS idx_topa_org ON public.time_off_policy_assignments(org_id);

CREATE TABLE IF NOT EXISTS public.time_off_ledger (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL,
  employee_id    uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  policy_id      uuid REFERENCES public.time_off_policies(id) ON DELETE SET NULL,
  entry_type     text NOT NULL,                 -- accrual | usage | adjustment | carryover
  hours          numeric(8,2) NOT NULL,         -- signed: accrual +, usage -
  effective_date date NOT NULL DEFAULT current_date,
  period_key     text,                          -- e.g. '2026-07' — accrual idempotency key
  pto_request_id uuid REFERENCES public.pto_requests(id) ON DELETE SET NULL,
  note           text,
  created_by_user_id uuid,
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tol_org_emp ON public.time_off_ledger(org_id, employee_id);
-- one accrual per employee+policy+period
CREATE UNIQUE INDEX IF NOT EXISTS uq_tol_accrual_period
  ON public.time_off_ledger(employee_id, policy_id, period_key)
  WHERE period_key IS NOT NULL AND entry_type = 'accrual';
-- one usage entry per approved PTO request
CREATE UNIQUE INDEX IF NOT EXISTS uq_tol_usage_request
  ON public.time_off_ledger(pto_request_id)
  WHERE pto_request_id IS NOT NULL AND entry_type = 'usage';

-- =========================================================================
-- 2. CHECKLISTS (onboarding / offboarding)
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.checklist_templates (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL,
  name       text NOT NULL,
  kind       text NOT NULL DEFAULT 'onboarding',   -- onboarding | offboarding
  -- items: [{title, category, assignee_role, due_days_offset, link}]
  items      jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, name)
);
CREATE INDEX IF NOT EXISTS idx_ct_org ON public.checklist_templates(org_id);

CREATE TABLE IF NOT EXISTS public.checklists (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id             uuid NOT NULL,
  employee_id        uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  template_id        uuid REFERENCES public.checklist_templates(id) ON DELETE SET NULL,
  kind               text NOT NULL DEFAULT 'onboarding',
  name               text NOT NULL,
  status             text NOT NULL DEFAULT 'active',   -- active | completed | archived
  created_by_user_id uuid,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cl_org_emp ON public.checklists(org_id, employee_id);

CREATE TABLE IF NOT EXISTS public.checklist_tasks (
  id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id               uuid NOT NULL,
  checklist_id         uuid NOT NULL REFERENCES public.checklists(id) ON DELETE CASCADE,
  title                text NOT NULL,
  category             text NOT NULL DEFAULT 'general', -- docs | equipment | intro | payroll | access | general
  assignee_role        text NOT NULL DEFAULT 'hr',      -- hr | manager | it | employee | payroll
  assignee_employee_id uuid REFERENCES public.employees(id) ON DELETE SET NULL,
  due_date             date,
  link                 text,                            -- deep link, e.g. payroll invite flow
  status               text NOT NULL DEFAULT 'open',    -- open | done | skipped
  sort_order           integer NOT NULL DEFAULT 0,
  completed_by_user_id uuid,
  completed_at         timestamptz,
  created_at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_clt_checklist ON public.checklist_tasks(checklist_id);
CREATE INDEX IF NOT EXISTS idx_clt_org ON public.checklist_tasks(org_id);

-- =========================================================================
-- 3. EFFECTIVE-DATED EMPLOYEE RECORDS
-- =========================================================================
CREATE TABLE IF NOT EXISTS public.comp_history (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id             uuid NOT NULL,
  employee_id        uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  amount             numeric(14,2) NOT NULL,
  currency           text NOT NULL DEFAULT 'USD',
  basis              text NOT NULL DEFAULT 'salary',    -- salary (annual) | hourly
  effective_date     date NOT NULL,
  end_date           date,                              -- NULL = current record
  reason             text,                              -- hire | merit | promotion | market | review
  review_id          uuid,                              -- optional link to performance_reviews.id
  created_by_user_id uuid,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ch_org_emp ON public.comp_history(org_id, employee_id);

CREATE TABLE IF NOT EXISTS public.job_history (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id              uuid NOT NULL,
  employee_id         uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  job_title           text,
  department          text,
  manager_employee_id uuid REFERENCES public.employees(id) ON DELETE SET NULL,
  effective_date      date NOT NULL,
  end_date            date,                             -- NULL = current record
  reason              text,                             -- hire | promotion | transfer | reorg
  created_by_user_id  uuid,
  created_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_jh_org_emp ON public.job_history(org_id, employee_id);

CREATE TABLE IF NOT EXISTS public.emergency_contacts (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id       uuid NOT NULL,
  employee_id  uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  full_name    text NOT NULL,
  relationship text,
  phone        text NOT NULL,
  email        text,
  is_primary   boolean NOT NULL DEFAULT false,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ec_org_emp ON public.emergency_contacts(org_id, employee_id);
