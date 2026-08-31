"""Explainable interview scoring + Human-in-the-Loop (HITL) recourse.

NET-NEW P0 differentiator — attacks the #1 AI-hiring complaint: black-box
scores with no recourse. Two capabilities, built on top of the existing
`interview_scorecard_service` (no rebuild):

  1. EXPLAINABLE BREAKDOWN — for each interview score, a per-rubric-dimension
     score + the evidence/quotes that drove it + a per-dimension confidence.
     The overall composite is an *explicit weighted sum* of the dimension
     scores (weights sum to 1.0), so the breakdown always reconciles with the
     headline number.

  2. HITL RECOURSE — a candidate or recruiter can flag a score for human
     review; a reviewer can adjust it with a written reason. Every AI score is
     marked "AI-assisted, human-reviewable" and carries an audit trail of who
     opened / adjusted it and why.

COMPLIANCE MAPPING
------------------
  * NYC Local Law 144      — automated employment decision tools require a bias
                             audit + candidate notice; an explainable,
                             evidence-cited breakdown supports both.
  * Colorado AI Act (SB 24-205) — high-risk AI must give consumers an
                             explanation and an opportunity to correct data /
                             appeal — that is exactly the recourse flow here.
  * EU AI Act (Annex III)  — hiring is "high-risk"; requires human oversight,
                             transparency and record-keeping. The audit trail +
                             human adjustment satisfy the oversight + logging
                             obligations.

Deterministic and fail-soft: no submitted scorecards → a zero-confidence
explanation with a reason, never an exception.
"""
from __future__ import annotations

import statistics
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.services.interview_scorecard_service import RATING_SCALE, list_scorecards


AI_DISCLOSURE = "AI-assisted, human-reviewable"

