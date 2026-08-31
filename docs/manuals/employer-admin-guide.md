# Employer / Admin Guide

The operator's guide to running the whole business on Fintra: the finance OS (accounting,
close, reports), the industry verticals, procurement, rev rec, bill pay, cards, the
persona dashboards, HR admin, and the security/compliance layer. Each section links to
the per-module manual for step-by-step detail.

> Related: Dashboards *(not in this build)* · Security & compliance *(not in this build)*
> · the honest flow audit in `../E2E_FLOW_AUDIT.md`.

---

## 1. The finance OS — accounting, close, reports

Fintra **is** the ledger. Every economic event posts a real double-entry journal entry;
there's no external book to sync.

- **Accounting.** Invoices and bills auto-post AR/AP and revenue/expense entries;
  payments post cash entries (FX-aware, with realized gain/loss on settlement). Manual
  journals are available; posted entries are immutable and voided via reversal (full audit
  trail). Chart of accounts, contacts/customers/vendors, credit notes, fixed assets, and
  banking (Plaid feeds + reconciliation) round out the core.
- **The close.** The **Close Board** (`/close`) instantiates a task template (15 tasks in
  the SMB default) with a dependency graph and **auto-check rules** — e.g. when all bank
  recs are done, the "reconciliations complete" task auto-ticks and unblocks downstream
  tasks. Periods transition `in_progress → vertical_review → controller_review → approved
  → locked`. A days-to-close KPI tracks you against prior periods. `/month-end` is the
  lighter checklist view with a flux narrative and alerts.
- **Reports.** Trial balance, P&L, balance sheet, and cash flow — on **accrual or cash**
  basis (global toggle), for preset or custom periods, single- or multi-column
  (by month/quarter/year, with PY/PP comparisons), with parent/child account rollups.
  **Matrix reports** pivot by time and dimension. **Saved reports** recall your configs.
  Multi-currency consolidation via `reporting_currency`. The **Reports Center** is the
  QuickBooks-style browser; **Report Library** and **Multi-period** add more views.

---

## 2. The verticals

Native, in-ledger accounting for what your industry actually does:

- **Manufacturing** — BOMs, work orders, WA/standard/FIFO costing, variances, E&O
  reserves, perpetual inventory. Manual *(not in this build)*.
- **Construction / job costing** — cost codes, committed costs, change orders, AIA
  progress billing with retainage, POC revenue, and the WIP schedule.
  Manual *(not in this build)*.
- **Demand planning** — forecasting, safety stock, reorder points, KPIs — feeding
  procurement. Manual *(not in this build)*.

Enable a vertical for your org and its dashboard persona (plant manager, project manager)
lights up automatically.

---

## 3. Procurement

The full spend spine: **PO → approve → receive → 3-way match → bill → pay → inventory.**
Receiving accrues GR-IR; the 3-way match clears GR-IR and books purchase-price variance
before creating AP; supplier scorecards track on-time %, fill rate, lead time, and price
variance. Reorder suggestions from demand planning bridge into POs (draft-first). See the
Procurement manual *(not in this build)*.

---

## 4. Rev rec (ASC 606 — the ARM add-on)

License-gated. Build products with standalone selling prices and a recognition rule
(straight-line / milestone / point-in-time / usage), assemble contracts, allocate the
transaction price by relative SSP, and generate schedules. Posting an invoice can
**auto-schedule** recognition. Month-end, post recognition to book the period's revenue
against deferred revenue; watch the **deferred-revenue waterfall** and contract
asset/liability, and check the **ASC 606 auditor score**. See the
Rev rec manual *(not in this build)*.

---

## 5. Bill pay (guarded pay runs)

License-gated. **AI/OCR capture** reads an invoice into a draft bill; you review and post
(DR expense/inventory, CR AP). The differentiator is the **guarded pay run**: the
money-mover calls the **unified SentriAI decision engine** before releasing payment —
**held** items drop out of the run, released items post a balanced payment JE, and the run
fails soft to a fraud fallback if the engine is unreachable. Plus spend insights,
duplicate detection, 1099 management, and ACH batch export. See the
Bill pay manual *(not in this build)*.

---

## 6. Cards

License-gated. **Scaffolding — mock issuer, no real money.** Demonstrates the full card
model: issue virtual/physical cards, set spend controls (per-txn / daily / monthly /
lifetime limits, MCC allowlist, vendor lock, single-use), a **SentriAI at-the-swipe
authorization guard** that checks every swipe in real time, and **interchange/cashback →
GL** economics on settlement. This is the freemium+interchange card model shown
end-to-end, without a live money rail. See the Cards manual *(not in this build)*.

