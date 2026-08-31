"""Fail on a broken test harness BEFORE reporting application failures.

WHY THIS EXISTS
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` removes pytest-asyncio along with the
plugin it was meant to suppress. Every async test then reports

    Failed: async def functions are not natively supported

which looks exactly like nineteen broken features and is actually one broken
command. That misdiagnosis is expensive in both directions: it manufactures
failures that waste a debugging session, and -- far worse -- it would let a
real async regression hide inside a wall of identical noise.

THE PRINCIPLE
    TEST INFRASTRUCTURE FAILURE != APPLICATION TEST FAILURE

A test runner is part of the evidence chain. Evidence produced by an
instrument that cannot execute a whole class of tests is not weak evidence; it
is evidence about the instrument. So this refuses to run at all rather than
producing results that would be read as product findings.

USAGE
    conftest.py:  pytest_plugins = ["tools.pytest_harness_guard"]
or  pytest.ini:   addopts = -p tools.pytest_harness_guard
"""
from __future__ import annotations

import sys

import pytest


def _async_tests_present(session) -> bool:
    return any("async def test" in _read(item)
               for item in _candidate_files(session))


def _candidate_files(session):
    seen = set()
    for item in getattr(session, "items", []):
        path = getattr(item, "path", None) or getattr(item, "fspath", None)
        if path and str(path) not in seen:
            seen.add(str(path))
            yield str(path)


def _read(path: str) -> str:
    try:
        with open(path, "r", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def pytest_collection_modifyitems(session, config, items):
    """Refuse to report results the runner cannot legitimately produce."""
    if not items:
        return

    needs_async = _async_tests_present(session)
    if not needs_async:
        return

    has_asyncio = config.pluginmanager.hasplugin("asyncio")
    if has_asyncio:
        return

    sys.stderr.write(
        "\n"
        "════════════════════════════════════════════════════════════════\n"
        "  TEST INFRASTRUCTURE FAILURE — not an application failure\n"
        "════════════════════════════════════════════════════════════════\n"
        "  This selection contains async tests and pytest-asyncio is NOT\n"
        "  loaded. Every async test would report\n"
        "      'async def functions are not natively supported'\n"
        "  which reads as broken features and is a broken command.\n"
        "\n"
        "  Most likely cause: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1, which\n"
        "  removes pytest-asyncio along with whatever it was aimed at.\n"
        "\n"
        "  Use the canonical invocation instead:\n"
        "      tools/gate.sh <package>\n"
        "  which disables ONLY the conflicting plugin:\n"
        "      pytest -p no:pytest_ethereum\n"
        "════════════════════════════════════════════════════════════════\n")
    # pytest.exit, not SystemExit: a raise inside a hook surfaces as an
    # INTERNALERROR traceback, which is itself a confusing thing to show
    # someone whose real problem is one wrong environment variable.
    pytest.exit("TEST INFRASTRUCTURE FAILURE: pytest-asyncio is not loaded "
                "but this selection contains async tests. Use tools/gate.sh.",
                returncode=3)
