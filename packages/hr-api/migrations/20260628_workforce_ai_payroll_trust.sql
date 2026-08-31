-- Migration: Workforce AI Proficiency + Payroll Trust
-- Target: Postgres (Supabase). Idempotent.

-- =========================================================================
-- Workforce AI Proficiency
-- =========================================================================

CREATE TABLE IF NOT EXISTS wf_ai_sessions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL,
  employee_id uuid NOT NULL,
  task        text,
  model       text,
  tokens      integer,
  cost_usd    numeric(12, 4),
  quality     integer,
  created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wf_ai_proficiency (
  org_id      uuid NOT NULL,
  employee_id uuid NOT NULL,
  delegation  integer,
  description integer,
  discernment integer,
  diligence   integer,
  overall     integer,
  ai_cost_usd numeric(14, 4),
  sessions    integer,
  period      date NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, employee_id, period)
);

CREATE TABLE IF NOT EXISTS wf_coaching_notes (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL,
  employee_id uuid NOT NULL,
  kind        text,
  body        text,
  author      text,
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- =========================================================================
-- Payroll Trust
-- =========================================================================

CREATE TABLE IF NOT EXISTS payroll_agent_runs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id        uuid NOT NULL,
  period        text,
  gross_usd     numeric(16, 2),
  employees     integer,
  status        text,
  ai_assisted   boolean NOT NULL DEFAULT false,
  anomaly_count integer NOT NULL DEFAULT 0,
  trust_score   integer,
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payroll_trust_scores (
  org_id                  uuid NOT NULL,
  run_id                  uuid NOT NULL,
  accuracy                integer,
  policy_compliance       integer,
  approval_coverage       integer,
  sensitive_data_handling integer,
  anomaly_recovery        integer,
  overall                 integer,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, run_id)
);

CREATE TABLE IF NOT EXISTS payroll_alerts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_id      uuid NOT NULL,
  run_id      uuid NOT NULL,
  title       text,
  severity    text,
  detected_at timestamptz NOT NULL DEFAULT now(),
  evidence    jsonb,
  resolved    boolean NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS payroll_evidence (
  id         bigserial PRIMARY KEY,
  org_id     uuid NOT NULL,
  run_id     uuid NOT NULL,
  action     text,
  actor      text,
  source     text,
  hash       text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- =========================================================================
-- Indexes
-- =========================================================================

CREATE INDEX IF NOT EXISTS idx_wf_ai_sessions_org          ON wf_ai_sessions (org_id);
CREATE INDEX IF NOT EXISTS idx_wf_ai_sessions_org_employee ON wf_ai_sessions (org_id, employee_id);
CREATE INDEX IF NOT EXISTS idx_wf_ai_sessions_org_created  ON wf_ai_sessions (org_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_wf_ai_proficiency_org          ON wf_ai_proficiency (org_id);
CREATE INDEX IF NOT EXISTS idx_wf_ai_proficiency_org_period   ON wf_ai_proficiency (org_id, period DESC);

CREATE INDEX IF NOT EXISTS idx_wf_coaching_notes_org          ON wf_coaching_notes (org_id);
CREATE INDEX IF NOT EXISTS idx_wf_coaching_notes_org_employee ON wf_coaching_notes (org_id, employee_id);

CREATE INDEX IF NOT EXISTS idx_payroll_agent_runs_org         ON payroll_agent_runs (org_id);
CREATE INDEX IF NOT EXISTS idx_payroll_agent_runs_org_created ON payroll_agent_runs (org_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payroll_agent_runs_org_status  ON payroll_agent_runs (org_id, status);

CREATE INDEX IF NOT EXISTS idx_payroll_trust_scores_org       ON payroll_trust_scores (org_id);

CREATE INDEX IF NOT EXISTS idx_payroll_alerts_org             ON payroll_alerts (org_id);
CREATE INDEX IF NOT EXISTS idx_payroll_alerts_org_run         ON payroll_alerts (org_id, run_id);
CREATE INDEX IF NOT EXISTS idx_payroll_alerts_org_unresolved  ON payroll_alerts (org_id, severity) WHERE resolved = false;

CREATE INDEX IF NOT EXISTS idx_payroll_evidence_org           ON payroll_evidence (org_id);
CREATE INDEX IF NOT EXISTS idx_payroll_evidence_org_run       ON payroll_evidence (org_id, run_id);
CREATE INDEX IF NOT EXISTS idx_payroll_evidence_org_created   ON payroll_evidence (org_id, created_at DESC);
