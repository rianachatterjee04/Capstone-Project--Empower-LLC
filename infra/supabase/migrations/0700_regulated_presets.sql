
create table compliance_presets (
  id uuid primary key default gen_random_uuid(),
  industry text,
  policies jsonb,
  controls jsonb,
  created_at timestamptz default now()
);
