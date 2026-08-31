"""Interview Scorecard service — structured rating, evidence chips, calibration support.

Each scorecard is a per-interviewer × per-interview rating across:
  - competencies (required + nice-to-have)
  - values / team fit
  - role-specific signals

The service supports:
  - upsert + retrieve
  - AI-drafted rating that cites transcript evidence
  - calibration view that compares ratings across interviewers and flags
    raters who diverged from the panel median
  - evidence-gap detection (rating with no transcript citation)

Stays in-process for the demo.
"""
from __future__ import annotations

import re
import statistics
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.services.interview_fairness_service import check_scorecard_note
from app.services.interview_transcription_service import full_transcript

try:
    from app.services.llm import llm_complete  # type: ignore
except Exception:
    llm_complete = None  # type: ignore


RATING_SCALE = {0: "no_hire", 1: "lean_no_hire", 2: "lean_hire", 3: "hire", 4: "strong_hire"}


@dataclass
class CompetencyScore:
    competency: str
    rating: Optional[int] = None              # 0..4
    ai_suggested_rating: Optional[int] = None
    notes: str = ""
    evidence_snippets: list[str] = field(default_factory=list)
    final_rating: Optional[int] = None        # set on submit
    fairness_flags: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {**self.__dict__, "rating_label": RATING_SCALE.get(self.rating or -1, "pending")}


@dataclass
class Scorecard:
    id: str
    interview_id: str
    interviewer_id: str
    interviewer_name: str
    competencies: list[CompetencyScore]
    overall_rating: Optional[int] = None
    overall_recommendation: Optional[str] = None  # hire | no_hire | unsure
    interviewer_confidence: Optional[int] = None  # 1..5
    submitted_at: Optional[str] = None
    status: str = "draft"             # draft | submitted
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            **self.__dict__,
            "competencies": [c.to_dict() for c in self.competencies],
        }


# ---------------------------------------------------------------------------
# In-process store
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_scorecards: dict[str, dict[str, Scorecard]] = {}  # interview_id → id → scorecard


def _key(interviewer_id: str) -> str:
    return interviewer_id or "unknown"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def upsert_scorecard(
    *,
    interview_id: str,
    interviewer_id: str,
    interviewer_name: str,
    competencies: list[str],
) -> Scorecard:
    """Create a new scorecard with empty competency rows, or return existing."""
    with _lock:
        existing = next(
            (s for s in _scorecards.get(interview_id, {}).values() if s.interviewer_id == interviewer_id),
            None,
        )
        if existing:
            return existing
        sc = Scorecard(
            id=str(uuid.uuid4()),
            interview_id=interview_id,
            interviewer_id=interviewer_id,
            interviewer_name=interviewer_name,
            competencies=[CompetencyScore(competency=c) for c in competencies],
        )
        _scorecards.setdefault(interview_id, {})[sc.id] = sc
        return sc


def list_scorecards(interview_id: str) -> list[Scorecard]:
    with _lock:
        return list(_scorecards.get(interview_id, {}).values())


def get_scorecard(interview_id: str, scorecard_id: str) -> Optional[Scorecard]:
    with _lock:
        return _scorecards.get(interview_id, {}).get(scorecard_id)


def update_competency(
    *,
    interview_id: str,
    scorecard_id: str,
    competency: str,
    rating: Optional[int] = None,
    notes: Optional[str] = None,
    evidence_snippets: Optional[list[str]] = None,
) -> Optional[Scorecard]:
    with _lock:
        sc = _scorecards.get(interview_id, {}).get(scorecard_id)
        if not sc:
            return None
        row = next((c for c in sc.competencies if c.competency == competency), None)
        if not row:
            row = CompetencyScore(competency=competency)
            sc.competencies.append(row)
        if rating is not None:
            row.rating = max(0, min(4, int(rating)))
        if notes is not None:
            row.notes = notes
            # auto-attach fairness flags as the interviewer writes
            row.fairness_flags = [f.to_dict() for f in check_scorecard_note(notes, evidence_snippets=row.evidence_snippets)]
        if evidence_snippets is not None:
            row.evidence_snippets = list(evidence_snippets)
        return sc


def submit_scorecard(
    *,
    interview_id: str,
    scorecard_id: str,
    overall_rating: int,
    overall_recommendation: str,
    interviewer_confidence: int,
) -> Optional[Scorecard]:
    with _lock:
        sc = _scorecards.get(interview_id, {}).get(scorecard_id)
        if not sc:
            return None
        sc.overall_rating = max(0, min(4, int(overall_rating)))
        sc.overall_recommendation = overall_recommendation
        sc.interviewer_confidence = max(1, min(5, int(interviewer_confidence)))
        sc.submitted_at = datetime.now(timezone.utc).isoformat()
        sc.status = "submitted"
        for c in sc.competencies:
            c.final_rating = c.rating
        return sc


