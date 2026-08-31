-- The performance review workflow queried six columns the table never had.
--
-- GET /api/reviews returned 500:
--
--   column "ai_decision" does not exist
--   [SQL: select id, employee_id, cycle, status, ai_decision,
--                self_submitted_at, manager_submitted_at, finalized_at
--         from public.performance_reviews ...]
--
-- and it is not one column. app/api/routers/reviews.py reads or writes
-- ai_decision, ai_flags, self_submitted_at, manager_submitted_at, finalized_at
-- and manager_review against a table that has only id, org_id, employee_id,
-- cycle, status, rating, reviewer_id, notes and the timestamps. Three
-- endpoints were broken: the list, the finalize, and the calibration roll-up.
--
-- The code is the intent. Its own comment says the list exists to "render each
-- employee's true position in the cycle (self -> manager -> finalized) instead
-- of inferring progress from list order" — which needs the three stage
-- timestamps to be columns, because a status string cannot say WHEN a stage
-- was reached, and a calibration that cannot see when a manager submitted
-- cannot tell a fast reviewer from a rubber stamp.
--
-- Every column is nullable with no default. A review that predates this
-- migration genuinely does not know when its self-assessment was submitted,
-- and backfilling created_at into self_submitted_at would manufacture a
-- timeline: the finalize endpoint would then compute turnaround figures from
-- dates nobody recorded. An unknown stage date has to read as unknown.

-- TWO DEFINITIONS OF THIS TABLE ALREADY EXIST, and which one you get depends
-- on how the database was provisioned:
--
--   migrations/20260630_create_performance_and_comp.sql  10 columns
--   init_db_fixed.py (raw SQL after create_all)          19 columns
--
-- CREATE TABLE IF NOT EXISTS means the second is a no-op wherever the first
-- ran. bootstrap_hr.sh runs init_db_fixed.py and gets the full shape;
-- ephemeral_interview_db.sh runs create_all plus migrations only, and gets the
-- narrow one — and that is the path docs/DEMO.md tells an operator to use. The
-- demo database was missing columns the routers query.
--
-- These types match init_db_fixed.py exactly so the two paths CONVERGE. I first
-- wrote manager_review as text; it is jsonb there, and the finalize endpoint
-- passes it straight into performance_discrepancy_flags(self_r or {}, mgr_r or
-- {}) as a mapping. Two provisioning paths disagreeing about a column's TYPE
-- is worse than one of them missing it, because nothing fails until the value
-- is read.
ALTER TABLE public.performance_reviews
    ADD COLUMN IF NOT EXISTS self_review          jsonb DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS manager_review       jsonb DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS ai_flags             jsonb DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS ai_decision          text,
    ADD COLUMN IF NOT EXISTS cycle_id             uuid,
    ADD COLUMN IF NOT EXISTS calibrated_rating    numeric,
    ADD COLUMN IF NOT EXISTS outcome              text,
    ADD COLUMN IF NOT EXISTS self_submitted_at    timestamptz,
    ADD COLUMN IF NOT EXISTS manager_submitted_at timestamptz,
    ADD COLUMN IF NOT EXISTS finalized_at         timestamptz;

-- ai_decision is written by the finalize endpoint and read back by
-- calibration. Constrain it rather than leaving free text: a calibration
-- roll-up that groups by a misspelled decision silently drops those reviews
-- out of the distribution it exists to check.
--
-- The three values are the ones finalize_review actually writes:
--
--     decision = "normal"
--     if risk.get("pip_recommended"):        decision = "pip"
--     elif risk.get("promotion_recommended"): decision = "promotion"
--
-- I first wrote a plausible-sounding set here — retain/watch/exit_risk — and
-- it would have made every finalize fail the constraint. A vocabulary belongs
-- to the code that writes it, not to whoever writes the migration.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'performance_reviews_ai_decision_ck'
    ) THEN
        ALTER TABLE public.performance_reviews
            ADD CONSTRAINT performance_reviews_ai_decision_ck
            CHECK (ai_decision IS NULL OR ai_decision IN (
                'normal', 'pip', 'promotion'));
    END IF;
END $$;

-- The list orders by created_at and filters by org; the calibration roll-up
-- filters by (org, cycle, status).
CREATE INDEX IF NOT EXISTS ix_performance_reviews_org_cycle_status
    ON public.performance_reviews (org_id, cycle, status);
