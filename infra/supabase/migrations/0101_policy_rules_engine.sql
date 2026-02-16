-- Policy -> executable rules engine (versioned)
create table if not exists public.policies (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  name text not null,
  scope text not null default 'org',
  created_at timestamptz not null default now()
);

create table if not exists public.policy_versions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  policy_id uuid not null references public.policies(id) on delete cascade,
  version int not null,
  policy_text text not null,
  created_at timestamptz not null default now(),
  unique (org_id, policy_id, version)
);

create table if not exists public.policy_rules (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  policy_version_id uuid not null references public.policy_versions(id) on delete cascade,
  rule jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.policy_executions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  policy_rule_id uuid not null references public.policy_rules(id) on delete cascade,
  status text not null default 'pending' check (status in ('pending','executed','failed')),
  context jsonb not null default '{}'::jsonb,
  result jsonb not null default '{}'::jsonb,
  executed_at timestamptz null,
  created_at timestamptz not null default now()
);

alter table public.policies enable row level security;
alter table public.policy_versions enable row level security;
alter table public.policy_rules enable row level security;
alter table public.policy_executions enable row level security;

drop policy if exists policies_rw on public.policies;
create policy policies_rw on public.policies
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists policy_versions_rw on public.policy_versions;
create policy policy_versions_rw on public.policy_versions
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists policy_rules_rw on public.policy_rules;
create policy policy_rules_rw on public.policy_rules
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists policy_exec_rw on public.policy_executions;
create policy policy_exec_rw on public.policy_executions
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));
