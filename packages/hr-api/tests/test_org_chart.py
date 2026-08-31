"""Unit tests for app/services/org_chart_service.py (tree + metrics).

Run: PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest test_org_chart.py
"""
from __future__ import annotations

from app.services.org_chart_service import (
    attrition_rate,
    build_tree,
    headcount_by_department,
)


def _rows():
    return [
        {"id": "ceo", "manager_id": None, "name": "Cleo", "department": "Exec"},
        {"id": "vp", "manager_id": "ceo", "name": "Vic", "department": "Engineering"},
        {"id": "e1", "manager_id": "vp", "name": "Ada", "department": "Engineering"},
        {"id": "e2", "manager_id": "vp", "name": "Bo", "department": "Engineering"},
        {"id": "s1", "manager_id": "ceo", "name": "Sal", "department": "Sales"},
    ]


def test_build_tree_nests_reports():
    roots = build_tree(_rows())
    assert len(roots) == 1
    ceo = roots[0]
    assert ceo["id"] == "ceo" and ceo["team_size"] == 4
    by_id = {n["id"]: n for n in ceo["reports"]}
    assert set(by_id) == {"vp", "s1"}
    assert by_id["vp"]["team_size"] == 2
    assert {n["id"] for n in by_id["vp"]["reports"]} == {"e1", "e2"}


def test_build_tree_orphan_manager_becomes_root():
    rows = [
        {"id": "a", "manager_id": "ghost", "name": "A"},
        {"id": "b", "manager_id": "a", "name": "B"},
    ]
    roots = build_tree(rows)
    assert [r["id"] for r in roots] == ["a"]
    assert roots[0]["reports"][0]["id"] == "b"


def test_build_tree_cycle_safe():
    rows = [
        {"id": "a", "manager_id": "b", "name": "A"},
        {"id": "b", "manager_id": "a", "name": "B"},
        {"id": "c", "manager_id": "a", "name": "C"},
    ]
    roots = build_tree(rows)
    # Nobody is dropped: everyone reachable from the returned roots.
    def collect(nodes):
        out = []
        for n in nodes:
            out.append(n["id"])
            out.extend(collect(n["reports"]))
        return out
    assert sorted(collect(roots))[:3] == ["a", "b", "c"]


def test_build_tree_self_managed_is_root():
    rows = [{"id": "x", "manager_id": "x", "name": "X"}]
    roots = build_tree(rows)
    assert len(roots) == 1 and roots[0]["team_size"] == 0


def test_headcount_by_department_buckets_unassigned():
    rows = _rows() + [{"id": "n1", "manager_id": None, "name": "N", "department": ""}]
    hc = headcount_by_department(rows)
    assert hc[0] == {"department": "Engineering", "count": 3}
    assert {"department": "Unassigned", "count": 1} in hc


def test_attrition_rate_average_headcount():
    # 3 terminations, headcount went 32 -> 28: 3 / 30 = 0.1
    assert attrition_rate(3, 32, 28) == 0.1
    assert attrition_rate(0, 10, 10) == 0.0
    assert attrition_rate(5, 0, 0) == 0.0
