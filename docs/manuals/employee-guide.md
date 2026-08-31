# Employee Guide

Everything you do as an employee in Fintra, in one place: your pay and Total Comp,
expenses, time off, and your goals, reviews, and tasks. One login lands you in
the hub; this guide walks each surface in the order you'll actually use it.

> Related manual: [Total Comp](./modules/total-comp.md).

---

## Your employee dashboard

Your home is the **employee dashboard** (`GET /dashboards/employee`, rendered at `/home`).
It shows the numbers that are about *you*:

- **Target total comp** vs **actual to date**, and your **comp attainment %**.
- **PTO balance** in days.
- A **comp-mix donut** (how base / bonus / benefits split) and a **target-vs-actual**
  bar.

If a piece isn't connected yet (say your org hasn't wired Total Comp), the dashboard
degrades to a calm "not connected" note rather than erroring — it never shows a fake
number.

---

## My pay & Total Comp

Total Comp is the single view that answers "what am I actually paid?" It combines five
streams into one target-vs-actual picture:

1. **Base** salary and **bonus** (from HR).
2. **Commission** (if you're on a sales plan — `quota × commission_pct`).
3. **Payroll actuals** (your YTD, via the internal payroll seam).

Open your **Compensation** page in the employee portal. You'll see cash (base + bonus
+ benefits), your annualized value, and the target vs actual for each component.
Because it's assembled fail-soft, a missing source is flagged as unavailable rather than
silently shown as zero.

> **How do I see my pay stubs and YTD?** Pay stubs, YTD, and W-2 status come from the
> payroll module's employee portal (`my-paystubs`, `my-ytd`, `my-w2-status`). Your SSN
> and bank number are encrypted and masked — you'll only ever see the last few digits.

See the full [Total Comp manual](./modules/total-comp.md).

---

## Expenses (T&E): snap → submit → reimburse

Expenses are native to the ledger — no separate app, no CSV export.

1. **Capture.** On the **Expenses** page, upload a receipt photo or PDF. Fintra reads it
   and **AI-codes the GL account, amount, and vendor** for you. If the AI is unavailable,
   you fall back to manual entry — nothing blocks.
2. **Review.** Check the parsed account and amount. The system runs a **policy check**
   and flags anything outside policy (it can auto-approve within limits).
3. **Submit.** Group expenses into a report and submit it. It lands in your manager's
   unified approvals inbox.
4. **Reimburse.** When approved, a **reimbursement run** posts a balanced journal entry
   in the ledger. (This produces GL entries and file records — not a live ACH transfer.)

Mileage and per-diem use deterministic rules. See the Expenses manual *(not in this build)*.

---

## PTO (time off)

On the **PTO** page in the employee portal:

1. **Request** time off — start date, end date, reason. Submit.
2. Watch the **status** — pending → approved / denied. Your manager approves.
3. Check your **balance** tab — accrued, used, and remaining. Approved requests post to
   the time-off ledger (the same accrual engine payroll uses).

---

## Goals & reviews

- **Goals / OKRs.** Your objectives and key results live under **Goals**, scoped to the
  current cycle. You (and your manager) update key-result progress as you go.
- **Performance reviews.** In a review cycle you **submit a self-review**; your manager
  submits theirs. Fintra's AI **flags discrepancies** between the two for the calibration
  step. Raises made off a review are effective-dated and link back to the review, so your
  comp history shows exactly why a number changed.

---

## My records & profile

Under **Employee records / Profile** you can view your own:

- **Comp history** (effective-dated — each change closes the previous record).
- **Job history** (title, department, location changes over time).
- **Emergency contacts** and profile fields — which you can update yourself (every edit
  is audited).

---

## Tasks & requests

- **Onboarding checklist.** As a new hire you'll request and complete your onboarding
  packet (I-9, tax forms, benefits) and tick items to done.
- **Requests & approvals.** Anything you submit that needs a sign-off (an expense report,
  a PTO request) is tracked to its decision in the unified approvals system.

---

## FAQ

**My commission shows on Total Comp but not my pay stub — why?** Total Comp aggregates
projected commission (`quota × commission_pct`); the stub shows what's actually been paid
through payroll. They reconcile as commission is paid out.

**Is my receipt data sent anywhere risky?** Receipt parsing runs through the metered AI
gateway; if it's down you code the expense manually. Sensitive identifiers are handled by
the payroll service (encrypted, masked).

> **Not in this build.** The cap table and equity module are not part of this
> evaluation build. Where equity was one input to a larger figure, the API
> reports it as unavailable with a reason rather than as zero.
