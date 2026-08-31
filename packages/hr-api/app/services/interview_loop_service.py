"""Interview Loop Orchestration — panel scheduling + multi-interviewer scorecards.

The AI Interview gives you one calibrated voice. A real hire decision needs a
*panel*: 3-5 humans each scoring the candidate on a distinct competency, then
a debrief that rolls up into one composite recommendation.

This service models:
  - Interview *Loops* (e.g. "Sr Python Engineer · panel of 5")
  - Stages within a loop (recruiter screen → tech screen → onsite → final)
  - Slots (interviewer × stage × time)
  - Scorecards per slot (rating + signal + rec)
  - Cross-interviewer calibration (variance flags, dissent detection)

Stays in-process for the demo. Schema is laid out for a clean Postgres
swap-in: one table per dataclass.
"""
from __future__ import annotations

import statistics
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
DEFAULT_STAGES = [
    ("recruiter_screen", "Recruiter screen",  30),
    ("tech_screen",      "Technical screen",  60),
    ("onsite_1",         "Onsite · system design", 60),
    ("onsite_2",         "Onsite · coding",  60),
    ("onsite_3",         "Onsite · values + collaboration", 45),
    ("final_round",      "Final round (hiring manager)", 45),
]

RATING_SCALE = {
    4: "strong_hire",
    3: "hire",
    2: "lean_hire",
    1: "lean_no_hire",
    0: "no_hire",
}


@dataclass
class InterviewSlot:
    id: str
    stage_key: str
    stage_label: str
    interviewer_id: str
    interviewer_name: str
    interviewer_role: str = ""
    focus_competency: str = ""
    scheduled_at: Optional[str] = None
    duration_min: int = 60
    completed_at: Optional[str] = None
    rating: Optional[int] = None             # 0-4 per RATING_SCALE
    signals: dict[str, int] = field(default_factory=dict)  # competency -> 0-100
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {**self.__dict__, "rating_label": RATING_SCALE.get(self.rating or -1, "pending")}


@dataclass
class InterviewLoop:
    id: str
    org_id: str
    candidate_name: str
    candidate_id: Optional[str]
    job_title: str
    job_id: Optional[str]
    hiring_manager: str
    coordinator: str = ""
    slots: list[InterviewSlot] = field(default_factory=list)
    status: str = "draft"  # draft | scheduled | in_progress | debrief | decided
    decision: Optional[str] = None  # advance | advance_with_caveats | hold | decline
    debrief_notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            **self.__dict__,
            "slots": [s.to_dict() for s in self.slots],
        }


# ---------------------------------------------------------------------------
# In-process store
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_loops: dict[str, dict[str, InterviewLoop]] = {}  # org_id -> loop_id -> loop


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def create_loop(
    *,
    org_id: str,
    candidate_name: str,
    candidate_id: Optional[str],
    job_title: str,
    job_id: Optional[str],
    hiring_manager: str,
    panel: list[dict],
    stages: Optional[list[str]] = None,
) -> InterviewLoop:
    """Build a new interview loop with a per-panel default scaffold.

    panel: list of {interviewer_id, interviewer_name, interviewer_role,
                    focus_competency, stage_key}
    """
    loop = InterviewLoop(
        id=str(uuid.uuid4()),
        org_id=org_id,
        candidate_name=candidate_name,
        candidate_id=candidate_id,
        job_title=job_title,
        job_id=job_id,
        hiring_manager=hiring_manager,
    )
    stage_lookup = {k: (lbl, dur) for k, lbl, dur in DEFAULT_STAGES}
    for p in panel:
        stage_key = p.get("stage_key", "tech_screen")
        lbl, dur = stage_lookup.get(stage_key, ("Custom stage", 60))
        loop.slots.append(InterviewSlot(
            id=str(uuid.uuid4()),
            stage_key=stage_key,
            stage_label=lbl,
            interviewer_id=str(p.get("interviewer_id") or ""),
            interviewer_name=str(p.get("interviewer_name") or ""),
            interviewer_role=str(p.get("interviewer_role") or ""),
            focus_competency=str(p.get("focus_competency") or ""),
            duration_min=int(p.get("duration_min") or dur),
        ))
    if loop.slots:
        loop.status = "scheduled"
    with _lock:
        _loops.setdefault(org_id, {})[loop.id] = loop
    return loop


def list_loops(org_id: str) -> list[InterviewLoop]:
    with _lock:
        items = list(_loops.get(org_id, {}).values())
    items.sort(key=lambda l: l.created_at, reverse=True)
    return items


def get_loop(org_id: str, loop_id: str) -> Optional[InterviewLoop]:
    with _lock:
        return _loops.get(org_id, {}).get(loop_id)


