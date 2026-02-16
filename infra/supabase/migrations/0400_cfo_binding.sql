
create table workforce_scenarios (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  name text,
  approved boolean default false,
  constraints jsonb,
  created_at timestamptz default now()
);

create table reconciliation_authority (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  source text,
  winner text,
  created_at timestamptz default now()
);
