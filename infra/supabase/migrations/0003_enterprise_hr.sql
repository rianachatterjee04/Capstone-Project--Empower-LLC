-- 0003_enterprise_hr.sql
-- Enterprise HR: org graph, compensation, performance, benefits, documents, policy/rules, escalations, integrations, AI memory

create extension if not exists "vector";

-- Org graph: org units and matrix assignments
create table if not exists public.org_units (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  name text not null,
  parent_unit_id uuid null references public.org_units(id) on delete set null,
  created_at timestamptz not null default now(),
  unique (org_id, name)
);

create index if not exists org_units_org_idx on public.org_units(org_id);

-- employee -> org unit membership (supports matrix org)
create table if not exists public.employee_org_units (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  org_unit_id uuid not null references public.org_units(id) on delete cascade,
  role text not null default 'member' check (role in ('member','lead','manager')),
  is_primary boolean not null default false,
  created_at timestamptz not null default now(),
  unique (org_id, employee_id, org_unit_id)
);

create index if not exists employee_org_units_org_idx on public.employee_org_units(org_id);
create index if not exists employee_org_units_emp_idx on public.employee_org_units(employee_id);

-- Compensation: bands, comp history, market benchmarks, pay equity signals
create table if not exists public.salary_bands (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  job_family text not null,
  level text not null,
  currency text not null default 'USD',
  min_base numeric not null,
  mid_base numeric not null,
  max_base numeric not null,
  created_at timestamptz not null default now(),
  unique (org_id, job_family, level, currency)
);

create table if not exists public.compensation_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  effective_date date not null,
  currency text not null default 'USD',
  base_salary numeric not null,
  target_bonus_pct numeric null,
  equity_grant_value numeric null,
  reason text null,
  created_at timestamptz not null default now()
);

create index if not exists comp_events_org_idx on public.compensation_events(org_id);
create index if not exists comp_events_emp_idx on public.compensation_events(employee_id);

create table if not exists public.market_benchmarks (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  source text not null, -- salary.com, levels, etc.
  job_title text not null,
  location text null,
  currency text not null default 'USD',
  p25 numeric null,
  p50 numeric null,
  p75 numeric null,
  captured_at timestamptz not null default now()
);

create index if not exists market_benchmarks_org_idx on public.market_benchmarks(org_id);

-- Performance: cycles, goals (MBO), reviews, ratings
create table if not exists public.performance_cycles (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  name text not null,
  start_date date not null,
  end_date date not null,
  status text not null default 'draft' check (status in ('draft','active','closed')),
  created_at timestamptz not null default now()
);

create table if not exists public.goals (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  cycle_id uuid null references public.performance_cycles(id) on delete set null,
  title text not null,
  description text null,
  weight numeric not null default 1.0,
  metric text null,
  target_value text null,
  status text not null default 'active' check (status in ('active','completed','dropped')),
  created_at timestamptz not null default now()
);

create table if not exists public.performance_reviews (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  cycle_id uuid not null references public.performance_cycles(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  manager_employee_id uuid null references public.employees(id) on delete set null,
  self_summary text null,
  manager_summary text null,
  rating numeric null,
  status text not null default 'draft' check (status in ('draft','submitted','manager_review','finalized')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (org_id, cycle_id, employee_id)
);

drop trigger if exists performance_reviews_set_updated_at on public.performance_reviews;
create trigger performance_reviews_set_updated_at before update on public.performance_reviews
for each row execute function public.set_updated_at();

-- Benefits: plans, elections, budgets, optimization runs
create table if not exists public.benefit_plans (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  name text not null,
  type text not null, -- medical/dental/vision/401k/other
  employer_monthly_cost numeric null,
  employee_monthly_cost numeric null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.benefit_elections (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  plan_id uuid not null references public.benefit_plans(id) on delete cascade,
  coverage_level text null,
  start_date date not null,
  end_date date null,
  created_at timestamptz not null default now(),
  unique (org_id, employee_id, plan_id, start_date)
);

create table if not exists public.benefits_budget (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  fiscal_year int not null,
  total_budget numeric not null,
  created_at timestamptz not null default now(),
  unique (org_id, fiscal_year)
);

-- Documents: storage pointers + verification workflows
create table if not exists public.documents (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  employee_id uuid null references public.employees(id) on delete set null,
  category text not null, -- i9/w4/visa/other
  storage_bucket text not null,
  storage_path text not null,
  mime_type text null,
  sha256 text null,
  status text not null default 'uploaded' check (status in ('uploaded','in_review','verified','rejected','expired')),
  expires_at date null,
  uploaded_by_user_id uuid null,
  created_at timestamptz not null default now()
);

create index if not exists documents_org_idx on public.documents(org_id);

-- Policy + rules (English -> DSL stored)
create table if not exists public.policies (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  name text not null,
  body text not null, -- human readable
  dsl jsonb not null default '{}'::jsonb, -- executable rules
  version int not null default 1,
  status text not null default 'draft' check (status in ('draft','active','archived')),
  created_at timestamptz not null default now()
);

create index if not exists policies_org_idx on public.policies(org_id);

-- SLA + escalations for cases, onboarding, reviews, etc.
create table if not exists public.escalation_rules (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  name text not null,
  entity_type text not null, -- case/onboarding/review
  condition_dsl jsonb not null default '{}'::jsonb,
  sla_minutes int not null,
  route jsonb not null default '{}'::jsonb, -- role chain
  severity_floor text null, -- for cases
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists escalation_rules_org_idx on public.escalation_rules(org_id);

create table if not exists public.escalations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  entity_type text not null,
  entity_id uuid not null,
  rule_id uuid not null references public.escalation_rules(id) on delete cascade,
  level int not null default 0,
  status text not null default 'open' check (status in ('open','acknowledged','resolved')),
  due_at timestamptz not null,
  last_notified_at timestamptz null,
  created_at timestamptz not null default now(),
  unique (org_id, entity_type, entity_id, rule_id)
);

create index if not exists escalations_org_idx on public.escalations(org_id);

-- Integrations: connection records + sync status
create table if not exists public.integrations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null, -- gusto/adp/rippling/qb/netSuite
  status text not null default 'disconnected' check (status in ('disconnected','connected','error')),
  config jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (org_id, provider)
);

create table if not exists public.integration_sync_runs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz null,
  status text not null default 'running' check (status in ('running','success','error')),
  details jsonb not null default '{}'::jsonb
);

-- AI system-of-record memory: per-tenant vector memory + decision lineage
create table if not exists public.ai_memories (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  namespace text not null, -- e.g. comp, policy, recruiting, cases
  entity_type text null,
  entity_id uuid null,
  content text not null,
  embedding vector(1536) null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ai_memories_org_idx on public.ai_memories(org_id);
