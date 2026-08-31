"""
A handler does not record an action its UPDATE never performed.

WHY THIS IS A TEST
Attacking one organisation's records with another organisation's token, the
isolation held -- the case was untouched, the approval stayed pending, nothing
changed. That part was already right: every UPDATE is org-scoped in its WHERE.

What was wrong is what happened next. The handlers did not look at whether the
UPDATE had matched anything. They carried straight on to

    db.add(AuditEvent(... event_type="case.closed" ...))

so a request that changed nothing still wrote an audit event saying the action
occurred, and answered the caller as though it had. Ten handlers did this,
across cases, employees, investigations, performance decisions, comp cycles and
login records.

Two things follow from it, and the second is the serious one.

A caller gets a success for a no-op -- an HR lead told an employee was
terminated when no row matched. And the audit log, whose entire purpose is to
be the record of what happened, gains entries for things that did not.

In this deployment the attacking org did not exist, so the audit insert failed
its foreign key and the write rolled back -- which is why nothing was recorded
and why the response was a confusing 422 about a referenced record. On a
deployment where both organisations are real, nothing would have stopped it.
"""
from __future__ import annotations

import ast
import pathlib
import re

ROUTERS = pathlib.Path("app/api/routers")

ORG_SCOPED_UPDATE = re.compile(r"\bupdate\s+(?:public\.)?\w+\s+set\b", re.IGNORECASE)
HAS_ORG = re.compile(r"org_id\s*=\s*:", re.IGNORECASE)


def _unguarded(tree: ast.AST, label: str) -> list[str]:
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = ast.unparse(node)
        sqls = [
            n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        updates = [q for q in sqls if ORG_SCOPED_UPDATE.search(q) and HAS_ORG.search(q)]
        if not updates or "AuditEvent(" not in body:
            continue
        # Any of these is a real check that the row belonged to this org:
        #   rowcount on the UPDATE, RETURNING plus a first()/scalar, or an
        #   explicit 404 raised after looking the row up first.
        guarded = (
            "rowcount" in body
            or (any(re.search(r"returning", q, re.I) for q in updates)
                and re.search(r"\.first\(\)|scalar", body))
            or re.search(r"HTTPException\((?:status_code=)?404", body)
        )
        if not guarded:
            out.append(f"{label}:{node.lineno} {node.name}")
    return out


def test_no_handler_audits_an_update_it_did_not_make():
    found: list[str] = []
    for path in sorted(ROUTERS.glob("*.py")):
        try:
            found += _unguarded(ast.parse(path.read_text()), str(path))
        except SyntaxError:
            continue
    assert found == [], (
        "these update an org-scoped row and then write an AuditEvent without "
        "checking the update matched anything. A request that changed nothing "
        "gets a success response and puts an entry in the audit log saying it "
        "happened:\n  " + "\n  ".join(found)
    )


def test_the_detector_finds_the_original_shape():
    """MUTATION CONTROL. cases.assign as it was."""
    original = '''
async def assign(case_id, investigator_id, actor=None, db=None):
    await db.execute(text("""
        update public.cases
        set investigator_employee_id=:inv, status='assigned'
        where org_id=:org and id=:cid
    """), {"org": actor.org_id, "cid": case_id, "inv": investigator_id})
    db.add(AuditEvent(org_id=actor.org_id, event_type="case.assigned"))
'''
    found = _unguarded(ast.parse(original), "CONTROL")
    assert len(found) == 1, found
    assert "assign" in found[0]


def test_the_detector_accepts_a_rowcount_check():
    fine = '''
async def assign(case_id, investigator_id, actor=None, db=None):
    _updated = await db.execute(text("""
        update public.cases set status='assigned' where org_id=:org and id=:cid
    """), {"org": actor.org_id, "cid": case_id})
    if _updated.rowcount == 0:
        raise HTTPException(status_code=404, detail="no such case in this organisation")
    db.add(AuditEvent(org_id=actor.org_id, event_type="case.assigned"))
'''
    assert _unguarded(ast.parse(fine), "FINE") == []


def test_the_detector_accepts_a_returning_check():
    """CONTROL. legal.freeze already did it this way and was correct; flagging
    it would have sent someone to 'fix' working code."""
    fine = '''
async def freeze(case_id, actor=None, db=None):
    res = await db.execute(text("""
        update public.cases set legal_freeze = true
        where id = :id and org_id = :org_id returning id
    """), {"id": case_id, "org_id": actor.org_id})
    if not res.first():
        raise HTTPException(status_code=404, detail="Case not found")
    db.add(AuditEvent(org_id=actor.org_id, event_type="case.frozen"))
'''
    assert _unguarded(ast.parse(fine), "FINE") == []
