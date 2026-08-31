"""Engagement / eNPS pulse surveys with deterministic driver analysis.

Lattice "Engagement" parity. A survey has questions (scale, eNPS 0-10, open
text, multi-choice), collects responses (optionally anonymous), and produces
aggregates: overall score, eNPS, participation rate, and driver analysis.

Persistence: ``engagement_surveys`` / ``survey_questions`` / ``survey_responses``
(migration 20260722) via the sync->async bridge in
``app.services._hr_persistence``. Signatures are unchanged and all aggregate math
below is untouched. Fail-soft: if the DB is unreachable an in-process seeded
``_store`` is used so the page is alive day-one and the app always boots; when
the DB is reachable but empty for an org the seed set is written once.

MATH
----
eNPS  : on an ``enps_0_10`` question, 9-10 = promoter, 7-8 = passive,
        0-6 = detractor.  eNPS = round(%promoters - %detractors), range -100..+100.
overall_score : mean of every ``scale_1_5`` answer, on the 1-5 scale
        (also reported as a 0-100 pct = (mean - 1) / 4 x 100).
participation : round(unique_respondents / audience_size x 100). Null if the
        survey has no declared audience size.
driver analysis : scale_1_5 questions carry a ``category`` (leadership / growth /
        recognition ...).  Per driver we report the mean and its Pearson
        correlation with each respondent's headline score (their mean scale_1_5).
        Deterministic: zero variance -> correlation 0 (no div-by-zero, no RNG).

K-ANONYMITY
-----------
On an anonymous survey a driver answered by fewer than ``K_ANON`` (=3) distinct
respondents is suppressed: its mean/correlation are null and ``suppressed=True``.
If the whole survey has < K_ANON responses, every aggregate is suppressed. Raw
individual responses are NEVER returned by any endpoint for an anonymous survey.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from app.services import _hr_persistence as _p

try:  # pragma: no cover - import guard
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None
    LLMError = Exception


K_ANON = 3
SURVEY_TYPES = ("engagement", "enps", "pulse", "custom")
QUESTION_KINDS = ("scale_1_5", "enps_0_10", "nps", "open", "multi")
SURVEY_STATUSES = ("draft", "open", "closed")
DRIVERS = ("leadership", "growth", "recognition", "wellbeing", "enablement", "belonging")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@dataclass
class Question:
    id: str
    text: str
    kind: str                       # scale_1_5 | enps_0_10 | nps | open | multi
    category: Optional[str] = None  # driver tag
    options: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "text": self.text, "kind": self.kind,
                "category": self.category, "options": self.options}


@dataclass
class Response:
    id: str
    survey_id: str
    respondent_user_id: str
    anonymous: bool
    answers: dict            # question_id -> value (int for scale/enps, str for open/multi)
    submitted_at: str = field(default_factory=_now_iso)


@dataclass
class Survey:
    id: str
    title: str
    type: str = "engagement"
    cadence: str = "quarterly"
    status: str = "draft"
    anonymous: bool = True
    audience_size: Optional[int] = None
    questions: list[Question] = field(default_factory=list)
    responses: list[Response] = field(default_factory=list)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict:
        """Metadata only — never leaks individual responses."""
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "cadence": self.cadence,
            "status": self.status,
            "anonymous": self.anonymous,
            "audience_size": self.audience_size,
            "questions": [q.to_dict() for q in self.questions],
            "response_count": len(self.responses),
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------
_lock = threading.RLock()
_store: dict[str, list[Survey]] = {}
_seeded: set[str] = set()
_db_seeded: set[str] = set()


def _seed_rows() -> list[Survey]:
    s = Survey(
        id=str(uuid.uuid4()),
        title="Q3 Engagement Pulse",
        type="engagement",
        cadence="quarterly",
        status="open",
        anonymous=True,
        audience_size=10,
    )
    q_enps = Question(id=str(uuid.uuid4()), text="How likely are you to recommend us as a place to work?",
                      kind="enps_0_10", category=None)
    q_lead = Question(id=str(uuid.uuid4()), text="My manager gives me useful feedback.",
                      kind="scale_1_5", category="leadership")
    q_grow = Question(id=str(uuid.uuid4()), text="I have room to grow here.",
                      kind="scale_1_5", category="growth")
    q_recog = Question(id=str(uuid.uuid4()), text="Good work gets recognised.",
                       kind="scale_1_5", category="recognition")
    q_open = Question(id=str(uuid.uuid4()), text="What would make this a better place to work?",
                      kind="open")
    s.questions = [q_enps, q_lead, q_grow, q_recog, q_open]

    # Four seeded responses (>= K_ANON so aggregates are visible day-one).
    seed_rows = [
        {q_enps.id: 9, q_lead.id: 5, q_grow.id: 4, q_recog.id: 4, q_open.id: "More async, fewer meetings."},
        {q_enps.id: 8, q_lead.id: 4, q_grow.id: 4, q_recog.id: 3, q_open.id: "Clearer career ladder."},
        {q_enps.id: 6, q_lead.id: 3, q_grow.id: 2, q_recog.id: 2, q_open.id: "Recognise quiet, steady work."},
        {q_enps.id: 10, q_lead.id: 5, q_grow.id: 5, q_recog.id: 4, q_open.id: "Keep the calm culture."},
    ]
    for i, ans in enumerate(seed_rows):
        s.responses.append(Response(
            id=str(uuid.uuid4()), survey_id=s.id,
            respondent_user_id=f"seed-{i}", anonymous=True, answers=ans,
        ))
    return [s]


# ---------------------------------------------------------------------------
# DB access
# ---------------------------------------------------------------------------
def _survey_from_rows(sr: dict, q_rows: list[dict], r_rows: list[dict]) -> Survey:
    created = sr["created_at"]
    survey = Survey(
        id=str(sr["id"]),
        title=sr["title"],
        type=sr["type"],
        cadence=sr["cadence"],
        status=sr["status"],
        anonymous=bool(sr["anonymous"]),
        audience_size=sr["audience_size"],
        created_at=created.isoformat() if hasattr(created, "isoformat") else str(created),
    )
    survey.questions = [
        Question(id=str(q["id"]), text=q["text"], kind=q["kind"],
                 category=q["category"], options=_p.json_load(q["options"]) or [])
        for q in q_rows
    ]
    resp: list[Response] = []
    for r in r_rows:
        submitted = r["submitted_at"]
        resp.append(Response(
            id=str(r["id"]),
            survey_id=str(r["survey_id"]),
            respondent_user_id=r["respondent_user_id"],
            anonymous=bool(r["anonymous"]),
            answers=_p.json_load(r["answers"]) or {},
            submitted_at=submitted.isoformat() if hasattr(submitted, "isoformat") else str(submitted),
        ))
    survey.responses = resp
    return survey


def _db_seed_if_empty(org_id: str) -> None:
    if org_id in _db_seeded:
        return

    async def _op(s):
        rows = await _p.afetchall(s, "SELECT count(*) AS n FROM engagement_surveys WHERE org_id = CAST(:o AS uuid)", o=org_id)
        if rows and rows[0]["n"]:
            return
        for survey in _seed_rows():
            await s.execute(_p.text(
                "INSERT INTO engagement_surveys (id, org_id, title, type, cadence, status, anonymous, audience_size, created_at) "
                "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :title, :type, :cadence, :status, :anon, :aud, :created)"),
                {"id": survey.id, "org": org_id, "title": survey.title, "type": survey.type,
                 "cadence": survey.cadence, "status": survey.status, "anon": survey.anonymous,
                 "aud": survey.audience_size, "created": datetime.fromisoformat(survey.created_at)})
            for i, qq in enumerate(survey.questions):
                await s.execute(_p.text(
                    "INSERT INTO survey_questions (id, survey_id, text, kind, category, options, position) "
                    "VALUES (CAST(:id AS uuid), CAST(:sv AS uuid), :text, :kind, :cat, CAST(:opts AS jsonb), :pos)"),
                    {"id": qq.id, "sv": survey.id, "text": qq.text, "kind": qq.kind,
                     "cat": qq.category, "opts": _p.json_dump(qq.options), "pos": i})
            for rr in survey.responses:
                await s.execute(_p.text(
                    "INSERT INTO survey_responses (id, survey_id, respondent_user_id, anonymous, answers, submitted_at) "
                    "VALUES (CAST(:id AS uuid), CAST(:sv AS uuid), :ru, :anon, CAST(:ans AS jsonb), :sub)"),
                    {"id": rr.id, "sv": survey.id, "ru": rr.respondent_user_id, "anon": rr.anonymous,
                     "ans": _p.json_dump(rr.answers), "sub": datetime.fromisoformat(rr.submitted_at)})

    _p.tx(_op)
    _db_seeded.add(org_id)


def _db_load(org_id: str) -> list[Survey]:
    _db_seed_if_empty(org_id)
    s_rows = _p.q("SELECT * FROM engagement_surveys WHERE org_id = CAST(:o AS uuid) ORDER BY created_at DESC, id", o=org_id)
    if not s_rows:
        return []
    q_rows = _p.q(
        "SELECT q.* FROM survey_questions q JOIN engagement_surveys s ON s.id = q.survey_id "
        "WHERE s.org_id = CAST(:o AS uuid) ORDER BY q.position, q.id", o=org_id)
    r_rows = _p.q(
        "SELECT r.* FROM survey_responses r JOIN engagement_surveys s ON s.id = r.survey_id "
        "WHERE s.org_id = CAST(:o AS uuid) ORDER BY r.submitted_at, r.id", o=org_id)
    q_by_s: dict[str, list[dict]] = {}
    for q in q_rows:
        q_by_s.setdefault(str(q["survey_id"]), []).append(q)
    r_by_s: dict[str, list[dict]] = {}
    for r in r_rows:
        r_by_s.setdefault(str(r["survey_id"]), []).append(r)
    return [_survey_from_rows(sr, q_by_s.get(str(sr["id"]), []), r_by_s.get(str(sr["id"]), [])) for sr in s_rows]


# ---------------------------------------------------------------------------
# In-memory fallback + unified loaders
# ---------------------------------------------------------------------------
def _mem_ensure(org_id: str) -> list[Survey]:
    with _lock:
        if org_id not in _seeded:
            _store[org_id] = _seed_rows()
            _seeded.add(org_id)
        return _store.setdefault(org_id, [])


def _use_db() -> bool:
    return _p.db_available()


def _load(org_id: str) -> list[Survey]:
    if _use_db():
        try:
            return _db_load(org_id)
        except Exception as e:
            _p.note_fallback("engagement._load", e)
    return _mem_ensure(org_id)


def _find(org_id: str, survey_id: str) -> Optional[Survey]:
    for s in _load(org_id):
        if s.id == survey_id:
            return s
    return None


# ---------------------------------------------------------------------------
# CRUD (unchanged signatures)
# ---------------------------------------------------------------------------
def list_surveys(org_id: str) -> dict:
    rows = _load(org_id)
    return {"items": [s.to_dict() for s in rows], "total": len(rows)}


def get_survey(org_id: str, survey_id: str) -> Optional[dict]:
    s = _find(org_id, survey_id)
    return s.to_dict() if s else None


def create_survey(org_id: str, payload: dict) -> Optional[dict]:
    title = (payload.get("title") or "").strip()
    if not title:
        return None
    stype = str(payload.get("type") or "engagement")
    if stype not in SURVEY_TYPES:
        stype = "custom"
    s = Survey(
        id=str(uuid.uuid4()),
        title=title,
        type=stype,
        cadence=str(payload.get("cadence") or "quarterly"),
        status="draft",
        anonymous=bool(payload.get("anonymous", True)),
        audience_size=(int(payload["audience_size"]) if payload.get("audience_size") is not None else None),
    )

    if _use_db():
        try:
            _db_seed_if_empty(org_id)

            async def _op(sess):
                await sess.execute(_p.text(
                    "INSERT INTO engagement_surveys (id, org_id, title, type, cadence, status, anonymous, audience_size, created_at) "
                    "VALUES (CAST(:id AS uuid), CAST(:org AS uuid), :title, :type, :cadence, :status, :anon, :aud, :created)"),
                    {"id": s.id, "org": org_id, "title": s.title, "type": s.type, "cadence": s.cadence,
                     "status": s.status, "anon": s.anonymous, "aud": s.audience_size, "created": datetime.fromisoformat(s.created_at)})

            _p.tx(_op)
            return s.to_dict()
        except Exception as e:
            _p.note_fallback("engagement.create_survey", e)

    with _lock:
        _mem_ensure(org_id).insert(0, s)
    return s.to_dict()


def add_question(org_id: str, survey_id: str, payload: dict) -> Optional[dict]:
    s = _find(org_id, survey_id)
    if not s:
        return None
    text = (payload.get("text") or "").strip()
    kind = str(payload.get("kind") or "scale_1_5")
    if not text or kind not in QUESTION_KINDS:
        return None
    q = Question(
        id=str(uuid.uuid4()),
        text=text,
        kind=kind,
        category=(payload.get("category") or None),
        options=[str(o) for o in (payload.get("options") or [])],
    )

    if _use_db():
        try:
            position = len(s.questions)

            async def _op(sess):
                await sess.execute(_p.text(
                    "INSERT INTO survey_questions (id, survey_id, text, kind, category, options, position) "
                    "VALUES (CAST(:id AS uuid), CAST(:sv AS uuid), :text, :kind, :cat, CAST(:opts AS jsonb), :pos)"),
                    {"id": q.id, "sv": survey_id, "text": q.text, "kind": q.kind,
                     "cat": q.category, "opts": _p.json_dump(q.options), "pos": position})

            _p.tx(_op)
            return q.to_dict()
        except Exception as e:
            _p.note_fallback("engagement.add_question", e)

    with _lock:
        s.questions.append(q)
    return q.to_dict()


def set_status(org_id: str, survey_id: str, status: str) -> Optional[dict]:
    s = _find(org_id, survey_id)
    if not s or status not in SURVEY_STATUSES:
        return None

    if _use_db():
        try:
            async def _op(sess):
                await sess.execute(_p.text(
                    "UPDATE engagement_surveys SET status = :status WHERE id = CAST(:sv AS uuid) AND org_id = CAST(:o AS uuid)"),
                    {"status": status, "sv": survey_id, "o": org_id})

            _p.tx(_op)
            s.status = status
            return s.to_dict()
        except Exception as e:
            _p.note_fallback("engagement.set_status", e)

    with _lock:
        s.status = status
    return s.to_dict()


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------
def submit_response(org_id: str, survey_id: str, respondent_user_id: str, answers: dict) -> Optional[dict]:
    """Submit a response. Only allowed while the survey is open. Anonymity is
    driven by the survey flag, not the caller — an anonymous survey NEVER surfaces
    respondent identity in any aggregate."""
    s = _find(org_id, survey_id)
    if not s:
        return {"error": "not_found"}
    if s.status != "open":
        return {"error": "not_open"}
    if not isinstance(answers, dict) or not answers:
        return {"error": "empty"}
    valid_qids = {q.id for q in s.questions}
    clean = {qid: v for qid, v in answers.items() if qid in valid_qids}
    if not clean:
        return {"error": "no_valid_answers"}
    r = Response(
        id=str(uuid.uuid4()),
        survey_id=survey_id,
        respondent_user_id=respondent_user_id,
        anonymous=s.anonymous,
        answers=clean,
    )

    if _use_db():
        try:
            async def _op(sess):
                await sess.execute(_p.text(
                    "INSERT INTO survey_responses (id, survey_id, respondent_user_id, anonymous, answers, submitted_at) "
                    "VALUES (CAST(:id AS uuid), CAST(:sv AS uuid), :ru, :anon, CAST(:ans AS jsonb), :sub)"),
                    {"id": r.id, "sv": survey_id, "ru": r.respondent_user_id, "anon": r.anonymous,
                     "ans": _p.json_dump(r.answers), "sub": datetime.fromisoformat(r.submitted_at)})

            _p.tx(_op)
            return {"submitted": True, "survey_id": survey_id, "anonymous": s.anonymous}
        except Exception as e:
            _p.note_fallback("engagement.submit_response", e)

    with _lock:
        s.responses.append(r)
    # Acknowledgement only — never echoes other responses or identities.
    return {"submitted": True, "survey_id": survey_id, "anonymous": s.anonymous}


# ---------------------------------------------------------------------------
# Aggregate math  (unchanged)
# ---------------------------------------------------------------------------
def _pearson(xs: list[float], ys: list[float]) -> float:
    """Deterministic Pearson correlation. Zero variance -> 0.0."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return 0.0
    return round(num / (dx * dy), 3)