COMPLIANCE_TAGS = [
    {"framework": "NYC Local Law 144", "obligation": "AEDT bias audit + candidate notice",
     "satisfied_by": "evidence-cited rubric breakdown + AI disclosure"},
    {"framework": "Colorado AI Act (SB 24-205)", "obligation": "explanation + right to correct/appeal",
     "satisfied_by": "score explanation + HITL review/adjust recourse"},
    {"framework": "EU AI Act (Annex III high-risk employment)",
     "obligation": "human oversight + transparency + record-keeping",
     "satisfied_by": "reviewer adjustment + full audit trail"},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Explainable breakdown (pure w.r.t. the scorecard store)
# ---------------------------------------------------------------------------
def _dimension_confidence(ratings: list[int], evidence_count: int, rater_count: int,
                          avg_interviewer_conf: Optional[float]) -> float:
    """Deterministic per-dimension confidence in [0,1]:
       0.4·evidence_ratio + 0.4·panel_agreement + 0.2·avg_interviewer_confidence."""
    if rater_count == 0:
        return 0.0
    evidence_ratio = min(1.0, evidence_count / rater_count)
    spread = (max(ratings) - min(ratings)) if len(ratings) > 1 else 0
    agreement = 1.0 - (spread / 4.0)  # rating scale is 0..4
    conf_component = ((avg_interviewer_conf or 0.0) / 5.0) if avg_interviewer_conf else 0.0
    return round(max(0.0, min(1.0, 0.4 * evidence_ratio + 0.4 * agreement + 0.2 * conf_component)), 4)


def build_explanation(org_id: str, interview_id: str,
                      weights: Optional[dict[str, float]] = None) -> dict:
    """Build the explainable rubric breakdown from submitted scorecards."""
    scorecards = list_scorecards(interview_id)
    submitted = [s for s in scorecards if s.status == "submitted"]

    # gather per-competency ratings + evidence across the panel
    dim_data: dict[str, dict] = {}
    for s in submitted:
        for c in s.competencies:
            if c.final_rating is None:
                continue
            d = dim_data.setdefault(c.competency, {"ratings": [], "evidence": [], "raters_with_evidence": 0})
            d["ratings"].append(int(c.final_rating))
            if c.evidence_snippets:
                d["raters_with_evidence"] += 1
                for snip in c.evidence_snippets:
                    d["evidence"].append({"interviewer": s.interviewer_name, "quote": snip})

    rater_count = len(submitted)
    avg_conf = statistics.mean([s.interviewer_confidence for s in submitted if s.interviewer_confidence]) \
        if any(s.interviewer_confidence for s in submitted) else None

    dims = sorted(dim_data.keys())
    if not dims:
        return {
            "interview_id": interview_id,
            "available": False,
            "reason": "No submitted scorecards with rated competencies yet.",
            "ai_disclosure": AI_DISCLOSURE,
            "human_reviewable": True,
            "rubric": [],
            "overall_score": 0.0,
            "overall_confidence": 0.0,
            "compliance": COMPLIANCE_TAGS,
            "reviews": [r.to_dict() for r in list_reviews(org_id, interview_id)],
        }

    # weights: caller-provided (normalised) or equal across dimensions
    if weights:
        w = {d: max(0.0, float(weights.get(d, 0.0))) for d in dims}
        tot = sum(w.values()) or 1.0
        w = {d: w[d] / tot for d in dims}
    else:
        w = {d: 1.0 / len(dims) for d in dims}

    rubric: list[dict] = []
    composite = 0.0
    for d in dims:
        data = dim_data[d]
        ratings = data["ratings"]
        dim_score = round(statistics.mean(ratings), 4)  # 0..4 scale
        conf = _dimension_confidence(ratings, data["raters_with_evidence"], rater_count, avg_conf)
        weight = round(w[d], 4)
        contribution = round(weight * dim_score, 4)
        composite += weight * dim_score
        rubric.append({
            "dimension": d,
            "score": dim_score,
            "rating_label": RATING_SCALE.get(round(dim_score), "mixed"),
            "weight": weight,
            "weighted_contribution": contribution,
            "n_ratings": len(ratings),
            "rating_spread": (max(ratings) - min(ratings)) if len(ratings) > 1 else 0,
            "confidence": conf,
            "evidence": data["evidence"],
            "evidence_gap": len(data["evidence"]) == 0,
        })

    overall_conf = round(statistics.mean([r["confidence"] for r in rubric]), 4)
    return {
        "interview_id": interview_id,
        "available": True,
        "ai_disclosure": AI_DISCLOSURE,
        "human_reviewable": True,
        "panel_size": rater_count,
        "weights_sum": round(sum(r["weight"] for r in rubric), 4),
        "rubric": rubric,
        "overall_score": round(composite, 4),          # equals Σ weight·dimension_score
        "overall_score_max": 4.0,
        "overall_confidence": overall_conf,
        "compliance": COMPLIANCE_TAGS,
        "reviews": [r.to_dict() for r in list_reviews(org_id, interview_id)],
        "note": (
            "Overall score is the explicit weighted sum of the rubric dimensions "
            "(weights sum to 1.0). Every dimension cites the evidence that drove "
            "it. This score is AI-assisted and can be sent for human review."
        ),
    }


# ---------------------------------------------------------------------------
# HITL recourse store
# ---------------------------------------------------------------------------
@dataclass
class ScoreReview:
    id: str
    interview_id: str
    dimension: str                       # a competency name or "overall"
    status: str                          # open | resolved
    requested_by: str
    requested_by_role: str               # candidate | recruiter | manager | hr
    reason: str
    original_rating: Optional[float]
    scorecard_id: Optional[str] = None
    adjusted_rating: Optional[float] = None
    reviewer: Optional[str] = None
    review_reason: Optional[str] = None
    opened_at: str = field(default_factory=_now)
    resolved_at: Optional[str] = None
    audit_trail: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {**self.__dict__, "ai_disclosure": AI_DISCLOSURE}


_lock = threading.RLock()
_reviews: dict[str, dict[str, list[ScoreReview]]] = {}  # org_id → interview_id → [reviews]


def _bucket(org_id: str, interview_id: str) -> list[ScoreReview]:
    return _reviews.setdefault(org_id, {}).setdefault(interview_id, [])


def open_review(
    org_id: str, interview_id: str, *,
    dimension: str,
    reason: str,
    requested_by: str,
    requested_by_role: str,
    original_rating: Optional[float] = None,
    scorecard_id: Optional[str] = None,
) -> dict:
    rv = ScoreReview(
        id=str(uuid.uuid4()),
        interview_id=interview_id,
        dimension=dimension or "overall",
        status="open",
        requested_by=requested_by,
        requested_by_role=requested_by_role,
        reason=reason,
        original_rating=original_rating,
        scorecard_id=scorecard_id,
    )
    rv.audit_trail.append({
        "ts": _now(), "action": "review_opened", "actor": requested_by,
        "actor_role": requested_by_role, "detail": reason,
        "dimension": rv.dimension, "original_rating": original_rating,
    })
    with _lock:
        _bucket(org_id, interview_id).append(rv)
    return rv.to_dict()


def adjust_review(
    org_id: str, interview_id: str, review_id: str, *,
    reviewer: str,
    adjusted_rating: Optional[float],
    reason: str,
) -> Optional[dict]:
    with _lock:
        for rv in _bucket(org_id, interview_id):
            if rv.id != review_id:
                continue
            rv.adjusted_rating = adjusted_rating
            rv.reviewer = reviewer
            rv.review_reason = reason
            rv.status = "resolved"
            rv.resolved_at = _now()
            rv.audit_trail.append({
                "ts": rv.resolved_at, "action": "score_adjusted", "actor": reviewer,
                "actor_role": "reviewer", "detail": reason,
                "dimension": rv.dimension,
                "from_rating": rv.original_rating, "to_rating": adjusted_rating,
            })
            return rv.to_dict()
    return None


def list_reviews(org_id: str, interview_id: str) -> list[ScoreReview]:
    with _lock:
        return list(_reviews.get(org_id, {}).get(interview_id, []))
