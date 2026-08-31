"""What a non-privileged caller can receive from the ombudsman channel.

This is the whistleblowing surface. Its own docstring says managers are
"explicitly excluded by default to avoid retaliation risk", which makes the
shape of the non-privileged response a safety property rather than a
formatting choice.

WHAT PROMPTED THIS
`_redact` -- "Crude PII redaction for surfaces visible to non-privileged roles"
-- is defined in that router and called by nothing, in production or in tests.
Chasing it down showed the endpoint is SAFER than its own docstring claims: it
does not send non-privileged callers redacted case text, it sends them no case
text at all. Redaction is a filter someone has to remember to apply; omission
cannot be forgotten.

But that stronger behaviour was accidental in the sense that nothing asserted
it, and the dead helper is a standing invitation to "fix" the gap by sending
redacted details instead -- which would be a downgrade wearing the costume of
an improvement. So the omission is pinned here.

The router has no other behavioural coverage; the tests are structural because
public.cases is not in the schema the hr-api test databases build, and a claim
about which keys a branch can emit is a property of the code rather than of any
particular row.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

ROUTER = (pathlib.Path(__file__).parent.parent
          / "app" / "api" / "routers" / "ombudsman.py")
SOURCE = ROUTER.read_text()
TREE = ast.parse(SOURCE)

#: Anything carrying the reporter's own words, or a person's identity.
FREE_TEXT = ("details", "_summarize", "summary", "description", "notes",
             "reporter_name", "employee_name", "email")


def _func(name):
    for node in ast.walk(TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    pytest.fail(f"{name} not found — this guard needs updating")


def _split_on_privileged(node):
    """(privileged-branch source, everything after it).

    The endpoint returns early for privileged roles, so 'after' is the
    non-privileged path.
    """
    src = ast.get_source_segment(SOURCE, node)
    assert src, "could not read the handler's source"
    marker = "if actor.role in PRIVILEGED_ROLES:"
    assert marker in src, "the privileged branch is no longer written this way"
    head, tail = src.split(marker, 1)
    # the privileged branch runs until the dedented comment that follows it
    parts = re.split(r"\n    # Non-privileged", tail, maxsplit=1)
    assert len(parts) == 2, "the non-privileged branch is no longer marked"
    return parts[0], parts[1]


# ── the property ──────────────────────────────────────────────────────────

def test_a_non_privileged_caller_receives_no_case_free_text():
    _, non_priv = _split_on_privileged(_func("list_cases_ombudsman"))
    leaked = [f for f in FREE_TEXT if f in non_priv]
    assert not leaked, (
        f"the non-privileged branch of the ombudsman list now references "
        f"{leaked}. A reporter's own words are the most identifying thing in "
        f"a case: redacting them is a filter someone must remember to apply, "
        f"omitting them cannot be forgotten.")


def test_a_non_privileged_caller_sees_only_their_own_cases():
    _, non_priv = _split_on_privileged(_func("list_cases_ombudsman"))
    assert "e.user_id = :uid" in non_priv, (
        "the reporter query no longer filters to the caller's own user. "
        "Managers reading their reports' cases is the retaliation risk this "
        "router says it exists to avoid.")


def test_the_dashboard_and_ai_summary_stay_privileged():
    """Both read case text. Both must refuse a non-privileged caller."""
    for name in ("risk_dashboard", "ai_summary"):
        node = next((n for n in ast.walk(TREE)
                     if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                     and n.name == name), None)
        if node is None:
            continue
        src = ast.get_source_segment(SOURCE, node) or ""
        assert "PRIVILEGED_ROLES" in src, f"{name} has no privilege check"
        assert re.search(r"not in PRIVILEGED_ROLES", src), (
            f"{name} does not refuse a non-privileged caller")


# ── controls ──────────────────────────────────────────────────────────────

def test_control_the_privileged_branch_does_carry_case_text():
    """Proves the scan can see free text where it exists. Without this, a
    split that returned two empty strings would pass every test above."""
    priv, _ = _split_on_privileged(_func("list_cases_ombudsman"))
    assert "_summarize(c.details)" in priv, (
        "the privileged branch no longer returns case text, so the test above "
        "is no longer distinguishing the two audiences")


def test_control_the_split_produced_two_real_branches():
    priv, non_priv = _split_on_privileged(_func("list_cases_ombudsman"))
    assert len(priv) > 200 and len(non_priv) > 200, (
        f"branch split looks wrong: {len(priv)} / {len(non_priv)} chars")


def test_control_the_unused_redaction_helper_is_still_unused():
    """If someone wires `_redact` into the non-privileged path, that is a
    deliberate decision to start sending case text to non-privileged callers,
    and it should come past this test rather than slip through as a fix.
    """
    calls = len(re.findall(r"(?<!def )\b_redact\(", SOURCE))
    assert calls == 0, (
        "_redact is now called. If the intent is to send non-privileged "
        "callers redacted case text, that REPLACES sending them none — "
        "weigh it deliberately and update these tests.")
