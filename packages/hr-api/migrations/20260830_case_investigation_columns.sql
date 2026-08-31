-- The whole investigation workflow wrote columns that do not exist, so none of
-- it worked:
--
--   POST /api/cases/{id}/assign    set investigator_employee_id=...
--   POST /api/cases/{id}/findings  set findings=cast(... as jsonb)
--   POST /api/cases/{id}/close     set closure_reason=...
--   POST /api/legal/hold/{id}      set legal_freeze = true
--
-- Assign an investigator, record what they found, close the case, place a legal
-- hold: that is the feature, end to end, and every step raised UndefinedColumn.
--
-- legal_freeze is the one to note. A legal hold that does not persist is worse
-- than one that was never offered -- someone believes evidence is preserved
-- when nothing is marked. It defaults to false, which is the honest default:
-- no case is under hold until somebody places one.
--
-- findings is jsonb to match the writer, which casts its payload.
--
-- These columns are added to app/db/models.py as well. A migration alone would
-- leave a deployment provisioned by create_all rebuilding cases without them --
-- the two-provisioning-paths problem in BETA_READINESS blocker #6.

ALTER TABLE public.cases
    ADD COLUMN IF NOT EXISTS investigator_employee_id uuid REFERENCES public.employees(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS findings                 jsonb,
    ADD COLUMN IF NOT EXISTS closure_reason           text,
    ADD COLUMN IF NOT EXISTS legal_freeze             boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.cases.legal_freeze IS
    'Case is under legal hold. false means no hold has been placed, not that one lapsed.';
COMMENT ON COLUMN public.cases.findings IS
    'Investigator findings payload. NULL means none recorded, not none found.';
