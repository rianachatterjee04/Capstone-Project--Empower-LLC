# Total Comp Manual

One target-vs-actual number per employee, assembled from five compensation streams across
finance and payroll.

Backend: `hr-api routes/total_comp.py` (`app/services/total_comp_service.py`), with the
commission stream from `packages/api routes/sales_commission.py`. Employee view in the HR
portal's **Compensation** page.

---

## What are the five streams?

`build_total_comp()` assembles:

1. **Base** salary (HR).
2. **Bonus** (HR).
3. **Commission** — `quota × commission_pct` for reps on a sales plan.
4. **Payroll actuals** — YTD, via the internal payroll seam (`X-Internal-Secret`).

Each is shown **target vs actual**; the view is **fail-soft** — a missing source is
flagged unavailable, never silently zeroed.

## How do I view it?

- **Employee:** your own total comp (`GET /comp/total/{employee_id}`, or self via your
  token) — cash stacked, annualized value, target vs actual per component.
- **HR / admin / manager:** the roster roll-up (`GET /comp/total?plan_year=&employee_ids=`)
  with an org-level target-vs-actual aggregate.

## How does the commission stream stay correct?

The leaderboard the HR side reads surfaces `commission_pct` on each row, so target
commission (`quota × pct`) computes correctly. (This was a fixed seam — before the fix HR
silently computed 0; see `../E2E_FLOW_AUDIT.md`.) Billing-basis commission accrues only
after the invoice posts and its AR/revenue JE exists, not at draft-create.

## How does it connect to payroll and the GL?

Total Comp reads payroll YTD through the internal seam. Separately, commission **payouts**
post a GL JE, and **payroll runs** post their own balanced JE into the ledger via the
code→id ingest bridge — so "what we owe" (Total Comp) and "what we paid" (the GL)
reconcile.

---

### Related
[Employee guide](../employee-guide.md) · [Manager guide](../manager-guide.md) ·
Dashboards *(not in this build)* (HR and employee comp tiles).

> **Not in this build.** The cap table and equity module are not part of this
> evaluation build. Where equity was one input to a larger figure, the API
> reports it as unavailable with a reason rather than as zero.
