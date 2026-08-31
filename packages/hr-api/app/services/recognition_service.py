"""Recognition & peer praise feed.

Lattice / Bonusly style: public recognition + reactions + optional value tags.

Persistence: ``recognitions`` + ``recognition_reactions`` (migration 20260722)
via the sync->async bridge in ``app.services._hr_persistence``. Signatures are
unchanged. Fail-soft: if the DB is unreachable the module uses an in-process,
seeded ``_store`` so the feed is alive day-one and the app always boots. When the
DB is reachable but empty for an org, the same seed set is written once.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.services import _hr_persistence as _p


VALUE_TAGS = [
    "ownership", "craft", "teamwork", "customer obsession",
    "calm", "speed", "trust", "growth",
]


@dataclass
class Reaction:
    emoji: str
    by: list[str] = field(default_factory=list)


@dataclass
class Recognition:
    id: str
    from_name: str
    to_name: str
    body: str
    values: list[str] = field(default_factory=list)
    visibility: str = "company"   # company | team | private
    reactions: list[Reaction] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_name": self.from_name,
            "to_name": self.to_name,
            "body": self.body,
            "values": self.values,
            "visibility": self.visibility,
            "reactions": [{"emoji": r.emoji, "count": len(r.by), "by": r.by} for r in self.reactions],
            "created_at": self.created_at,
        }


_lock = threading.RLock()
_store: dict[str, list[Recognition]] = {}
_seeded: set[str] = set()
_db_seeded: set[str] = set()


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Seed data (shared by the in-memory fallback and the one-time DB seed)
# ---------------------------------------------------------------------------
def _seed_rows() -> list[Recognition]:
    now = datetime.now(timezone.utc)

    def _r(**kw) -> Recognition:
        return Recognition(id=str(uuid.uuid4()), **kw)

    return [
        _r(
            from_name="Sam Rivera", to_name="Avery Chen",
            body="Held the line on the payments incident this weekend — found the root cause in 25 minutes and shipped the fix Sunday night. Customers never noticed.",
            values=["ownership", "craft"],
            reactions=[Reaction(emoji="❤", by=["Casey", "Reese", "Jamie"]), Reaction(emoji="\U0001f6e0", by=["Sarah", "James"])],
            created_at=_iso(now - timedelta(hours=4)),
        ),
        _r(
            from_name="Avery CS Lead", to_name="Emily Stone",
            body="Closed the loop with a frustrated customer this week with calm + clarity. They explicitly said they're staying because of you.",
            values=["customer obsession", "calm", "trust"],
            reactions=[Reaction(emoji="❤", by=["Casey", "Reese"]), Reaction(emoji="✨", by=["Avery", "Jordan"])],
            created_at=_iso(now - timedelta(days=1)),
        ),
        _r(
            from_name="Reese Allen", to_name="Morgan Lee",
            body="Quietly shipped the new compliance training program with zero noise. Calm execution.",
            values=["craft", "calm"],
            reactions=[Reaction(emoji="✨", by=["Casey"]), Reaction(emoji="\U0001f64c", by=["Avery", "Sam"])],
            created_at=_iso(now - timedelta(days=2)),
        ),
        _r(
            from_name="Jamie Cole", to_name="Diego Marin",
            body="Held the room in the mid-market call this week. Asked the right questions, no pushy energy.",
            values=["trust", "speed"],
            reactions=[Reaction(emoji="\U0001f64c", by=["Casey", "Jamie"])],
            created_at=_iso(now - timedelta(days=4)),
        ),
        _r(
            from_name="Casey Reed", to_name="Sarah Chen",
            body="The way you mentored James through the design system migration was exactly the culture we want.",
            values=["teamwork", "growth"],
            reactions=[Reaction(emoji="❤", by=["Reese", "Avery"]), Reaction(emoji="✨", by=["Sam", "Jamie", "Riley"])],
            created_at=_iso(now - timedelta(days=6)),
        ),
    ]


# ---------------------------------------------------------------------------
# DB access
# ---------------------------------------------------------------------------
def _rec_from_rows(r: dict, reaction_rows: list[dict]) -> Recognition:
    # Group reactions by emoji, preserving first-seen order.
    order: list[str] = []
    by_emoji: dict[str, list[str]] = {}
    for rr in reaction_rows:
        e = rr["emoji"]
        if e not in by_emoji:
            by_emoji[e] = []
            order.append(e)
        by_emoji[e].append(rr["by_name"])
    created = r["created_at"]
    return Recognition(
        id=str(r["id"]),
        from_name=r["from_name"],
        to_name=r["to_name"],
        body=r["body"],
        values=_p.json_load(r["value_tags"]) or [],
        visibility=r["visibility"],
        reactions=[Reaction(emoji=e, by=by_emoji[e]) for e in order],
        created_at=created.isoformat() if hasattr(created, "isoformat") else str(created),
    )


def _db_seed_if_empty(org_id: str) -> None:
    if org_id in _db_seeded:
        return

    async def _op(s):
        rows = await _p.afetchall(s, "SELECT count(*) AS n FROM recognitions WHERE org_id = CAST(:o AS uuid)", o=org_id)
        if rows and rows[0]["n"]:
            return
        for rec in _seed_rows():
            await s.execute(_p.text(
                "INSERT INTO recognitions (id, org_id, from_name, to_name, body, value_tags, visibility, created_at) "
                "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :from_name, :to_name, :body, CAST(:vals AS jsonb), :vis, :created)"),
                {"id": rec.id, "org": org_id, "from_name": rec.from_name, "to_name": rec.to_name,
                 "body": rec.body, "vals": _p.json_dump(rec.values), "vis": rec.visibility,
                 "created": datetime.fromisoformat(rec.created_at)})
            for rx in rec.reactions:
                for name in rx.by:
                    await s.execute(_p.text(
                        "INSERT INTO recognition_reactions (id, recognition_id, emoji, by_name) "
                        "VALUES (CAST(:id AS uuid), CAST(:rec AS uuid), :emoji, :by) "
                        "ON CONFLICT (recognition_id, emoji, by_name) DO NOTHING"),
                        {"id": str(uuid.uuid4()), "rec": rec.id, "emoji": rx.emoji, "by": name})

    _p.tx(_op)
    _db_seeded.add(org_id)


def _db_load(org_id: str) -> list[Recognition]:
    _db_seed_if_empty(org_id)
    rec_rows = _p.q(
        "SELECT * FROM recognitions WHERE org_id = CAST(:o AS uuid) ORDER BY created_at DESC, id", o=org_id)
    if not rec_rows:
        return []
    rx_rows = _p.q(
        "SELECT rr.* FROM recognition_reactions rr JOIN recognitions r ON r.id = rr.recognition_id "
        "WHERE r.org_id = CAST(:o AS uuid) ORDER BY rr.created_at, rr.id", o=org_id)
    by_rec: dict[str, list[dict]] = {}
    for rr in rx_rows:
        by_rec.setdefault(str(rr["recognition_id"]), []).append(rr)
    return [_rec_from_rows(r, by_rec.get(str(r["id"]), [])) for r in rec_rows]


# ---------------------------------------------------------------------------
# In-memory fallback
# ---------------------------------------------------------------------------
def _mem_ensure(org_id: str) -> list[Recognition]:
    with _lock:
        if org_id not in _seeded:
            _store[org_id] = _seed_rows()
            _seeded.add(org_id)
        return _store.setdefault(org_id, [])


def _use_db() -> bool:
    return _p.db_available()


def _load(org_id: str) -> list[Recognition]:
    if _use_db():
        try:
            return _db_load(org_id)
        except Exception as e:
            _p.note_fallback("recognition._load", e)
    return _mem_ensure(org_id)


# ---------------------------------------------------------------------------
# Public surface (unchanged signatures)
# ---------------------------------------------------------------------------
def list_recognitions(org_id: str, *, value: Optional[str] = None, to_name: Optional[str] = None) -> dict:
    rows = _load(org_id)
    out: list[Recognition] = []
    for r in rows:
        if value and value not in r.values:
            continue
        if to_name and r.to_name.lower() != to_name.lower():
            continue
        out.append(r)
    out.sort(key=lambda r: r.created_at, reverse=True)

    # leaderboard — received
    leaderboard: dict[str, int] = {}
    for r in rows:
        leaderboard[r.to_name] = leaderboard.get(r.to_name, 0) + 1
    top = sorted(leaderboard.items(), key=lambda kv: -kv[1])[:5]

    value_counts: dict[str, int] = {}
    for r in rows:
        for v in r.values:
            value_counts[v] = value_counts.get(v, 0) + 1

    # WHOSE PRAISE IS THIS.
    #
    # The feed opened with "Sam Rivera recognised Avery Chen — 4H AGO · Held
    # the line on the payments incident this weekend", for an organisation
    # whose only employee is a CDL driver. These are the seed rows this service
    # writes into an empty tenant, and once written they are indistinguishable
    # from real posts.
    #
    # Rather than a schema flag, the test is the one that actually matters:
    # does the person being praised exist in your employee records? A post
    # about somebody who does not work here is a sample post, and the moment a
    # real recognition is written this resolves itself.
    named = {r.to_name.strip().lower() for r in rows} | {
        r.from_name.strip().lower() for r in rows}
    employees = _employee_names(org_id)
    unknown = sorted(n for n in named if n not in employees) if employees is not None else []
    all_unknown = bool(rows) and employees is not None and len(unknown) == len(named)

    return {
        "items": [r.to_dict() for r in out],
        "leaderboard": [{"name": n, "received": c} for n, c in top],
        "value_counts": value_counts,
        "values": VALUE_TAGS,
        "total": len(rows),
        "provenance": {
            "all_sample": all_unknown,
            "people_not_in_your_records": len(unknown),
            "note": (
                "Every name in this feed belongs to the illustrative team shipped "
                "with the product — none of them are in your employee records. "
                "Post a recognition to start your own."
                if all_unknown else None
            ),
        },
    }


def _employee_names(org_id: str) -> Optional[set[str]]:
    """Lower-cased names of this org's employees, or None if unreadable.

    None means "we could not check", which must not be reported as "these are
    all samples" — unavailable is not empty, and a wrong disclaimer over real
    praise from real colleagues would be its own insult.
    """
    try:
        rows = _p.q(
            "SELECT coalesce(preferred_name, legal_name) AS name "
            "FROM public.employees WHERE org_id = CAST(:o AS uuid)", o=org_id)
    except Exception:
        return None
    return {(r["name"] or "").strip().lower() for r in rows if r.get("name")}


def post_recognition(org_id: str, payload: dict, from_name: str) -> Optional[dict]:
    to_name = (payload.get("to_name") or "").strip()
    body = (payload.get("body") or "").strip()
    if not to_name or not body:
        return None
    values = [v for v in (payload.get("values") or []) if v in VALUE_TAGS]
    r = Recognition(
        id=str(uuid.uuid4()),
        from_name=from_name,
        to_name=to_name,
        body=body,
        values=values,
        visibility=str(payload.get("visibility") or "company"),
    )

    if _use_db():
        try:
            _db_seed_if_empty(org_id)

            async def _op(s):
                await s.execute(_p.text(
                    "INSERT INTO recognitions (id, org_id, from_name, to_name, body, value_tags, visibility, created_at) "
                    "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :from_name, :to_name, :body, CAST(:vals AS jsonb), :vis, :created)"),
                    {"id": r.id, "org": org_id, "from_name": r.from_name, "to_name": r.to_name,
                     "body": r.body, "vals": _p.json_dump(r.values), "vis": r.visibility,
                     "created": datetime.fromisoformat(r.created_at)})

            _p.tx(_op)
            return r.to_dict()
        except Exception as e:
            _p.note_fallback("recognition.post_recognition", e)

    rows = _mem_ensure(org_id)
    with _lock:
        rows.insert(0, r)
    return r.to_dict()


def react(org_id: str, recognition_id: str, emoji: str, by_name: str) -> Optional[dict]:
    if _use_db():
        try:
            return _db_react(org_id, recognition_id, emoji, by_name)
        except Exception as e:
            _p.note_fallback("recognition.react", e)

    rows = _mem_ensure(org_id)
    with _lock:
        for r in rows:
            if r.id != recognition_id:
                continue
            for rx in r.reactions:
                if rx.emoji == emoji:
                    if by_name in rx.by:
                        rx.by.remove(by_name)
                    else:
                        rx.by.append(by_name)
                    return r.to_dict()
            r.reactions.append(Reaction(emoji=emoji, by=[by_name]))
            return r.to_dict()
    return None


def _db_react(org_id: str, recognition_id: str, emoji: str, by_name: str) -> Optional[dict]:
    async def _op(s):
        owned = await _p.afetchall(s,
            "SELECT id FROM recognitions WHERE id = CAST(:rec AS uuid) AND org_id = CAST(:o AS uuid)",
            rec=recognition_id, o=org_id)
        if not owned:
            return False
        existing = await _p.afetchall(s,
            "SELECT id FROM recognition_reactions WHERE recognition_id = CAST(:rec AS uuid) AND emoji = :emoji AND by_name = :by",
            rec=recognition_id, emoji=emoji, by=by_name)
        if existing:  # toggle off
            await s.execute(_p.text(
                "DELETE FROM recognition_reactions WHERE recognition_id = CAST(:rec AS uuid) AND emoji = :emoji AND by_name = :by"),
                {"rec": recognition_id, "emoji": emoji, "by": by_name})
        else:  # toggle on
            await s.execute(_p.text(
                "INSERT INTO recognition_reactions (id, recognition_id, emoji, by_name) "
                "VALUES (CAST(:id AS uuid), CAST(:rec AS uuid), :emoji, :by) "
                "ON CONFLICT (recognition_id, emoji, by_name) DO NOTHING"),
                {"id": str(uuid.uuid4()), "rec": recognition_id, "emoji": emoji, "by": by_name})
        return True

    ok = _p.tx(_op)
    if not ok:
        return None
    for r in _db_load(org_id):
        if r.id == recognition_id:
            return r.to_dict()
    return None
