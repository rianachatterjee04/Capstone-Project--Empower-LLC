-- Immutable audit ledger (hash chain) + evidence locking flags
create table if not exists public.audit_ledger (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  prev_hash text null,
  payload jsonb not null default '{}'::jsonb,
  hash text not null,
  created_at timestamptz not null default now()
);

create index if not exists audit_ledger_org_idx on public.audit_ledger(org_id);

alter table public.audit_ledger enable row level security;
drop policy if exists audit_ledger_select on public.audit_ledger;
create policy audit_ledger_select on public.audit_ledger
for select
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','legal'));

drop policy if exists audit_ledger_write on public.audit_ledger;
create policy audit_ledger_write on public.audit_ledger
for insert
with check (org_id = public.current_org_id());

alter table public.documents add column if not exists is_locked boolean not null default false;
alter table public.cases add column if not exists legal_freeze boolean not null default false;
