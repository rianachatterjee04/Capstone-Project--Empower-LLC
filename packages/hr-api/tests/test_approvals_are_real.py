"""
Nothing in the approvals queue is invented.

WHY THIS IS A TEST
Two approvals were appended unconditionally, under a comment that admitted it:

    # 5. Synthetic comp letters (until a comp_letters table exists)
    "Comp letter · Sam Rivera"
    "Promotion · Avery Chen — Engineering Lead, Payments, 89% role-fit per
     marketplace."

They rendered beside genuine items — offers pulled from candidates at offer
stage, agent actions awaiting approval — with nothing marking them apart, in a
queue whose whole purpose is that a person acts on it. Their CTA opened a comp
review for someone who does not exist, and the 89% role-fit came from no
marketplace.

A queue with two fewer rows is worth more than one a user learns to distrust.
The unbuilt feature is reported as unavailable instead.
"""
from __future__ import annotations

import inspect
import re

from app.services import approvals_service as A


def test_no_approval_is_constructed_from_a_literal_name():
    """Approval(...) calls must take their title from data, not a string."""
    src = inspect.getsource(A)
    body = src.split('"""', 2)[-1]          # skip the module docstring
    # A title= that is a plain string literal rather than an f-string/variable.
    literal_titles = re.findall(r'title\s*=\s*"(?!\s*\{)([^"]{3,})"', body)
    assert literal_titles == [], (
        "approvals built from hard-coded titles — these appear in the queue "
        f"whether or not they exist: {literal_titles}")


def test_the_two_synthetic_approvals_are_gone():
    src = inspect.getsource(A)
    body = src.split('"""', 2)[-1]
    for gone in ("Sam Rivera", "Avery Chen", "89% role-fit"):
        # allowed in the explanatory comment, not in a constructed Approval
        in_code = [ln for ln in body.splitlines()
                   if gone in ln and not ln.strip().startswith("#")]
        assert in_code == [], f"{gone!r} is still in constructed code: {in_code}"


def test_the_missing_feature_is_declared():
    src = inspect.getsource(A)
    assert "comp_letters table" in src, (
        "the comp-letter gap is no longer explained anywhere in the service")
    assert '"unavailable"' in src, (
        "the response no longer reports what is not routed here yet")
