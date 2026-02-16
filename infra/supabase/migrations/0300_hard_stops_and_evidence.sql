
create table if not exists evidence_vault (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  hash text not null,
  uri text not null,
  locked boolean default true,
  created_at timestamptz default now()
);

create table if not exists enforcement_blocks (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  entity_type text,
  entity_id uuid,
  reason text,
  active boolean default true,
  created_at timestamptz default now()
);