# ---------------------------------------------------------------------------
# AI: draft ratings from transcript evidence
# ---------------------------------------------------------------------------
def draft_from_transcript(
    *,
    interview_id: str,
    competencies: list[str],
    candidate_name: str = "the candidate",
) -> list[dict]:
    """Generate AI-suggested ratings per competency, citing transcript evidence."""
    transcript = full_transcript(interview_id)
    if not transcript:
        return [{
            "competency": c,
            "suggested_rating": None,
            "evidence_snippets": [],
            "note": "No transcript captured yet.",
        } for c in competencies]

    if llm_complete is not None:
        try:
            import json
            prompt = (
                f"Read this transcript of an interview with {candidate_name}.\n\n"
                f"{transcript[:6000]}\n\n"
                f"For each competency, suggest a rating 0-4 (0=no_hire, 4=strong_hire) "
                f"and cite up to 2 short transcript snippets as evidence.\n\n"
                f"Competencies: {', '.join(competencies)}\n\n"
                "Return JSON: [{\"competency\": \"...\", \"suggested_rating\": int|null, "
                "\"evidence_snippets\": [\"...\"], \"note\": \"...\"}]"
            )
            raw = llm_complete(prompt, system="You are a calibrated interview scorecard auditor.")
            cleaned = re.sub(r"^```(?:json)?", "", raw.strip()).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
            return json.loads(cleaned)
        except Exception:
            pass

    # Local heuristic fallback — keyword search per competency
    out: list[dict] = []
    transcript_lower = transcript.lower()
    lines = transcript.splitlines()
    keyword_map = {
        "communication":     ["explained", "walked through", "summarised", "described"],
        "technical_depth":   ["architecture", "system", "design", "algorithm", "trade-off"],
        "problem_solving":   ["debugged", "root cause", "investigated", "hypothesis"],
        "ownership":         ["i owned", "i led", "i drove", "end-to-end"],
        "collaboration":     ["team", "peer", "stakeholder"],
        "values_alignment":  ["values", "pushed back", "ethics"],
        "judgment":          ["weighed", "decided", "trade-off"],
        "scope":             ["million", "thousand", "headcount", "users"],
    }
    for comp in competencies:
        kws = keyword_map.get(comp, [])
        hits: list[str] = []
        for line in lines:
            if any(k in line.lower() for k in kws):
                hits.append(line.strip())
            if len(hits) >= 2:
                break
        if hits:
            suggested = 3 if len(hits) >= 2 else 2
            note = f"Evidence present in {len(hits)} line(s)."
        else:
            suggested = None
            note = f"No transcript evidence found for {comp.replace('_', ' ')}."
        out.append({
            "competency": comp,
            "suggested_rating": suggested,
            "evidence_snippets": hits,
            "note": note,
        })
    return out


# ---------------------------------------------------------------------------
# Panel calibration view
# ---------------------------------------------------------------------------
def calibration_view(interview_id: str) -> dict:
    """Across-panel calibration: rating spread, dissenters, evidence-gap counts."""
    scs = list_scorecards(interview_id)
    submitted = [s for s in scs if s.status == "submitted"]
    if not submitted:
        return {
            "n_scorecards": 0,
            "panel_size": len(scs),
            "by_competency": {},
            "dissenters": [],
            "evidence_gap_count": 0,
        }

    # Per-competency stats
    by_comp: dict[str, dict] = {}
    for s in submitted:
        for c in s.competencies:
            if c.final_rating is None:
                continue
            entry = by_comp.setdefault(c.competency, {"ratings": [], "evidence_gaps": 0})
            entry["ratings"].append(c.final_rating)
            if not c.evidence_snippets:
                entry["evidence_gaps"] += 1
    for comp, entry in by_comp.items():
        ratings = entry["ratings"]
        entry["avg"] = round(sum(ratings) / len(ratings), 2)
        entry["median"] = statistics.median(ratings)
        entry["spread"] = max(ratings) - min(ratings)

    # Overall-rating dissenters
    overall_ratings = [s.overall_rating for s in submitted if s.overall_rating is not None]
    median_overall = statistics.median(overall_ratings) if overall_ratings else 0
    dissenters: list[dict] = []
    for s in submitted:
        if s.overall_rating is not None and abs(s.overall_rating - median_overall) >= 2:
            dissenters.append({
                "interviewer_name": s.interviewer_name,
                "overall_rating": s.overall_rating,
                "rating_label": RATING_SCALE.get(s.overall_rating, ""),
                "delta_from_median": s.overall_rating - median_overall,
            })

    evidence_gap_count = sum(
        1 for s in submitted for c in s.competencies if c.final_rating is not None and not c.evidence_snippets
    )

    return {
        "n_scorecards": len(submitted),
        "panel_size": len(scs),
        "by_competency": by_comp,
        "dissenters": dissenters,
        "median_overall_rating": median_overall,
        "evidence_gap_count": evidence_gap_count,
    }
