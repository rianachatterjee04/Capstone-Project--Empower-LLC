# Manager Guide

You manage a team. This guide covers the four things you do in Fintra as a manager: read
your team's comp, approve time off, run reviews and comp proposals, and clear your
approvals inbox — plus the Manager Copilot that surfaces what needs your attention.

> Related manuals: [Total Comp](./modules/total-comp.md) · Dashboards *(not in this build)*.

---

## Your manager dashboard & copilot

Your **manager dashboard** (`GET /dashboards/manager`) leads with the operational numbers
you own:

- **Approvals pending** and **approvals overdue** (an overdue item names the bottleneck
  owner and raises a warning).
- **Automation coverage %** and **open reconciliations**.
- Up to three ranked **top actions** scoped to your role.

The **Manager Copilot** (`/manager-copilot`) is your daily read: it flags who's
**overloaded**, **attrition risk**, **promotion readiness**, and **1:1 prep**. Every
insight links to the evidence behind it and writes an AI receipt — nothing is a black box.

---

## My team's comp

Total Comp isn't just an employee view — as a manager you can read the **roster roll-up**
for your reports: each person's base + bonus + benefits + commission + payroll actuals,
target vs actual, and the aggregate for your team.

Use it before a comp cycle to see where people sit against target, and during the cycle
to keep proposals inside budget. See the [Total Comp manual](./modules/total-comp.md).

---

## PTO approvals

When a report requests time off it lands in your queue:

1. Open the **PTO** requests list (or the request surfaces in your approvals inbox).
2. Review the dates and reason.
3. **Approve** (or deny). Approval posts a usage entry to the time-off ledger and updates
   the employee's balance.

---

## Reviews & comp cycles

### Performance reviews
In a review cycle: your report submits a **self-review**, you submit the **manager
review**. Fintra's AI **flags discrepancies** between the two so calibration is grounded
in specifics. HR runs the calibration and final approval.

### Comp cycle (proposing raises)
When HR opens a **comp cycle** with a budget:

1. You **propose** salary / bonus per report, with a justification.
2. HR **adjusts** (they can override with approved figures).
3. The cycle is **submitted for executive approval**, which triggers the payroll export.

Raises tie back to the driving review (`review_id`), so the employee's effective-dated
comp history shows the reason.

---

## The unified approvals inbox

`/approvals` is one queue for everything that needs your sign-off — **expense reports,
budget overrides, bill pay, payroll, commission** — not a separate inbox per module.

- Items are sorted by **age** and **SLA remaining**, with an **overdue** flag.
- Each row shows the amount, who requested it, and the **source module**.
- Open a row to **approve or reject with a comment**; the decision is dispatched back to
  the originating module (approving an expense updates its report status, etc.).
- **Authority tiers** apply: you can only approve within your amount tier (a per-user
  override wins if set). Over-tier items route up.
- A **team approvals** tab appears if you have reports; an **external payroll** section is
  read-only (syndicated from Workday/ADP where connected).

---

## FAQ

**A payment I need to approve isn't in my inbox — where is it?** Guarded pay runs (bill
pay) route by amount tier and category; if it's above your authority it went to the next
approver. Check the source-module column and the tier.

**Can I see why a raise was given?** Yes — comp changes are effective-dated and link to
the review that drove them, visible in the employee's comp history.

**Does approving an expense move money?** No. It advances the report to reimbursable; the
reimbursement run later posts GL entries and file records (not a live ACH transfer).

**The copilot flagged someone as overloaded — is that real data?** The copilot's demo
surface uses deterministic data; wired to live signals it draws from workload, incident
rotations, and attrition models, always with an evidence link.

> **Not in this build.** The cap table and equity module are not part of this
> evaluation build. Where equity was one input to a larger figure, the API
> reports it as unavailable with a reason rather than as zero.
