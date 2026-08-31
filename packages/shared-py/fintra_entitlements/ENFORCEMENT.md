# Module enforcement — how "turn a module on/off" is made real

Each backend composes its existing auth with a thin **entitlements bridge** and
attaches it as a **router-level dependency** on its core routers, so a disabled
module actually blocks the API (402/403), not just the UI.

| Module      | Backend        | Bridge dependency            | Gated on                                   |
|-------------|----------------|------------------------------|--------------------------------------------|
| accounting  | `packages/api` | `require_accounting_access`  | core accounting routers (accounts, journals, reports, invoices, bills, payments, expenses, banking, reconciliation, periods, tax, FX, …) |
| hr          | `packages/hr-api` | `require_hr_access`       | core HR data routers (employees, reports, onboarding, recruiting, cases, timeoff, pto, performance, reviews, benefits, bonuses, org chart, documents, goals, …) |
| compliance  | `packages/sentri-api` | `require_compliance_access` | core compliance routers (profile, frameworks, controls, control-tests, audits, risks, vendors, policies) |

Public/service routers are intentionally **not** gated: finance public quote
portal, HR `/health` and `ai_internal` (service-to-service auth), compliance
`/auth` (login) and the evidence router.

## Enforcement model (prod-safe)

Two env flags, read live per request:

- **`FINTRA_ENFORCE`** — default **`1`** (ON). Set `0` to disable gating entirely.
- **`FINTRA_FAIL_OPEN`** — default **`1`**. Controls behaviour only when the
  control plane is **unreachable** (missing config, network error, bad key):
  - `1` (default): **fail-open** → request is allowed. Keeps local/dev/test and
    control-plane outages from bricking every module.
  - `0`: **fail-closed** → request gets `503 entitlement_unavailable`.

A *definitive* "not licensed" answer from the control plane is **never**
fail-open — it always returns `402 module_not_licensed` (or `403 seat_required`).

### Production checklist
- Set `FINTRA_ENFORCE=1` (already the default).
- Set `FINTRA_FAIL_OPEN=0` to fail closed on a control-plane outage.
- Point `PLATFORM_SUPABASE_URL` / `PLATFORM_SUPABASE_SERVICE_KEY` at the platform
  (control-plane) Supabase project that owns the `cp_*` tables.
- HR only: leave `FINTRA_ALLOW_DEMO_TOKEN` unset (the unsigned `dev:` auth bypass
  is off by default; if set in prod it still works but logs a loud warning).

## Reconciliation: control-plane `org_id` ↔ finance `company_id`

The control plane keys everything on `cp_organizations.id`. There is **no mapping
table** — the id model is 1:1 by construction (see `control-api/schema.sql`):

> `cp_organizations.id` IS the tenant id used everywhere — it is reused as
> accounting `company_id`, HR `org_id`, compliance `org_id`. A self-serve signup
> mints `cp_organizations.id` first, then each module provisions its tenant row
> with that exact UUID.

So the bridges resolve the entitlement decision using the request's own tenant id
directly:

- accounting: `org_id = auth["company_id"]`
- hr: `org_id = actor.org_id`
- compliance: `org_id = current_user.org_id`

The invariant `accounting company_id == control-plane org_id` is asserted by
`packages/api/tests/test_module_enforcement.py::
test_enabled_module_allows_and_keys_on_company_id` (the id handed to
`entitlements.require_module` is exactly the caller's `company_id`), and was
verified end-to-end against the seeded org `856bd3e4-…-314bf` (Northwind
Robotics), whose `cp_organizations.id` equals its finance `company_id`.

> **Cross-references.** Paths under `packages/api`, `packages/payroll`, `packages/sentri-api`
> and similar refer to services in the wider Fintra platform that are **not part of this
> build**. They are named so the seam is visible, not because the code ships here.
