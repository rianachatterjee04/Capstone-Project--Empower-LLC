
create table decision_precedents (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null,
  decision_type text,
  pattern jsonb,
  outcome text,
  created_at timestamptz default now()
);
