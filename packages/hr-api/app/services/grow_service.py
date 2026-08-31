"""Grow — career ladders, competency frameworks, and growth plans.

Lattice "Grow" parity. A ladder belongs to a job family (Engineering / Sales …)
and has ordered levels (L1..Ln), competencies (name / category / description),
and per-(competency, level) expectations (a rubric + an expected 1–5 rating).

An employee growth plan pins a current level and a target level, holds self +
manager competency ratings, links growth goals to goals.py, and can be tied to
the review / goal it supports.

Same in-process, org-scoped, thread-safe store pattern as goals_service. DB-free,
deterministic, fail-soft.

GAP LOGIC
---------
For a plan's target level, each competency has an ``expected_rating`` (1–5). The
employee's current rating is the manager rating (falling back to self, then 0).
``gap = expected_rating − current_rating``; a competency is ``below_bar`` when
current < expected. The gap view returns every competency with its numbers and a
``below_bar`` list sorted by gap descending (biggest gap first).
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

try:  # pragma: no cover - import guard
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


PLAN_STATUSES = ("draft", "active", "complete")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass
class Level:
    id: str
    name: str            # "L3"
    title: str           # "Senior Engineer"
    index: int           # 1-based order

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "title": self.title, "index": self.index}


@dataclass
class Competency:
    id: str
    name: str
    category: str
    description: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "category": self.category, "description": self.description}


@dataclass
class Expectation:
    id: str
    competency_id: str
    level_id: str
    rubric: str
    expected_rating: int = 3   # 1..5 bar for that level

    def to_dict(self) -> dict:
        return {"id": self.id, "competency_id": self.competency_id, "level_id": self.level_id,
                "rubric": self.rubric, "expected_rating": self.expected_rating}


@dataclass
class Ladder:
    id: str
    family: str
    levels: list[Level] = field(default_factory=list)
    competencies: list[Competency] = field(default_factory=list)
    expectations: list[Expectation] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "family": self.family,
            "levels": [lv.to_dict() for lv in sorted(self.levels, key=lambda x: x.index)],
            "competencies": [c.to_dict() for c in self.competencies],
            "expectations": [e.to_dict() for e in self.expectations],
            "created_at": self.created_at,
        }


@dataclass
class GrowthPlan:
    id: str
    employee_id: str
    ladder_id: str
    current_level_id: Optional[str] = None
    target_level_id: Optional[str] = None
    # competency_id -> {"self": int|None, "manager": int|None}
    ratings: dict = field(default_factory=dict)
    growth_goals: list[dict] = field(default_factory=list)   # [{text, goal_id?}]
    status: str = "draft"
    linked_review_id: Optional[str] = None
    linked_goal_id: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "ladder_id": self.ladder_id,
            "current_level_id": self.current_level_id,
            "target_level_id": self.target_level_id,
            "ratings": self.ratings,
            "growth_goals": self.growth_goals,
            "status": self.status,
            "linked_review_id": self.linked_review_id,
            "linked_goal_id": self.linked_goal_id,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_ladders: dict[str, list[Ladder]] = {}
_plans: dict[str, list[GrowthPlan]] = {}
_seeded: set[str] = set()


def _seed(org_id: str) -> None:
    lid = str(uuid.uuid4())
    l1 = Level(id=str(uuid.uuid4()), name="L2", title="Engineer", index=1)
    l2 = Level(id=str(uuid.uuid4()), name="L3", title="Senior Engineer", index=2)
    l3 = Level(id=str(uuid.uuid4()), name="L4", title="Staff Engineer", index=3)
    c_craft = Competency(id=str(uuid.uuid4()), name="Technical craft", category="craft",
                         description="Designs, builds and ships reliable systems.")
    c_impact = Competency(id=str(uuid.uuid4()), name="Impact & ownership", category="impact",
                          description="Owns outcomes end-to-end.")
    c_collab = Competency(id=str(uuid.uuid4()), name="Collaboration", category="collaboration",
                          description="Raises the team through mentorship and communication.")
    ladder = Ladder(id=lid, family="Engineering", levels=[l1, l2, l3],
                    competencies=[c_craft, c_impact, c_collab])
    # Expectations — expected rating rises with level.
    for lv, bar in ((l1, 2), (l2, 3), (l3, 4)):
        for c in (c_craft, c_impact, c_collab):
            ladder.expectations.append(Expectation(
                id=str(uuid.uuid4()), competency_id=c.id, level_id=lv.id,
                rubric=f"At {lv.name}, demonstrates {c.name.lower()} consistently.",
                expected_rating=bar,
            ))
    _ladders[org_id] = [ladder]

    plan = GrowthPlan(
        id=str(uuid.uuid4()),
        employee_id="e-avery",
        ladder_id=lid,
        current_level_id=l2.id,
        target_level_id=l3.id,
        ratings={
            c_craft.id: {"self": 4, "manager": 4},
            c_impact.id: {"self": 3, "manager": 3},
            c_collab.id: {"self": 3, "manager": 2},
        },
        growth_goals=[{"text": "Lead the design-system migration", "goal_id": None}],
        status="active",
    )
    _plans[org_id] = [plan]


def _ensure(org_id: str) -> tuple[list[Ladder], list[GrowthPlan]]:
    with _lock:
        if org_id not in _seeded:
            _seed(org_id)
            _seeded.add(org_id)
        return _ladders.setdefault(org_id, []), _plans.setdefault(org_id, [])


def _find_ladder(org_id: str, ladder_id: str) -> Optional[Ladder]:
    ladders, _ = _ensure(org_id)
    for l in ladders:
        if l.id == ladder_id:
            return l
    return None


def _find_plan(org_id: str, plan_id: str) -> Optional[GrowthPlan]:
    _, plans = _ensure(org_id)
    for p in plans:
        if p.id == plan_id:
            return p
    return None


# ---------------------------------------------------------------------------
# Ladder CRUD
# ---------------------------------------------------------------------------
def list_ladders(org_id: str) -> dict:
    ladders, _ = _ensure(org_id)
    return {"items": [l.to_dict() for l in ladders], "total": len(ladders)}


def get_ladder(org_id: str, ladder_id: str) -> Optional[dict]:
    l = _find_ladder(org_id, ladder_id)
    return l.to_dict() if l else None


def create_ladder(org_id: str, payload: dict) -> Optional[dict]:
    family = (payload.get("family") or "").strip()
    if not family:
        return None
    l = Ladder(id=str(uuid.uuid4()), family=family)
    with _lock:
        ladders, _ = _ensure(org_id)
        ladders.insert(0, l)
    return l.to_dict()


def add_level(org_id: str, ladder_id: str, payload: dict) -> Optional[dict]:
    l = _find_ladder(org_id, ladder_id)
    if not l:
        return None
    name = (payload.get("name") or "").strip()
    if not name:
        return None
    idx = payload.get("index")
    if idx is None:
        idx = (max((lv.index for lv in l.levels), default=0) + 1)
    lv = Level(id=str(uuid.uuid4()), name=name, title=str(payload.get("title") or name), index=int(idx))
    with _lock:
        l.levels.append(lv)
    return lv.to_dict()


def add_competency(org_id: str, ladder_id: str, payload: dict) -> Optional[dict]:
    l = _find_ladder(org_id, ladder_id)
    if not l:
        return None
    name = (payload.get("name") or "").strip()
    if not name:
        return None
    c = Competency(id=str(uuid.uuid4()), name=name,
                   category=str(payload.get("category") or "general"),
                   description=str(payload.get("description") or ""))
    with _lock:
        l.competencies.append(c)
    return c.to_dict()


def set_expectation(org_id: str, ladder_id: str, payload: dict) -> Optional[dict]:
    """Create or update the expectation for a (competency, level) pair."""
    l = _find_ladder(org_id, ladder_id)
    if not l:
        return None
    cid = (payload.get("competency_id") or "").strip()
    lid = (payload.get("level_id") or "").strip()
    if not cid or not lid:
        return None
    if cid not in {c.id for c in l.competencies} or lid not in {lv.id for lv in l.levels}:
        return None
    rubric = str(payload.get("rubric") or "")
    bar = int(payload.get("expected_rating") or 3)
    bar = max(1, min(5, bar))
    with _lock:
        for e in l.expectations:
            if e.competency_id == cid and e.level_id == lid:
                e.rubric = rubric
                e.expected_rating = bar
                return e.to_dict()
        e = Expectation(id=str(uuid.uuid4()), competency_id=cid, level_id=lid,
                        rubric=rubric, expected_rating=bar)
        l.expectations.append(e)
    return e.to_dict()


# ---------------------------------------------------------------------------
# Growth plan CRUD
# ---------------------------------------------------------------------------
def list_plans(org_id: str, employee_id: Optional[str] = None) -> dict:
    _, plans = _ensure(org_id)
    rows = [p for p in plans if (not employee_id or p.employee_id == employee_id)]
    return {"items": [p.to_dict() for p in rows], "total": len(rows)}


def get_plan(org_id: str, plan_id: str) -> Optional[dict]:
    p = _find_plan(org_id, plan_id)
    return p.to_dict() if p else None


def create_plan(org_id: str, payload: dict) -> Optional[dict]:
    employee_id = (payload.get("employee_id") or "").strip()
    ladder_id = (payload.get("ladder_id") or "").strip()
    if not employee_id or not ladder_id:
        return None
    if not _find_ladder(org_id, ladder_id):
        return None
    p = GrowthPlan(
        id=str(uuid.uuid4()),
        employee_id=employee_id,
        ladder_id=ladder_id,
        current_level_id=(payload.get("current_level_id") or None),
        target_level_id=(payload.get("target_level_id") or None),
        status=str(payload.get("status") or "draft"),
    )
    with _lock:
        _, plans = _ensure(org_id)
        plans.insert(0, p)
    return p.to_dict()


def update_plan(org_id: str, plan_id: str, payload: dict) -> Optional[dict]:
    p = _find_plan(org_id, plan_id)
    if not p:
        return None
    with _lock:
        if "current_level_id" in payload:
            p.current_level_id = payload["current_level_id"] or None
        if "target_level_id" in payload:
            p.target_level_id = payload["target_level_id"] or None
        if "status" in payload and payload["status"] in PLAN_STATUSES:
            p.status = payload["status"]
        if "growth_goals" in payload and isinstance(payload["growth_goals"], list):
            p.growth_goals = payload["growth_goals"]
    return p.to_dict()


def set_rating(org_id: str, plan_id: str, payload: dict) -> Optional[dict]:
    p = _find_plan(org_id, plan_id)
    if not p:
        return None
    cid = (payload.get("competency_id") or "").strip()
    if not cid:
        return None
    with _lock:
        cur = p.ratings.get(cid, {"self": None, "manager": None})
        if "self" in payload and payload["self"] is not None:
            cur["self"] = max(1, min(5, int(payload["self"])))
        if "manager" in payload and payload["manager"] is not None:
            cur["manager"] = max(1, min(5, int(payload["manager"])))
        p.ratings[cid] = cur
    return p.to_dict()


def add_growth_goal(org_id: str, plan_id: str, payload: dict) -> Optional[dict]:
    p = _find_plan(org_id, plan_id)
    if not p:
        return None
    text = (payload.get("text") or "").strip()
    if not text:
        return None
    with _lock:
        p.growth_goals.append({"text": text, "goal_id": payload.get("goal_id")})
    return p.to_dict()


def link_plan(org_id: str, plan_id: str, payload: dict) -> Optional[dict]:
    """Tie a growth plan to the review and/or goal it supports."""
    p = _find_plan(org_id, plan_id)
    if not p:
        return None
    with _lock:
        if "review_id" in payload:
            p.linked_review_id = payload["review_id"] or None
        if "goal_id" in payload:
            p.linked_goal_id = payload["goal_id"] or None
    return p.to_dict()


# ---------------------------------------------------------------------------
# Gap view
# ---------------------------------------------------------------------------
def _current_rating(ratings: dict, competency_id: str) -> int:
    r = ratings.get(competency_id) or {}
    if r.get("manager") is not None:
        return int(r["manager"])
    if r.get("self") is not None:
        return int(r["self"])
    return 0


def gap_view(org_id: str, plan_id: str) -> Optional[dict]:
    p = _find_plan(org_id, plan_id)
    if not p:
        return None
    l = _find_ladder(org_id, p.ladder_id)
    if not l:
        return None

    target_level_id = p.target_level_id
    exp_by_comp: dict[str, Expectation] = {}
    for e in l.expectations:
        if e.level_id == target_level_id:
            exp_by_comp[e.competency_id] = e

    rows = []
    for c in l.competencies:
        exp = exp_by_comp.get(c.id)
        expected = exp.expected_rating if exp else None
        current = _current_rating(p.ratings, c.id)
        gap = (expected - current) if expected is not None else None
        below = bool(expected is not None and current < expected)
        rows.append({
            "competency_id": c.id,
            "competency": c.name,
            "category": c.category,
            "target_expected_rating": expected,
            "current_rating": current,
            "gap": gap,
            "below_bar": below,
            "rubric": exp.rubric if exp else None,
        })

    below_bar = sorted([r for r in rows if r["below_bar"]], key=lambda r: -(r["gap"] or 0))
    return {
        "plan_id": p.id,
        "employee_id": p.employee_id,
        "ladder_id": l.id,
        "current_level_id": p.current_level_id,
        "target_level_id": p.target_level_id,
        "linked_review_id": p.linked_review_id,
        "linked_goal_id": p.linked_goal_id,
        "competencies": rows,
        "below_bar": below_bar,
        "below_bar_count": len(below_bar),
    }


# ---------------------------------------------------------------------------
# AI assist — development actions for the biggest gaps (fail-soft)
# ---------------------------------------------------------------------------
def _llm(prompt: str, system: str) -> Optional[str]:
    if llm_complete is None:
        return None
    try:
        return llm_complete(prompt, system=system)
    except (LLMError, Exception):
        return None


def suggest_actions(org_id: str, plan_id: str) -> Optional[dict]:
    gap = gap_view(org_id, plan_id)
    if gap is None:
        return None
    gaps = gap["below_bar"]

    llm_out = _llm(
        prompt=(
            "For each competency gap below, suggest one concrete development action "
            f"(project, mentorship, or training). Gaps: {[(g['competency'], g['gap']) for g in gaps]}"
        ),
        system="You are a supportive career coach. Be concrete and encouraging.",
    )
    if llm_out:
        return {"actions": [ln.strip("-• ").strip() for ln in llm_out.splitlines() if ln.strip()][:8],
                "source": "ai", "gaps": gaps}

    # Deterministic fallback — one action per below-bar competency, biggest first.
    actions = []
    for g in gaps:
        actions.append(
            f"Close the {g['competency']} gap (now {g['current_rating']}/5, target "
            f"{g['target_expected_rating']}/5): take on a stretch project and pair with a mentor "
            f"who is strong in {g['category']}."
        )
    if not actions:
        actions = ["No competency is below the target bar — focus on depth and mentoring others."]
    return {"actions": actions, "source": "fallback", "gaps": gaps}
