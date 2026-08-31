"""
No demo seed writes an authority source that claims a government lookup.

WHY THIS IS A TEST
The load page renders `authority_source` verbatim. With the demo carriers
seeded as FMCSA_LIVE it read:

    CARRIER    Delta Line Transport
    AUTHORITY  ACTIVE   fmcsa live
    CHECKED    Aug 28, 03:53 AM

on the screen a broker uses to decide whether to tender freight to that
carrier — while the same board's disclosure listed "FMCSA live lookup" under
what is NOT connected. No FMCSA lookup has ever run against these rows.

FMCSA_CACHED is the same claim one step removed: a cached result still asserts
that a lookup happened once. MANUAL_ENTRY is what actually occurred — a human
put the status in the row.

check_carrier treats every source except NOT_CONNECTED identically and judges
FRESHNESS, so the demo's three cases behave exactly as before: stale at 90
days, unverified, and eligible at 2 days. Nothing about the journey changed
except that it stopped claiming a government check.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

CLAIMS_A_LOOKUP = ("FMCSA_LIVE", "FMCSA_CACHED")


def _code(path: Path) -> str:
    """Source with comments and docstrings dropped.

    The fix is explained in a comment that names FMCSA_LIVE, and a guard that
    fires on its own explanation teaches people to reword the comment.
    """
    src = re.sub(r'"""[\s\S]*?"""', "", path.read_text())
    src = re.sub(r"(?m)^\s*#.*$", "", src)
    return re.sub(r"(?m)^\s*--.*$", "", src)


def _demo_scripts():
    return [f for f in sorted(SCRIPTS.glob("*.py")) if "demo" in f.name or "seed" in f.name]


def test_there_are_demo_scripts_to_check():
    """CONTROL. If the scripts move, this file silently checks nothing."""
    scripts = _demo_scripts()
    assert len(scripts) >= 2, f"only found {[f.name for f in scripts]}"
    assert any("brokered" in f.name for f in scripts)


def test_no_demo_script_seeds_an_fmcsa_sourced_authority():
    bad = []
    for f in _demo_scripts():
        code = _code(f)
        for claim in CLAIMS_A_LOOKUP:
            if claim in code:
                line = code[:code.index(claim)].count("\n") + 1
                bad.append(f"{f.name}:{line}  {claim}")
    assert bad == [], (
        "these demo seeds write an authority source that asserts an FMCSA "
        "lookup happened. Nothing has looked these carriers up; the load page "
        "prints the field verbatim next to ACTIVE authority. Use MANUAL_ENTRY:"
        "\n  " + "\n  ".join(bad))


def test_manual_entry_is_still_dispatchable():
    """CONTROL. The fix must not have quietly broken the demo journey.

    check_carrier refuses NOT_CONNECTED and stale checks. MANUAL_ENTRY inside
    the window has to remain eligible, or the honest seed would have turned the
    happy path into a refusal.
    """
    from datetime import date, timedelta
    from app.trucking.eligibility import check_carrier

    carrier = type("C", (), {
        "is_approved": True,
        "authority_status": "ACTIVE",
        "authority_source": "MANUAL_ENTRY",
        "authority_checked_at": date.today() - timedelta(days=2),
        "insurance_expires_on": date.today() + timedelta(days=180),
    })()
    d = check_carrier(carrier=carrier)
    assert d.eligible, [r.code for r in d.reasons]


def test_a_stale_manual_entry_is_still_refused():
    """CONTROL. And the staleness case the demo exists to show still refuses."""
    from datetime import date, timedelta
    from app.trucking.eligibility import check_carrier

    carrier = type("C", (), {
        "is_approved": True,
        "authority_status": "ACTIVE",
        "authority_source": "MANUAL_ENTRY",
        "authority_checked_at": date.today() - timedelta(days=90),
        "insurance_expires_on": date.today() + timedelta(days=200),
    })()
    d = check_carrier(carrier=carrier)
    assert not d.eligible
    assert "CARRIER_AUTHORITY_STALE" in [r.code for r in d.reasons]
