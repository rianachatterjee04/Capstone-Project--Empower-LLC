"""
No SQL statement contains a bind parameter the driver will never fill.

WHY THIS IS A TEST
POST /api/ai/decision answered 500 with

    asyncpg.exceptions.PostgresSyntaxError: syntax error at or near ":"

The statement was written the way you would write it in psql:

    values (..., :input::jsonb, :output::jsonb, :model)

SQLAlchemy's text() will not read that as "bind input, then cast". Its bind
regex stops before the "::", so it registers a parameter named "inpu" -- the
name with its last character eaten -- and leaves ":input::jsonb" in the SQL
untouched. The caller passes "input", nothing fills "inpu", and Postgres is
handed a literal colon.

    text('values (:input::jsonb)')._bindparams  ->  ['inpu']

Every occurrence in the codebase was broken the same way, silently, with the
last character of the name eaten each time: cursor->curso, data->dat,
meta->met, payload->payloa, metadata->metadat, output->outpu. It reached the
audit ledger, the human decision ledger, the AI system of record, performance
review submission, investigation cases, and ATS sync -- the write paths whose
whole job is to leave a record. One of them already carried a comment
describing this exact failure, worked around in that one file and nowhere else.

CAST(:input AS jsonb) compiles correctly. This test asserts the property for
every statement in the package, so the next one written the psql way fails here
instead of in front of a customer.
"""
from __future__ import annotations

import ast
import pathlib
import re

from sqlalchemy import text

APP = pathlib.Path("app")

# A bind name immediately followed by "::". The negative lookbehind keeps
# ordinary Postgres casts (conrelid::regclass::text) out of it -- those have no
# bind parameter in front and are perfectly fine.
MISPARSED = re.compile(r"(?<!:):(\w+)::(\w+)")


def _sql_literals():
    """Every string handed to text(), with its file and line."""
    for path in sorted(APP.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "text"):
                continue
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                yield path, node.lineno, node.args[0].value


def test_no_statement_uses_the_psql_cast_shorthand():
    offenders = [
        f"{path}:{lineno} :{m.group(1)}::{m.group(2)}  ->  use cast(:{m.group(1)} as {m.group(2)})"
        for path, lineno, sql in _sql_literals()
        for m in MISPARSED.finditer(sql)
    ]
    assert offenders == [], (
        "these bind parameters are followed by '::', so SQLAlchemy registers the "
        "name with its last character removed and leaves a literal colon in the "
        "SQL. The statement raises PostgresSyntaxError the first time it runs:\n  "
        + "\n  ".join(offenders)
    )


def test_every_bind_name_survives_parsing():
    """The general property, independent of the ':: ' shape above: a parameter
    SQLAlchemy registers must be a name that actually appears in the SQL. A
    registered 'inpu' that the caller never passes is a statement that cannot
    execute."""
    broken = []
    for path, lineno, sql in _sql_literals():
        for name in text(sql)._bindparams:
            if not re.search(r":" + re.escape(name) + r"\b", sql):
                broken.append(f"{path}:{lineno} registered {name!r}, which is not in the SQL")
    assert broken == [], "\n  ".join(["mangled bind parameters:"] + broken)


def test_the_detector_fires_on_the_original_statement():
    """MUTATION CONTROL. The exact statement that produced the 500, verbatim.
    If the scan does not flag it, a clean run above means nothing."""
    original = """
        insert into public.ai_decisions(org_id, input, output, model)
        values (:org_id, :input::jsonb, :output::jsonb, :model)
        returning id
    """
    found = [m.group(0) for m in MISPARSED.finditer(original)]
    assert found == [":input::jsonb", ":output::jsonb"], found
    # and the reason it matters
    assert "inpu" in text(original)._bindparams, (
        "SQLAlchemy no longer truncates the name, so this whole class of defect "
        "may have been fixed upstream -- re-check before relaxing the guard"
    )


def test_the_detector_leaves_ordinary_casts_alone():
    """CONTROL, the other direction. A guard that flags every '::' in the
    codebase would be unusable -- ordinary casts are correct and common."""
    fine = "SELECT c.conrelid::regclass::text, now()::date, x::jsonb FROM t"
    assert list(MISPARSED.finditer(fine)) == [], "flagged a cast that has no bind parameter"


def test_the_corrected_form_binds_correctly():
    """And the replacement really is right."""
    fixed = text("values (:org_id, cast(:input as jsonb), cast(:output as jsonb), :model)")
    assert sorted(fixed._bindparams) == ["input", "model", "org_id", "output"]
