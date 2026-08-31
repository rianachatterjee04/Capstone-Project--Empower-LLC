"""
No UPDATE writes a column straight from a bare .get().

WHY THIS IS A TEST
POST /api/performance/reviews/{id}/calibrate answered {"ok": true} and stored
nothing. The handler did

    set calibrated_rating=:rating ...   {"rating": payload.get("rating")}

so a body using any other field name wrote NULL over the calibrated rating and
advanced the review to 'decision' regardless. A calibration committee sending
the wrong key silently erased the rating and moved the review on to a promotion
decision with nothing behind it.

Nothing crashed. That is what makes this shape dangerous and why it survived a
sweep that looked for 5xx: unlike a raw payload["x"], a .get() on a missing key
is silent, and the UPDATE happily writes the None.

A scan for the shape found five more, all on records about people or money:

    comp_proposals.approved_bonus     adjusting only a salary erased an
                                      already-approved bonus
    performance_reviews.outcome       a promotion/PIP decision finalised with
                                      no decision in it
    cases.closure_reason              a case closed with no reason recorded
    investigation_cases.outcome       findings recorded with no finding
    investigation_cases.closure_notes closing erased existing notes

Two remedies, chosen per field. Where the value IS the point of the call --
a calibration's rating, a decision's outcome -- it is required. Where it is
genuinely optional -- closure notes -- the column is COALESCEd so omitting it
preserves what is there instead of erasing it.
"""
from __future__ import annotations

import ast
import pathlib
import re

APP = pathlib.Path("app")

UPDATE = re.compile(r"update\s+(?:public\.)?(\w+)\s+set\s+(.*?)\s+where",
                    re.IGNORECASE | re.DOTALL)
BARE_GET = re.compile(r"'(\w+)':\s*(?:payload|body)\.get\('(\w+)'\)(?!\s*,)")


def _offenders(tree: ast.AST, label: str) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        sqls = [
            n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and "update" in n.value.lower()
        ]
        if not sqls:
            continue
        body = ast.unparse(node)
        bare = {m.group(1) for m in BARE_GET.finditer(body)}
        if not bare:
            continue
        for sql in sqls:
            for m in UPDATE.finditer(sql):
                assigns = m.group(2)
                for col, param in re.findall(r"(\w+)\s*=\s*:(\w+)", assigns):
                    if param not in bare:
                        continue
                    # coalesce(:x, col) preserves the existing value: that is
                    # the deliberate optional-field form, not the defect.
                    if re.search(rf"coalesce\s*\(\s*:{param}\b", assigns, re.IGNORECASE):
                        continue
                    hits.append(f"{label}:{node.lineno} {node.name}  {m.group(1)}.{col} <- .get('{param}')")
    return hits


def test_no_update_nulls_a_column_when_a_key_is_omitted():
    found: list[str] = []
    for path in sorted(APP.rglob("*.py")):
        try:
            found += _offenders(ast.parse(path.read_text()), str(path))
        except SyntaxError:
            continue
    assert sorted(set(found)) == [], (
        "these write a column directly from payload.get(), so a request that "
        "omits the key silently overwrites the stored value with NULL and still "
        "reports success. Require the field, or COALESCE the column:\n  "
        + "\n  ".join(sorted(set(found)))
    )


def test_the_detector_finds_the_original_calibrate_defect():
    """MUTATION CONTROL. The exact handler that returned ok and stored nothing.

    An earlier version of this scan matched against ast.unparse() output, where
    the SQL is escaped inside a quoted string -- it matched no UPDATE anywhere
    in the package and reported a clean zero. This control is why that was
    caught.
    """
    original = '''
async def calibrate(review_id, payload, actor=None, db=None):
    await db.execute(text("""
        update public.performance_reviews
        set calibrated_rating=:rating, status='decision'
        where id=:id and org_id=:org_id
    """), {"id": review_id, "org_id": actor.org_id, "rating": payload.get("rating")})
'''
    found = _offenders(ast.parse(original), "CONTROL")
    assert len(found) == 1, found
    assert "calibrated_rating" in found[0]


def test_the_detector_accepts_a_coalesced_optional_field():
    """CONTROL, the other direction. Preserving an omitted value is the correct
    form for an optional column and must not be flagged."""
    fine = '''
async def close(case_id, payload, actor=None, db=None):
    await db.execute(text("""
        update public.investigation_cases
        set status='closed', closure_notes = coalesce(:notes, closure_notes)
        where id=:case and org_id=:org_id
    """), {"case": case_id, "org_id": actor.org_id, "notes": payload.get("notes")})
'''
    assert _offenders(ast.parse(fine), "FINE") == []


def test_the_detector_accepts_a_required_field():
    """The other correct form."""
    fine = '''
async def decide(review_id, payload, actor=None, db=None):
    await db.execute(text("""
        update public.performance_reviews
        set outcome=:outcome, status='finalized'
        where id=:id and org_id=:org_id
    """), {"id": review_id, "org_id": actor.org_id,
           "outcome": required_field(payload, "outcome")})
'''
    assert _offenders(ast.parse(fine), "FINE") == []
