"""
Every writer to a table agrees on that table's columns.

WHY THIS IS A TEST
POST /api/ai/decision answered "ai_decisions is not available in this
deployment". The obvious fix is to write the migration. It is not that simple:
five call sites insert into public.ai_decisions and they disagree about what
the table looks like.

    app/services/ai_system_of_record.py   input,  output,  model, actor_user_id
    app/org_ai/memory.py                  input,  output
    app/api/routers/resume_ai.py          inputs, outputs
    app/api/routers/screening.py          inputs, outputs   (and SELECTs them)
    app/api/routers/ai_memory.py          decision_payload

Three vocabularies for the same ledger. Whichever schema gets created, at least
two of these writers break -- and they break at write time, on the audit trail,
which is the one place a silent failure is least acceptable.

This is blocker #6 in a sharper form. There the problem was two definitions of
one table racing to be created first. Here there is no definition at all, and
the disagreement is only visible by reading five files.

The baseline below records the divergence that exists today. It is not
approval. A NEW divergence fails this test; closing an existing one means
deleting its entry.
"""
from __future__ import annotations

import pathlib
import re
from collections import defaultdict

APP = pathlib.Path("app")

INSERT = re.compile(
    r"insert\s+into\s+(?:public\.)?(\w+)\s*\(([^)]*)\)",
    re.IGNORECASE | re.DOTALL,
)

# Tables whose writers already disagree. Each entry is the price of not having
# one schema source of truth; none is a decision to keep it that way.
KNOWN_DIVERGENT = {
    "ai_decisions",
}


def _writers() -> dict[str, dict[str, set[str]]]:
    """table -> {file: set(columns)} for every INSERT in the package."""
    out: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text()
        for m in INSERT.finditer(text):
            table = m.group(1).lower()
            cols = {
                c.strip().lower()
                for c in m.group(2).replace("\n", " ").split(",")
                if c.strip() and c.strip().isidentifier()
            }
            if cols:
                out[table].setdefault(str(path), set()).update(cols)
    return out


def _divergent(writers: dict[str, dict[str, set[str]]]) -> dict[str, dict]:
    """Tables where writers use different names for the same slot.

    Writers legitimately insert different SUBSETS of a table's columns -- one
    supplies an optional field, another omits it. That is not divergence.

    Divergence is a singular/plural twin -- "input" and "inputs" both appearing
    among a table's columns, with no single writer using both. One writer would
    never insert into two columns that differ only by an "s"; two writers each
    believing theirs is the real name is exactly the ai_decisions bug.
    """
    bad = {}
    for table, by_file in writers.items():
        if len(by_file) < 2:
            continue
        all_cols = set().union(*by_file.values())
        conflicts = set()
        for col in all_cols:
            twin = col + "s"
            if twin not in all_cols:
                continue
            # a single writer using both means they really are two columns
            if any({col, twin} <= cols for cols in by_file.values()):
                continue
            conflicts |= {col, twin}
        if conflicts:
            bad[table] = {"conflicting": sorted(conflicts),
                          "writers": {f: sorted(c) for f, c in by_file.items()}}
    return bad


def test_no_new_table_has_writers_that_disagree():
    found = _divergent(_writers())
    new = {t: v for t, v in found.items() if t not in KNOWN_DIVERGENT}
    assert not new, (
        "these tables are written by call sites that use different names for the "
        "same column, so whichever schema is created will break some of them:\n"
        + "\n".join(f"  {t}: {v['conflicting']}\n    " +
                    "\n    ".join(f"{f}: {c}" for f, c in v["writers"].items())
                    for t, v in new.items())
    )


def test_the_known_divergence_is_still_real():
    """CONTROL. If ai_decisions has been unified, this test should stop claiming
    it is divergent -- a stale baseline hides the next one."""
    found = _divergent(_writers())
    stale = KNOWN_DIVERGENT - set(found)
    assert not stale, (
        f"{sorted(stale)} no longer has disagreeing writers. Remove it from "
        "KNOWN_DIVERGENT so a future divergence is caught."
    )


def test_ai_decisions_disagreement_is_the_one_we_documented():
    found = _divergent(_writers())
    assert "ai_decisions" in found
    conflicting = found["ai_decisions"]["conflicting"]
    assert {"input", "inputs"} & set(conflicting) or {"output", "outputs"} & set(conflicting), (
        f"the ai_decisions conflict has changed shape: {conflicting}. Re-read the "
        "writers before provisioning the table."
    )


def test_the_detector_finds_a_planted_disagreement(tmp_path, monkeypatch):
    """MUTATION CONTROL."""
    planted = {
        "widgets": {
            "a.py": {"org_id", "payload"},
            "b.py": {"org_id", "payloads"},
        }
    }
    assert "widgets" in _divergent(planted)


def test_the_detector_allows_writers_that_insert_different_subsets():
    """CONTROL, the other direction. One writer supplying an optional column and
    another omitting it is normal, not a schema disagreement."""
    fine = {
        "widgets": {
            "a.py": {"org_id", "name", "note"},
            "b.py": {"org_id", "name"},
        }
    }
    assert _divergent(fine) == {}, _divergent(fine)
