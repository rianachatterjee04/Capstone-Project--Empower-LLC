create table if not exists public.approval_requests (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  title text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending' check (status in ('pending','approved','rejected')),
  created_by uuid null,
  created_at timestamptz not null default now()
);

create table if not exists public.approval_actions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  approval_request_id uuid not null references public.approval_requests(id) on delete cascade,
  actor_user_id uuid null,
  actor_role text null,
  action text not null,
  created_at timestamptz not null default now()
);

create table if not exists public.expo_push_tokens (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  user_id uuid null,
  token text not null,
  platform text null,
  created_at timestamptz not null default now(),
  unique(org_id, token)
);

alter table public.approval_requests enable row level security;
alter table public.approval_actions enable row level security;
alter table public.expo_push_tokens enable row level security;

drop policy if exists approvals_select on public.approval_requests;
create policy approvals_select on public.approval_requests for select
using (org_id = public.current_org_id());

drop policy if exists approvals_write on public.approval_requests;
create policy approvals_write on public.approval_requests for insert
with check (org_id = public.current_org_id());

drop policy if exists approval_actions_rw on public.approval_actions;
create policy approval_actions_rw on public.approval_actions for all
using (org_id = public.current_org_id())
with check (org_id = public.current_org_id());

drop policy if exists push_tokens_rw on public.expo_push_tokens;
create policy push_tokens_rw on public.expo_push_tokens for all
using (org_id = public.current_org_id())
with check (org_id = public.current_org_id());
