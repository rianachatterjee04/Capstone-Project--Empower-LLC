"""The licence that permits outreach cannot be granted through the API.

check_marketing_allowed refuses unless the SOURCE carries a licence permitting
direct marketing. The refusal is only worth having if the licence itself is
out of reach of the thing being refused: an endpoint that let a caller create a
source with permits_direct_marketing=true, or move a prospect onto one, would
turn a hard rule into a two-step form.

That is the laundering path this guards. A carrier register is readable, and
being readable is not permission to run a campaign against the businesses in
it; the way that rule gets defeated in practice is not by arguing with it but
by re-attributing the prospects to a source that does carry a licence.

TODAY IT IS SAFE BY ABSENCE. No route creates or updates a commercial source,
and none reassigns a prospect's source_id -- the two write statements in the
router insert an action and set a prospect's stage. Safety by absence is real
safety and it is also invisible, so it disappears the first time somebody adds
a perfectly reasonable "add a source" endpoint. These tests make that addition
a deliberate decision rather than an unnoticed one.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

ROUTER = (pathlib.Path(__file__).parent.parent
          / "app" / "api" / "routers" / "commercial.py")
APP_DIR = pathlib.Path(__file__).parent.parent / "app"

SOURCE = ROUTER.read_text()

#: Column names that, if written, would grant or move the licence.
LICENCE_COLUMNS = ("permits_direct_marketing", "licence_note")
ATTRIBUTION_COLUMNS = ("source_id",)


def _sql_literals(path: pathlib.Path):
    """Every string constant in the file. SQL here is written as literals, so
    this reads what the module can actually execute rather than what it
    happens to import."""
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value


def _write_statements(path: pathlib.Path):
    for text in _sql_literals(path):
        upper = " ".join(text.upper().split())
        if re.search(r"\b(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", upper):
            yield " ".join(text.split())


# ── the licence cannot be granted ─────────────────────────────────────────

def test_no_route_writes_the_commercial_sources_table():
    offending = [s for s in _write_statements(ROUTER)
                 if "commercial_sources" in s.lower()]
    assert not offending, (
        "a route writes commercial_sources, which is where the outreach "
        "licence lives. If this is deliberate, the licence must not be "
        "settable by the caller who benefits from it:\n  "
        + "\n  ".join(offending))


def test_no_route_writes_a_licence_column():
    offending = [s for s in _write_statements(ROUTER)
                 if any(c in s.lower() for c in LICENCE_COLUMNS)]
    assert not offending, (
        "a route writes an outreach-licence column:\n  " + "\n  ".join(offending))


def test_no_route_reassigns_a_prospects_source():
    offending = [s for s in _write_statements(ROUTER)
                 if any(c in s.lower() for c in ATTRIBUTION_COLUMNS)]
    assert not offending, (
        "a route writes source_id. Moving a prospect from an unlicensed source "
        "to a licensed one defeats check_marketing_allowed without ever "
        "calling it:\n  " + "\n  ".join(offending))


def test_the_stage_change_touches_only_stage_and_who_decided():
    """The one UPDATE in the router, pinned by column. A future edit that adds
    a column to this statement has to come past this test."""
    updates = [s for s in _write_statements(ROUTER)
               if s.upper().lstrip().startswith("UPDATE")]
    assert len(updates) == 1, f"expected one UPDATE, found {len(updates)}"
    setclause = re.split(r"(?i)\bSET\b", updates[0], 1)[1]
    setclause = re.split(r"(?i)\bWHERE\b", setclause, 1)[0].lower()
    written = {m.group(1) for m in re.finditer(r"(\w+)\s*=", setclause)}
    assert written <= {"stage", "saved_by", "saved_at"}, (
        f"the stage endpoint now writes {sorted(written)}")


# ── and nowhere else in the app either ────────────────────────────────────

def test_nothing_in_the_app_grants_the_licence():
    """Not just this router. A licence granted from any request-handling code
    is the same hole wherever it lives."""
    offenders = {}
    for path in APP_DIR.rglob("*.py"):
        if path.name == "loop.py" and path.parent.name == "commercial":
            continue                      # defines the rule, writes nothing
        for stmt in _write_statements(path):
            low = stmt.lower()
            if "commercial_sources" in low or any(c in low for c in LICENCE_COLUMNS):
                offenders.setdefault(str(path.relative_to(APP_DIR)), []).append(stmt)
    assert not offenders, f"licence writes found outside the router: {offenders}"


# ── control: the guard can actually see a write ───────────────────────────

def test_control_the_scanner_detects_a_write_it_should_object_to():
    """These tests pass when they find nothing, which is also what happens if
    the scanner cannot read SQL. This proves it can."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
        fh.write(
            'q = """UPDATE public.commercial_sources '
            'SET permits_direct_marketing = true WHERE id = :i"""\n')
        planted = pathlib.Path(fh.name)
    try:
        found = list(_write_statements(planted))
        assert found, "the scanner did not see a plain UPDATE"
        assert "commercial_sources" in found[0].lower()
        assert "permits_direct_marketing" in found[0].lower()
    finally:
        planted.unlink()


def test_control_the_scanner_finds_the_writes_that_do_exist():
    """And that it is reading THIS router, not an empty file."""
    stmts = list(_write_statements(ROUTER))
    assert len(stmts) == 2, (
        f"expected the two known writes (insert an action, set a stage), "
        f"found {len(stmts)}: {stmts}")
    assert any("commercial_actions" in s.lower() for s in stmts)
    assert any("commercial_prospects" in s.lower() for s in stmts)
