-- Three more endpoints that 500'd on tables and columns nobody created.
--
-- Found by probing all 188 parameterless GET routes:
--
--   GET /api/benefits/plans             relation "public.benefit_plans" does not exist
--   GET /api/benefits/optimization-runs relation "public.benefit_optimization_runs" ...
--   GET /api/bonuses/pools              relation "public.bonus_pools" does not exist
--   GET /api/reviews/cycles             column "opened_at" does not exist
--
-- Every one of them was invisible from the browser, because the pages degrade
-- to an honest empty state: /app/benefits says "No plans yet", /app/bonuses
-- shows nothing, /app/performance says "No review cycle is running yet". An
-- empty list and a failed request render identically, which is the same
-- unavailable-is-not-empty problem this codebase names elsewhere — here it hid
-- four server errors.
--
-- The column sets come from the INSERT statements in the routers, which are
-- the only specification these tables have.

CREATE TABLE IF NOT EXISTS public.benefit_plans (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL,
    name           text NOT NULL,
    provider       text,
    category       text,
    employer_cost  numeric(14,2) NOT NULL DEFAULT 0,
    employee_cost  numeric(14,2) NOT NULL DEFAULT 0,
    metadata       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_benefit_plans_org ON public.benefit_plans (org_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.benefit_optimization_runs (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL,
    fiscal_year  integer,
    budget       numeric(14,2),
    result       jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_benefit_opt_runs_org
    ON public.benefit_optimization_runs (org_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.bonus_pools (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    name          text NOT NULL,
    cycle_id      uuid,
    currency      text NOT NULL DEFAULT 'USD',
    total_amount  numeric(14,2),
    status        text NOT NULL DEFAULT 'draft',
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bonus_pools_status_ck CHECK (status IN ('draft', 'approved', 'paid'))
);
CREATE INDEX IF NOT EXISTS ix_bonus_pools_org ON public.bonus_pools (org_id, created_at DESC);

-- `amount`, not `allocation_amount`.
--
-- The router disagreed with itself: the read joins `ba.amount` under a comment
-- reading "Schema column is bonus_allocations.amount (not allocation_amount)",
-- while the update thirty lines earlier set `allocation_amount`. With no table
-- to arbitrate, nothing had ever failed. The comment and the read agree, so the
-- update is the one that was wrong, and it is corrected in the same commit.
CREATE TABLE IF NOT EXISTS public.bonus_allocations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL,
    pool_id      uuid NOT NULL REFERENCES public.bonus_pools(id) ON DELETE CASCADE,
    employee_id  uuid NOT NULL,
    amount       numeric(14,2) NOT NULL DEFAULT 0,
    basis        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT bonus_allocations_unique UNIQUE (pool_id, employee_id)
);
CREATE INDEX IF NOT EXISTS ix_bonus_allocations_org_pool
    ON public.bonus_allocations (org_id, pool_id);

-- A cycle's status says WHERE it is; these say WHEN it got there. GET
-- /api/reviews/cycles orders by opened_at, so without the column the whole
-- list 500s rather than degrading.
--
-- Nullable, no backfill: a cycle created before this migration does not know
-- when it opened, and defaulting to created_at would assert that a cycle
-- opened the moment its row was written, which is exactly the kind of invented
-- timeline the review turnaround figures would then be computed from.
ALTER TABLE public.performance_cycles
    ADD COLUMN IF NOT EXISTS opened_at timestamptz,
    ADD COLUMN IF NOT EXISTS closed_at timestamptz;
