"""
Anything that reports itself unavailable also says why.

WHY THIS IS A TEST
"Unavailable is not empty" is the rule this codebase keeps rediscovering. A
zero, an empty list or a null means "we looked and there was nothing"; an
absent capability means "we did not look". Rendered, they are identical, and
the difference is the whole claim.

Several endpoints were changed to report `available: false` rather than crash
or, worse, answer with a default:

  * /api/intelligence/workforce/forecast -- returned a hardcoded 120
  * /api/intel/recon/run -- would have diffed real people against a fixture
  * /api/market/compare/{employee_id} -- has no salary to compare
  * /api/equity/me/total-comp (handoff package) -- no comp_records here

A false `available` with no `reason` is barely better than the empty state it
replaced: the reader learns something is missing but not what, so they cannot
tell whether it is a deployment gap they can fix, a permission, or a genuine
absence of data. The reason is the part that does the work.
"""
from __future__ import annotations

import ast
import pathlib

APP = pathlib.Path("app")


def _unavailable_dicts(tree: ast.AST):
    """Every dict literal that sets available/ok to False."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {
            k.value: v for k, v in zip(node.keys, node.values)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }
        flag = keys.get("available")
        if isinstance(flag, ast.Constant) and flag.value is False:
            yield node, set(keys)


def test_every_unavailable_response_carries_a_reason():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node, keys in _unavailable_dicts(tree):
            if not keys & {"reason", "detail", "message", "note"}:
                offenders.append(f"{path}:{node.lineno}  keys={sorted(keys)}")
    assert offenders == [], (
        "these report available: false without saying why. The reader learns "
        "something is missing but not what, so they cannot tell a deployment "
        "gap from a permission from a genuine absence of data:\n  "
        + "\n  ".join(offenders)
    )


def test_the_detector_finds_a_reasonless_refusal(tmp_path):
    """MUTATION CONTROL."""
    planted = tmp_path / "planted.py"
    planted.write_text('def h():\n    return {"available": False, "value": 0}\n')
    found = list(_unavailable_dicts(ast.parse(planted.read_text())))
    assert found, "the scan did not see an available: false dict"
    node, keys = found[0]
    assert not keys & {"reason", "detail", "message", "note"}


def test_the_detector_accepts_a_refusal_that_explains_itself(tmp_path):
    """CONTROL, the other direction."""
    planted = tmp_path / "ok.py"
    planted.write_text(
        'def h():\n    return {"available": False, "reason": "no comp_records here"}\n'
    )
    node, keys = next(_unavailable_dicts(ast.parse(planted.read_text())))
    assert keys & {"reason"}


def test_the_detector_ignores_available_true(tmp_path):
    planted = tmp_path / "fine.py"
    planted.write_text('def h():\n    return {"available": True, "value": 3}\n')
    assert list(_unavailable_dicts(ast.parse(planted.read_text()))) == []
