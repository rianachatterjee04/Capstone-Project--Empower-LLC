create table if not exists public.pto_requests (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  employee_id uuid not null references public.employees(id) on delete cascade,
  start_date date not null,
  end_date date not null,
  reason text not null,
  status text not null default 'pending' check (status in ('pending','approved','denied')),
  reviewed_by_user_id uuid null,
  reviewed_at timestamptz null,
  review_note text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (end_date >= start_date)
);

create index if not exists pto_requests_org_idx
  on public.pto_requests(org_id);

create index if not exists pto_requests_org_status_idx
  on public.pto_requests(org_id, status);

drop trigger if exists pto_requests_set_updated_at on public.pto_requests;
create trigger pto_requests_set_updated_at before update on public.pto_requests
for each row execute function public.set_updated_at();
