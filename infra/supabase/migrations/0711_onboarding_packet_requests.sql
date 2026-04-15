-- Employee-initiated requests for HR to create an onboarding packet
create table if not exists public.onboarding_packet_requests (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.orgs(id) on delete cascade,
  requested_by_user_id uuid not null,
  employee_id uuid null references public.employees(id) on delete set null,
  requester_email text null,
  message text null,
  status text not null default 'pending' check (status in ('pending','done')),
  created_at timestamptz not null default now(),
  resolved_at timestamptz null
);

create index if not exists onboarding_packet_requests_org_idx
  on public.onboarding_packet_requests(org_id);

create index if not exists onboarding_packet_requests_org_pending_idx
  on public.onboarding_packet_requests(org_id, status)
  where status = 'pending';

-- At most one open request per user per org
create unique index if not exists onboarding_packet_requests_one_pending_per_user
  on public.onboarding_packet_requests(org_id, requested_by_user_id)
  where status = 'pending';
