"""Wellness / engagement pulse.

Recurring micro-survey + sentiment trend. Submissions are anonymous; we only
store aggregate score per question per pulse cycle.

The store is in-process and seeded with 6 cycles of data so the page has a
real trend out of the box.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class PulseQuestion:
    id: str
    prompt: str
    scale_label: str = "1 = strongly disagree · 5 = strongly agree"
    helper: str = ""


@dataclass
class PulseSubmission:
    id: str
    cycle_id: str
    answers: dict[str, int]    # question_id -> 1..5
    comment: str = ""
    submitted_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class PulseCycle:
    id: str
    label: str                 # "Week of Apr 7"
    opened_at: str
    closed_at: Optional[str] = None
    n_submissions: int = 0
    averages: dict[str, float] = field(default_factory=dict)
    sentiment_score: float = 0.0  # 0..1 (engagement)


QUESTIONS: list[PulseQuestion] = [
    PulseQuestion(id="q1", prompt="I'm clear on what's expected of me this week.", helper="Calm > vague."),
    PulseQuestion(id="q2", prompt="I have the resources and information I need.", helper="Tools, docs, access."),
    PulseQuestion(id="q3", prompt="I felt recognised in the last 7 days."),
    PulseQuestion(id="q4", prompt="My workload feels sustainable.", helper="Honest answer is the helpful answer."),
    PulseQuestion(id="q5", prompt="My manager is open to my ideas + feedback."),
]


_lock = threading.RLock()
_cycles: dict[str, list[PulseCycle]] = {}
_open_cycle: dict[str, str] = {}
_submissions: dict[str, list[PulseSubmission]] = {}
_seeded: set[str] = set()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _seed(org_id: str) -> None:
    """Seed 6 historical weekly cycles + 1 open cycle."""
    now = datetime.now(timezone.utc)
    history: list[PulseCycle] = []
    # weeks 6..1 ago, all closed
    seeds = [
        # (week label, averages by question_id, sentiment)
        ("Apr 7", {"q1": 4.2, "q2": 4.0, "q3": 3.6, "q4": 3.8, "q5": 4.4}, 0.79),
        ("Apr 14", {"q1": 4.3, "q2": 4.1, "q3": 3.8, "q4": 3.9, "q5": 4.5}, 0.81),
        ("Apr 21", {"q1": 4.1, "q2": 4.0, "q3": 3.4, "q4": 3.5, "q5": 4.3}, 0.74),
        ("Apr 28", {"q1": 4.0, "q2": 3.9, "q3": 3.3, "q4": 3.4, "q5": 4.2}, 0.71),
        ("May 5",  {"q1": 4.2, "q2": 4.0, "q3": 3.5, "q4": 3.5, "q5": 4.3}, 0.74),
        ("May 12", {"q1": 4.4, "q2": 4.2, "q3": 3.7, "q4": 3.6, "q5": 4.4}, 0.77),
    ]
    for i, (label, averages, sentiment) in enumerate(seeds):
        opened = now - timedelta(days=(7 * (len(seeds) - i)) + 1)
        closed = opened + timedelta(days=5)
        history.append(PulseCycle(
            id=f"pulse-{uuid.uuid4().hex[:8]}",
            label=f"Week of {label}",
            opened_at=_iso(opened),
            closed_at=_iso(closed),
            n_submissions=18 + i,
            averages=averages,
            sentiment_score=sentiment,
        ))

    # Open cycle (this week)
    open_cycle = PulseCycle(
        id=f"pulse-{uuid.uuid4().hex[:8]}",
        label=f"Week of {(now - timedelta(days=now.weekday())).strftime('%b %-d')}",
        opened_at=_iso(now - timedelta(days=now.weekday())),
    )

    _cycles[org_id] = history + [open_cycle]
    _open_cycle[org_id] = open_cycle.id
    _submissions[org_id] = []


def _ensure(org_id: str) -> None:
    with _lock:
        if org_id not in _seeded:
            _seed(org_id)
            _seeded.add(org_id)


def _open(org_id: str) -> PulseCycle:
    _ensure(org_id)
    cycles = _cycles[org_id]
    open_id = _open_cycle[org_id]
    for c in cycles:
        if c.id == open_id:
            return c
    return cycles[-1]


def overview(org_id: str) -> dict:
    _ensure(org_id)
    cycles = _cycles[org_id]
    open_cycle = _open(org_id)
    history = [c for c in cycles if c.id != open_cycle.id]

    # Live aggregate for the open cycle from any submissions
    subs = [s for s in _submissions.get(org_id, []) if s.cycle_id == open_cycle.id]
    if subs:
        averages: dict[str, float] = {}
        for q in QUESTIONS:
            vals = [s.answers.get(q.id) for s in subs if s.answers.get(q.id) is not None]
            averages[q.id] = round(sum(vals) / len(vals), 2) if vals else 0.0
        open_cycle.n_submissions = len(subs)
        open_cycle.averages = averages
        open_cycle.sentiment_score = round(sum(averages.values()) / (len(averages) or 1) / 5.0, 2)

    # Latest closed cycle vs. previous for delta
    latest_closed = history[-1] if history else None
    prev_closed = history[-2] if len(history) >= 2 else None
    delta = 0.0
    if latest_closed and prev_closed:
        delta = round(latest_closed.sentiment_score - prev_closed.sentiment_score, 3)

    # Trend series for sparkline
    series = [round(c.sentiment_score * 100) for c in history]
    labels = [c.label.replace("Week of ", "") for c in history]

    return {
        "questions": [asdict(q) for q in QUESTIONS],
        "open_cycle": asdict(open_cycle),
        "history": [asdict(c) for c in history],
        "summary": {
            "current_sentiment_pct": round((latest_closed.sentiment_score if latest_closed else 0) * 100),
            "delta": delta,
            "trend": {"series": series, "labels": labels, "suffix": "%"},
            "total_submissions": sum(c.n_submissions for c in history) + open_cycle.n_submissions,
        },
    }


def submit(org_id: str, payload: dict) -> dict:
    _ensure(org_id)
    open_cycle = _open(org_id)
    raw_answers = payload.get("answers") or {}
    clean: dict[str, int] = {}
    for qid, val in raw_answers.items():
        try:
            v = int(val)
            if 1 <= v <= 5:
                clean[qid] = v
        except Exception:
            continue
    if not clean:
        return {"ok": False, "detail": "answers required"}
    sub = PulseSubmission(
        id=str(uuid.uuid4()),
        cycle_id=open_cycle.id,
        answers=clean,
        comment=str(payload.get("comment") or "").strip(),
    )
    with _lock:
        _submissions.setdefault(org_id, []).append(sub)
    return {"ok": True, "cycle_id": open_cycle.id, "submission_id": sub.id}
