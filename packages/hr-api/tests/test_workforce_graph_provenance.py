"""
The workforce graph says which workers are real, and does not score what it
cannot measure.

WHY THIS IS A TEST
An organisation with one employee rendered "Total workforce 11", every node
carrying a trust score, under a header reading "No HRIS or hiring marketplace
can show you this." Ten of the eleven were seeded operator profiles, and
nothing in the payload distinguished them.

The eleventh was worse. A real employee not present in the demo seed inherited
the seed's defaults:

    "salary":       fallback.get("salary", 120_000)
    "perf_rating":  fallback.get("perf_rating", 3.5)
    "tenure_years": fallback.get("tenure_years", 2.0)

So a CDL driver we hold no compensation record for was drawn with a $120,000
salary, a 3.5 performance rating, and a trust score of 74 computed from both —
and that invented cost was summed into total workforce cost. A trust score
attached to a named person is a claim about that person.

Unscored is not a low score, and unpriced is not free.
"""
from __future__ import annotations

import asyncio

from app.services import workforce_graph_service as W

ORG = "11111111-1111-1111-1111-111111111111"


def _nodes(humans):
    return W.build_workforce(humans)["nodes"]


REAL_EMPLOYEE = [{
    "id": "8d3af8bd-788b-486c-991c-55779c3e5d19",
    "name": "Marcus Delgado",
    "role": "CDL Driver — Regional Reefer",
    "team": "Operations",
    "manager_id": None,
    "salary": None,
    "skills": [],
    "perf_rating": None,
    "tenure_years": None,
}]


def test_an_employee_with_no_salary_is_not_given_one():
    human = [n for n in _nodes(REAL_EMPLOYEE) if n.type == "human"][0]
    assert human.cost_annual is None, (
        f"invented an annual cost of {human.cost_annual} for an employee with "
        "no salary on record")
    assert human.compensation.get("available") is False
    assert human.compensation.get("reason")


def test_an_employee_with_no_performance_data_is_not_scored():
    human = [n for n in _nodes(REAL_EMPLOYEE) if n.type == "human"][0]
    assert human.trust_score is None, (
        f"gave a trust score of {human.trust_score} to an employee with no "
        "performance rating on record — that is a claim about a named person")
    assert human.trust_basis, "does not say why there is no score"


def test_totals_exclude_what_was_never_measured():
    summary = W._summary_from(_nodes(REAL_EMPLOYEE))
    assert summary["workers_without_a_cost"] >= 1
    assert summary["workers_without_a_trust_score"] >= 1
    assert summary["avg_trust_humans"] is None, (
        "averaged a human trust score when no human is scored")
    # The unpriced worker must not appear in the total as a zero either — the
    # total is the sum of the priced ones only.
    priced = sum(n.cost_annual for n in _nodes(REAL_EMPLOYEE)
                 if n.cost_annual is not None)
    assert summary["total_workforce_cost"] == round(priced)


def test_every_node_declares_where_it_came_from():
    for n in _nodes(REAL_EMPLOYEE):
        assert n.source in ("employee_record", "sample_profile"), (
            f"{n.name} does not say whether it is a real worker: {n.source!r}")


def test_seeded_workers_are_counted_as_illustrative():
    prov = W._provenance(_nodes(REAL_EMPLOYEE))
    assert prov["employee_records"] == 1
    assert prov["sample_profiles"] >= 9
    assert "illustrative" in prov["note"]


def test_a_seeded_employee_still_scores(  ):
    """CONTROL. The fix withholds scores for missing data, not for all humans."""
    seeded = W._human_seed()[:1]
    human = [n for n in _nodes(seeded) if n.type == "human"][0]
    assert human.trust_score is not None, (
        "an employee WITH a performance rating lost their score too — the "
        "withholding is too broad")
    assert human.cost_annual is not None


# ---------------------------------------------------------------------------
# The defaults live in the DB loader, not in the node builder.
#
# The tests above construct a human dict directly and prove build_workforce
# handles a missing salary. They passed with the $120,000 default restored,
# because that default is applied by _humans_for_org before build_workforce
# ever sees the row. Evidence at one layer says nothing about the layer that
# actually had the bug.
# ---------------------------------------------------------------------------

class _Row:
    """The Employee columns _humans_for_org reads."""
    def __init__(self):
        from uuid import UUID
        self.id = UUID("8d3af8bd-788b-486c-991c-55779c3e5d19")
        self.org_id = UUID(ORG)
        self.status = "active"
        self.legal_name = "Marcus Delgado"
        self.preferred_name = None
        self.job_title = "CDL Driver — Regional Reefer"
        self.department = "Operations"
        self.manager_employee_id = None


class _EmployeeDB:
    async def execute(self, *a, **k):
        class Res:
            def scalars(self_inner):
                class S:
                    def all(self_s):
                        return [_Row()]
                return S()
        return Res()


def test_the_loader_does_not_default_a_real_employee_into_the_seed():
    humans = asyncio.run(W._humans_for_org(_EmployeeDB(), ORG))
    assert len(humans) == 1, humans
    h = humans[0]
    assert h["name"] == "Marcus Delgado"
    assert h["salary"] is None, (
        f"the loader gave a real employee a salary of {h['salary']} — this is "
        "the exact default that put $120,000 on a CDL driver")
    assert h["perf_rating"] is None, (
        f"the loader gave a real employee a performance rating of "
        f"{h['perf_rating']}, from which a trust score was computed")
    assert h["tenure_years"] is None