---

## 7. Dashboards (per persona)

Nine persona dashboards (`GET /dashboards/{role}`): employee, manager, HR, CFO/controller,
plant manager, project manager, CRO, CISO, and CEO. Owners/admins can switch lenses.
Every dashboard is **fail-soft** — it never 500s and never fakes a number; a missing
module shows an honest empty state. The CEO view rolls up an org-health score plus a
cross-module KPI strip (cash, runway, DSO, WIP, reorders, PO commitment, construction
under-billing, commission liability, AI trust). See the
Dashboards manual *(not in this build)*.

---

## 8. HR admin

The people side runs on the same identity and books.

- **Recruiting & AI interviewer.** Job and candidate CRUD with **explainable AI resume
  scoring**. The **AI interview copilot** generates questions from the JD + resume,
  records answers (written/audio/video), scores per competency, and produces a panel
  recommendation — every action audited. Recruiting ROI and talent intelligence analytics
  show cost-per-hire and source quality.
- **Onboarding.** Create packets (I-9, tax, benefits); new hires request and complete
  them. Hire syncs to a payroll employee automatically.
- **Performance.** Review cycles (self → manager → calibration) with AI discrepancy
  flagging; recognition; an ombudsman channel.
- **Comp cycles.** Open a cycle with a budget → managers propose → HR adjusts → exec
  approves → payroll export. Effective-dated comp history links raises to reviews.
- **Total Comp** unifies each pay stream per employee — target vs actual — and
  marks any stream it cannot reach as unavailable, with the reason.

See the HR API reference in `../../packages/hr-api/README.md`.

---

## 9. Security & compliance

The layer that guards every dollar. **SentriAI** (Adaptive Trust) and **AegisGraph**
(runtime action decision fabric) fuse into one **unified verdict** — `allow` / `step_up`
/ `hold` / `block` (stricter-wins). Every decision writes **hash-chained trust-ledger
evidence** and maps to **continuous compliance controls** (SOC 2, ISO 27001, HIPAA, GDPR,
SOX 404; PCI DSS opt-in), so your audit evidence accrues automatically. Admin surfaces:
the **Aegis console** (`/console`), **continuous-evidence**, the **trust centers** (AI /
HR / lead-to-cash), the **prompt firewall**, AI-exposure, and AI-governance.

**Demo-safe:** red-team runs are synthetic; phishing sends nothing; deepfake exercises are
persona text only. See the Security & compliance manual *(not in this build)*.

---

## 10. Platform administration

- **Licensing & seats.** The control plane (`../PLATFORM.md`) governs which modules,
  seats, and AI budget each org has. Add-ons (rev rec, bill pay, sales tax, cards,
  payroll) return `402` until activated.
- **RBAC & admin.** Company-scoped roles (owner, admin, accountant, user, viewer) with an
  admin passcode / step-up flow and an activity audit log (`/admin`).
- **Migration.** The QuickBooks migration wizard (`/migrate`) brings customers **onto**
  Fintra's books — source → conversion date → scope → connect/upload → review → reconcile
  → commit — as a one-time import, not an ongoing sync.
- **Integrations.** OAuth integrations hub (QBO, Workday, Carta, etc.).
- **AI gateway.** Every LLM call is metered per app through the gateway.

---

## FAQ

**Do I have to reconcile Fintra against QuickBooks?** No — Fintra is the ledger. The QBO
wizard migrates you off QuickBooks once.

**Which modules cost extra?** Rev rec (ARM), bill pay, sales tax, cards, and payroll are
license-gated add-ons; core accounting, verticals, dashboards, and HR are part of the
platform per your plan.

**How does a payroll run reach the GL?** Payroll's balanced journal entry is posted via a
secret-guarded, tenant-scoped code→id ingest bridge; unmapped account codes fail soft
(422 listing the missing codes) rather than posting a partial entry.

**Is any of the security demo doing something real?** No. Cards move no real money;
phishing/deepfake are simulations; the decision engine's verdicts are real, but the
attack content is synthetic.

> **Not in this build.** The cap table and equity module are not part of this
> evaluation build. Where equity was one input to a larger figure, the API
> reports it as unavailable with a reason rather than as zero.
