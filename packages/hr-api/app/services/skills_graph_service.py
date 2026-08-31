"""Skills Graph — first-class skill taxonomy with adjacencies, clusters,
and internal supply/demand signals.

This is the Eightfold / Phenom hero feature reframed for SMB. Instead of a
hidden bag of strings in resume text, skills become a navigable graph:

  - **Clusters** group related skills ("Python backend", "React frontend",
    "Data engineering").
  - **Adjacencies** connect skills you'd expect a strong practitioner of one
    to be able to learn ("python" → "go", "react" → "next.js").
  - **Supply** = employees in the org with the skill.
  - **Demand** = open requisitions that need the skill.
  - **Gap** = demand minus supply; surfaces hiring + learning priorities.

In-process taxonomy + heuristic counts pulled from the existing Candidate /
JobPosting tables.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Candidate, JobPosting

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------
SKILL_CLUSTERS: list[dict] = [
    {
        "id": "py-backend",
        "name": "Python backend",
        "skills": ["python", "fastapi", "django", "flask", "asyncio", "postgres", "sqlalchemy"],
        "adjacent": ["go", "rust", "nodejs", "kubernetes", "redis"],
    },
    {
        "id": "frontend",
        "name": "Frontend / React",
        "skills": ["react", "typescript", "javascript", "next.js", "tailwind", "redux"],
        "adjacent": ["vue", "svelte", "graphql", "webpack", "vite"],
    },
    {
        "id": "ml-ai",
        "name": "AI / ML",
        "skills": ["pytorch", "tensorflow", "llm", "embeddings", "transformers", "rag", "ml", "vector"],
        "adjacent": ["python", "cuda", "jupyter", "huggingface", "langchain"],
    },
    {
        "id": "platform",
        "name": "Platform / DevOps",
        "skills": ["kubernetes", "terraform", "aws", "gcp", "docker", "ci/cd", "observability"],
        "adjacent": ["bash", "python", "go", "ansible", "prometheus", "grafana"],
    },
    {
        "id": "data-eng",
        "name": "Data engineering",
        "skills": ["sql", "dbt", "snowflake", "spark", "airflow", "postgres", "bigquery"],
        "adjacent": ["python", "scala", "kafka", "redshift", "looker"],
    },
    {
        "id": "design",
        "name": "Design / Product UX",
        "skills": ["figma", "ux", "ui", "research", "prototype", "design"],
        "adjacent": ["motion", "illustrator", "after-effects", "interaction"],
    },
    {
        "id": "product",
        "name": "Product",
        "skills": ["product", "roadmap", "discovery", "prd", "stakeholder", "saas"],
        "adjacent": ["analytics", "experimentation", "research"],
    },
    {
        "id": "sales",
        "name": "Sales / GTM",
        "skills": ["sales", "outbound", "pipeline", "close", "ae", "saas", "quota"],
        "adjacent": ["partnerships", "marketing", "rev-ops"],
    },
    {
        "id": "ops-fin",
        "name": "Operations / Finance",
        "skills": ["ops", "finance", "accounting", "compliance", "audit", "fp&a"],
        "adjacent": ["sql", "excel", "tableau", "looker"],
    },
]

# Pre-build lookup tables
_SKILL_TO_CLUSTER: dict[str, str] = {}
_ALL_SKILLS: set[str] = set()
for c in SKILL_CLUSTERS:
    for s in c["skills"]:
        _SKILL_TO_CLUSTER[s] = c["id"]
        _ALL_SKILLS.add(s)


# "&" is here for fp&a, which is in the taxonomy. Without it the tokeniser split
# that skill into "fp" and "a" and it could never be matched by anything.
_TOKEN_PATTERN = re.compile(r"[a-z0-9+/.#&-]+")

# Trimmed from the ENDS of a token only, and only after the whole token fails to
# match. "." and "-" and "/" are inside real skill names (next.js, ci/cd), so
# they cannot simply be dropped from the pattern -- but a skill that ends a
# sentence keeps its full stop, and "we use aws." matched nothing at all.
# "+" and "#" are never trimmed: c++ and c# end in them legitimately.
_EDGE_PUNCTUATION = "./-&"


def _extract_skills_from_text(text: str) -> set[str]:
    """Lightweight skill tokenisation against the taxonomy."""
    if not text:
        return set()
    found: set[str] = set()
    for token in _TOKEN_PATTERN.findall(text.lower()):
        if token in _ALL_SKILLS:
            found.add(token)
            continue
        trimmed = token.strip(_EDGE_PUNCTUATION)
        if trimmed in _ALL_SKILLS:
            found.add(trimmed)
    return found


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------
@dataclass
class SkillStat:
    skill: str
    cluster_id: str
    cluster_name: str
    supply: int
    demand: int
    gap: int           # demand - supply (positive = under-staffed)
    adjacents: list[str] = field(default_factory=list)
    # Every cluster this skill belongs to. Usually one; postgres is in both
    # "Python backend" and "Data engineering", saas in both "Product" and
    # "Sales". Callers rendering a flat list need this to explain why the same
    # skill name can appear more than once.
    clusters: list[str] = field(default_factory=list)


@dataclass
class ClusterStat:
    id: str
    name: str
    supply: int
    demand: int
    gap: int
    top_skills: list[str]
    top_adjacents: list[str]
    health: str        # ok | watch | gap | critical


async def compute_graph(db: AsyncSession, org_id: UUID) -> dict:
    """Compute per-skill + per-cluster supply/demand from candidates + jobs."""
    cands = (await db.execute(
        select(Candidate).where(Candidate.org_id == org_id)
    )).scalars().all()
    jobs = (await db.execute(
        select(JobPosting).where(JobPosting.org_id == org_id)
    )).scalars().all()

    supply: dict[str, int] = {}
    demand: dict[str, int] = {}

    for c in cands:
        for s in _extract_skills_from_text(c.resume_text or ""):
            supply[s] = supply.get(s, 0) + 1

    for j in jobs:
        for s in _extract_skills_from_text(j.description or ""):
            demand[s] = demand.get(s, 0) + 1

    # Per-skill
    skill_stats: list[SkillStat] = []
    for cluster in SKILL_CLUSTERS:
        for s in cluster["skills"]:
            sup = supply.get(s, 0)
            dem = demand.get(s, 0)
            skill_stats.append(SkillStat(
                skill=s,
                cluster_id=cluster["id"],
                cluster_name=cluster["name"],
                supply=sup,
                demand=dem,
                gap=dem - sup,
                adjacents=cluster["adjacent"][:5],
            ))

    # Per-cluster roll-up
    cluster_stats: list[ClusterStat] = []
    for cluster in SKILL_CLUSTERS:
        sup = sum(supply.get(s, 0) for s in cluster["skills"])
        dem = sum(demand.get(s, 0) for s in cluster["skills"])
        gap = dem - sup
        if dem == 0 and sup == 0:
            health = "ok"
        elif gap <= 0:
            health = "ok"
        elif gap <= 2:
            health = "watch"
        elif gap <= 5:
            health = "gap"
        else:
            health = "critical"
        # top skills in this cluster by supply
        ranked_skills = sorted(cluster["skills"], key=lambda s: -supply.get(s, 0))[:5]
        cluster_stats.append(ClusterStat(
            id=cluster["id"],
            name=cluster["name"],
            supply=sup,
            demand=dem,
            gap=gap,
            top_skills=ranked_skills,
            top_adjacents=cluster["adjacent"][:5],
            health=health,
        ))

    # skill_stats is a cluster x skill MATRIX: one row per (cluster, skill).
    # A skill in two clusters therefore has two rows carrying the same people.
    # That is correct for the matrix and for the per-cluster roll-up above -- a
    # team that needs postgres does have that one engineer -- but it is wrong
    # for anything org-wide. Summing the rows counted that engineer twice, so
    # supply_total over-reported the bench, and total_skills_tracked reported
    # 60 rows as 60 skills when only 58 distinct skills exist.
    #
    # So: per-cluster figures come from the matrix, org-wide figures come from
    # one row per distinct skill.
    clusters_of: dict[str, list[str]] = {}
    for st in skill_stats:
        clusters_of.setdefault(st.skill, []).append(st.cluster_name)
    for st in skill_stats:
        st.clusters = clusters_of[st.skill]

    per_skill: dict[str, SkillStat] = {}
    for st in skill_stats:
        per_skill.setdefault(st.skill, st)   # identical supply/demand; keep first cluster
    distinct = list(per_skill.values())

    top_gaps = sorted([s for s in distinct if s.gap > 0], key=lambda s: -s.gap)[:10]
    top_surplus = sorted([s for s in distinct if s.gap < 0], key=lambda s: s.gap)[:10]

    return {
        "clusters": [c.__dict__ for c in cluster_stats],
        "skills": [s.__dict__ for s in skill_stats],
        "top_gaps": [s.__dict__ for s in top_gaps],
        "top_surplus": [s.__dict__ for s in top_surplus],
        "total_skills_tracked": len(distinct),
        "summary": {
            "supply_total": sum(s.supply for s in distinct),
            "demand_total": sum(s.demand for s in distinct),
            "net_gap": sum(s.gap for s in distinct if s.gap > 0),
            # Cluster supplies deliberately overlap, so they do NOT sum to
            # supply_total. Stated here so nobody reconciles the bars against
            # the headline and concludes one of them is broken.
            "cluster_supply_overlaps": True,
        },
    }