def compute_enps(scores: list[int]) -> dict:
    """eNPS from 0-10 scores. Promoters 9-10, passives 7-8, detractors 0-6."""
    n = len(scores)
    if n == 0:
        return {"enps": None, "promoters": 0, "passives": 0, "detractors": 0, "n": 0}
    promoters = sum(1 for s in scores if s >= 9)
    passives = sum(1 for s in scores if 7 <= s <= 8)
    detractors = sum(1 for s in scores if s <= 6)
    enps = round((promoters - detractors) / n * 100)
    return {
        "enps": enps,
        "promoters": promoters,
        "passives": passives,
        "detractors": detractors,
        "promoter_pct": round(promoters / n * 100, 1),
        "detractor_pct": round(detractors / n * 100, 1),
        "n": n,
    }


def results(org_id: str, survey_id: str) -> Optional[dict]:
    s = _find(org_id, survey_id)
    if not s:
        return None

    responses = s.responses
    n_resp = len(responses)

    # Whole-survey k-anonymity gate for anonymous surveys.
    suppressed_all = s.anonymous and n_resp < K_ANON

    # Participation rate.
    unique = len({r.respondent_user_id for r in responses}) if not s.anonymous else n_resp
    participation = None
    if s.audience_size:
        participation = round(min(unique, s.audience_size) / s.audience_size * 100)

    base = {
        "survey_id": s.id,
        "title": s.title,
        "type": s.type,
        "status": s.status,
        "anonymous": s.anonymous,
        "response_count": n_resp,
        "audience_size": s.audience_size,
        "participation_rate": participation,
        "k_anon": K_ANON,
        "suppressed": suppressed_all,
    }
    if suppressed_all:
        base.update({"overall_score": None, "overall_pct": None, "enps": None, "drivers": []})
        return base

    # eNPS across all enps_0_10 / nps questions.
    enps_qids = [q.id for q in s.questions if q.kind in ("enps_0_10", "nps")]
    enps_scores: list[int] = []
    for r in responses:
        for qid in enps_qids:
            v = r.answers.get(qid)
            if isinstance(v, (int, float)):
                enps_scores.append(int(v))
    enps_block = compute_enps(enps_scores)

    # Per-respondent headline = mean of their scale_1_5 answers.
    scale_qs = [q for q in s.questions if q.kind == "scale_1_5"]
    scale_qids = [q.id for q in scale_qs]
    per_resp_headline: list[float] = []
    all_scale_vals: list[int] = []
    for r in responses:
        vals = [int(r.answers[q]) for q in scale_qids if isinstance(r.answers.get(q), (int, float))]
        if vals:
            per_resp_headline.append(sum(vals) / len(vals))
            all_scale_vals.extend(vals)
        else:
            per_resp_headline.append(0.0)

    overall_score = round(sum(all_scale_vals) / len(all_scale_vals), 2) if all_scale_vals else None
    overall_pct = round((overall_score - 1) / 4 * 100, 1) if overall_score is not None else None

    # Driver analysis: group scale questions by category.
    by_cat: dict[str, list[str]] = {}
    for q in scale_qs:
        cat = q.category or "uncategorized"
        by_cat.setdefault(cat, []).append(q.id)

    drivers = []
    for cat, qids in sorted(by_cat.items()):
        # respondents who answered at least one question in this driver
        resp_driver_scores: list[float] = []
        resp_headline_aligned: list[float] = []
        distinct = 0
        for idx, r in enumerate(responses):
            vals = [int(r.answers[q]) for q in qids if isinstance(r.answers.get(q), (int, float))]
            if not vals:
                continue
            distinct += 1
            resp_driver_scores.append(sum(vals) / len(vals))
            resp_headline_aligned.append(per_resp_headline[idx])
        # per-driver k-anonymity
        if s.anonymous and distinct < K_ANON:
            drivers.append({"category": cat, "mean": None, "correlation": None,
                            "n": distinct, "suppressed": True})
            continue
        mean = round(sum(resp_driver_scores) / len(resp_driver_scores), 2) if resp_driver_scores else None
        corr = _pearson(resp_driver_scores, resp_headline_aligned)
        drivers.append({"category": cat, "mean": mean, "correlation": corr,
                        "n": distinct, "suppressed": False})

    # Rank the drivers that most correlate with the headline score.
    visible = [d for d in drivers if not d["suppressed"]]
    top_drivers = sorted(visible, key=lambda d: -(d["correlation"] or 0))

    base.update({
        "overall_score": overall_score,
        "overall_pct": overall_pct,
        "enps": enps_block["enps"],
        "enps_breakdown": enps_block,
        "drivers": drivers,
        "top_correlated_drivers": [d["category"] for d in top_drivers[:3]],
    })
    return base


