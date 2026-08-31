"""
The recognition feed knows whether it is praising anyone who works here.

WHY THIS IS A TEST
The culture page opened with "Sam Rivera recognised Avery Chen · 4H AGO — Held
the line on the payments incident this weekend, found the root cause in 25
minutes and shipped the fix Sunday night", for an organisation whose only
employee is a CDL driver.

These are the rows recognition_service writes into an empty tenant. Once
written they are ordinary database rows, indistinguishable from real praise —
so a schema flag would have meant a migration.

The rule used instead is the one that actually matters, and it generalises: is
the person being praised in your employee records? A feed entirely about people
who do not work here is a sample feed, and the moment somebody posts a real
recognition it stops being one, with no flag to clear.
"""
from __future__ import annotations

from app.services import recognition_service as R

ORG = "11111111-1111-1111-1111-111111111111"


def test_a_feed_about_strangers_is_marked_as_a_sample(monkeypatch):
    monkeypatch.setattr(R, "_employee_names", lambda org_id: {"marcus delgado"})
    out = R.list_recognitions(ORG)
    prov = out["provenance"]
    assert out["items"], "no recognitions at all — the assertion would be vacuous"
    assert prov["all_sample"] is True
    # Substance, not phrasing: the note must say these people are not in the
    # reader's employee records. Pinning the exact sentence is how a test ends
    # up failing on an improved sentence.
    note = (prov["note"] or "").lower()
    assert "employee records" in note
    assert "illustrative" in note or "sample" in note


def test_a_feed_naming_a_real_employee_is_not_marked(monkeypatch):
    """CONTROL. A disclaimer over real praise from real colleagues is an insult."""
    rows = R._load(ORG)
    real = {r.to_name.strip().lower() for r in rows} | {
        r.from_name.strip().lower() for r in rows}
    monkeypatch.setattr(R, "_employee_names", lambda org_id: real)
    prov = R.list_recognitions(ORG)["provenance"]
    assert prov["all_sample"] is False
    assert prov["note"] is None


def test_unreadable_employee_records_are_not_reported_as_all_sample(monkeypatch):
    """CONTROL. Unavailable is not empty.

    If the employee table cannot be read, we do not know whether these people
    work here — and guessing "sample" would put a false disclaimer over real
    praise.
    """
    monkeypatch.setattr(R, "_employee_names", lambda org_id: None)
    prov = R.list_recognitions(ORG)["provenance"]
    assert prov["all_sample"] is False
    assert prov["note"] is None
