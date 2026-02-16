
create table if not exists ai_authority_scopes (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id),
  decision_type text not null,
  allowed boolean not null default false,
  requires_human boolean not null default true,
  allowed_roles text[] not null,
  created_at timestamptz default now(),
  unique(org_id, decision_type)
);

create table if not exists policy_consequences (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id),
  policy_id uuid not null references policies(id),
  trigger text not null,
  action text not null,
  parameters jsonb,
  created_at timestamptz default now()
);

create table if not exists human_decision_ledger (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id),
  decision_type text not null,
  entity_type text not null,
  entity_id uuid,
  actors jsonb not null,
  ai_involvement jsonb,
  policies_applied jsonb,
  rationale text,
  evidence_refs jsonb,
  created_at timestamptz default now()
);

create table if not exists authority_delegations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id),
  from_user uuid not null references users(id),
  to_user uuid not null references users(id),
  authority text not null,
  valid_from timestamptz,
  valid_to timestamptz
);

create table if not exists organizational_time_constraints (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id),
  constraint_type text,
  start_at timestamptz,
  end_at timestamptz,
  rules jsonb
);

create table if not exists board_exports (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references orgs(id),
  export_type text,
  generated_by text,
  payload jsonb,
  created_at timestamptz default now()
);
