"""
A skill in two clusters is one skill, and the person who has it is one person.

WHY THIS IS A TEST
/app/skills rendered its bench-depth list twice for the same skill and React
warned "Encountered two children with the same key, 'postgres'". The duplicate
key was the visible symptom; the arithmetic underneath was the actual defect.

skill_stats is a cluster x skill matrix, one row per (cluster, skill). Two
skills sit in two clusters each -- postgres in "Python backend" and "Data
engineering", saas in "Product" and "Sales" -- so each got two rows carrying
the same people. Every org-wide figure was then summed straight off that
matrix:

    "supply_total":        sum(s.supply for s in skill_stats)
    "total_skills_tracked": len(skill_stats)

So the one engineer who knows postgres was counted twice in the org's bench,
and the product reported 60 skills tracked when the taxonomy holds 58.

A buyer asked "how deep is our postgres bench" would have been told two people
when we know of one. The per-cluster roll-up is a different question and keeps
the overlap on purpose: a team that needs postgres really can call on that
engineer, and both teams can. What must not overlap is the org-wide total.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.services import skills_graph_service as S

ORG = "11111111-1111-1111-1111-111111111111"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDB:
    """compute_graph reads candidates then jobs, in that order, and nothing else."""

    def __init__(self, cands, jobs):
        self._queue = [cands, jobs]

    async def execute(self, _stmt):
        return _FakeResult(self._queue.pop(0))


# ONE candidate, who knows postgres. Whatever the graph says about postgres
# supply, it is saying it about this single person.
ONE_PG_ENGINEER = [SimpleNamespace(resume_text="Backend engineer: python, postgres, aws.")]
NO_JOBS: list = []


def _graph(cands=None, jobs=None):
    return asyncio.run(
        S.compute_graph(_FakeDB(cands or ONE_PG_ENGINEER, jobs or NO_JOBS), ORG)
    )


def _multi_cluster_skills() -> dict[str, list[str]]:
    owner: dict[str, list[str]] = {}
    for c in S.SKILL_CLUSTERS:
        for skill in c["skills"]:
            owner.setdefault(skill, []).append(c["id"])
    return {s: ids for s, ids in owner.items() if len(ids) > 1}


def test_the_overlap_this_guards_still_exists():
    """CONTROL. If no skill sits in two clusters, every assertion below passes
    vacuously and proves nothing. Fail loudly instead of reporting a green."""
    multi = _multi_cluster_skills()
    assert multi, (
        "no skill belongs to more than one cluster any more, so this test can no "
        "longer detect double-counting. Either the taxonomy changed and this "
        "guard needs a new fixture, or the overlap was removed deliberately."
    )
    assert "postgres" in multi, f"expected postgres in >1 cluster; multi-cluster skills are {multi}"


def test_the_old_summation_really_did_double_count():
    """MUTATION CONTROL. Recompute the way the code used to -- straight off the
    matrix -- and show that it disagrees. If these ever match, the fix has been
    reverted or the fixture no longer exercises an overlapping skill."""
    g = _graph()
    off_matrix = sum(s["supply"] for s in g["skills"])
    assert off_matrix > g["summary"]["supply_total"], (
        "summing the cluster x skill matrix no longer over-counts "
        f"({off_matrix} vs {g['summary']['supply_total']}), so this test is not "
        "measuring the defect it was written for."
    )
    assert len(g["skills"]) > g["total_skills_tracked"], (
        "the matrix no longer has more rows than there are distinct skills"
    )


def test_one_engineer_is_not_two():
    g = _graph()
    # The fixture has exactly one person, holding python + postgres + aws.
    # Each of those is one person's worth of supply, counted once.
    assert g["summary"]["supply_total"] == 3, (
        f"one engineer with three skills should contribute 3 to supply_total, "
        f"got {g['summary']['supply_total']} -- postgres is being counted once "
        f"per cluster again"
    )


def test_total_skills_tracked_is_distinct_skills():
    g = _graph()
    distinct = len({s for c in S.SKILL_CLUSTERS for s in c["skills"]})
    assert g["total_skills_tracked"] == distinct, (
        f"reported {g['total_skills_tracked']} skills tracked, taxonomy holds "
        f"{distinct} distinct skills"
    )


def test_surfaced_lists_name_each_skill_once():
    g = _graph()
    for key in ("top_gaps", "top_surplus"):
        names = [s["skill"] for s in g[key]]
        dupes = sorted({n for n in names if names.count(n) > 1})
        assert not dupes, (
            f"{key} lists {dupes} more than once. The page renders these with the "
            f"skill name as the React key, so one of the rows is dropped or "
            f"duplicated, and a reader sees the same skill twice with its bench "
            f"split across the entries."
        )


def test_a_multi_cluster_skill_says_which_clusters_it_is_in():
    g = _graph()
    pg = next(s for s in g["skills"] if s["skill"] == "postgres")
    assert len(pg["clusters"]) == 2, (
        f"postgres is in two clusters but reports {pg['clusters']} -- a reader "
        f"seeing it under one cluster cannot tell it also serves the other"
    )


def test_cluster_rollups_still_credit_every_cluster_that_has_the_skill():
    """The org-wide dedupe must NOT silently remove postgres from a cluster.
    Both teams can call on that engineer; that is not double-counting, it is
    what a cluster roll-up means."""
    g = _graph()
    by_id = {c["id"]: c for c in g["clusters"]}
    assert by_id["py-backend"]["supply"] >= 1, "Python backend lost its postgres engineer"
    assert by_id["data-eng"]["supply"] >= 1, "Data engineering lost its postgres engineer"
    assert g["summary"]["cluster_supply_overlaps"] is True, (
        "cluster supplies overlap and the payload must say so, or someone will "
        "sum the bars, get more than supply_total, and file a bug against the "
        "wrong number"
    )
