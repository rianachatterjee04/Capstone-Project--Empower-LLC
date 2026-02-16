-- 0002_rls_policies.sql
-- Tenant isolation + role-based access

alter table public.orgs enable row level security;
alter table public.employees enable row level security;
alter table public.onboarding_packets enable row level security;
alter table public.cases enable row level security;
alter table public.job_postings enable row level security;
alter table public.candidates enable row level security;
alter table public.audit_events enable row level security;

-- orgs: users can only see their own org row (by claim)
drop policy if exists orgs_select on public.orgs;
create policy orgs_select on public.orgs
for select
using (id = public.current_org_id());

-- employees: HR/admin/owner can read/write within org. managers can read their subtree (MVP: same org). employees can read self.
drop policy if exists employees_select on public.employees;
create policy employees_select on public.employees
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or user_id = auth.uid()
  )
);

drop policy if exists employees_insert on public.employees;
create policy employees_insert on public.employees
for insert
with check (
  org_id = public.current_org_id()
  and public.current_role() in ('owner','admin','hr')
);

drop policy if exists employees_update on public.employees;
create policy employees_update on public.employees
for update
using (
  org_id = public.current_org_id()
  and public.current_role() in ('owner','admin','hr')
)
with check (
  org_id = public.current_org_id()
  and public.current_role() in ('owner','admin','hr')
);

-- onboarding packets
drop policy if exists onboarding_select on public.onboarding_packets;
create policy onboarding_select on public.onboarding_packets
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or employee_id in (select id from public.employees where user_id = auth.uid())
  )
);

drop policy if exists onboarding_insert on public.onboarding_packets;
create policy onboarding_insert on public.onboarding_packets
for insert
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists onboarding_update on public.onboarding_packets;
create policy onboarding_update on public.onboarding_packets
for update
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr')
    or employee_id in (select id from public.employees where user_id = auth.uid())
  )
)
with check (org_id = public.current_org_id());

-- cases
drop policy if exists cases_select on public.cases;
create policy cases_select on public.cases
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or (
      -- reporter can read non-anonymous cases they filed
      reporter_employee_id in (select id from public.employees where user_id = auth.uid())
      and is_anonymous = false
    )
  )
);

drop policy if exists cases_insert on public.cases;
create policy cases_insert on public.cases
for insert
with check (org_id = public.current_org_id());

drop policy if exists cases_update on public.cases;
create policy cases_update on public.cases
for update
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

-- recruiting
drop policy if exists jobs_select on public.job_postings;
create policy jobs_select on public.job_postings
for select
using (org_id = public.current_org_id());

drop policy if exists jobs_write on public.job_postings;
create policy jobs_write on public.job_postings
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'));

drop policy if exists cands_select on public.candidates;
create policy cands_select on public.candidates
for select
using (org_id = public.current_org_id());

drop policy if exists cands_write on public.candidates;
create policy cands_write on public.candidates
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'));

-- audit
drop policy if exists audit_select on public.audit_events;
create policy audit_select on public.audit_events
for select
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists audit_insert on public.audit_events;
create policy audit_insert on public.audit_events
for insert
with check (org_id = public.current_org_id());
