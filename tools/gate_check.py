"""Prove the required evidence classes were actually exercised.

WHY A MANIFEST AND NOT JUST A COMMAND
This repository's evidence pipeline has failed three distinct ways:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 stripped pytest-asyncio, manufacturing
        nineteen failures that looked like broken features
    tools/gate.sh omitted FINTRA_PAYROLL_PG_ADMIN_DSN, so the fifty
        database-enforced tests SKIPPED and the gate reported green over a
        tree whose central control was never run
    three concurrent gate runs wrote the same output paths and produced a
        summary whose author could not be established

Every one of those reported success while measuring less than it claimed. A
command that runs is not evidence that the right things ran, so the gate now
states what it EXPECTED, what it COLLECTED, and what it EXECUTED -- and a
critical suite that vanishes or collects zero makes the whole run
GATE_INCOMPLETE rather than green.

    GATE_INCOMPLETE != PASS != FAIL

Those are three different answers and collapsing any two of them is how a gate
certifies its own blind spot.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "tools", "gate_manifest.json")


def collect_count(pkg_dir: str, path: str, env: dict) -> int:
    """`path` may name SEVERAL files, space separated.

    Passed as one argument, pytest treats "a.py b.py" as a single nonexistent
    path, collects nothing, and the suite reports GATE_INCOMPLETE -- which
    reads as missing evidence when the tests exist and pass.
    """
    """How many tests this selection actually collects.

    pytest's -q --collect-only emits either a "N tests collected" summary or
    a per-file "path: N" listing depending on version and plugins, and a
    collector that understands only one of them reports ZERO for a healthy
    suite. That is exactly the false GATE_INCOMPLETE this instrument would
    otherwise raise -- and an instrument that cries wolf gets ignored, which
    is a slower way to arrive at the same blind spot.
    """
    r = subprocess.run(
        [sys.executable, "-m", "pytest", *path.split(), "--collect-only", "-q",
         "-p", "no:cacheprovider", "-p", "no:pytest_ethereum"],
        cwd=pkg_dir, capture_output=True, text=True, env=env)

    m = re.search(r"(\d+) tests? collected", r.stdout)
    if m:
        return int(m.group(1))

    per_file = re.findall(r"^\S+\.py: (\d+)$", r.stdout, re.M)
    if per_file:
        return sum(int(n) for n in per_file)

    # Last resort: count node ids (file::test_name).
    return len(re.findall(r"^\S+\.py::\S+$", r.stdout, re.M))


def run_suite(pkg_dir: str, path: str, env: dict):
    """Execute a suite and read its outcome from a MACHINE-READABLE report.

    Parsing pytest's console output is the wrong instrument. The summary line
    moves with pytest version, plugins and config, and one real package here
    (aegis) prints no summary at all in quiet mode because a warnings block
    follows it. A parser reading that text saw zero passed on a suite that
    passes 104 -- and briefly reported PASS over it.

    --junitxml is stable across versions and states counts as attributes, so
    the instrument stops depending on how a human-facing renderer happens to
    format itself today.
    """
    import xml.etree.ElementTree as ET

    with tempfile.TemporaryDirectory() as tmp:
        report = os.path.join(tmp, "report.xml")
        r = subprocess.run(
            [sys.executable, "-m", "pytest", *path.split(), "-q", "--no-header",
             "-p", "no:cacheprovider", "-p", "no:pytest_ethereum",
             f"--junitxml={report}"],
            cwd=pkg_dir, capture_output=True, text=True, env=env)
        if not os.path.exists(report):
            return {"passed": 0, "failed": 0, "skipped": 0,
                    "returncode": r.returncode, "report_missing": True}
        root = ET.parse(report).getroot()
        suite = root.find("testsuite") if root.tag == "testsuites" else root
        total = int(suite.get("tests", 0))
        failures = int(suite.get("failures", 0))
        errors = int(suite.get("errors", 0))
        skipped = int(suite.get("skipped", 0))
        return {"passed": total - failures - errors - skipped,
                "failed": failures + errors, "skipped": skipped,
                "returncode": r.returncode, "report_missing": False}


def main() -> int:
    with open(MANIFEST) as fh:
        manifest = json.load(fh)

    env = dict(os.environ)
    if not env.get("FINTRA_PAYROLL_PG_ADMIN_DSN"):
        try:
            if subprocess.run(["pg_isready", "-q"]).returncode == 0:
                env["FINTRA_PAYROLL_PG_ADMIN_DSN"] = "postgresql:///postgres"
        except FileNotFoundError:
            pass

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"GATE MANIFEST CHECK  run={stamp}")
    print(f"{'SUITE':<26}{'EXP':>6}{'COLL':>6}{'EXEC':>6}{'PASS':>6}"
          f"{'FAIL':>6}{'SKIP':>6}  STATUS")
    print("-" * 88)

    incomplete, failed = [], []
    for suite in manifest["suites"]:
        pkg_dir = os.path.join(ROOT, "packages", suite["package"])
        need_env = suite.get("requires_env")
        if need_env and not env.get(need_env):
            print(f"{suite['id']:<26}{suite['min_tests']:>6}{'-':>6}{'-':>6}"
                  f"{'-':>6}{'-':>6}{'-':>6}  GATE_INCOMPLETE ({need_env} unset)")
            incomplete.append(suite["id"])
            continue

        collected = collect_count(pkg_dir, suite["path"], env)
        if collected == 0:
            print(f"{suite['id']:<26}{suite['min_tests']:>6}{0:>6}{'-':>6}"
                  f"{'-':>6}{'-':>6}{'-':>6}  GATE_INCOMPLETE (collected zero)")
            incomplete.append(suite["id"])
            continue

        res = run_suite(pkg_dir, suite["path"], env)
        executed = res["passed"] + res["failed"]
        status = "PASS"
        if collected < suite["min_tests"]:
            status = "GATE_INCOMPLETE (below minimum)"
            incomplete.append(suite["id"])
        elif executed + res["skipped"] == 0:
            # Collected tests that never ran. The instrument reported PASS
            # over exactly this once; a suite that executes nothing is missing
            # evidence, not passing.
            status = "GATE_INCOMPLETE (collected but executed none)"
            incomplete.append(suite["id"])
        elif res["failed"]:
            status = "FAIL"
            failed.append(suite["id"])
        print(f"{suite['id']:<26}{suite['min_tests']:>6}{collected:>6}"
              f"{executed:>6}{res['passed']:>6}{res['failed']:>6}"
              f"{res['skipped']:>6}  {status}")

    print("-" * 88)
    critical = {s["id"] for s in manifest["suites"] if s["critical"]}
    ci = [s for s in incomplete if s in critical]
    if ci:
        print(f"GATE_INCOMPLETE — critical evidence missing: {ci}")
        return 3
    if failed:
        print(f"FAIL — {failed}")
        return 1
    if incomplete:
        print(f"PASS (non-critical evidence missing: {incomplete})")
        return 0
    print("PASS — every required evidence class was collected and executed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
