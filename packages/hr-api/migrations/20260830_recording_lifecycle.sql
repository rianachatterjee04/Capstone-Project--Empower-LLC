-- A recording says whether it is whole.
--
-- WHY
-- A RecordingAsset row exists the moment bytes land, and nothing
-- distinguished a recording that captured the whole interview from one where
-- the candidate's laptop slept through part three, or where the tab closed
-- while the last part was uploading. Both look like "there is a recording",
-- and a recruiter opening either sees a player.
--
-- That is the failure this product cannot afford: an assessment defended by a
-- recording that is missing the answer it rests on.
--
-- WHY THE COUNT COMES FROM THE CLIENT
-- A part that never reached the server leaves no trace on the server. The
-- browser is the only party that knows how many it produced, so sealing is an
-- explicit statement -- "that was all of them" -- which the server then checks
-- against what it holds. Absent that statement the state is CAPTURING, never
-- SEALED: holding three parts is not holding all the parts.
BEGIN;

ALTER TABLE public.interviews
    ADD COLUMN IF NOT EXISTS recording_state text NOT NULL DEFAULT 'NOT_CAPTURED',
    ADD COLUMN IF NOT EXISTS recording_parts_expected integer,
    ADD COLUMN IF NOT EXISTS recording_sealed_at timestamptz,
    ADD COLUMN IF NOT EXISTS recording_state_detail text;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'interviews_recording_state_ck') THEN
        ALTER TABLE public.interviews
            ADD CONSTRAINT interviews_recording_state_ck CHECK (
                recording_state IN ('NOT_CAPTURED','CAPTURING','SEALED',
                                    'INCOMPLETE'));
    END IF;

    -- SEALED is the only state that authorises calling a recording complete,
    -- so it has to carry both the count it was sealed against and the time.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'interviews_recording_sealed_ck') THEN
        ALTER TABLE public.interviews
            ADD CONSTRAINT interviews_recording_sealed_ck CHECK (
                recording_state <> 'SEALED'
                OR (recording_parts_expected IS NOT NULL
                    AND recording_sealed_at IS NOT NULL));
    END IF;

    -- An INCOMPLETE recording must say what is wrong with it. "Incomplete"
    -- with no detail is a shrug in a column.
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'interviews_recording_detail_ck') THEN
        ALTER TABLE public.interviews
            ADD CONSTRAINT interviews_recording_detail_ck CHECK (
                recording_state <> 'INCOMPLETE'
                OR (recording_state_detail IS NOT NULL
                    AND length(recording_state_detail) >= 12));
    END IF;
END $$;

COMMIT;
