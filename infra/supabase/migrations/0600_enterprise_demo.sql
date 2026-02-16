
create table demo_scenarios (
  id uuid primary key default gen_random_uuid(),
  name text,
  description text,
  payload jsonb,
  created_at timestamptz default now()
);
