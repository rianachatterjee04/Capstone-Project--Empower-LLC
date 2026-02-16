-- 0001_init.sql
-- Core schema for Foundry People

create extension if not exists "pgcrypto";
create extension if not exists "uuid-ossp";

-- helper: access JWT claims
create or replace function public.jwt_claims()
returns jsonb
language sql stable
as $$
  select coalesce(current_setting('request.jwt.claims', true), '{}')::jsonb;
$$;

create or replace function public.current_org_id()
returns uuid
language sql stable
as $$
  select nullif((jwt_claims()->'app_metadata'->>'org_id'), '')::uuid;
$$;

create or replace function public.current_role()
returns text
language sql stable
as $$
  select coalesce(jwt_claims()->'app_metadata'->>'role', 'employee');
$$;

create table if not exists public.orgs (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.employees (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  user_id uuid null, -- supabase auth.users.id
  employee_number text null,
  legal_name text not null,
  preferred_name text null,
  email text not null,
  status text not null default 'invited' check (status in ('invited','active','terminated','leave')),
  job_title text null,
  department text null,
  location text null,
  manager_employee_id uuid null references public.employees(id) on delete set null,
  start_date date null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (org_id, email)
);

create index if not exists employees_org_idx on public.employees(org_id);
create index if not exists employees_manager_idx on public.employees(manager_employee_id);

create table if not exists public.onboarding_packets (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  status text not null default 'pending' check (status in ('pending','in_progress','completed')),
  requested_items jsonb not null default '{}'::jsonb,
  submitted_items jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists onboarding_packets_org_idx on public.onboarding_packets(org_id);
create index if not exists onboarding_packets_employee_idx on public.onboarding_packets(employee_id);

create table if not exists public.cases (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  reporter_employee_id uuid null references public.employees(id) on delete set null,
  is_anonymous boolean not null default true,
  category text not null,
  severity text not null default 'medium' check (severity in ('low','medium','high','critical')),
  details text not null,
  status text not null default 'open' check (status in ('open','in_review','resolved','dismissed')),
  escalation_level int not null default 0,
  created_at timestamptz not null default now()
);

create index if not exists cases_org_idx on public.cases(org_id);

create table if not exists public.job_postings (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  title text not null,
  location text null,
  description text not null,
  status text not null default 'draft' check (status in ('draft','open','paused','closed')),
  created_at timestamptz not null default now()
);

create index if not exists job_postings_org_idx on public.job_postings(org_id);

create table if not exists public.candidates (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  job_posting_id uuid not null references public.job_postings(id) on delete cascade,
  full_name text not null,
  email text not null,
  resume_text text null,
  status text not null default 'new' check (status in ('new','screened','interview','rejected','hired')),
  ai_score int null,
  ai_summary text null,
  created_at timestamptz not null default now(),
  unique (org_id, job_posting_id, email)
);

create index if not exists candidates_org_idx on public.candidates(org_id);
create index if not exists candidates_job_idx on public.candidates(job_posting_id);

-- audit events (minimal)
create table if not exists public.audit_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  actor_user_id uuid null,
  actor_role text null,
  event_type text not null,
  entity_type text null,
  entity_id uuid null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_events_org_idx on public.audit_events(org_id);

-- updated_at triggers
create or replace function public.set_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists employees_set_updated_at on public.employees;
create trigger employees_set_updated_at before update on public.employees
for each row execute function public.set_updated_at();

drop trigger if exists onboarding_packets_set_updated_at on public.onboarding_packets;
create trigger onboarding_packets_set_updated_at before update on public.onboarding_packets
for each row execute function public.set_updated_at();
