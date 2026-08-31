"""
A bonus pool holding money cannot be finalised with nothing allocated.

WHY THIS IS A TEST
Two defects, found by walking the pool workflow end to end against the running
API rather than by calling the endpoints in isolation.

    POST /api/bonuses/pools/{id}/calculate   422 CheckViolation
    POST /api/bonuses/pools/{id}/finalize    200 {"status": "locked"}

Calculate could never succeed: bonus_calc sets status='calculated' and
bonus_pools_status_ck allowed only ('draft','approved','paid'). The constraint
had been written earlier the same day from the column list rather than from the
code that writes it — a CHECK is a claim about what the application does, and
it has to be read off the application.

Finalize then locked a pool holding $50,000 with zero allocations, answered
"locked", and wrote an audit event saying it had been finalised. The money was
committed to nobody and the record said the opposite.

The second defect was only reachable BECAUSE of the first. Calculate always
failed, so every pool reaching finalize was empty, and finalize was perfectly
happy about it. Fixing the constraint alone would have left the real hole
behind a step that now works.

A pool deliberately finalised at zero is fine. A pool holding money and
allocating none of it is a mistake nobody makes on purpose, and the only cheap
moment to catch it is before the lock.
"""
from __future__ import annotations

import ast
import pathlib
import re

ROUTER = pathlib.Path("app/api/routers/bonuses.py")
CALC = pathlib.Path("app/services/bonus_calc.py")
MIGRATIONS = pathlib.Path("migrations")


def _statuses_the_code_writes() -> set[str]:
    """Every literal status assigned to bonus_pools anywhere in the package."""
    found: set[str] = set()
    for path in (ROUTER, CALC):
        for m in re.finditer(r"bonus_pools\s+set\s+status\s*=\s*'(\w+)'",
                             path.read_text(), re.IGNORECASE):
            found.add(m.group(1))
    return found


def _statuses_the_constraint_allows() -> set[str]:
    allowed: set[str] = set()
    for path in MIGRATIONS.glob("*.sql"):
        sql = path.read_text()
        for m in re.finditer(r"bonus_pools_status_ck[\s\S]{0,200}?CHECK\s*\(\s*status\s+IN\s*\(([^)]*)\)",
                             sql, re.IGNORECASE):
            allowed |= set(re.findall(r"'(\w+)'", m.group(1)))
    return allowed


def test_every_status_the_code_writes_is_allowed_by_the_constraint():
    writes = _statuses_the_code_writes()
    allowed = _statuses_the_constraint_allows()
    assert writes, "found no status writes at all; the scan is broken"
    assert allowed, "found no CHECK constraint at all; the scan is broken"
    rejected = sorted(writes - allowed)
    assert not rejected, (
        f"the code writes {rejected} and bonus_pools_status_ck allows "
        f"{sorted(allowed)}. Every write of those values raises CheckViolation."
    )


def test_calculated_is_specifically_allowed():
    """The value that made calculate impossible."""
    assert "calculated" in _statuses_the_constraint_allows()
    assert "calculated" in _statuses_the_code_writes()


def test_finalize_refuses_a_funded_pool_with_no_allocations():
    tree = ast.parse(ROUTER.read_text())
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and "finalize" in n.name
    )
    src = ast.unparse(fn)
    assert "bonus_allocations" in src, (
        "finalize does not look at the allocations before locking the pool, so a "
        "funded pool with none still commits its money to nobody"
    )
    assert "409" in src, "the refusal must be a conflict, not a silent success"
    assert "total_amount" in src, (
        "the guard must consider the pool's amount -- a pool deliberately "
        "finalised at zero is legitimate and must not be blocked"
    )


def test_a_zero_pool_is_not_blocked():
    """CONTROL. Over-refusing is its own defect: a pool finalised at zero is a
    real thing an operator may want."""
    src = ast.unparse(ast.parse(ROUTER.read_text()))
    guard = src[src.index("n_alloc") : src.index("n_alloc") + 400]
    assert ">" in guard and "total_amount" in guard, (
        "the guard does not appear to be conditional on the pool holding money"
    )
