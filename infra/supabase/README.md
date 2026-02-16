# Supabase schema + RLS

This folder contains starter SQL migrations and RLS guidance.

Apply in Supabase SQL editor or via Supabase CLI migrations.

## RLS approach (recommended)
- Tables contain `org_id`
- Policies enforce that JWT `app_metadata.org_id` matches row `org_id`
- Service roles (backend) can bypass RLS if needed; best practice is *not* to bypass and instead use per-request `set_config` with JWT claims (advanced).

For MVP:
- Keep RLS on for client-facing access patterns
- Backend enforces tenant checks in queries (already implemented)

Next step:
- Add policies so `employees` can only see their own data; managers can see their reports; HR can see org-wide.
