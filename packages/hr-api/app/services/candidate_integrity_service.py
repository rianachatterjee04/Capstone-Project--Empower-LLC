"""Candidate Fraud / Deepfake / Proxy detection.

NET-NEW P0 differentiator (Mercor/HireVue don't do this today). Produces a
deterministic, explainable fraud score (0-100) per candidate/interview from
signal inputs, plus a risk band and a recommended action. Mirrors the
deterministic scoring style of the SentriAI trust score: fixed category
weights, per-category severity in [0,1], score = Σ severity·weight.

SIGNAL MODEL (six categories, weights sum to 100)
-------------------------------------------------
  identity_consistency      25   name / email / resume vs interview identity
  proxy_interview           25   voice-change / face-change / multiple-faces flags
  ai_generated_response     20   answer uniformity / latency anomaly / paste bursts
  location_timezone         15   VPN / geo-IP mismatch / timezone mismatch
  reference_mismatch        10   reference-check contradictions (reuses ref-check)
  resume_inflation           5   inflated titles / unverifiable employers / date gaps

Each category maps its raw signals to a severity in [0,1]; contribution =
severity · weight. The final score is the sum of contributions from the
categories that HAD data. Missing categories contribute ZERO and lower the
`confidence` (= categories_with_data / 6) — this is the fail-soft rule: absent
signals never crash and never inflate risk.

BANDS (on score)                RECOMMENDED ACTION
  clear      0  – 29            proceed
  review     30 – 59            verify
  high_risk  60 – 100           block

This is a security/trust feature: it is decision-support for a recruiter, never
an automatic rejection. The recommended action is advisory and every flag is
explainable down to the contributing signal.
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# ---------------------------------------------------------------------------
# Category weights (sum to 100) — the deterministic trust-score kernel
# ---------------------------------------------------------------------------
WEIGHTS = {
    "identity_consistency": 25,
    "proxy_interview": 25,
    "ai_generated_response": 20,
    "location_timezone": 15,
    "reference_mismatch": 10,
    "resume_inflation": 5,
}

BAND_CLEAR_MAX = 29
BAND_REVIEW_MAX = 59

ACTION_BY_BAND = {"clear": "proceed", "review": "verify", "high_risk": "block"}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _bool_fraction(signals: dict, keys: list[str]) -> Optional[float]:
    """Fraction of the provided boolean keys that are truthy. None if none present."""
    present = [k for k in keys if k in signals and signals[k] is not None]
    if not present:
        return None
    trues = sum(1 for k in present if bool(signals[k]))
    return trues / len(present)


# ---------------------------------------------------------------------------
# Per-category severity (each returns (severity|None, detail))
# ---------------------------------------------------------------------------
def _sev_identity(sig: dict) -> tuple[Optional[float], dict]:
    # mismatches raise severity: checks are "match" booleans, so severity = fraction MISMATCHED
    keys = ["name_match", "email_matches_resume", "resume_matches_interview"]
    present = [k for k in keys if k in sig and sig[k] is not None]
    if not present:
        return None, {"present": False}
    mismatches = sum(1 for k in present if not bool(sig[k]))
    sev = mismatches / len(present)
    return sev, {"present": True, "checks": len(present), "mismatches": mismatches,
                 "failed": [k for k in present if not bool(sig[k])]}


def _sev_proxy(sig: dict) -> tuple[Optional[float], dict]:
    keys = ["voice_change_flag", "face_change_flag", "multiple_faces_detected"]
    sev = _bool_fraction(sig, keys)
    if sev is None:
        return None, {"present": False}
    flags = [k for k in keys if sig.get(k)]
    return sev, {"present": True, "flags_raised": flags, "n_checks": len([k for k in keys if k in sig])}


def _sev_ai_generated(sig: dict) -> tuple[Optional[float], dict]:
    parts: list[tuple[str, float]] = []
    if sig.get("response_uniformity") is not None:
        parts.append(("response_uniformity", _clamp01(sig["response_uniformity"])))
    if sig.get("latency_anomaly") is not None:
        parts.append(("latency_anomaly", _clamp01(sig["latency_anomaly"])))
    if sig.get("paste_burst_count") is not None:
        parts.append(("paste_burst", _clamp01(float(sig["paste_burst_count"]) / 5.0)))
    if not parts:
        return None, {"present": False}
    sev = sum(v for _, v in parts) / len(parts)
    return sev, {"present": True, "components": {k: round(v, 4) for k, v in parts}}


def _sev_location(sig: dict) -> tuple[Optional[float], dict]:
    keys = ["vpn_detected", "geo_ip_mismatch", "timezone_mismatch"]
    sev = _bool_fraction(sig, keys)
    if sev is None:
        return None, {"present": False}
    flags = [k for k in keys if sig.get(k)]
    return sev, {"present": True, "flags_raised": flags, "n_checks": len([k for k in keys if k in sig])}


def _sev_reference(sig: dict) -> tuple[Optional[float], dict]:
    total = sig.get("references_total")
    mism = sig.get("reference_mismatches")
    if total is None or mism is None or int(total) <= 0:
        return None, {"present": False}
    sev = _clamp01(int(mism) / int(total))
    return sev, {"present": True, "mismatches": int(mism), "total": int(total)}


def _sev_resume(sig: dict) -> tuple[Optional[float], dict]:
    keys = ["inflated_titles", "unverifiable_employers", "suspicious_date_gaps"]
    sev = _bool_fraction(sig, keys)
    if sev is None:
        return None, {"present": False}
    flags = [k for k in keys if sig.get(k)]
    return sev, {"present": True, "flags_raised": flags, "n_checks": len([k for k in keys if k in sig])}


_CATEGORY_FUNCS = {
    "identity_consistency": _sev_identity,
    "proxy_interview": _sev_proxy,
    "ai_generated_response": _sev_ai_generated,
    "location_timezone": _sev_location,
    "reference_mismatch": _sev_reference,
    "resume_inflation": _sev_resume,
}


def band_for(score: float) -> str:
    if score <= BAND_CLEAR_MAX:
        return "clear"
    if score <= BAND_REVIEW_MAX:
        return "review"
    return "high_risk"


def score_candidate(signals: dict) -> dict:
    """Pure, deterministic fraud scoring. `signals` is a flat dict of raw
    signal inputs. Returns score, band, action, per-category contributions and
    confidence. Fail-soft: unknown/missing signals are ignored."""
    signals = signals or {}
    contributions: list[dict] = []
    total = 0.0
    present_categories = 0
    for cat, weight in WEIGHTS.items():
        sev, detail = _CATEGORY_FUNCS[cat](signals)
        if sev is None:
            contributions.append({
                "category": cat, "weight": weight, "present": False,
                "severity": None, "points": 0.0, "detail": detail,
            })
            continue
        present_categories += 1
        points = round(sev * weight, 2)
        total += points
        contributions.append({
            "category": cat, "weight": weight, "present": True,
            "severity": round(sev, 4), "points": points, "detail": detail,
        })
    score = int(round(total))
    band = band_for(score)
    confidence = round(present_categories / len(WEIGHTS), 4)
    # Surface the top drivers (present categories, highest points first)
    drivers = sorted(
        [c for c in contributions if c["present"] and c["points"] > 0],
        key=lambda c: -c["points"],
    )
    return {
        "fraud_score": score,
        "band": band,
        "recommended_action": ACTION_BY_BAND[band],
        "confidence": confidence,
        "categories_with_data": present_categories,
        "categories_total": len(WEIGHTS),
        "contributing_signals": contributions,
        "top_drivers": [{"category": d["category"], "points": d["points"]} for d in drivers[:3]],
        "low_confidence": confidence < 0.5,
        "disclaimer": (
            "Deterministic fraud-risk signal for recruiter review. Advisory only "
            "— not an automated rejection. Verify flagged candidates with a human."
        ),
    }


# ---------------------------------------------------------------------------
# Org-scoped in-process store (mirrors goals/recognition pattern)
# ---------------------------------------------------------------------------
@dataclass
class IntegrityAssessment:
    id: str
    candidate_id: str
    candidate_name: str
    interview_id: Optional[str]
    result: dict
    signals: dict
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    assessed_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "candidate_id": self.candidate_id,
            "candidate_name": self.candidate_name,
            "interview_id": self.interview_id,
            "assessed_by": self.assessed_by,
            "created_at": self.created_at,
            **self.result,
        }


_lock = threading.RLock()
_store: dict[str, dict[str, IntegrityAssessment]] = {}  # org_id → candidate_id → latest assessment


def assess(
    org_id: str, *,
    candidate_id: str,
    candidate_name: str,
    signals: dict,
    interview_id: Optional[str] = None,
    assessed_by: Optional[str] = None,
) -> dict:
    result = score_candidate(signals)
    rec = IntegrityAssessment(
        id=str(uuid.uuid4()),
        candidate_id=candidate_id,
        candidate_name=candidate_name,
        interview_id=interview_id,
        result=result,
        signals=signals or {},
        assessed_by=assessed_by,
    )
    with _lock:
        _store.setdefault(org_id, {})[candidate_id] = rec
    return rec.to_dict()


def get_candidate(org_id: str, candidate_id: str) -> Optional[dict]:
    with _lock:
        rec = _store.get(org_id, {}).get(candidate_id)
        return rec.to_dict() if rec else None


def review_queue(org_id: str, *, min_band: str = "review") -> dict:
    order = {"clear": 0, "review": 1, "high_risk": 2}
    floor = order.get(min_band, 1)
    with _lock:
        recs = list(_store.get(org_id, {}).values())
    flagged = [r.to_dict() for r in recs if order.get(r.result["band"], 0) >= floor]
    flagged.sort(key=lambda r: -r["fraud_score"])
    return {
        "items": flagged,
        "summary": {
            "total_assessed": len(recs),
            "flagged": len(flagged),
            "high_risk": sum(1 for r in recs if r.result["band"] == "high_risk"),
            "review": sum(1 for r in recs if r.result["band"] == "review"),
            "clear": sum(1 for r in recs if r.result["band"] == "clear"),
        },
    }
