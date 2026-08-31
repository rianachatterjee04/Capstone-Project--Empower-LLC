-- Migration: AI Workforce OS schema
-- Created: 2026-06-28
-- Idempotent: safe to re-run.

BEGIN;

-- Required for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- workforce_registry: catalog of human + AI workforce entities per org
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS workforce_registry (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            uuid        NOT NULL,
    kind              text        NOT NULL,
    name              text        NOT NULL,
    title             text,
    department        text,
    owner             text,
    model_provider    text,
    monthly_cost_usd  numeric(14,2) NOT NULL DEFAULT 0,
    permissions       jsonb       NOT NULL DEFAULT '{}'::jsonb,
    capabilities      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    lifecycle_status  text        NOT NULL DEFAULT 'active',
    approval_status   text        NOT NULL DEFAULT 'pending',
    last_active       timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workforce_registry_org_id
    ON workforce_registry (org_id);

-- ---------------------------------------------------------------------------
-- ai_skills: per-employee skill proficiency
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_skills (
    org_id       uuid        NOT NULL,
    employee_id  uuid        NOT NULL,
    skill        text        NOT NULL,
    proficiency  integer     NOT NULL DEFAULT 0,
    certified    boolean     NOT NULL DEFAULT false,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, employee_id, skill)
);

CREATE INDEX IF NOT EXISTS idx_ai_skills_org_id
    ON ai_skills (org_id);

-- ---------------------------------------------------------------------------
-- ai_productivity: per-employee productivity metrics by period
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_productivity (
    org_id            uuid        NOT NULL,
    employee_id       uuid        NOT NULL,
    period            date        NOT NULL,
    hours_saved       numeric(14,2) NOT NULL DEFAULT 0,
    automations       integer     NOT NULL DEFAULT 0,
    tasks_eliminated  integer     NOT NULL DEFAULT 0,
    cost_savings_usd  numeric(14,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (org_id, employee_id, period)
);

CREATE INDEX IF NOT EXISTS idx_ai_productivity_org_id
    ON ai_productivity (org_id);

-- ---------------------------------------------------------------------------
-- ai_onboarding_runs: onboarding execution log per employee
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_onboarding_runs (
    id                       uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                   uuid        NOT NULL,
    employee_id              uuid        NOT NULL,
    tools                    jsonb       NOT NULL DEFAULT '[]'::jsonb,
    mfa                      boolean     NOT NULL DEFAULT false,
    training_done            boolean     NOT NULL DEFAULT false,
    policies_signed          boolean     NOT NULL DEFAULT false,
    least_privilege          boolean     NOT NULL DEFAULT false,
    status                   text        NOT NULL DEFAULT 'pending',
    time_to_productive_days  numeric(8,2),
    started_at               timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_onboarding_runs_org_id
    ON ai_onboarding_runs (org_id);

COMMIT;
