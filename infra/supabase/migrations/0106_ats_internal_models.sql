create table if not exists public.ats_job_postings (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  external_id text not null,
  title text not null,
  location text null,
  status text null,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique(org_id, provider, external_id)
);

create table if not exists public.ats_candidates (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  external_id text not null,
  name text null,
  email text null,
  stage text null,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique(org_id, provider, external_id)
);

alter table public.ats_job_postings enable row level security;
alter table public.ats_candidates enable row level security;

drop policy if exists ats_jobs_rw on public.ats_job_postings;
create policy ats_jobs_rw on public.ats_job_postings
for all using (org_id = public.current_org_id()) with check (org_id = public.current_org_id());

drop policy if exists ats_candidates_rw on public.ats_candidates;
create policy ats_candidates_rw on public.ats_candidates
for all using (org_id = public.current_org_id()) with check (org_id = public.current_org_id());
