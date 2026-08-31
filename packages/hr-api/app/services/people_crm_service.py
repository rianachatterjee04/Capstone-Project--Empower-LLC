"""People CRM — Salesforce-style records for talent relationships.

Tracks every person Foundry wants to keep a long-term relationship with:
  - Candidates  (active recruiting funnel)
  - Alumni      (formerly employed)
  - Referrals   (introduced by employees)
  - Boomerangs  (alumni we want to re-hire)
  - Succession  (internal candidates in a known pipeline)

Each record carries pipeline, status, last touch, AI signals, and a notes
log. In-memory for the demo, with rich seed data so the page is alive on
day one. The schema mirrors what a Postgres table would look like.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional


# ---------------------------------------------------------------------------
@dataclass
class CRMNote:
    id: str
    contact_id: str
    body: str
    author: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CRMContact:
    id: str
    org_id: str
    name: str
    pipeline: str          # candidates | alumni | referrals | boomerangs | succession
    status: str
    role_target: Optional[str] = None
    department: Optional[str] = None
    location: Optional[str] = None
    email: Optional[str] = None
    linkedin: Optional[str] = None
    source: Optional[str] = None
    referred_by: Optional[str] = None
    last_touch_at: Optional[str] = None
    next_touch_at: Optional[str] = None
    owner: Optional[str] = None
    rating: Optional[int] = None          # 0..100, recruiter signal
    ai_signal: Optional[str] = None       # short AI-written note
    tags: list[str] = field(default_factory=list)
    notes_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


PIPELINES = ["candidates", "alumni", "referrals", "boomerangs", "succession"]

PIPELINE_LABELS = {
    "candidates": "Candidates",
    "alumni": "Alumni",
    "referrals": "Referrals",
    "boomerangs": "Boomerangs",
    "succession": "Succession",
}

DEFAULT_STATUSES = {
    "candidates": ["new", "screening", "interview", "offer", "hired", "rejected", "nurture"],
    "alumni":     ["in_touch", "lost_touch", "do_not_contact"],
    "referrals":  ["new", "screening", "interview", "hired", "rejected", "thanked"],
    "boomerangs": ["watching", "warm", "engaged", "rehired"],
    "succession": ["watching", "groom", "ready_now", "promoted"],
}


# ---------------------------------------------------------------------------
_lock = threading.RLock()
_store: dict[str, list[CRMContact]] = {}
_notes: dict[str, list[CRMNote]] = {}
_seeded: set[str] = set()


def _now_iso(delta_days: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta_days)).isoformat()


def _seed(org_id: str) -> None:
    rows: list[CRMContact] = []

    def add(**kwargs) -> None:
        rows.append(CRMContact(id=f"crm-{uuid.uuid4().hex[:8]}", org_id=org_id, **kwargs))

    # Candidates
    add(name="Aisha Sankar", pipeline="candidates", status="interview",
        role_target="Senior Software Engineer", department="Engineering",
        location="Remote · EST", email="aisha.sankar@example.com",
        source="referral · Avery Chen", referred_by="Avery Chen",
        last_touch_at=_now_iso(-2), next_touch_at=_now_iso(2),
        owner="Sam Rivera", rating=88,
        ai_signal="Strong Python + AWS background; flagged as fast-track in last AI screening.",
        tags=["python", "aws", "leadership"])
    add(name="Diego Marin", pipeline="candidates", status="offer",
        role_target="Account Executive", department="Sales",
        location="NYC", email="diego.marin@example.com",
        source="LinkedIn inbound",
        last_touch_at=_now_iso(-1), next_touch_at=_now_iso(1),
        owner="Jamie Cole", rating=82,
        ai_signal="Closed 4 mid-market deals last quarter; offer pending finance approval.",
        tags=["sales", "mid-market"])
    add(name="Priya Iyer", pipeline="candidates", status="nurture",
        role_target="Designer", department="Design",
        location="SF", email="priya.iyer@example.com",
        source="event · Config 2025",
        last_touch_at=_now_iso(-21), next_touch_at=_now_iso(14),
        owner="Riley Manager", rating=70,
        ai_signal="Nurture — not actively hiring her band, but watch for next opening.",
        tags=["design", "systems"])

    # Alumni
    add(name="Nina Park", pipeline="alumni", status="in_touch",
        role_target="ex-Engineering Manager", department="Engineering",
        location="LA", email="nina.park@example.com",
        last_touch_at=_now_iso(-30),
        owner="Sam Rivera", rating=92,
        ai_signal="Top-quartile EM during tenure; founded ai-infra startup last year.",
        tags=["alumni", "engineering"])
    add(name="Marcus Lee", pipeline="alumni", status="lost_touch",
        role_target="ex-Sales", department="Sales", location="Austin",
        email="marcus.lee@example.com",
        last_touch_at=_now_iso(-220),
        owner="Reese Allen",
        ai_signal="Lost touch ~7 months ago. Reconnect candidate for boomerang.",
        tags=["alumni", "sales"])

    # Referrals
    add(name="Yuki Tanaka", pipeline="referrals", status="screening",
        role_target="Software Engineer", department="Engineering",
        email="yuki.tanaka@example.com",
        source="referral · Sam Rivera", referred_by="Sam Rivera",
        last_touch_at=_now_iso(-5), next_touch_at=_now_iso(2),
        owner="HR",
        ai_signal="Referred by Sam Rivera; resume scored 72/100. Move to interview.",
        tags=["referral", "python"])
    add(name="Hannah Schmitt", pipeline="referrals", status="new",
        role_target="Customer Success", department="Customer Success",
        email="hannah.schmitt@example.com",
        source="referral · Emily Stone", referred_by="Emily Stone",
        last_touch_at=_now_iso(-1),
        owner="Avery CS Lead",
        ai_signal="Just submitted. Acknowledge referrer within 48h per policy.",
        tags=["referral", "cs"])

    # Boomerangs
    add(name="Nina Park", pipeline="boomerangs", status="warm",
        role_target="VP Engineering (future)", department="Engineering",
        email="nina.park@example.com",
        last_touch_at=_now_iso(-30), next_touch_at=_now_iso(45),
        owner="VP People", rating=95,
        ai_signal="Stay-in-touch quarterly. Re-engage when senior IC band opens.",
        tags=["boomerang", "leadership"])
    add(name="Carlos Diaz", pipeline="boomerangs", status="engaged",
        role_target="Staff Engineer", department="Engineering",
        email="carlos.diaz@example.com",
        last_touch_at=_now_iso(-10), next_touch_at=_now_iso(7),
        owner="Sam Rivera", rating=90,
        ai_signal="Active conversation; coffee scheduled next week.",
        tags=["boomerang", "engineering"])

    # Succession
    add(name="Avery Chen", pipeline="succession", status="ready_now",
        role_target="Engineering Lead, Payments", department="Engineering",
        owner="Sam Rivera", rating=89,
        last_touch_at=_now_iso(-7),
        ai_signal="89% role-fit per marketplace match. Promotion conversation overdue.",
        tags=["internal", "ready"])
    add(name="Emily Stone", pipeline="succession", status="groom",
        role_target="Customer Success Manager", department="Customer Success",
        owner="Avery CS Lead", rating=76,
        last_touch_at=_now_iso(-21),
        ai_signal="On track; coverage 76%. Pair with leadership coaching this quarter.",
        tags=["internal", "groom"])
    add(name="Jordan Patel", pipeline="succession", status="watching",
        role_target="Senior Account Executive", department="Sales",
        owner="Jamie Cole", rating=63,
        last_touch_at=_now_iso(-14),
        ai_signal="High flight-risk this quarter — pause grooming, focus on retention.",
        tags=["internal", "risk"])

    _store[org_id] = rows
    _notes[org_id] = []


def _ensure(org_id: str) -> list[CRMContact]:
    with _lock:
        if org_id not in _seeded:
            _seed(org_id)
            _seeded.add(org_id)
        return _store.setdefault(org_id, [])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def list_pipelines() -> list[dict]:
    return [
        {"id": p, "label": PIPELINE_LABELS[p], "statuses": DEFAULT_STATUSES[p]}
        for p in PIPELINES
    ]


def pipeline_counts(org_id: str) -> dict:
    rows = _ensure(org_id)
    out: dict[str, int] = {p: 0 for p in PIPELINES}
    for r in rows:
        out[r.pipeline] = out.get(r.pipeline, 0) + 1
    return out


def list_contacts(
    org_id: str,
    *,
    pipeline: Optional[str] = None,
    status: Optional[str] = None,
    owner: Optional[str] = None,
    q: Optional[str] = None,
) -> list[dict]:
    rows = _ensure(org_id)
    out = []
    for r in rows:
        if pipeline and r.pipeline != pipeline:
            continue
        if status and r.status != status:
            continue
        if owner and (r.owner or "").lower() != owner.lower():
            continue
        if q:
            ql = q.lower()
            if ql not in r.name.lower() and ql not in (r.role_target or "").lower() and ql not in (r.email or "").lower():
                continue
        out.append(r.to_dict())
    out.sort(key=lambda r: (r["pipeline"], r.get("last_touch_at") or ""), reverse=False)
    return out


def get_contact(org_id: str, contact_id: str) -> Optional[dict]:
    rows = _ensure(org_id)
    for r in rows:
        if r.id == contact_id:
            d = r.to_dict()
            d["notes"] = [n.to_dict() for n in (_notes.get(org_id, []) if org_id in _notes else []) if n.contact_id == contact_id]
            return d
    return None


def create_contact(org_id: str, payload: dict) -> dict:
    rows = _ensure(org_id)
    pipeline = (payload.get("pipeline") or "candidates").lower()
    if pipeline not in PIPELINES:
        pipeline = "candidates"
    default_status = DEFAULT_STATUSES[pipeline][0] if DEFAULT_STATUSES.get(pipeline) else "new"
    c = CRMContact(
        id=f"crm-{uuid.uuid4().hex[:8]}",
        org_id=org_id,
        name=str(payload.get("name") or "Unnamed"),
        pipeline=pipeline,
        status=str(payload.get("status") or default_status),
        role_target=payload.get("role_target"),
        department=payload.get("department"),
        location=payload.get("location"),
        email=payload.get("email"),
        linkedin=payload.get("linkedin"),
        source=payload.get("source"),
        referred_by=payload.get("referred_by"),
        last_touch_at=payload.get("last_touch_at") or _now_iso(0),
        next_touch_at=payload.get("next_touch_at"),
        owner=payload.get("owner"),
        rating=payload.get("rating"),
        ai_signal=payload.get("ai_signal"),
        tags=list(payload.get("tags") or []),
    )
    with _lock:
        rows.insert(0, c)
    return c.to_dict()


def update_contact(org_id: str, contact_id: str, payload: dict) -> Optional[dict]:
    rows = _ensure(org_id)
    with _lock:
        for r in rows:
            if r.id == contact_id:
                for k, v in payload.items():
                    if hasattr(r, k):
                        setattr(r, k, v)
                r.updated_at = _now_iso(0)
                return r.to_dict()
    return None


def add_note(org_id: str, contact_id: str, body: str, author: str) -> Optional[dict]:
    rows = _ensure(org_id)
    if not any(r.id == contact_id for r in rows):
        return None
    n = CRMNote(id=f"note-{uuid.uuid4().hex[:8]}", contact_id=contact_id, body=body, author=author)
    with _lock:
        _notes.setdefault(org_id, []).append(n)
        for r in rows:
            if r.id == contact_id:
                r.notes_count += 1
                r.last_touch_at = n.created_at
                r.updated_at = n.created_at
                break
    return n.to_dict()


def signals_summary(org_id: str) -> dict:
    """High-level CRM signals surfaced for the index header."""
    rows = _ensure(org_id)
    overdue_touch = 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    for r in rows:
        if r.pipeline in ("alumni", "boomerangs", "candidates") and r.last_touch_at:
            try:
                if datetime.fromisoformat(r.last_touch_at) < cutoff:
                    overdue_touch += 1
            except Exception:
                pass
    # WHOSE RELATIONSHIPS THESE ARE.
    #
    # This service seeds twelve contacts into an empty tenant — Priya Iyer and
    # the rest — and the page headed them "Total contacts 12 · Active offers 1
    # · Overdue touch 4 · Succession ready 1". "Overdue touch 4" reads as four
    # people the reader has neglected.
    #
    # The word "source" appears throughout this module and means the recruiting
    # channel ("LinkedIn inbound", "referral · Avery Chen"), which is why the
    # sample-people inventory wrongly counted this service as already declaring
    # its provenance. It did not.
    #
    # Same rule as recognition and goals: a contact whose referrer is not in
    # your employee records, in a book where nobody is, is a sample contact.
    referrers = {(r.referred_by or "").strip().lower() for r in rows if r.referred_by}
    employees = _employee_names(org_id)
    all_sample = (bool(rows) and employees is not None and bool(referrers)
                  and not (referrers & employees))
    return {
        "total_contacts": len(rows),
        "pipelines": pipeline_counts(org_id),
        "overdue_touch": overdue_touch,
        "high_rating": sum(1 for r in rows if (r.rating or 0) >= 85),
        "ready_succession": sum(1 for r in rows if r.pipeline == "succession" and r.status == "ready_now"),
        "active_offers": sum(1 for r in rows if r.pipeline == "candidates" and r.status == "offer"),
        "provenance": {
            "all_sample": all_sample,
            "note": (
                "This relationship book was seeded as an example — the people who "
                "referred these contacts are not in your employee records. Add a "
                "contact to start your own."
                if all_sample else None
            ),
        },
    }


def _employee_names(org_id: str) -> Optional[set[str]]:
    """Lower-cased names of this org's employees, or None if unreadable.

    None means "we could not check". Reporting that as "all samples" would put
    a false disclaimer over a recruiter's real relationship book.
    """
    try:
        from app.services import _hr_persistence as _pp
        rows = _pp.q(
            "SELECT coalesce(preferred_name, legal_name) AS name "
            "FROM public.employees WHERE org_id = CAST(:o AS uuid)", o=org_id)
    except Exception:
        return None
    return {(r["name"] or "").strip().lower() for r in rows if r.get("name")}
