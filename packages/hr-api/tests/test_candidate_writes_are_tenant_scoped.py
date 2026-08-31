"""
Loading a Candidate by primary key is not a tenant check.

WHY THIS IS A TEST
POST /recruiting/candidates/{id}/decision checked the caller's ROLE and then
loaded the candidate by primary key with no organisation check at all:

    if actor.role not in ("owner","admin","hr","manager"):
        raise HTTPException(status_code=403, detail="Not allowed")
    cand = await db.get(Candidate, UUID(candidate_id))
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    cand.status = "hired" if hire else "rejected"

Proved against the running API: an owner of org 1111… posted
decision?hire=true against a candidate belonging to org 2222…, received 200,
and the victim organisation's row became "hired". The same call to
/candidates/{id}/stage returned 404, because move_stage — twenty lines above in
the same file — compares org_id.

A role check answers "may this person hire someone". It does not answer "is
this their candidate". service_role bypasses RLS here, so the application's
WHERE clause is the control, not a backstop behind one.

This checks the shape rather than the one endpoint: every by-primary-key load
of a Candidate in a router must be followed by an org comparison, or be listed
below with the reason it does not need one.
"""
from __future__ import annotations

import re
from pathlib import Path

ROUTERS = Path(__file__).resolve().parents[1] / "app" / "api" / "routers"

# Sites where the id is already known to be in-tenant, with why.
SCOPED_UPSTREAM = {
    "resume_ai.py": (
        "screen_job selects the JobPosting with org_id == actor.org_id and then "
        "the Candidate rows with Candidate.org_id == org_uuid; the ids handed to "
        "db.get come from that scoped query"),
}

LOAD = re.compile(r"db\.get\(\s*Candidate\s*,")
ORG_CHECK = re.compile(r"org_id\s*(!=|==)|actor\.org_id")


def _sites():
    for f in sorted(ROUTERS.glob("*.py")):
        src = f.read_text()
        # drop docstrings: this file's own fix is described in one
        body = re.sub(r'"""[\s\S]*?"""', "", src)
        for m in LOAD.finditer(body):
            line = body[:m.start()].count("\n") + 1
            following = "\n".join(body.split("\n")[line - 1:line + 5])
            yield f.name, line, following


def test_the_scan_finds_the_loads():
    """CONTROL. Zero sites would make the assertion below vacuous."""
    sites = list(_sites())
    assert len(sites) >= 2, f"only {len(sites)} db.get(Candidate, ...) sites found"
    assert any(name == "recruiting.py" for name, _, _ in sites)


def test_every_candidate_load_is_tenant_scoped():
    unscoped = []
    for name, line, following in _sites():
        if ORG_CHECK.search(following):
            continue
        if name in SCOPED_UPSTREAM:
            continue
        unscoped.append(f"{name}:{line}")
    assert unscoped == [], (
        "these load a Candidate by primary key without comparing org_id — any "
        "authenticated caller with the right ROLE can reach another tenant's "
        f"row:\n  " + "\n  ".join(unscoped))


def test_the_upstream_exemptions_still_hold():
    """An exemption is a claim about other code; check that code still says so."""
    for name, reason in SCOPED_UPSTREAM.items():
        src = (ROUTERS / name).read_text()
        assert "Candidate.org_id == org_uuid" in src, (
            f"{name} is exempted because {reason}, but that scoping is gone")
        assert "JobPosting.org_id == org_uuid" in src, (
            f"{name} no longer scopes the job posting by org")
