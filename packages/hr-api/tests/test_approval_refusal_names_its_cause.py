"""
A refused approval says WHICH refusal it is.

WHY THIS IS A TEST
Approving anything answered

    403  "Approval exceeds authority level"

on a fresh deployment, for every request and every amount. The sentence is a
claim about the amount, and the amount was not the problem: approval_authority
starts empty, so no role and no user has any band at all and nothing is
approvable by anyone.

The two cases need different actions. "Above your authority" means escalate to
a bigger approver. "No authority configured" means nobody can approve anything
until someone sets it up — and an approver who reads the first message will go
looking for a colleague who does not exist.

Both are still 403. Only the sentence changes, and the sentence is the entire
useful content of a refusal.
"""
from __future__ import annotations

import ast
import pathlib

SOURCE = pathlib.Path("app/api/routers/approvals.py")


def _approve_source() -> str:
    tree = ast.parse(SOURCE.read_text())
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "approve"
    )
    return ast.unparse(fn)


def test_the_refusal_distinguishes_unconfigured_from_exceeded():
    src = _approve_source()
    assert "no approval authority is configured" in src, (
        "an approver on a fresh deployment is still told the amount exceeded "
        "their authority, when in fact no authority exists for anyone"
    )
    assert "above your authority" in src


def test_the_unconfigured_branch_actually_checks_the_table():
    """A message is not a diagnosis. It has to be reached by looking."""
    src = _approve_source()
    assert "approval_authority" in src and "count(*)" in src, (
        "the 'not configured' message is issued without checking whether any "
        "authority row exists, so it could be shown when one does"
    )


def test_both_branches_are_still_403():
    src = _approve_source()
    assert src.count("status_code=403") >= 2, (
        "a refusal must stay a 403 -- neither case is a server error, and "
        "neither is a success"
    )


def test_the_amount_and_role_appear_in_the_exceeded_message():
    """An approver needs to know what to escalate and from whom."""
    src = _approve_source()
    exceeded = src[src.index("above your authority") - 300:src.index("above your authority") + 200]
    assert "amount" in exceeded and "actor.role" in exceeded, exceeded
