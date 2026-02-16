-- 0005_manager_subtree_rls_and_workflows.sql
-- True manager subtree RLS + approvals + view audit + bonus pools + benefit optimization prefs

create or replace function public.current_employee_id()
returns uuid
language sql stable
as $$
  select e.id
  from public.employees e
  where e.org_id = public.current_org_id()
    and e.user_id = auth.uid()
  limit 1;
$$;

create or replace function public.is_manager_of(target_employee_id uuid)
returns boolean
language sql stable
as $$
  with recursive chain as (
    select e.id, e.manager_employee_id
    from public.employees e
    where e.id = target_employee_id and e.org_id = public.current_org_id()
    union all
    select m.id, m.manager_employee_id
    from public.employees m
    join chain c on c.manager_employee_id = m.id
    where m.org_id = public.current_org_id()
  )
  select exists (select 1 from chain where id = public.current_employee_id());
$$;

create table if not exists public.view_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  actor_user_id uuid null,
  actor_role text null,
  route text not null,
  entity_type text null,
  entity_id uuid null,
  ip text null,
  user_agent text null,
  created_at timestamptz not null default now()
);

create index if not exists view_events_org_idx on public.view_events(org_id);

alter table public.view_events enable row level security;

drop policy if exists view_events_rw on public.view_events;
create policy view_events_rw on public.view_events
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id());

create table if not exists public.approval_requests (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  requester_employee_id uuid not null references public.employees(id) on delete cascade,
  entity_type text not null,
  entity_id uuid not null,
  status text not null default 'pending' check (status in ('pending','approved','rejected','cancelled')),
  current_step int not null default 0,
  route jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists public.approval_actions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  request_id uuid not null references public.approval_requests(id) on delete cascade,
  actor_employee_id uuid null references public.employees(id) on delete set null,
  actor_role text null,
  action text not null check (action in ('approved','rejected','comment')),
  comment text null,
  created_at timestamptz not null default now()
);

alter table public.approval_requests enable row level security;
alter table public.approval_actions enable row level security;

drop policy if exists approval_requests_select on public.approval_requests;
create policy approval_requests_select on public.approval_requests
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr')
    or requester_employee_id = public.current_employee_id()
  )
);

drop policy if exists approval_requests_write on public.approval_requests;
create policy approval_requests_write on public.approval_requests
for all
using (org_id = public.current_org_id())
with check (org_id = public.current_org_id());

drop policy if exists approval_actions_rw on public.approval_actions;
create policy approval_actions_rw on public.approval_actions
for all
using (org_id = public.current_org_id())
with check (org_id = public.current_org_id());

create table if not exists public.bonus_pools (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  name text not null,
  cycle_id uuid null references public.performance_cycles(id) on delete set null,
  currency text not null default 'USD',
  total_amount numeric not null,
  status text not null default 'draft' check (status in ('draft','calculated','approved','paid')),
  created_at timestamptz not null default now()
);

create table if not exists public.bonus_allocations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  pool_id uuid not null references public.bonus_pools(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  allocation_amount numeric not null,
  basis jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (org_id, pool_id, employee_id)
);

alter table public.bonus_pools enable row level security;
alter table public.bonus_allocations enable row level security;

drop policy if exists bonus_pools_rw on public.bonus_pools;
create policy bonus_pools_rw on public.bonus_pools
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists bonus_allocations_select on public.bonus_allocations;
create policy bonus_allocations_select on public.bonus_allocations
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or employee_id = public.current_employee_id()
  )
);

drop policy if exists bonus_allocations_write on public.bonus_allocations;
create policy bonus_allocations_write on public.bonus_allocations
for insert
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

create table if not exists public.benefit_preferences (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  preferences jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (org_id, employee_id)
);

create table if not exists public.benefit_optimization_runs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  fiscal_year int not null,
  budget numeric not null,
  result jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.benefit_preferences enable row level security;
alter table public.benefit_optimization_runs enable row level security;

drop policy if exists benefit_preferences_select on public.benefit_preferences;
create policy benefit_preferences_select on public.benefit_preferences
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or employee_id = public.current_employee_id()
  )
);

drop policy if exists benefit_preferences_rw on public.benefit_preferences;
create policy benefit_preferences_rw on public.benefit_preferences
for all
using (org_id = public.current_org_id())
with check (org_id = public.current_org_id());

drop policy if exists benefit_opt_runs_rw on public.benefit_optimization_runs;
create policy benefit_opt_runs_rw on public.benefit_optimization_runs
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists employees_select on public.employees;
create policy employees_select on public.employees
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr')
    or user_id = auth.uid()
    or (public.current_role() = 'manager' and public.is_manager_of(id))
  )
);
