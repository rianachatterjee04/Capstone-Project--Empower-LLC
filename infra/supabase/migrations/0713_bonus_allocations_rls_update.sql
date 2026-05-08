-- ON CONFLICT DO UPDATE on bonus_allocations requires an UPDATE RLS policy (not only INSERT).
-- Align bonus_pools roles with API (finance).

drop policy if exists bonus_allocations_update on public.bonus_allocations;
create policy bonus_allocations_update on public.bonus_allocations
for update
using (
  org_id = public.current_org_id()
  and public.current_role() in ('owner', 'admin', 'hr', 'finance')
)
with check (
  org_id = public.current_org_id()
  and public.current_role() in ('owner', 'admin', 'hr', 'finance')
);

drop policy if exists bonus_allocations_write on public.bonus_allocations;
create policy bonus_allocations_write on public.bonus_allocations
for insert
with check (
  org_id = public.current_org_id()
  and public.current_role() in ('owner', 'admin', 'hr', 'finance')
);

drop policy if exists bonus_pools_rw on public.bonus_pools;
create policy bonus_pools_rw on public.bonus_pools
for all
using (
  org_id = public.current_org_id()
  and public.current_role() in ('owner', 'admin', 'hr', 'finance')
)
with check (
  org_id = public.current_org_id()
  and public.current_role() in ('owner', 'admin', 'hr', 'finance')
);
