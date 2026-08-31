# Security Model — Fintra

Fintra is a multi-tenant SaaS handling financial, HR, compliance, and AI-governance
data. This document is the security contract every change must uphold. See
`SECURITY_AUDIT_REPORT.md` for the audit and the launch checklist.

## Reporting a vulnerability
Email **security@fintrahub.com** (or jaimani1@gmail.com until that inbox exists). Do
not open public issues for security bugs. Include repro steps and impact.

## Authentication
- Auth is Supabase JWTs. The platform project (wixb) issues **ES256** (verified via
  JWKS); other projects may use HS256. Services pin the accepted algorithm to the
  project's real scheme and **reject any other `alg`**. Never select the algorithm
  from the token header.
- All identity, role, and tenant claims come from **`app_metadata`** (server-set),
  never `user_metadata` (user-editable).
- **Dev auth** (`FINTRA_DEV_AUTH`, `dev:` bearer tokens) is reachable ONLY when
  `APP_ENV`/`ENV` is `development`/`dev`/`test`/`local`. Production (the secure
  default when unset) rejects it. Never set those flags in a real deploy.
- Every protected page, API route, RPC, and query must verify the user **server-side**.
  Frontend hiding is UX only, never an authorization boundary.

## Tenant isolation (the most important rule)
- Tenants are keyed by `organization_id` (control-api), `company_id` (accounting),
  `org_id` (hr/compliance). **Derive the tenant from the verified token, never from
  the request body, query, or path.** Client-supplied tenant ids are ignored.
- Every read filters by the caller's tenant; every write forces the tenant + actor
  server-side; updates/deletes verify ownership (cross-tenant ⇒ 403/404).
- Deny by default: access is granted only when explicitly allowed.

## Row Level Security (RLS)
- RLS is **defense-in-depth**. The backends currently use the Supabase service_role
  key, which bypasses RLS, so the primary control is the app-code isolation above.
- Sensitive tables still enable RLS with `company_id`/`org_id` isolation policies
  (`company_id IN (SELECT company_id FROM users WHERE id = auth.uid())`). Service
  helper policies are restricted `TO service_role`, never `USING(true)` for all roles.
- Goal state: run user-scoped reads under the user's JWT so RLS becomes a live control.

## Secrets & environment variables
- No secret is ever committed. `.gitignore` blocks all `.env*` (except `*.example`).
- Private secrets never carry a `NEXT_PUBLIC_`/`VITE_` prefix (those ship to the
  browser). The `service_role` key is server-only and never reaches any frontend.
- Required secrets **fail closed in production** (the app refuses to boot if missing
  or still set to a placeholder). Secret comparisons use `hmac.compare_digest`.

## AI / LLM security
- Treat the model as **untrusted**. Never let it police itself.
- Enforce permission + tenant checks in app code **before and after** model calls.
  AI must never read another tenant's data or act outside the caller's permissions.
- The ai-gateway fails **closed** (no inference for unknown/unprovisioned orgs),
  enforces an internal shared secret, and caps request size (model-DoS / cost guard).
- High-impact AI actions (writes to finance/HR/commission/compliance, sending email,
  triggering integrations) require an explicit app-level approval gate. Filter model
  output for secrets/PII before returning it.

## Webhooks & integrations
- Verify the provider signature and timestamp; reject unsigned/expired/malformed
  requests; be idempotent (dedup on the provider event id); never trust external ids
  for tenant mapping. The Stripe webhook follows this pattern.

## File uploads
- Validate type/extension/size; store under tenant-scoped paths in private buckets;
  serve via short-lived signed URLs; never render uploaded HTML/SVG; treat every
  uploaded document as untrusted input (including for AI/RAG).

## Transport / headers
- Production sends HSTS, X-Frame-Options/`frame-ancestors 'none'`, X-Content-Type-
  Options, Referrer-Policy, Permissions-Policy, and a CSP (strict on the static
  marketing site). HTTPS only.

## Incident response (basics)
1. Rotate the affected credential immediately (Supabase keys, JWT/internal secrets).
2. Revoke active sessions / API keys; check audit logs for the blast radius.
3. Patch, deploy, then write a short post-mortem. Treat any secret seen in a repo,
   log, or error as compromised.
