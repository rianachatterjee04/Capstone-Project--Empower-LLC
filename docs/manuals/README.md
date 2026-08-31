# Fintra User Manuals

Task-oriented documentation for the fully-assembled Fintra platform. Everything here is
written against the code that shipped on `integration/platform` — no roadmap features.
For the honest cross-module flow audit (what's wired, what's a known gap), see
`../E2E_FLOW_AUDIT.md`. For positioning, see `../POSITIONING.md`.

## Role-based guides — start here

Pick the guide that matches your seat. Each links out to the per-module manuals for the
"how do I…" detail.

- **[Employee guide](./employee-guide.md)** — my pay, my Total Comp,
  expenses (T&E), PTO, goals & reviews, tasks.
- **[Manager guide](./manager-guide.md)** — my team's comp, PTO, reviews, and the unified
  approvals inbox.
- **[Employer / Admin guide](./employer-admin-guide.md)** — the finance OS (accounting,
  close, reports), verticals, procurement, rev rec, bill pay, cards, dashboards, HR admin
  (recruiting/AI interviewer/performance/comp cycles), and security/compliance.

## Per-module manuals

| Module | Manual |
|---|---|
| Manufacturing (BOM / work orders / costing / E&O) | manufacturing.md *(not in this build)* |
| Construction (jobs / AIA billing / WIP / POC) | construction.md *(not in this build)* |
| Demand planning | demand-planning.md *(not in this build)* |
| Procurement (PO → receive → 3-way → pay) | procurement.md *(not in this build)* |
| Multi-currency | multi-currency.md *(not in this build)* |
| Rev rec (waterfall / usage / auto-schedule) | rev-rec.md *(not in this build)* |
| Bill pay (AI capture / guarded pay runs / spend insights) | bill-pay.md *(not in this build)* |
| Expenses (T&E) | expenses.md *(not in this build)* |
| Cards (issue / controls / at-swipe guard / interchange) | cards.md *(not in this build)* |
| Total Comp | [total-comp.md](./modules/total-comp.md) |
| Dashboards (per role) | dashboards.md *(not in this build)* |
| Security & compliance layer | security-compliance.md *(not in this build)* |

## Safety framing (true across every manual)

- **Cards move no real money.** The card program is scaffolding: a pluggable mock issuer
  that demonstrates issue → controls → at-swipe guard → interchange→GL. No real card is
  provisioned and no funds move.
- **Payroll credentials are hash-only.** SSNs and bank numbers are encrypted at rest,
  masked everywhere, and never logged. The payroll license key is compared by hash; the
  plaintext is not stored in the repo.
- **Phishing and deepfake exercises are demo-safe.** Phishing is a deterministic
  simulation that transmits nothing; deepfake exercises are persona/scenario text only,
  never real media.
- **Reimbursements produce GL entries and file records**, not a live ACH money movement.

## The one-login model

One sign-in lands you in the unified hub. What you see is governed by your platform role
and the modules your organization has licensed (`../PLATFORM.md`). Add-on modules (rev
rec / ARM, bill pay, sales tax, cards, payroll) are license-gated and return `402` until
activated.