# ---------------------------------------------------------------------------
# AI insight summary (fail-soft)
# ---------------------------------------------------------------------------
def _llm(prompt: str, system: str) -> Optional[str]:
    if llm_complete is None:
        return None
    try:
        return llm_complete(prompt, system=system)
    except (LLMError, Exception):
        return None


def insights(org_id: str, survey_id: str) -> Optional[dict]:
    s = _find(org_id, survey_id)
    if not s:
        return None
    agg = results(org_id, survey_id) or {}
    if agg.get("suppressed"):
        return {"summary": "Not enough responses yet to report safely (k-anonymity).",
                "themes": [], "driver_readout": [], "source": "suppressed"}

    # Collect open-text (never attributed) for theme extraction.
    open_qids = [q.id for q in s.questions if q.kind == "open"]
    open_texts: list[str] = []
    for r in s.responses:
        for qid in open_qids:
            v = r.answers.get(qid)
            if isinstance(v, str) and v.strip():
                open_texts.append(v.strip())

    llm_out = _llm(
        prompt=(
            "Summarise this employee engagement survey in 2 sentences, then list up to 4 "
            f"themes from the open-text comments. eNPS={agg.get('enps')}, "
            f"overall={agg.get('overall_score')}/5, drivers={agg.get('drivers')}. "
            f"Comments: {open_texts}"
        ),
        system="You are a concise people-analytics partner. Never identify individuals.",
    )
    if llm_out:
        return {"summary": llm_out.strip(), "themes": [], "driver_readout": [], "source": "ai"}

    # Deterministic fallback readout.
    drivers = [d for d in agg.get("drivers", []) if not d.get("suppressed") and d.get("mean") is not None]
    strongest = max(drivers, key=lambda d: d["mean"], default=None)
    weakest = min(drivers, key=lambda d: d["mean"], default=None)
    readout = []
    for d in sorted(drivers, key=lambda d: -(d["correlation"] or 0)):
        readout.append(f"{d['category']}: {d['mean']}/5 (correlation with overall {d['correlation']})")
    summary = (
        f"eNPS is {agg.get('enps')} with an overall score of {agg.get('overall_score')}/5 "
        f"across {agg.get('response_count')} responses."
    )
    if strongest and weakest:
        summary += f" Strongest driver: {strongest['category']}; area to watch: {weakest['category']}."
    # crude, deterministic keyword themes from open text
    themes = _keyword_themes(open_texts)
    return {"summary": summary, "themes": themes, "driver_readout": readout, "source": "fallback"}


def _keyword_themes(texts: list[str], top: int = 4) -> list[str]:
    stop = {"the", "a", "an", "to", "of", "and", "for", "in", "on", "is", "it", "be",
            "more", "less", "would", "make", "this", "that", "with", "keep", "our", "we"}
    counts: dict[str, int] = {}
    for t in texts:
        for w in "".join(c.lower() if c.isalnum() or c.isspace() else " " for c in t).split():
            if len(w) < 4 or w in stop:
                continue
            counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:top]]
