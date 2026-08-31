"""
A comp cycle cannot propose a raise for nobody, and cannot claim it paid one.

WHY THIS IS A TEST
Walking the merit-cycle workflow end to end against the running API:

    POST /api/compcycle/{id}/propose  {}   ->  200 {"ok": true}
    POST /api/compcycle/{id}/finalize      ->  200 {"status": "closed",
                                                    "payroll_export": {"exported_records": 1}}

Every field of propose was read with .get(), so an empty body stored a comp
proposal with a null employee_id, a null salary and a null bonus -- a pay
decision about nobody, for no amount. Nothing crashed: unlike a raw
payload["x"], a .get() on a missing key is silent. For an optional field that
is right. For the person a raise belongs to it is not.

finalize then selected EVERY proposal in the cycle, whatever its state, and
handed the lot to payroll -- including ones still at 'proposed' with no
approved amount. Closing a merit cycle would have pushed pay changes nobody had
approved.

And the export itself was:

    def export_payroll(data):
        return {"exported_records": len(data)}

It counted its argument. Nothing was sent anywhere. To a finance lead closing a
cycle, "exported_records: 1" reads as confirmation that an approved raise
reached payroll. A count of what WOULD be sent is useful; calling it "exported"
is a claim about money having moved.
"""
from __future__ import annotations

import ast
import inspect
import pathlib

from app.services.payroll_export import export_payroll

ROUTER = pathlib.Path("app/api/routers/comp_cycle.py")


def _fn_source(name: str) -> str:
    """ast.unparse normalises string quoting, so these assertions compare
    against single-quoted source regardless of how the file is written."""
    tree = ast.parse(ROUTER.read_text())
    fn = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )
    return ast.unparse(fn).replace('"', "'")


def test_a_proposal_must_name_an_employee():
    src = _fn_source("propose")
    assert "required_field(payload, 'employee_id'" in src, (
        "employee_id is still optional, so a pay decision can be stored about "
        "nobody"
    )


def test_a_proposal_must_change_something():
    src = _fn_source("propose")
    assert "salary is None and bonus is None" in src, (
        "a proposal with neither a salary nor a bonus is accepted; it changes "
        "nothing and cannot be acted on"
    )
    assert "422" in src


def test_finalize_only_hands_over_approved_decisions():
    src = _fn_source("finalize_cycle")
    assert "r['approved_salary'] is not None or" in src, (
        "finalize still exports every proposal in the cycle regardless of "
        "state, including ones nobody approved"
    )


def test_finalize_says_what_it_left_out():
    """A decision silently dropped from a comp cycle is somebody's raise going
    missing. Excluding it is right; excluding it quietly is not."""
    src = _fn_source("finalize_cycle")
    assert "not_approved" in src and "not_approved_note" in src


def test_the_export_does_not_claim_to_have_exported():
    result = export_payroll([{"employee_id": "x", "approved_salary": 1}])
    assert result["exported"] is False
    assert result["records_ready"] == 1
    assert "reason" in result and "not been sent" in result["reason"]
    assert "exported_records" not in result, (
        "the old key is back. 'exported_records' reads as money having moved, "
        "and nothing is sent anywhere."
    )


def test_the_export_is_still_a_stub_and_says_so():
    """MUTATION CONTROL. If a real connector is implemented, this test should
    fail so nobody leaves the disclaimer on a working export."""
    src = inspect.getsource(export_payroll)
    assert "no payroll export connector is configured" in src, (
        "export_payroll no longer declares itself unconnected -- if it now "
        "really exports, remove available:false and update these tests"
    )


def test_an_empty_handover_is_still_reported_honestly():
    result = export_payroll([])
    assert result["records_ready"] == 0
    assert result["exported"] is False
