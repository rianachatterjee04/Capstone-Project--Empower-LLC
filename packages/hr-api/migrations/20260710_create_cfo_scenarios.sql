-- Migration: cfo_scenarios (CFO workforce simulator persistence)
-- Target: Postgres. Idempotent. Backs POST /cfo/simulate + the scenario history
-- and narrative endpoints, which currently 503 when this table is absent.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.cfo_scenarios (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id     uuid NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}'::jsonb,   -- the simulation inputs
  result     jsonb NOT NULL DEFAULT '{}'::jsonb,   -- the computed outputs
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cfo_scenarios_org
  ON public.cfo_scenarios(org_id, created_at DESC);
