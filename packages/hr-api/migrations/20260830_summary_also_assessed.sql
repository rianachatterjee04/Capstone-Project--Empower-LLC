-- The debrief's third list: scored, at the bar, not among the strongest four.
--
-- WHY IT NEEDS A COLUMN
-- The stored summary IS the debrief. Deriving this list at read time instead
-- would mean the artifact a recruiter's decision was recorded against no
-- longer matches what they were shown, the first time the ranking logic
-- changes.
--
-- Strengths take the top four and weaknesses take everything below the bar, so
-- a competency that was at the bar and fifth-best appeared in neither list:
-- assessed, and then absent from the summary of the assessment.
BEGIN;

ALTER TABLE public.interview_summaries
    ADD COLUMN IF NOT EXISTS also_assessed jsonb NOT NULL DEFAULT '[]'::jsonb;

COMMIT;