def submit_scorecard(
    org_id: str,
    loop_id: str,
    slot_id: str,
    *,
    rating: int,
    signals: dict[str, int],
    strengths: list[str],
    concerns: list[str],
    notes: str,
) -> Optional[InterviewSlot]:
    with _lock:
        loop = _loops.get(org_id, {}).get(loop_id)
        if not loop:
            return None
        slot = next((s for s in loop.slots if s.id == slot_id), None)
        if not slot:
            return None
        slot.rating = max(0, min(4, int(rating)))
        slot.signals = {k: max(0, min(100, int(v))) for k, v in (signals or {}).items()}
        slot.strengths = strengths or []
        slot.concerns = concerns or []
        slot.notes = notes or ""
        slot.completed_at = datetime.now(timezone.utc).isoformat()
        # Update loop status
        completed = [s for s in loop.slots if s.completed_at]
        if len(completed) == len(loop.slots):
            loop.status = "debrief"
        else:
            loop.status = "in_progress"
        return slot


def schedule_slot(
    org_id: str,
    loop_id: str,
    slot_id: str,
    scheduled_at_iso: str,
) -> Optional[InterviewSlot]:
    with _lock:
        loop = _loops.get(org_id, {}).get(loop_id)
        if not loop:
            return None
        slot = next((s for s in loop.slots if s.id == slot_id), None)
        if not slot:
            return None
        slot.scheduled_at = scheduled_at_iso
        return slot


def decide(
    org_id: str,
    loop_id: str,
    *,
    decision: str,
    debrief_notes: str = "",
) -> Optional[InterviewLoop]:
    with _lock:
        loop = _loops.get(org_id, {}).get(loop_id)
        if not loop:
            return None
        loop.decision = decision
        loop.debrief_notes = debrief_notes
        loop.status = "decided"
        return loop


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------
def calibrate(loop: InterviewLoop) -> dict:
    """Roll up panel scorecards into a calibrated debrief."""
    completed = [s for s in loop.slots if s.rating is not None]
    if not completed:
        return {
            "n_scorecards": 0,
            "panel_size": len(loop.slots),
            "composite": 0,
            "recommendation": "pending",
            "variance_flags": [],
            "consensus_strengths": [],
            "consensus_concerns": [],
            "dissenters": [],
        }
    ratings = [s.rating for s in completed if s.rating is not None]
    avg = round(sum(ratings) / len(ratings), 2)
    # Map 0-4 → composite 0-100
    composite = int(round((avg / 4.0) * 100))

    # Recommendation chain
    if avg >= 3.0:
        rec = "advance"
    elif avg >= 2.5:
        rec = "advance"
    elif avg >= 2.0:
        rec = "advance_with_caveats"
    elif avg >= 1.0:
        rec = "hold"
    else:
        rec = "decline"

    # Variance / dissent — flag if any rating is ≥ 2 away from the median
    median = statistics.median(ratings) if ratings else 0
    dissenters = []
    for s in completed:
        if s.rating is not None and abs(s.rating - median) >= 2:
            dissenters.append({
                "interviewer_name": s.interviewer_name,
                "rating": s.rating,
                "rating_label": RATING_SCALE.get(s.rating, ""),
                "delta_from_median": s.rating - median,
                "concerns": s.concerns,
            })

    variance_flags: list[str] = []
    if max(ratings) - min(ratings) >= 3:
        variance_flags.append(
            f"Panel disagrees strongly — ratings span {min(ratings)}–{max(ratings)}. Schedule a longer debrief."
        )
    if dissenters:
        names = ", ".join(d["interviewer_name"] for d in dissenters)
        variance_flags.append(
            f"Dissenting voice: {names}. Investigate the specific concern before deciding."
        )

    # Consensus strengths / concerns — phrases that show up in ≥ ⌈n/2⌉ scorecards
    threshold = max(2, len(completed) // 2 + 1)
    strength_counts: dict[str, int] = {}
    concern_counts: dict[str, int] = {}
    for s in completed:
        for x in s.strengths:
            strength_counts[x] = strength_counts.get(x, 0) + 1
        for x in s.concerns:
            concern_counts[x] = concern_counts.get(x, 0) + 1

    consensus_strengths = sorted(
        [s for s, c in strength_counts.items() if c >= threshold],
        key=lambda s: -strength_counts[s],
    )[:5]
    consensus_concerns = sorted(
        [s for s, c in concern_counts.items() if c >= threshold],
        key=lambda s: -concern_counts[s],
    )[:5]

    return {
        "n_scorecards": len(completed),
        "panel_size": len(loop.slots),
        "average_rating": avg,
        "median_rating": median,
        "composite": composite,
        "recommendation": rec,
        "variance_flags": variance_flags,
        "consensus_strengths": consensus_strengths,
        "consensus_concerns": consensus_concerns,
        "dissenters": dissenters,
    }
