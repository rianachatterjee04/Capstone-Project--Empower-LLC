-- AI HR System of Record: vector memory + decisions + policy interpretations
create extension if not exists vector;

create table if not exists public.ai_memory_chunks (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  namespace text not null default 'default',
  content text not null,
  metadata jsonb not null default '{}'::jsonb,
  embedding vector(1536),
  created_at timestamptz not null default now()
);

create index if not exists ai_memory_org_idx on public.ai_memory_chunks(org_id);
create index if not exists ai_memory_ns_idx on public.ai_memory_chunks(org_id, namespace);

alter table public.ai_memory_chunks enable row level security;
drop policy if exists ai_memory_chunks_rw on public.ai_memory_chunks;
create policy ai_memory_chunks_rw on public.ai_memory_chunks
for all
using (org_id = public.current_org_id())
with check (org_id = public.current_org_id());

create table if not exists public.ai_decisions (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  actor_user_id uuid null,
  actor_role text null,
  decision_type text not null,
  entity_type text null,
  entity_id uuid null,
  input jsonb not null default '{}'::jsonb,
  output jsonb not null default '{}'::jsonb,
  model text null,
  created_at timestamptz not null default now()
);

create index if not exists ai_decisions_org_idx on public.ai_decisions(org_id);

alter table public.ai_decisions enable row level security;
drop policy if exists ai_decisions_select on public.ai_decisions;
create policy ai_decisions_select on public.ai_decisions
for select
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists ai_decisions_write on public.ai_decisions;
create policy ai_decisions_write on public.ai_decisions
for insert
with check (org_id = public.current_org_id());

create table if not exists public.ai_policy_interpretations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  policy_id uuid null,
  version int null,
  interpretation text not null,
  model text null,
  created_at timestamptz not null default now()
);

alter table public.ai_policy_interpretations enable row level security;
drop policy if exists ai_policy_interp_rw on public.ai_policy_interpretations;
create policy ai_policy_interp_rw on public.ai_policy_interpretations
for all
using (org_id = public.current_org_id())
with check (org_id = public.current_org_id());
