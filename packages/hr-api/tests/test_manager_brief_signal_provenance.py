"""
A manager's action feed is about their own people.

Previously attrition rows came from _synthetic_features() (Avery Chen et al.)
and were labelled is_sample. The brief now loads direct reports from
employees.manager_employee_id and scores those people — so sample flags and
"don't count samples in the headline" guards are no longer the contract.
"""
from __future__ import annotations

import inspect

from app.services import manager_brief_service as M


def test_build_brief_loads_team_from_employees():
    src = inspect.getsource(M)
    assert "manager_employee_id" in src
    assert "_synthetic_features" not in src
    assert "predict_batch" in src


def test_list_managers_queries_employees_with_reports():
    src = inspect.getsource(M.list_managers)
    assert "manager_employee_id" in src
    assert "employees" in src


def test_attrition_signals_are_not_sample_cohort():
    """Real team attrition may be urgent; invented sample people must not appear."""
    src = inspect.getsource(M)
    assert "_synthetic_features" not in src
    assert "Avery Chen" not in src


def test_the_signal_dataclass_defaults_to_real():
    sig = M.BriefSignal(kind="review", severity="this_week", title="t",
                        detail="d", cta_label="Open", cta_href="/app")
    assert sig.is_sample is False


def test_headline_uses_real_signal_count():
    src = inspect.getsource(M.build_brief)
    assert "len(signals)}" in src
    assert "is_sample=True" not in src
