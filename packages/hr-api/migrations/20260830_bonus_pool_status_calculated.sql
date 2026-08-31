-- bonus_pools_status_ck allowed ('draft','approved','paid'). bonus_calc writes
-- 'calculated' after allocating a pool, so POST /api/bonuses/pools/{id}/calculate
-- raised CheckViolation and allocation could never complete.
--
-- The constraint was written earlier the same day, from the column list rather
-- than from the code that writes it -- the same mistake as inventing a review
-- CHECK vocabulary without reading what finalize stores. A CHECK is a claim
-- about what the application does, and it has to be read off the application.
--
-- 'calculated' sits between draft and approved: allocations exist and are
-- proposed, but nobody has signed them off yet.

ALTER TABLE public.bonus_pools
    DROP CONSTRAINT IF EXISTS bonus_pools_status_ck;

ALTER TABLE public.bonus_pools
    ADD CONSTRAINT bonus_pools_status_ck
    CHECK (status IN ('draft', 'calculated', 'approved', 'paid'));
