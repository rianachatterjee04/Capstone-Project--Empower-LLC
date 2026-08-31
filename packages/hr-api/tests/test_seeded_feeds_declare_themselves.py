"""
Seeded goals and notifications say they were not produced by anything that
happened here.

WHY THIS IS A TEST
Two more feeds shipped with content presented as this organisation's own:

  notifications  "Avery Chen flagged high attrition risk · WORKFORCE RISK AGENT
                 · Compa-ratio below 0.85 (under-paid vs. band midpoint). No
                 raise in 22 months. · 2H AGO"
                 and "2 high-severity ombudsman" — while the ombudsman page
                 correctly showed zero cases. Two screens disagreeing about the
                 same tenant.

  goals          "Objectives 5 · On track 4 · At risk 1 · Avg progress 75%",
                 owned by Jamie Cole and others, across Sales, Engineering,
                 Executive, HR and Customer Success — for an organisation with
                 one employee in Operations.

A notification is a claim that something HAPPENED, which makes it the sharpest
of these: it has a timestamp, an actor, and a verb.

Goals uses the same rule as the recognition feed — an objective owned by
somebody who is not in your employee records is a sample objective — so it
resolves itself the first time a real one is written.
"""
from __future__ import annotations

from app.services import goals_service as G
from app.services import notifications_service as N

ORG = "11111111-1111-1111-1111-111111111111"


def test_every_seeded_notification_is_marked():
    out = N.list_notifications(ORG)
    assert out["items"], "no notifications — the assertion would be vacuous"
    unmarked = [n["title"] for n in out["items"] if not n.get("is_sample")]
    assert unmarked == [], (
        f"these read as alerts raised by real events: {unmarked}")
    assert out["provenance"]["all_sample"] is True
    assert "your organisation" in (out["provenance"]["note"] or "")


def test_a_real_notification_would_not_be_marked():
    """CONTROL. The flag defaults False, so anything raised by an event is clean."""
    n = N.Notification(id="x", title="t", detail="d", topic="risk", severity="info")
    assert n.is_sample is False


def test_seeded_goals_are_declared(monkeypatch):
    monkeypatch.setattr(G, "_employee_names", lambda org_id: {"marcus delgado"})
    out = G.list_objectives(ORG)
    assert out["summary"]["total"] > 0
    assert out["provenance"]["all_sample"] is True
    assert "employee records" in (out["provenance"]["note"] or "")


def test_goals_owned_by_a_real_employee_are_not_declared(monkeypatch):
    """CONTROL. A disclaimer over objectives a team is working to is worse than none."""
    rows = G._mem_ensure(ORG) if not G._use_db() else G._db_load(ORG)
    owners = {(o.owner or "").strip().lower() for o in rows if o.owner}
    monkeypatch.setattr(G, "_employee_names", lambda org_id: owners)
    out = G.list_objectives(ORG)
    assert out["provenance"]["all_sample"] is False
    assert out["provenance"]["note"] is None


def test_unreadable_employees_do_not_mark_goals_as_samples(monkeypatch):
    """CONTROL. Unavailable is not empty."""
    monkeypatch.setattr(G, "_employee_names", lambda org_id: None)
    out = G.list_objectives(ORG)
    assert out["provenance"]["all_sample"] is False
