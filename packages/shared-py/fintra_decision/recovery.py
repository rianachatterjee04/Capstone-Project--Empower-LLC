"""Recovery / compensation planner — domain-neutral, pluggable.

"Restore the snapshot" is NOT business recovery. Undoing a machine action can be a
clean rollback (re-attach the IAM policy that was detached), a *compensating
transaction* (a payment already settled cannot be un-sent — it needs a recall or a
compensating journal), or genuinely irreversible with human intervention required.

This module lets each action type declare, up front, how it would be undone. Pure
+ dependency-free: planners are registered functions returning a canonical
`Recovery`. The assurance flows attach the plan to the Proof Object so recovery is
known *before* anything executes.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from .contract import Recovery

Planner = Callable[[Dict[str, Any]], Recovery]
_PLANNERS: Dict[str, Planner] = {}


def register_recovery(action_type: str) -> Callable[[Planner], Planner]:
    def deco(fn: Planner) -> Planner:
        _PLANNERS[action_type] = fn
        return fn
    return deco


def plan_recovery(action_type: str, context: Dict[str, Any] | None = None) -> Recovery:
    """Return the recovery plan for an action. Unknown action => fail-safe: not
    reversible, human required (never a false 'we can undo this')."""
    ctx = context or {}
    fn = _PLANNERS.get(action_type)
    if fn is None:
        return Recovery(recovery_id=f"rec:{action_type}", reversible=False, requires_human=True,
                        irreversible_consequences=["no recovery planner registered for this action"],
                        status="planned")
    r = fn(ctx)
    r.recovery_id = r.recovery_id or f"rec:{action_type}"
    return r


# ── security: IAM / RBAC changes are reversible by restoring prior state ─────
@register_recovery("change_iam")
def _rec_iam(ctx):
    return Recovery(reversible=True, rollback_mechanism="restore_previous_iam_policy_and_attachments",
                    compensating_actions=[], requires_human=(ctx.get("blast_radius") == "enterprise"),
                    dependencies=["prior IAM policy snapshot"], status="planned")


@register_recovery("change_rbac")
def _rec_rbac(ctx):
    return Recovery(reversible=True, rollback_mechanism="restore_previous_rbac_bindings",
                    compensating_actions=[], requires_human=False,
                    dependencies=["prior RoleBinding/ClusterRoleBinding snapshot"], status="planned")


# ── finance: reversibility depends on whether money already moved ────────────
def _rec_money(ctx):
    """A payment/payroll: cancellable before release; after ACH settlement it needs a
    recall + compensating accounting — NOT a data restore."""
    settled = bool(ctx.get("settled"))
    released = bool(ctx.get("released"))
    if not released:
        return Recovery(reversible=True, rollback_mechanism="cancel_unreleased_payment",
                        requires_human=False, dependencies=["payment not yet released"], status="planned")
    if not settled:
        return Recovery(reversible=True, rollback_mechanism="delete_pending_ach_entry_before_settlement",
                        requires_human=True, dependencies=["before ACH settlement window closes"],
                        status="planned")
    return Recovery(reversible=False, rollback_mechanism="",
                    compensating_actions=["initiate_ach_reversal_or_recall", "post_compensating_journal",
                                          "collect_overpayment_from_recipient"],
                    irreversible_consequences=["funds have left the originating account"],
                    requires_human=True, dependencies=["Nacha reversal eligibility window"], status="planned")


for _act in ("pay_invoice", "run_payroll", "send_wire", "issue_refund"):
    register_recovery(_act)(_rec_money)


@register_recovery("post_journal")
def _rec_journal(ctx):
    return Recovery(reversible=True, rollback_mechanism="post_reversing_journal_entry",
                    requires_human=False, dependencies=["open accounting period"], status="planned")
