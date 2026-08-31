-- POST /api/employees/{id}/terminate and /rehire both answered 500:
--   UndefinedColumn: column "termination_date" of relation "employees"
--
-- Terminating an employee is not an edge case. It is one of the two or three
-- things an HR system must do, and it has never worked on this schema. Six
-- statements across the package read or write termination_date and two write
-- termination_reason; none of them could run.
--
-- Found by sweeping the 145 POST/PATCH routes that take path parameters, using
-- real ids from the demo database. The parameterless sweep could not have found
-- it: the route needs an employee to terminate.
--
-- Nullable, with no backfill. Every existing employee is active; giving them a
-- termination date would say they had left, and defaulting the column to today
-- would say they all left today. NULL means "not terminated", which is what is
-- true.
--
-- Note for headcount forecasting: adding the column does not by itself make
-- attrition modelling possible. There is still no leaver history until people
-- are actually terminated through this path, and /api/intelligence/workforce/
-- forecast reports that distinction rather than projecting from an empty set.

ALTER TABLE public.employees
    ADD COLUMN IF NOT EXISTS termination_date   date,
    ADD COLUMN IF NOT EXISTS termination_reason text;

COMMENT ON COLUMN public.employees.termination_date IS
    'Date employment ended. NULL means still employed, not unknown.';
COMMENT ON COLUMN public.employees.termination_reason IS
    'Free text reason captured at termination. NULL when still employed.';
