-- POST /api/performance/cycles inserts start_date and end_date; the table has
-- neither, so creating a review cycle answered 500 UndefinedColumn.
--
-- Found by probing all 143 parameterless POST/PATCH routes. The GET sweep could
-- not have found it: /api/performance/cycles reads fine and returns an honest
-- empty list, because there are no cycles -- because none can be created.
--
-- These are NOT the same thing as opened_at / closed_at, added earlier today.
-- Those record when the cycle was opened and closed in the tool. start_date and
-- end_date are the period being reviewed, which is what an HR lead sets when
-- they launch a cycle ("H1 2026: January through June"). A review opened in
-- July can assess January through June; collapsing the two would make that
-- unrepresentable and would silently relabel every existing row's timestamps as
-- a review period.
--
-- Nullable on purpose: cycles created before this migration have no period
-- recorded, and inventing one would be a claim about which months those reviews
-- covered. Unset is not the same as "starts today".

ALTER TABLE public.performance_cycles
    ADD COLUMN IF NOT EXISTS start_date date,
    ADD COLUMN IF NOT EXISTS end_date   date;

COMMENT ON COLUMN public.performance_cycles.start_date IS
    'First day of the period under review. NULL means not recorded, not today.';
COMMENT ON COLUMN public.performance_cycles.end_date IS
    'Last day of the period under review. NULL means not recorded, not open-ended.';
