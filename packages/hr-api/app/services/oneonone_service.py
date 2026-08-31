"""1:1s — recurring manager <-> report meetings.

Lattice "1:1s" parity. A manager and a report share a recurring meeting series
(weekly / biweekly). Each meeting carries a shared agenda, private notes, shared
talking points, and action items.

Persistence: ``one_on_one_series`` / ``one_on_one_meetings`` / ``agenda_items`` /
``action_items`` / ``one_on_one_talking_points`` (migration 20260722) via the
sync->async bridge in ``app.services._hr_persistence``. Every public signature is
unchanged. Fail-soft: if the DB is unreachable an in-process seeded ``_store`` is
used so the page is alive day-one and the app always boots; when the DB is
reachable but empty for an org the seed set is written once.

CARRY-OVER
----------
``create_meeting`` clones forward, from the series' most recent prior meeting,
every **unresolved action item** (``done=False``) and every **unchecked agenda
item** (``checked=False``), as fresh rows on the new meeting — so open threads
never fall through the cracks between 1:1s.

PRIVACY RULE
------------
An agenda item may be marked ``is_private``. A private item is visible ONLY to
its author (matched by ``author_user_id``). When a meeting is serialized for a
viewer, every private item whose author is not the viewer is dropped from the
response. A report therefore never sees the manager's private notes and vice
versa — the filter happens server-side, before the payload leaves the process.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.services import _hr_persistence as _p

# Fail-soft AI: import the HR LLM helper exactly like content_gen_service does.
try:  # pragma: no cover - import guard
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


CADENCES = ("weekly", "biweekly", "monthly")
MEETING_STATUSES = ("scheduled", "done", "skipped")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def _add_cadence(d: date, cadence: str) -> date:
    if cadence == "weekly":
        return d + timedelta(days=7)
    if cadence == "biweekly":
        return d + timedelta(days=14)
    if cadence == "monthly":
        return d + timedelta(days=30)
    return d + timedelta(days=7)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass
class AgendaItem:
    id: str
    text: str
    author_user_id: str
    author_role: str            # "manager" | "report" | "hr"
    checked: bool = False
    is_private: bool = False
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "author_user_id": self.author_user_id,
            "author_role": self.author_role,
            "checked": self.checked,
            "is_private": self.is_private,
            "created_at": self.created_at,
        }


@dataclass
class TalkingPoint:
    id: str
    text: str
    author_user_id: str
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "author_user_id": self.author_user_id, "created_at": self.created_at}


@dataclass
class ActionItem:
    id: str
    text: str
    assignee_user_id: Optional[str] = None
    due: Optional[str] = None
    done: bool = False
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "assignee_user_id": self.assignee_user_id,
            "due": self.due,
            "done": self.done,
            "created_at": self.created_at,
        }


@dataclass
class Meeting:
    id: str
    series_id: str
    date: str
    status: str = "scheduled"
    agenda_items: list[AgendaItem] = field(default_factory=list)
    talking_points: list[TalkingPoint] = field(default_factory=list)
    action_items: list[ActionItem] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self, viewer_user_id: Optional[str] = None) -> dict:
        """Serialize. Private agenda items are dropped unless the viewer authored
        them. Passing ``viewer_user_id=None`` hides ALL private items (safe default)."""
        visible_agenda = [
            a for a in self.agenda_items
            if (not a.is_private) or (viewer_user_id is not None and a.author_user_id == viewer_user_id)
        ]
        return {
            "id": self.id,
            "series_id": self.series_id,
            "date": self.date,
            "status": self.status,
            "agenda_items": [a.to_dict() for a in visible_agenda],
            "talking_points": [t.to_dict() for t in self.talking_points],
            "action_items": [a.to_dict() for a in self.action_items],
            "created_at": self.created_at,
        }


@dataclass
class Series:
    id: str
    manager_user_id: str
    report_user_id: str
    cadence: str = "weekly"
    next_date: Optional[str] = None
    title: str = "1:1"
    meetings: list[Meeting] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "manager_user_id": self.manager_user_id,
            "report_user_id": self.report_user_id,
            "cadence": self.cadence,
            "next_date": self.next_date,
            "title": self.title,
            "meeting_count": len(self.meetings),
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Store (org-scoped, thread-safe) — in-memory fallback
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_store: dict[str, list[Series]] = {}
_seeded: set[str] = set()
_db_seeded: set[str] = set()

# Well-known demo user ids so seeded data lines up with the dev token user.
_DEMO_MANAGER = "22222222-2222-2222-2222-222222222222"
_DEMO_REPORT = "33333333-3333-3333-3333-333333333333"


def _seed_rows() -> list[Series]:
    today = date.today()
    sid = str(uuid.uuid4())
    m1 = Meeting(
        id=str(uuid.uuid4()),
        series_id=sid,
        date=(today - timedelta(days=7)).isoformat(),
        status="done",
        agenda_items=[
            AgendaItem(id=str(uuid.uuid4()), text="How did the payments migration land?",
                       author_user_id=_DEMO_MANAGER, author_role="manager", checked=True),
            AgendaItem(id=str(uuid.uuid4()), text="I'd like more context on the roadmap.",
                       author_user_id=_DEMO_REPORT, author_role="report", checked=True),
            AgendaItem(id=str(uuid.uuid4()), text="Private: watch for burnout signals — check in gently.",
                       author_user_id=_DEMO_MANAGER, author_role="manager", is_private=True),
        ],
        talking_points=[
            TalkingPoint(id=str(uuid.uuid4()), text="Career growth toward Senior", author_user_id=_DEMO_REPORT),
        ],
        action_items=[
            ActionItem(id=str(uuid.uuid4()), text="Share the Q3 roadmap doc",
                       assignee_user_id=_DEMO_MANAGER, due=(today).isoformat(), done=True),
        ],
    )
    m2 = Meeting(
        id=str(uuid.uuid4()),
        series_id=sid,
        date=today.isoformat(),
        status="scheduled",
        agenda_items=[
            AgendaItem(id=str(uuid.uuid4()), text="Review last week's action items",
                       author_user_id=_DEMO_MANAGER, author_role="manager"),
        ],
    )
    series = Series(
        id=sid,
        manager_user_id=_DEMO_MANAGER,
        report_user_id=_DEMO_REPORT,
        cadence="weekly",
        next_date=_add_cadence(today, "weekly").isoformat(),
        title="Avery <-> Manager weekly",
        meetings=[m1, m2],
    )
    return [series]


# ---------------------------------------------------------------------------
# DB reconstruction
# ---------------------------------------------------------------------------
def _agenda_from_row(r: dict) -> AgendaItem:
    c = r["created_at"]
    return AgendaItem(
        id=str(r["id"]), text=r["text"], author_user_id=r["author_user_id"],
        author_role=r["author_role"], checked=bool(r["checked"]), is_private=bool(r["is_private"]),
        created_at=c.isoformat() if hasattr(c, "isoformat") else str(c),
    )


def _tp_from_row(r: dict) -> TalkingPoint:
    c = r["created_at"]
    return TalkingPoint(id=str(r["id"]), text=r["text"], author_user_id=r["author_user_id"],
                        created_at=c.isoformat() if hasattr(c, "isoformat") else str(c))


def _action_from_row(r: dict) -> ActionItem:
    c = r["created_at"]
    return ActionItem(
        id=str(r["id"]), text=r["text"], assignee_user_id=r["assignee_user_id"],
        due=r["due"], done=bool(r["done"]),
        created_at=c.isoformat() if hasattr(c, "isoformat") else str(c),
    )


def _db_seed_if_empty(org_id: str) -> None:
    if org_id in _db_seeded:
        return

    async def _op(s):
        rows = await _p.afetchall(s, "SELECT count(*) AS n FROM one_on_one_series WHERE org_id = CAST(:o AS uuid)", o=org_id)
        if rows and rows[0]["n"]:
            return
        for series in _seed_rows():
            await _insert_series(s, org_id, series)
            for m in series.meetings:
                await _insert_meeting(s, m)
                for a in m.agenda_items:
                    await _insert_agenda(s, m.id, a)
                for t in m.talking_points:
                    await _insert_talking_point(s, m.id, t)
                for ai in m.action_items:
                    await _insert_action(s, m.id, ai)

    _p.tx(_op)
    _db_seeded.add(org_id)


async def _insert_series(s, org_id: str, series: Series) -> None:
    await s.execute(_p.text(
        "INSERT INTO one_on_one_series (id, org_id, manager_user_id, report_user_id, cadence, next_date, title, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :mgr, :rep, :cad, :nd, :title, :created)"),
        {"id": series.id, "org": org_id, "mgr": series.manager_user_id, "rep": series.report_user_id,
         "cad": series.cadence, "nd": series.next_date, "title": series.title,
         "created": _dt(series.created_at)})


async def _insert_meeting(s, m: Meeting) -> None:
    await s.execute(_p.text(
        "INSERT INTO one_on_one_meetings (id, series_id, date, status, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:sid AS uuid), :date, :status, :created)"),
        {"id": m.id, "sid": m.series_id, "date": m.date, "status": m.status, "created": _dt(m.created_at)})


async def _insert_agenda(s, meeting_id: str, a: AgendaItem) -> None:
    await s.execute(_p.text(
        "INSERT INTO agenda_items (id, meeting_id, text, author_user_id, author_role, checked, is_private, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:mid AS uuid), :text, :au, :ar, :checked, :priv, :created)"),
        {"id": a.id, "mid": meeting_id, "text": a.text, "au": a.author_user_id, "ar": a.author_role,
         "checked": a.checked, "priv": a.is_private, "created": _dt(a.created_at)})


async def _insert_talking_point(s, meeting_id: str, t: TalkingPoint) -> None:
    await s.execute(_p.text(
        "INSERT INTO one_on_one_talking_points (id, meeting_id, text, author_user_id, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:mid AS uuid), :text, :au, :created)"),
        {"id": t.id, "mid": meeting_id, "text": t.text, "au": t.author_user_id, "created": _dt(t.created_at)})


async def _insert_action(s, meeting_id: str, a: ActionItem) -> None:
    await s.execute(_p.text(
        "INSERT INTO action_items (id, meeting_id, text, assignee_user_id, due, done, created_at) "
        "VALUES (CAST(:id AS uuid), CAST(:mid AS uuid), :text, :assignee, :due, :done, :created)"),
        {"id": a.id, "mid": meeting_id, "text": a.text, "assignee": a.assignee_user_id,
         "due": a.due, "done": a.done, "created": _dt(a.created_at)})


def _db_load(org_id: str) -> list[Series]:
    _db_seed_if_empty(org_id)
    series_rows = _p.q("SELECT * FROM one_on_one_series WHERE org_id = CAST(:o AS uuid) ORDER BY created_at, id", o=org_id)
    if not series_rows:
        return []
    meeting_rows = _p.q(
        "SELECT m.* FROM one_on_one_meetings m JOIN one_on_one_series s ON s.id = m.series_id "
        "WHERE s.org_id = CAST(:o AS uuid) ORDER BY m.date, m.created_at, m.id", o=org_id)
    agenda_rows = _p.q(
        "SELECT a.* FROM agenda_items a JOIN one_on_one_meetings m ON m.id = a.meeting_id "
        "JOIN one_on_one_series s ON s.id = m.series_id WHERE s.org_id = CAST(:o AS uuid) "
        "ORDER BY a.created_at, a.id", o=org_id)
    tp_rows = _p.q(
        "SELECT t.* FROM one_on_one_talking_points t JOIN one_on_one_meetings m ON m.id = t.meeting_id "
        "JOIN one_on_one_series s ON s.id = m.series_id WHERE s.org_id = CAST(:o AS uuid) "
        "ORDER BY t.created_at, t.id", o=org_id)
    action_rows = _p.q(
        "SELECT ai.* FROM action_items ai JOIN one_on_one_meetings m ON m.id = ai.meeting_id "
        "JOIN one_on_one_series s ON s.id = m.series_id WHERE s.org_id = CAST(:o AS uuid) "
        "ORDER BY ai.created_at, ai.id", o=org_id)

    agenda_by_m: dict[str, list[AgendaItem]] = {}
    for r in agenda_rows:
        agenda_by_m.setdefault(str(r["meeting_id"]), []).append(_agenda_from_row(r))
    tp_by_m: dict[str, list[TalkingPoint]] = {}
    for r in tp_rows:
        tp_by_m.setdefault(str(r["meeting_id"]), []).append(_tp_from_row(r))
    action_by_m: dict[str, list[ActionItem]] = {}
    for r in action_rows:
        action_by_m.setdefault(str(r["meeting_id"]), []).append(_action_from_row(r))

    meetings_by_s: dict[str, list[Meeting]] = {}
    for mr in meeting_rows:
        c = mr["created_at"]
        m = Meeting(
            id=str(mr["id"]), series_id=str(mr["series_id"]), date=mr["date"], status=mr["status"],
            agenda_items=agenda_by_m.get(str(mr["id"]), []),
            talking_points=tp_by_m.get(str(mr["id"]), []),
            action_items=action_by_m.get(str(mr["id"]), []),
            created_at=c.isoformat() if hasattr(c, "isoformat") else str(c),
        )
        meetings_by_s.setdefault(str(mr["series_id"]), []).append(m)

    out: list[Series] = []
    for sr in series_rows:
        c = sr["created_at"]
        out.append(Series(
            id=str(sr["id"]), manager_user_id=sr["manager_user_id"], report_user_id=sr["report_user_id"],
            cadence=sr["cadence"], next_date=sr["next_date"], title=sr["title"],
            meetings=meetings_by_s.get(str(sr["id"]), []),
            created_at=c.isoformat() if hasattr(c, "isoformat") else str(c),
        ))
    return out


# ---------------------------------------------------------------------------
# Unified load + fallback
# ---------------------------------------------------------------------------
def _use_db() -> bool:
    return _p.db_available()


def _ensure(org_id: str) -> list[Series]:
    """Return the org's series tree — from Postgres when available, else the
    in-process seeded store (fail-soft)."""
    if _use_db():
        try:
            return _db_load(org_id)
        except Exception as e:
            _p.note_fallback("oneonone._ensure", e)
    with _lock:
        if org_id not in _seeded:
            _store[org_id] = _seed_rows()
            _seeded.add(org_id)
        return _store.setdefault(org_id, [])


def _mem_ensure(org_id: str) -> list[Series]:
    with _lock:
        if org_id not in _seeded:
            _store[org_id] = _seed_rows()
            _seeded.add(org_id)
        return _store.setdefault(org_id, [])


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------
def _is_privileged(role: str) -> bool:
    return role in ("owner", "admin", "hr")


def can_view_series(series: Series, user_id: str, role: str) -> bool:
    if _is_privileged(role):
        return True
    return user_id in (series.manager_user_id, series.report_user_id)


def _viewer_role(series: Series, user_id: str, role: str) -> str:
    if user_id == series.manager_user_id:
        return "manager"
    if user_id == series.report_user_id:
        return "report"
    return "hr" if _is_privileged(role) else "other"


def _find_series(org_id: str, series_id: str) -> Optional[Series]:
    for s in _ensure(org_id):
        if s.id == series_id:
            return s
    return None


def _find_meeting(org_id: str, meeting_id: str) -> tuple[Optional[Series], Optional[Meeting]]:
    for s in _ensure(org_id):
        for m in s.meetings:
            if m.id == meeting_id:
                return s, m
    return None, None


def _find_agenda(org_id: str, agenda_id: str) -> tuple[Optional[Series], Optional[Meeting], Optional[AgendaItem]]:
    for s in _ensure(org_id):
        for m in s.meetings:
            for a in m.agenda_items:
                if a.id == agenda_id:
                    return s, m, a
    return None, None, None


def _find_action(org_id: str, action_id: str) -> tuple[Optional[Series], Optional[Meeting], Optional[ActionItem]]:
    for s in _ensure(org_id):
        for m in s.meetings:
            for a in m.action_items:
                if a.id == action_id:
                    return s, m, a
    return None, None, None


# ---------------------------------------------------------------------------
# Series
# ---------------------------------------------------------------------------
def list_series(org_id: str, user_id: str, role: str) -> dict:
    rows = _ensure(org_id)
    visible = [s for s in rows if can_view_series(s, user_id, role)]
    return {"items": [s.to_dict() for s in visible], "total": len(visible)}


def create_series(org_id: str, payload: dict) -> Optional[dict]:
    manager = (payload.get("manager_user_id") or "").strip()
    report = (payload.get("report_user_id") or "").strip()
    if not manager or not report:
        return None
    cadence = str(payload.get("cadence") or "weekly")
    if cadence not in CADENCES:
        cadence = "weekly"
    nd = payload.get("next_date")
    if not nd:
        nd = _add_cadence(date.today(), cadence).isoformat()
    s = Series(
        id=str(uuid.uuid4()),
        manager_user_id=manager,
        report_user_id=report,
        cadence=cadence,
        next_date=str(nd),
        title=str(payload.get("title") or "1:1"),
    )

    if _use_db():
        try:
            _db_seed_if_empty(org_id)

            async def _op(sess):
                await _insert_series(sess, org_id, s)

            _p.tx(_op)
            return s.to_dict()
        except Exception as e:
            _p.note_fallback("oneonone.create_series", e)

    with _lock:
        _mem_ensure(org_id).insert(0, s)
    return s.to_dict()


# ---------------------------------------------------------------------------
# Meetings
# ---------------------------------------------------------------------------
def list_meetings(org_id: str, series_id: str, viewer_user_id: str) -> Optional[dict]:
    s = _find_series(org_id, series_id)
    if not s:
        return None
    ms = sorted(s.meetings, key=lambda m: m.date, reverse=True)
    return {"items": [m.to_dict(viewer_user_id) for m in ms], "total": len(ms)}


def _carry_over_items(prior: Optional[Meeting], new_meeting_id: str) -> tuple[list[AgendaItem], list[ActionItem]]:
    """Clone unchecked agenda + unresolved (open) action items from the prior
    meeting onto a fresh meeting. New ids; state reset to open/unchecked."""
    carried_agenda: list[AgendaItem] = []
    carried_actions: list[ActionItem] = []
    if prior is None:
        return carried_agenda, carried_actions
    for a in prior.agenda_items:
        if not a.checked:
            carried_agenda.append(AgendaItem(
                id=str(uuid.uuid4()), text=a.text, author_user_id=a.author_user_id,
                author_role=a.author_role, checked=False, is_private=a.is_private,
            ))
    for ai in prior.action_items:
        if not ai.done:
            carried_actions.append(ActionItem(
                id=str(uuid.uuid4()), text=ai.text, assignee_user_id=ai.assignee_user_id,
                due=ai.due, done=False,
            ))
    return carried_agenda, carried_actions


def create_meeting(org_id: str, series_id: str, payload: dict) -> Optional[dict]:
    s = _find_series(org_id, series_id)
    if not s:
        return None
    d = payload.get("date") or date.today().isoformat()

    # Most recent prior meeting in the series (by date) — source of carry-over.
    prior = max(s.meetings, key=lambda m: m.date) if s.meetings else None

    m = Meeting(id=str(uuid.uuid4()), series_id=series_id, date=str(d), status="scheduled")
    carried_agenda, carried_actions = _carry_over_items(prior, m.id)
    m.agenda_items = carried_agenda
    m.action_items = carried_actions

    try:
        new_next = _add_cadence(date.fromisoformat(str(d)), s.cadence).isoformat()
    except Exception:
        new_next = s.next_date

    if _use_db():
        try:
            async def _op(sess):
                await _insert_meeting(sess, m)
                for a in m.agenda_items:
                    await _insert_agenda(sess, m.id, a)
                for ai in m.action_items:
                    await _insert_action(sess, m.id, ai)
                # advance the series' next_date deterministically
                await sess.execute(_p.text(
                    "UPDATE one_on_one_series SET next_date = :nd WHERE id = CAST(:sid AS uuid)"),
                    {"nd": new_next, "sid": series_id})

            _p.tx(_op)
            return m.to_dict(None)
        except Exception as e:
            _p.note_fallback("oneonone.create_meeting", e)

    # In-memory fallback (operate on the live memory objects, not the DB copy).
    mem_series = None
    for ms in _mem_ensure(org_id):
        if ms.id == series_id:
            mem_series = ms
            break
    if mem_series is None:
        return None
    mem_prior = max(mem_series.meetings, key=lambda mm: mm.date) if mem_series.meetings else None
    mm = Meeting(id=str(uuid.uuid4()), series_id=series_id, date=str(d), status="scheduled")
    ca, cac = _carry_over_items(mem_prior, mm.id)
    mm.agenda_items = ca
    mm.action_items = cac
    with _lock:
        mem_series.meetings.append(mm)
        try:
            mem_series.next_date = _add_cadence(date.fromisoformat(str(d)), mem_series.cadence).isoformat()
        except Exception:
            pass
    return mm.to_dict(None)


def get_meeting(org_id: str, meeting_id: str, viewer_user_id: str) -> Optional[dict]:
    _, m = _find_meeting(org_id, meeting_id)
    if not m:
        return None
    return m.to_dict(viewer_user_id)


def set_meeting_status(org_id: str, meeting_id: str, status: str) -> Optional[dict]:
    _, m = _find_meeting(org_id, meeting_id)
    if not m:
        return None
    if status not in MEETING_STATUSES:
        return None

    if _use_db():
        try:
            async def _op(sess):
                await sess.execute(_p.text(
                    "UPDATE one_on_one_meetings SET status = :status WHERE id = CAST(:mid AS uuid)"),
                    {"status": status, "mid": meeting_id})

            _p.tx(_op)
            m.status = status
            return m.to_dict(None)
        except Exception as e:
            _p.note_fallback("oneonone.set_meeting_status", e)

    with _lock:
        m.status = status
    return m.to_dict(None)


# ---------------------------------------------------------------------------
# Agenda items
# ---------------------------------------------------------------------------
def add_agenda_item(org_id: str, meeting_id: str, text: str, author_user_id: str,
                    author_role: str, is_private: bool = False) -> Optional[dict]:
    _, m = _find_meeting(org_id, meeting_id)
    if not m or not (text or "").strip():
        return None
    a = AgendaItem(
        id=str(uuid.uuid4()),
        text=text.strip(),
        author_user_id=author_user_id,
        author_role=author_role,
        is_private=bool(is_private),
    )

    if _use_db():
        try:
            async def _op(sess):
                await _insert_agenda(sess, meeting_id, a)

            _p.tx(_op)
            return a.to_dict()
        except Exception as e:
            _p.note_fallback("oneonone.add_agenda_item", e)

    with _lock:
        m.agenda_items.append(a)
    return a.to_dict()


def update_agenda_item(org_id: str, agenda_id: str, actor_user_id: str, role: str,
                       payload: dict) -> Optional[dict]:
    s, _, a = _find_agenda(org_id, agenda_id)
    if not a:
        return None
    # A private item may only be edited by its author.
    if a.is_private and a.author_user_id != actor_user_id and not _is_privileged(role):
        return None

    new_checked = a.checked
    new_text = a.text
    if "checked" in payload:
        new_checked = bool(payload["checked"])
    if "text" in payload and str(payload["text"]).strip():
        new_text = str(payload["text"]).strip()

    if _use_db():
        try:
            async def _op(sess):
                await sess.execute(_p.text(
                    "UPDATE agenda_items SET checked = :checked, text = :text WHERE id = CAST(:aid AS uuid)"),
                    {"checked": new_checked, "text": new_text, "aid": agenda_id})

            _p.tx(_op)
            a.checked = new_checked
            a.text = new_text
            return a.to_dict()
        except Exception as e:
            _p.note_fallback("oneonone.update_agenda_item", e)

    with _lock:
        a.checked = new_checked
        a.text = new_text
    return a.to_dict()


def delete_agenda_item(org_id: str, agenda_id: str, actor_user_id: str, role: str) -> bool:
    s, m, a = _find_agenda(org_id, agenda_id)
    if not a or not m:
        return False
    if a.is_private and a.author_user_id != actor_user_id and not _is_privileged(role):
        return False

    if _use_db():
        try:
            async def _op(sess):
                await sess.execute(_p.text(
                    "DELETE FROM agenda_items WHERE id = CAST(:aid AS uuid)"), {"aid": agenda_id})

            _p.tx(_op)
            return True
        except Exception as e:
            _p.note_fallback("oneonone.delete_agenda_item", e)

    with _lock:
        m.agenda_items = [x for x in m.agenda_items if x.id != agenda_id]
    return True


# ---------------------------------------------------------------------------
# Talking points (always shared)
# ---------------------------------------------------------------------------
def add_talking_point(org_id: str, meeting_id: str, text: str, author_user_id: str) -> Optional[dict]:
    _, m = _find_meeting(org_id, meeting_id)
    if not m or not (text or "").strip():
        return None
    t = TalkingPoint(id=str(uuid.uuid4()), text=text.strip(), author_user_id=author_user_id)

    if _use_db():
        try:
            async def _op(sess):
                await _insert_talking_point(sess, meeting_id, t)

            _p.tx(_op)
            return t.to_dict()
        except Exception as e:
            _p.note_fallback("oneonone.add_talking_point", e)

    with _lock:
        m.talking_points.append(t)
    return t.to_dict()


# ---------------------------------------------------------------------------
# Action items
# ---------------------------------------------------------------------------
def add_action_item(org_id: str, meeting_id: str, text: str,
                    assignee_user_id: Optional[str] = None, due: Optional[str] = None) -> Optional[dict]:
    _, m = _find_meeting(org_id, meeting_id)
    if not m or not (text or "").strip():
        return None
    a = ActionItem(id=str(uuid.uuid4()), text=text.strip(),
                   assignee_user_id=assignee_user_id, due=due)

    if _use_db():
        try:
            async def _op(sess):
                await _insert_action(sess, meeting_id, a)

            _p.tx(_op)
            return a.to_dict()
        except Exception as e:
            _p.note_fallback("oneonone.add_action_item", e)

    with _lock:
        m.action_items.append(a)
    return a.to_dict()


def set_action_done(org_id: str, action_id: str, done: bool = True) -> Optional[dict]:
    _, _, a = _find_action(org_id, action_id)
    if not a:
        return None

    if _use_db():
        try:
            async def _op(sess):
                await sess.execute(_p.text(
                    "UPDATE action_items SET done = :done WHERE id = CAST(:aid AS uuid)"),
                    {"done": bool(done), "aid": action_id})

            _p.tx(_op)
            a.done = bool(done)
            return a.to_dict()
        except Exception as e:
            _p.note_fallback("oneonone.set_action_done", e)

    with _lock:
        a.done = bool(done)
    return a.to_dict()


# ---------------------------------------------------------------------------
# AI assist — suggest agenda talking points (fail-soft)
# ---------------------------------------------------------------------------
def _llm(prompt: str, system: str) -> Optional[str]:
    if llm_complete is None:
        return None
    try:
        return llm_complete(prompt, system=system)
    except (LLMError, Exception):
        return None


def suggest_agenda(org_id: str, series_id: str) -> dict:
    """Suggest talking points from recent goals + recognition. LLM when available;
    deterministic fallback always returns useful output (fail-soft)."""
    s = _find_series(org_id, series_id)
    if not s:
        return {"suggestions": [], "source": "none"}

    # Pull light context from the goals store (best-effort).
    goal_titles: list[str] = []
    try:
        from app.services.goals_service import list_objectives
        objs = list_objectives(org_id).get("items", [])
        goal_titles = [o["title"] for o in objs[:3]]
    except Exception:
        goal_titles = []

    llm_out = _llm(
        prompt=(
            "Suggest 4 concise 1:1 talking points for a manager and their report. "
            f"Recent goals: {goal_titles or 'none'}. Return one per line, no numbering."
        ),
        system="You are a concise, supportive manager coach.",
    )
    if llm_out:
        lines = [ln.strip("-* ").strip() for ln in llm_out.splitlines() if ln.strip()]
        if lines:
            return {"suggestions": lines[:6], "source": "ai"}

    # Deterministic fallback — grounded in whatever goals we found.
    base = [
        "Wins since our last 1:1 — what went well and what you're proud of.",
        "Any blockers I can clear for you this week.",
        "Career growth — the next skill or scope you want to stretch into.",
        "Feedback for me — what should I start, stop, or keep doing.",
    ]
    for g in goal_titles:
        base.append(f"Progress check on: {g}")
    return {"suggestions": base[:6], "source": "fallback"}
