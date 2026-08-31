"""
Every surface that needs a salary says so when there is none.

WHY THIS IS A TEST
comp_records holds zero rows in the demo deployment, and employees carries no
salary column -- compensation lives in comp_records by design. Five separate
surfaces depend on a salary, and walking them found that all five refuse
correctly:

    payroll sync                     syncs the person, basis_amount_cents 0
    /api/market/compare/{id}         available:false, names the missing half
    /api/intel/recon/run             available:false, nothing to reconcile
    /api/intelligence/comp/...       "none with salary data populated"
    /app/equity total comp           "$0 -- equity only, no cash on file"

That is the right behaviour and it is worth pinning, because the tempting fix
for a thin demo is to put a number in. A salary invented for a named person
would appear behind five screens that talk about their pay, and each of those
screens would then be making a claim about them that nobody made.

This test asserts the refusals stay refusals: that each surface still declares
the absence rather than defaulting, and that no default salary constant has
crept into the paths that read compensation.
"""
from __future__ import annotations

import ast
import pathlib
import re

APP = pathlib.Path("app")

MONEY_DEFAULT = re.compile(
    r"(salary|comp|pay|basis_amount)\w*[\"\']?\s*\)?\s*(?:or|,)\s*(\d{4,})",
    re.IGNORECASE,
)

# Files that decide what to do when compensation is missing.
COMP_READERS = [
    "app/api/routers/market.py",
    "app/api/routers/intelligence/reconciliation.py",
    "app/api/routers/intelligence/core.py",
]


def test_the_surfaces_declare_unavailable_rather_than_defaulting():
    for rel in COMP_READERS:
        src = pathlib.Path(rel).read_text()
        assert '"available": False' in src or "'available': False" in src, (
            f"{rel} does not declare unavailability anywhere; a comp surface with "
            f"no comp must say so rather than render a number"
        )


def test_no_comp_reader_substitutes_a_default_salary():
    """The specific failure this guards: `salary or 120000`, or a dict .get with
    a money default. workforce_graph_service once defaulted a missing salary to
    120_000 and drew a trust score from it."""
    offenders = []
    # Allows the closing quote/paren of a .get(): the real shape is
    # `e.get("salary") or 120000` or `.get("salary", 120000)`, not the bare
    # `salary or 120000` the first version of this regex looked for. Its own
    # control caught that.
    money = MONEY_DEFAULT
    for rel in COMP_READERS:
        path = pathlib.Path(rel)
        src = path.read_text()
        tree = ast.parse(src)
        # strip docstrings so an explanatory number in prose is not a finding
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                d = ast.get_docstring(node)
                if d:
                    src = src.replace(d, "")
        for m in money.finditer(src):
            line = src[:m.start()].count("\n") + 1
            offenders.append(f"{rel}:{line} {m.group(0)}")
    assert offenders == [], (
        "these substitute a number when compensation is missing. An invented "
        "salary behind a screen about someone's pay is a claim about that "
        "person:\n  " + "\n  ".join(offenders)
    )


def test_the_market_comparison_names_which_half_is_missing():
    src = pathlib.Path("app/api/routers/market.py").read_text()
    assert "comp_records" in src, (
        "the refusal does not say WHERE compensation lives, so the reader "
        "cannot tell a deployment gap from an unimplemented feature"
    )


def test_the_reconciliation_says_an_empty_result_is_not_a_clean_one():
    src = pathlib.Path("app/api/routers/intelligence/reconciliation.py").read_text()
    assert "does NOT mean your records reconcile" in src


def test_the_detector_would_catch_a_planted_default(tmp_path):
    """MUTATION CONTROL."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "def f(e):\n"
        "    a = e.get('salary') or 120000\n"
        "    b = e.get('salary', 95000)\n"
        "    return a, b\n"
    )
    # Allows the closing quote/paren of a .get(): the real shape is
    # `e.get("salary") or 120000` or `.get("salary", 120000)`, not the bare
    # `salary or 120000` the first version of this regex looked for. Its own
    # control caught that.
    money = MONEY_DEFAULT
    assert MONEY_DEFAULT.search(planted.read_text()), "the scan cannot see an obvious default salary"
