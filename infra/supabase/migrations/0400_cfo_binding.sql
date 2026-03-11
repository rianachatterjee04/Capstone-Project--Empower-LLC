create extension if not exists pgcrypto;

create table if not exists public.cfo_scenarios (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_cfo_scenarios_org_id
  on public.cfo_scenarios(org_id);

create index if not exists idx_cfo_scenarios_created_at
  on public.cfo_scenarios(created_at desc);

create table if not exists public.reconciliation_authority (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  source text,
  winner text,
  created_at timestamptz not null default now()
);

create index if not exists idx_reconciliation_authority_org_id
  on public.reconciliation_authority(org_id);
