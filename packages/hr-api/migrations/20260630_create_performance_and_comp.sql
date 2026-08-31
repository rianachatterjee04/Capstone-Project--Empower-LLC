-- Migration: Performance reviews + Compensation records
-- Target: Postgres (Supabase). Idempotent. Powers the live HR reports
-- (Performance Review Status, Compensation Benchmarking).

-- =========================================================================
-- performance_reviews
-- =========================================================================
CREATE TABLE IF NOT EXISTS performance_reviews (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL,
  employee_id uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  cycle       text NOT NULL DEFAULT 'Q4 2026',
  status      text NOT NULL DEFAULT 'pending',   -- pending | in_progress | completed | calibrated
  rating      integer,                           -- 1..5
  reviewer_id uuid,
  notes       text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, employee_id, cycle)
);
CREATE INDEX IF NOT EXISTS idx_perf_reviews_org ON performance_reviews(org_id);

-- Drift resolver: init_db_fixed.py creates performance_reviews with a
-- `calibrated_rating numeric` column but NO `rating` column. The reports,
-- digital-twin, org-AI context builder and the seed below all read/write
-- `rating`. Because the CREATE TABLE above is IF NOT EXISTS, on a DB that was
-- stood up by init_db_fixed first the table already exists without `rating`, so
-- add it here idempotently so both bootstrap paths converge on the same shape.
ALTER TABLE performance_reviews ADD COLUMN IF NOT EXISTS rating integer;   -- 1..5

-- Same drift: init_db_fixed's performance_reviews lacks UNIQUE(org_id, employee_id,
-- cycle), which the demo seed's ON CONFLICT below relies on. Add it idempotently.
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'performance_reviews_org_employee_cycle_key'
  ) THEN
    ALTER TABLE performance_reviews
      ADD CONSTRAINT performance_reviews_org_employee_cycle_key
      UNIQUE (org_id, employee_id, cycle);
  END IF;
END $$;

-- =========================================================================
-- comp_records (actual employee compensation)
-- =========================================================================
CREATE TABLE IF NOT EXISTS comp_records (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id         uuid NOT NULL,
  employee_id    uuid NOT NULL REFERENCES public.employees(id) ON DELETE CASCADE,
  base_salary    numeric(14,2) NOT NULL DEFAULT 0,
  bonus_target   numeric(14,2) NOT NULL DEFAULT 0,
  equity_value   numeric(14,2) NOT NULL DEFAULT 0,
  currency       text NOT NULL DEFAULT 'USD',
  effective_date date NOT NULL DEFAULT current_date,
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, employee_id, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_comp_records_org ON comp_records(org_id);

-- =========================================================================
-- Idempotent demo seed (one review + one comp record per existing employee).
-- Deterministic from the employee id so reports show realistic live data.
-- =========================================================================
INSERT INTO performance_reviews (org_id, employee_id, cycle, status, rating)
SELECT org_id, id, 'Q4 2026',
  (ARRAY['completed','in_progress','pending','completed','calibrated'])[1 + (abs(hashtext(id::text)) % 5)],
  3 + (abs(hashtext(id::text)) % 3)
FROM public.employees
ON CONFLICT (org_id, employee_id, cycle) DO NOTHING;

INSERT INTO comp_records (org_id, employee_id, base_salary, bonus_target, effective_date)
SELECT org_id, id,
  80000 + (abs(hashtext(id::text)) % 120000),
  (80000 + (abs(hashtext(id::text)) % 120000)) * 0.12,
  '2026-01-01'
FROM public.employees
ON CONFLICT (org_id, employee_id, effective_date) DO NOTHING;
