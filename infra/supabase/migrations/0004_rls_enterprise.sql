-- 0004_rls_enterprise.sql
-- RLS policies for new tables

alter table public.org_units enable row level security;
alter table public.employee_org_units enable row level security;
alter table public.salary_bands enable row level security;
alter table public.compensation_events enable row level security;
alter table public.market_benchmarks enable row level security;
alter table public.performance_cycles enable row level security;
alter table public.goals enable row level security;
alter table public.performance_reviews enable row level security;
alter table public.benefit_plans enable row level security;
alter table public.benefit_elections enable row level security;
alter table public.benefits_budget enable row level security;
alter table public.documents enable row level security;
alter table public.policies enable row level security;
alter table public.escalation_rules enable row level security;
alter table public.escalations enable row level security;
alter table public.integrations enable row level security;
alter table public.integration_sync_runs enable row level security;
alter table public.ai_memories enable row level security;

-- default helper
create or replace function public.in_org(uuid) returns boolean language sql stable as $$
  select $1 = public.current_org_id();
$$;

-- org units
drop policy if exists org_units_rw on public.org_units;
create policy org_units_rw on public.org_units
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'));

-- employee org units
drop policy if exists employee_org_units_rw on public.employee_org_units;
create policy employee_org_units_rw on public.employee_org_units
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'));

-- comp
drop policy if exists salary_bands_rw on public.salary_bands;
create policy salary_bands_rw on public.salary_bands
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists comp_events_select on public.compensation_events;
create policy comp_events_select on public.compensation_events
for select
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'));

drop policy if exists comp_events_write on public.compensation_events;
create policy comp_events_write on public.compensation_events
for insert
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

-- performance
drop policy if exists perf_cycles_rw on public.performance_cycles;
create policy perf_cycles_rw on public.performance_cycles
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists goals_select on public.goals;
create policy goals_select on public.goals
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or employee_id in (select id from public.employees where user_id = auth.uid())
  )
);

drop policy if exists goals_write on public.goals;
create policy goals_write on public.goals
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'));

drop policy if exists reviews_select on public.performance_reviews;
create policy reviews_select on public.performance_reviews
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or employee_id in (select id from public.employees where user_id = auth.uid())
  )
);

drop policy if exists reviews_update on public.performance_reviews;
create policy reviews_update on public.performance_reviews
for update
using (org_id = public.current_org_id())
with check (org_id = public.current_org_id());

drop policy if exists reviews_insert on public.performance_reviews;
create policy reviews_insert on public.performance_reviews
for insert
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'));

-- benefits
drop policy if exists benefit_plans_rw on public.benefit_plans;
create policy benefit_plans_rw on public.benefit_plans
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists benefit_elections_select on public.benefit_elections;
create policy benefit_elections_select on public.benefit_elections
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or employee_id in (select id from public.employees where user_id = auth.uid())
  )
);

drop policy if exists benefit_elections_write on public.benefit_elections;
create policy benefit_elections_write on public.benefit_elections
for insert
with check (org_id = public.current_org_id());

drop policy if exists benefits_budget_rw on public.benefits_budget;
create policy benefits_budget_rw on public.benefits_budget
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

-- documents
drop policy if exists documents_select on public.documents;
create policy documents_select on public.documents
for select
using (
  org_id = public.current_org_id()
  and (
    public.current_role() in ('owner','admin','hr','manager')
    or employee_id in (select id from public.employees where user_id = auth.uid())
  )
);

drop policy if exists documents_write on public.documents;
create policy documents_write on public.documents
for insert
with check (org_id = public.current_org_id());

drop policy if exists documents_update on public.documents;
create policy documents_update on public.documents
for update
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

-- policies & rules
drop policy if exists policies_rw on public.policies;
create policy policies_rw on public.policies
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists escalation_rules_rw on public.escalation_rules;
create policy escalation_rules_rw on public.escalation_rules
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists escalations_select on public.escalations;
create policy escalations_select on public.escalations
for select
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr','manager'));

drop policy if exists escalations_write on public.escalations;
create policy escalations_write on public.escalations
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

-- integrations
drop policy if exists integrations_rw on public.integrations;
create policy integrations_rw on public.integrations
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

drop policy if exists sync_runs_rw on public.integration_sync_runs;
create policy sync_runs_rw on public.integration_sync_runs
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

-- AI memories (read/write limited to hr/admin/owner by default)
drop policy if exists ai_memories_rw on public.ai_memories;
create policy ai_memories_rw on public.ai_memories
for all
using (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'))
with check (org_id = public.current_org_id() and public.current_role() in ('owner','admin','hr'));

-- Make audit_events append-only at DB level via RLS: only insert allowed; update/delete blocked
drop policy if exists audit_insert_only on public.audit_events;
create policy audit_insert_only on public.audit_events
for insert
with check (org_id = public.current_org_id());

drop policy if exists audit_no_update on public.audit_events;
create policy audit_no_update on public.audit_events
for update using (false) with check (false);

drop policy if exists audit_no_delete on public.audit_events;
create policy audit_no_delete on public.audit_events
for delete using (false);
