create table if not exists public.integration_cursors (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  cursor jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique (org_id, provider)
);

create table if not exists public.ats_stage_mappings (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  external_stage text not null,
  internal_stage text not null,
  updated_at timestamptz not null default now(),
  unique(org_id, provider, external_stage)
);

create table if not exists public.ats_job_screening_criteria (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  job_external_id text not null,
  criteria jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique(org_id, provider, job_external_id)
);

create table if not exists public.ats_screening_scores (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  provider text not null,
  candidate_external_id text not null,
  job_external_id text null,
  score numeric not null,
  rationale text null,
  model text null,
  created_at timestamptz not null default now(),
  unique(org_id, provider, candidate_external_id, job_external_id)
);

alter table public.integration_cursors enable row level security;
alter table public.ats_stage_mappings enable row level security;
alter table public.ats_job_screening_criteria enable row level security;
alter table public.ats_screening_scores enable row level security;

drop policy if exists integration_cursors_rw on public.integration_cursors;
create policy integration_cursors_rw on public.integration_cursors
for all using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists stage_mappings_rw on public.ats_stage_mappings;
create policy stage_mappings_rw on public.ats_stage_mappings
for all using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists job_criteria_rw on public.ats_job_screening_criteria;
create policy job_criteria_rw on public.ats_job_screening_criteria
for all using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists screening_scores_select on public.ats_screening_scores;
create policy screening_scores_select on public.ats_screening_scores
for select using (org_id = public.current_org_id());

drop policy if exists screening_scores_write on public.ats_screening_scores;
create policy screening_scores_write on public.ats_screening_scores
for insert with check (org_id = public.current_org_id());
