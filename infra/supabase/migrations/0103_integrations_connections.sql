create table if not exists public.integration_connections (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  status text not null default 'disconnected',
  external_account_id text null,
  token_ciphertext text null,
  refresh_ciphertext text null,
  scopes text[] null,
  webhook_secret text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (org_id, provider)
);

alter table public.integration_connections enable row level security;
drop policy if exists integration_connections_rw on public.integration_connections;
create policy integration_connections_rw on public.integration_connections
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));
