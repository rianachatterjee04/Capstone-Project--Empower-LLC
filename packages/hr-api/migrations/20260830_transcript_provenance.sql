-- Which instrument produced a transcript segment.
--
-- `source` already records the KIND of provenance (ASR | HUMAN |
-- DEMO_FIXTURE). It does not record WHICH ASR, and the two adapters that write
-- ASR segments are not comparable evidence:
--
--   browser-speech  the candidate's own browser recognised their speech live
--                   and POSTed the text. The server cannot re-derive it from
--                   the media; it is an assertion made by the client, and the
--                   only thing tying it to the recording is a shared clock.
--   local-whisper   the server transcribed the stored media itself. Anyone
--                   holding the file can reproduce it.
--
-- Both landed in this table as 'ASR', indistinguishable, while the adapter
-- name was returned in the HTTP response and dropped. An assessment cites
-- these segments as evidence, so "how do we know the candidate said this"
-- has to survive in the row rather than in a response body nobody stored.
--
-- Nullable on purpose: segments written before this column existed genuinely
-- do not know their adapter, and backfilling a guess would be inventing the
-- provenance this column exists to record.

ALTER TABLE public.transcript_segments
  ADD COLUMN IF NOT EXISTS asr_adapter text;

COMMENT ON COLUMN public.transcript_segments.asr_adapter IS
  'Adapter that produced this segment (browser-speech | local-whisper | NULL '
  'when unknown). NULL means unrecorded, never "assume the trustworthy one".';

CREATE INDEX IF NOT EXISTS transcript_segments_adapter_idx
  ON public.transcript_segments (org_id, interview_id, asr_adapter);
