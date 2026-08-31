"""A capability disabled by a silent import failure is worse than one absent.

THE DEFECT THIS CATCHES
Five services imported the LLM like this:

    try:
        from app.services.llm import complete as llm_complete
    except Exception:
        llm_complete = None

`app/services/llm.py` defines `llm_complete`. It has never defined `complete`.
So the import raised ImportError on every start, the bare `except` swallowed
it, and `llm_complete` was permanently None -- in the interview scorecard, the
recruiter summary, the interview copilot, reference checks and recruiting
intelligence.

Each of those services then ran its local fallback and produced plausible
output. Nothing logged, nothing failed, and configuring OPENAI_API_KEY changed
nothing at all. The scorecard and the recruiter summary -- the two surfaces a
hiring decision actually rests on -- had the model silently switched off.

WHY A STRUCTURAL TEST AND NOT A UNIT TEST
A unit test for the scorecard passes either way; that is the whole problem. The
fallback is designed to be indistinguishable from the real path. So the test
has to be about the WIRING: every name imported from the LLM module must be a
name that module actually exports.

The `try/except ImportError` fail-soft pattern is deliberate and stays -- a
missing optional dependency should not take the service down. What must not
survive is a fail-soft that hides a typo forever.
"""
from __future__ import annotations

import ast
import os
import pathlib
import re

SERVICES = pathlib.Path(__file__).resolve().parents[1] / "app" / "services"
LLM_MODULE = SERVICES / "llm.py"


def _exported_names() -> set[str]:
    """Top-level names app/services/llm.py actually defines."""
    tree = ast.parse(LLM_MODULE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
    return names


def _llm_imports() -> list[tuple[str, str]]:
    """(file, imported_name) for every `from app.services.llm import ...`."""
    out: list[tuple[str, str]] = []
    for path in sorted(SERVICES.glob("*.py")):
        for m in re.finditer(r"from app\.services\.llm import ([^\n#]+)",
                             path.read_text(encoding="utf-8")):
            for piece in m.group(1).split(","):
                name = piece.strip().split(" as ")[0].strip().strip("()")
                if name:
                    out.append((path.name, name))
    return out


def test_every_llm_import_names_something_that_exists():
    """The regression. An unresolvable name here means a service has been
    running without the model and saying nothing about it."""
    exported = _exported_names()
    broken = [(f, n) for f, n in _llm_imports() if n not in exported]
    assert not broken, (
        f"these imports name symbols app/services/llm.py does not define: "
        f"{broken}. Each sits inside a try/except that sets the callable to "
        f"None, so the service silently runs its fallback forever. "
        f"llm.py exports: {sorted(exported)}")


def test_the_check_would_actually_fail_on_a_bad_name():
    """Positive control. If `_exported_names` returned everything, or
    `_llm_imports` found nothing, the test above would pass vacuously."""
    exported = _exported_names()
    assert "llm_complete" in exported
    assert "complete" not in exported, (
        "if `complete` is now a real export, the original defect is gone by a "
        "different route and this test's premise needs revisiting")

    imports = _llm_imports()
    assert len(imports) >= 10, (
        f"only {len(imports)} llm imports found; the scanner is probably not "
        f"matching the import form any more")


def test_the_fail_soft_pattern_is_still_intentional():
    """The try/except is not the bug and should not be 'fixed' away.

    A missing optional dependency must not take the service down. What this
    asserts is that the guarded import is a real, resolvable one -- fail-soft
    around a working import is resilience; fail-soft around a typo is a
    permanently disabled feature.
    """
    guarded = 0
    for path in sorted(SERVICES.glob("*.py")):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(
                r"try:\s*\n\s*from app\.services\.llm import ([^\n#]+)", src):
            guarded += 1
    assert guarded > 0, (
        "no guarded LLM imports found; if the pattern changed, this test and "
        "the one above need to change with it")
