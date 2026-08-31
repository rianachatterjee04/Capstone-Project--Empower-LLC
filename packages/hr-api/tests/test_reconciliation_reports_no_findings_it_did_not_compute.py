"""
An empty findings list is not a clean reconciliation.

WHY THIS IS A TEST
POST /api/intel/recon/run answered 500 UndefinedColumn: it selected full_name,
salary and equity_shares from employees, and this schema has none of them.

Correcting the column names would have made it worse, because the other half of
the comparison was a fixture:

    external_df = pd.DataFrame([{"name": "Founders", "salary": 120000}])

A working version would have compared this organisation's real people against
one invented row and returned the differences as payroll mismatches -- findings
about money, with no external system involved. A finance buyer asked to
reconcile payroll is precisely the person who would act on that.

So the endpoint reports both blockers, marks its external side DEMO_SIMULATED,
and states in the payload that an empty findings list does not mean the records
reconcile. "Nothing found" and "nothing looked" must not render identically.
"""
from __future__ import annotations

import ast
import pathlib

SOURCE = pathlib.Path("app/api/routers/intelligence/reconciliation.py")


def _without_docstring(fn):
    """The docstring QUOTES the fabrication it describes, so a scan that reads
    it flags the explanation as if it were the code. Strip it and read what
    actually executes."""
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    stripped = ast.Module(body=body, type_ignores=[])
    return stripped


def test_the_handler_no_longer_builds_an_external_fixture():
    """The specific fabrication: a hardcoded 'external system' to diff against."""
    tree = ast.parse(SOURCE.read_text())
    handler = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run_reconciliation"
    )
    body = ast.dump(_without_docstring(handler))
    assert "external_df" not in body, (
        "the handler still constructs an external dataframe. If that is a "
        "fixture, its differences from real employee records are not findings."
    )
    assert "120000" not in ast.unparse(_without_docstring(handler)), (
        "the sample salary is still in the comparison path"
    )


def test_the_response_marks_its_external_source_as_simulated():
    src = SOURCE.read_text()
    assert "DEMO_SIMULATED" in src, (
        "the payload must say the external side is simulated; a reconciliation "
        "result with an unlabelled source reads as live"
    )


def test_the_response_says_empty_is_not_reconciled():
    src = SOURCE.read_text()
    assert "does NOT mean your records reconcile" in src, (
        "an empty findings list must carry its own disclaimer -- this is the "
        "exact shape where silence is read as an all-clear"
    )


def test_it_reports_unavailable_rather_than_findings():
    src = SOURCE.read_text()
    assert '"available": False' in src or "'available': False" in src, (
        "the endpoint must declare itself unavailable, not return an empty "
        "success"
    )


def test_the_guard_would_notice_the_fixture_coming_back(tmp_path):
    """MUTATION CONTROL. Plant the original fabrication and require the scan to
    see it."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import pandas as pd\n"
        "async def run_reconciliation(system):\n"
        "    external_df = pd.DataFrame([{'name': 'Founders', 'salary': 120000}])\n"
        "    return external_df\n"
    )
    tree = ast.parse(planted.read_text())
    handler = next(n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    assert "external_df" in ast.dump(_without_docstring(handler))
    assert "120000" in ast.unparse(_without_docstring(handler))
