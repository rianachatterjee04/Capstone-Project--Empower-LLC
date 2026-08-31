"""
Every model query in a router filters by organisation, or says why it does not.

WHY THIS IS A TEST
POST /recruiting/candidates/{id}/decision loaded a candidate by primary key
with no organisation check and wrote to it. An owner of one org hired another
org's candidate: 200, and the victim's row changed. service_role bypasses RLS
here, so the application's WHERE clause is the control, not a backstop.

That endpoint is fixed. This holds the shape across the whole router layer, so
the next one is caught by the build rather than by someone driving it in a
browser.

The exemptions below are all "already scoped upstream". Each is a claim about
code somewhere else, so each names what makes it true — and
test_the_exemptions_still_hold checks that code still says so. An exemption
nobody rechecks is how a real hole gets written down as fine.
"""
from __future__ import annotations

import re
from pathlib import Path

ROUTERS = Path(__file__).resolve().parents[1] / "app" / "api" / "routers"

# (file, model) -> why this query needs no org predicate.
EXEMPT = {
    ("ai_internal.py", "Case"):
        "internal cron endpoint behind require_internal_ai; scans every org by design",
    ("ai_internal.py", "OnboardingPacket"):
        "internal cron endpoint behind require_internal_ai; scans every org by design",
    ("ai_internal.py", "Candidate"):
        "internal cron endpoint behind require_internal_ai; scans every org by design",
    ("orgs.py", "UserProfile"):
        "filtered on actor.user_id, which is the caller's own identity",
    ("pto.py", "TimeOffPolicy"):
        "loaded via assignment.policy_id, and the assignment was fetched org-scoped",
    ("pto.py", "TimeOffLedgerEntry"):
        "loaded via req.id, and the request was fetched org-scoped",
}


def _where_clause(src: str, open_paren: int) -> str:
    """Text inside .where( ... ), counting parens.

    A predicate like `Candidate.id == UUID(candidate_id), Candidate.org_id ==
    UUID(actor.org_id)` contains its own parentheses. A `[^)]*` group stops at
    the first one and reports two correctly-scoped queries as unscoped, which
    is what the first version of this scan did.
    """
    depth, j = 0, open_paren
    while j < len(src):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0:
                return src[open_paren + 1:j]
        j += 1
    return src[open_paren + 1:]


START = re.compile(r"select\(\s*([A-Z]\w+)\s*\)\s*\.where\(")


def _queries():
    for f in sorted(ROUTERS.glob("*.py")):
        src = re.sub(r'"""[\s\S]*?"""', "", f.read_text())
        for m in START.finditer(src):
            cond = _where_clause(src, m.end() - 1)
            yield (f.name, src[:m.start()].count("\n") + 1, m.group(1), cond)


def test_the_scan_finds_the_queries():
    """CONTROL. A rotted pattern would report a clean router layer."""
    qs = list(_queries())
    assert len(qs) >= 50, f"only {len(qs)} select(Model).where(...) sites found"
    # ...and it must see an org predicate where one plainly exists.
    scoped = [q for q in qs if "org_id" in q[3] or "org_uuid" in q[3]]
    assert len(scoped) >= 40, (
        f"only {len(scoped)} of {len(qs)} queries appear scoped — the balanced "
        "paren reader is probably truncating predicates again")


def test_every_router_query_is_scoped_or_exempt():
    unscoped = []
    for name, line, model, cond in _queries():
        if "org_id" in cond or "org_uuid" in cond:
            continue
        if (name, model) in EXEMPT:
            continue
        unscoped.append(f"{name}:{line}  select({model})  where({' '.join(cond.split())[:70]})")
    assert unscoped == [], (
        "these query a model in a router without filtering by organisation. "
        "Either add the predicate, or add it to EXEMPT with the reason it is "
        "already scoped:\n  " + "\n  ".join(unscoped))


def test_the_exemptions_still_hold():
    internal = (ROUTERS / "ai_internal.py").read_text()
    assert "require_internal_ai" in internal, (
        "ai_internal is exempted because every route sits behind "
        "require_internal_ai — that dependency is gone")
    # every route in that file, not just some
    assert internal.count("@router.") == internal.count("require_internal_ai") - 1, (
        "a route in ai_internal.py no longer carries require_internal_ai, and "
        "its queries read across every organisation")

    orgs = (ROUTERS / "orgs.py").read_text()
    assert "UserProfile.user_id == actor.user_id" in orgs, (
        "orgs.py is exempted because it filters on the caller's own user_id")
