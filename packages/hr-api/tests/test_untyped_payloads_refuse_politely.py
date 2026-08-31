"""
An endpoint declared `payload: dict` still has to say what it needs.

WHY THIS IS A TEST
Nine equity write endpoints -- the cap-table surface integrators build
against -- are declared as `payload: dict`. FastAPI cannot validate an untyped
dict, so nothing rejected an incomplete body, and the handler's own
`payload["stakeholder_id"]` raised KeyError. The caller saw:

    500  {"message": "Internal Server Error", "detail": "'stakeholder_id'"}

A quoted field name as the entire explanation of a server error. The sweep that
found these hit every parameterless write endpoint with an empty object; nine
of them crashed rather than refusing.

`required_field` does not tighten what these endpoints accept. It replaces a
crash with the refusal that should always have been there, and names the field.
"""
from __future__ import annotations

import ast
import pathlib

import pytest
from fastapi import HTTPException

from app.api.deps import required_field

ROUTERS = pathlib.Path("app/api/routers")


def test_a_missing_field_is_refused_not_crashed():
    with pytest.raises(HTTPException) as e:
        required_field({}, "stakeholder_id")
    assert e.value.status_code == 422
    assert "stakeholder_id" in str(e.value.detail)


def test_an_explicit_null_is_also_missing():
    """A JSON null for a field the handler must have is not a value."""
    with pytest.raises(HTTPException) as e:
        required_field({"name": None}, "name")
    assert e.value.status_code == 422


def test_a_present_value_is_returned_untouched():
    assert required_field({"shares": 0}, "shares") == 0        # falsy but present
    assert required_field({"ok": False}, "ok") is False
    assert required_field({"name": "Acme"}, "name") == "Acme"


def test_a_non_object_body_is_refused():
    with pytest.raises(HTTPException) as e:
        required_field(["not", "an", "object"], "name")  # type: ignore[arg-type]
    assert e.value.status_code == 422


def test_the_message_says_what_is_needed():
    with pytest.raises(HTTPException) as e:
        required_field({}, "exit_value", what="the exit valuation in dollars")
    detail = str(e.value.detail)
    assert "exit_value" in detail and "exit valuation" in detail


def _raw_subscripts(path: pathlib.Path) -> list[str]:
    """Every `payload["x"]` / `body["x"]` READ still in a router.

    Assignments are excluded: `payload["x"] = v` builds a dict, it does not read
    a caller's field. Reads guarded by a conditional are excluded too -- those
    were never crashes, and rewriting them would have been noise.
    """
    tree = ast.parse(path.read_text())
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.IfExp):
            for sub in ast.walk(node.test):
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get":
                    for inner in ast.walk(node.body):
                        guarded.add(id(inner))
    assigned: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for sub in ast.walk(t):
                    assigned.add(id(sub))
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Subscript) or id(node) in assigned or id(node) in guarded:
            continue
        if not (isinstance(node.value, ast.Name) and node.value.id in ("payload", "body")):
            continue
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            out.append(f"{path.name}:{node.lineno} {node.value.id}[{node.slice.value!r}]")
    return out


def test_no_router_reads_a_required_field_without_refusing_first():
    """The general form. Any NEW `payload["x"]` read in a router is a 500
    waiting for the first caller who omits x, so fail here instead."""
    offenders = [s for f in sorted(ROUTERS.glob("*.py")) for s in _raw_subscripts(f)]
    assert offenders == [], (
        "these read a caller-supplied field without checking it is present, so an "
        "incomplete request returns 500 with the field name as the entire "
        "explanation. Use required_field(payload, 'x'):\n  " + "\n  ".join(offenders)
    )


def test_the_detector_finds_a_planted_raw_read(tmp_path):
    """MUTATION CONTROL. If the scan above cannot see a raw read, its clean
    result means nothing."""
    planted = tmp_path / "planted_router.py"
    planted.write_text(
        "async def create(payload: dict):\n"
        "    return {'id': payload['stakeholder_id']}\n"
    )
    found = _raw_subscripts(planted)
    assert found, "the scan did not flag an obvious raw payload read"
    assert "stakeholder_id" in found[0]


def test_the_detector_ignores_assignments_and_guarded_reads(tmp_path):
    """CONTROL, the other direction. A scan that flags dict-building or an
    already-guarded read produces busywork and gets switched off."""
    planted = tmp_path / "ok_router.py"
    planted.write_text(
        "from uuid import UUID\n"
        "async def create(payload: dict):\n"
        "    body = {}\n"
        "    body['built'] = 1\n"
        "    eid = UUID(payload['entity_id']) if payload.get('entity_id') else None\n"
        "    return body, eid\n"
    )
    assert _raw_subscripts(planted) == [], _raw_subscripts(planted)
