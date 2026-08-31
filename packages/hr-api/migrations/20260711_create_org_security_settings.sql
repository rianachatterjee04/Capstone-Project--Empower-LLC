-- Migration: org_security_settings (per-org SSO / SCIM config)
-- Target: Postgres. Idempotent. Backs the /security SSO + SCIM endpoints, which
-- currently 500 when this table is absent. org_id is UNIQUE so the enable-SSO
-- upsert (`on conflict (org_id)`) resolves.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.org_security_settings (
  org_id      uuid PRIMARY KEY,
  sso_enabled boolean NOT NULL DEFAULT false,
  idp_name    text,
  scim_secret text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
