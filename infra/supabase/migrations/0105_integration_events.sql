create table if not exists public.integration_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  event_type text null,
  external_id text null,
  payload jsonb not null default '{}'::jsonb,
  received_at timestamptz not null default now(),
  processed_at timestamptz null
);

create index if not exists integration_events_org_idx on public.integration_events(org_id, provider, received_at desc);

alter table public.integration_events enable row level security;
drop policy if exists integration_events_rw on public.integration_events;
create policy integration_events_rw on public.integration_events
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));
