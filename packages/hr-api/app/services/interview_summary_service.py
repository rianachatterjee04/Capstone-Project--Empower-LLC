"""Interview Summary service — post-interview synthesis + recommendations.

After all scorecards are in, this service rolls up:
  - strengths + concerns (evidence-grounded)
  - per-competency evidence-based ratings
  - hiring recommendation (advance / advance_with_caveats / hold / decline)
  - panel debrief packet (interviewer-by-interviewer view)
  - candidate feedback draft (professional, empathetic, defensible)
  - offer risk notes (comp expectations, timeline, geo)
  - next-step recommendation
"""
from __future__ import annotations

import re
import textwrap
from typing import Optional

from app.services.interview_copilot_service import list_insights
from app.services.interview_scorecard_service import RATING_SCALE, calibration_view, list_scorecards
from app.services.interview_transcription_service import full_transcript

try:
    from app.services.llm import llm_complete  # type: ignore
except Exception:
    llm_complete = None  # type: ignore


def _evidence_lines(transcript: str, term: str, n: int = 2) -> list[str]:
    if not transcript or not term:
        return []
    lines = transcript.splitlines()
    out: list[str] = []
    for line in lines:
        if term.lower() in line.lower():
            out.append(line.strip())
        if len(out) >= n:
            break
    return out


def generate_post_interview_summary(
    *,
    interview_id: str,
    candidate_name: str,
    job_title: str,
) -> dict:
    """Calibrated post-interview synthesis. Designed to be defensible."""
    scorecards = list_scorecards(interview_id)
    calibration = calibration_view(interview_id)
    transcript = full_transcript(interview_id)
    insights = list_insights(interview_id)

    submitted = [s for s in scorecards if s.status == "submitted"]
    if not submitted:
        return {
            "candidate_name": candidate_name,
            "job_title": job_title,
            "ready": False,
            "narrative": "Awaiting scorecards. Post-interview summary is generated after the panel submits.",
        }

    # Per-competency consensus
    competency_scores: dict[str, int] = {}
    for comp, stat in calibration["by_competency"].items():
        competency_scores[comp] = int(round(stat["avg"] * 25))  # 0-4 → 0-100

    # Overall composite
    overall_avg = sum(s.overall_rating or 0 for s in submitted) / max(len(submitted), 1)
    overall = int(round(overall_avg * 25))

    if overall_avg >= 3.0:
        recommendation = "advance"
    elif overall_avg >= 2.3:
        recommendation = "advance_with_caveats"
    elif overall_avg >= 1.3:
        recommendation = "hold"
    else:
        recommendation = "decline"
    band = (
        "strong" if overall >= 75 else
        "moderate" if overall >= 55 else
        "weak"
    )

    # Strengths + concerns from scorecard notes
    strengths: list[str] = []
    concerns: list[str] = []
    for s in submitted:
        for c in s.competencies:
            if c.final_rating is None:
                continue
            if c.final_rating >= 3 and c.notes:
                strengths.append(f"{c.competency.replace('_', ' ')} — {c.notes[:140]}")
            elif c.final_rating <= 1 and c.notes:
                concerns.append(f"{c.competency.replace('_', ' ')} — {c.notes[:140]}")

    # Dedup
    seen: set[str] = set()
    strengths = [x for x in strengths if not (x in seen or seen.add(x))][:6]
    seen = set()
    concerns = [x for x in concerns if not (x in seen or seen.add(x))][:6]

    # Narrative (LLM-preferred, local fallback)
    narrative = ""
    if llm_complete is not None:
        try:
            prompt = textwrap.dedent(f"""
                Write a calm, defensible 4-sentence post-interview summary for
                {candidate_name} interviewing for {job_title}. Avoid superlatives;
                lead with evidence. Mention the recommendation: {recommendation}.

                Per-competency scores: {competency_scores}
                Strengths: {strengths[:3]}
                Concerns: {concerns[:3]}
                Calibration: {calibration['n_scorecards']} scorecards, median overall {calibration.get('median_overall_rating')}.
            """).strip()
            raw = llm_complete(prompt, system="You are a calibrated hiring debrief writer.")
            narrative = raw.strip()
        except Exception:
            pass
    if not narrative:
        narrative = (
            f"{candidate_name} interviewed for {job_title}. Panel of {calibration['n_scorecards']} "
            f"produced a {band} composite of {overall}/100. "
            f"Strongest competency on the panel: "
            f"{max(competency_scores, key=competency_scores.get) if competency_scores else 'n/a'}. "
            f"Recommendation: {recommendation.replace('_', ' ')}."
        )

    # Candidate feedback draft (always professional + empathetic)
    if recommendation == "advance":
        feedback = (
            f"Thanks for the time, {candidate_name.split()[0] if candidate_name else 'there'}. "
            "The team was impressed by your work in our key focus areas. We'd like to move you to the next round."
        )
    elif recommendation == "decline":
        feedback = (
            f"Thanks for interviewing with us, {candidate_name.split()[0] if candidate_name else 'there'}. "
            "After careful discussion the panel felt this particular role wasn't the right match. We genuinely appreciated the conversation and would welcome you to apply again as our needs evolve."
        )
    else:
        feedback = (
            f"Thanks for the time, {candidate_name.split()[0] if candidate_name else 'there'}. "
            "We're discussing next steps as a panel and will follow up shortly."
        )

    # Offer risk notes (heuristic from transcript)
    offer_risk: list[str] = []
    if re.search(r"\b(other offer|competing offer|deciding by|deadline)\b", transcript or "", re.IGNORECASE):
        offer_risk.append("Candidate referenced a competing offer / decision deadline.")
    if re.search(r"\b(remote|hybrid|relocation)\b", transcript or "", re.IGNORECASE):
        offer_risk.append("Geography / remote expectations surfaced — confirm in offer prep.")
    if re.search(r"\b(equity|stock|rsus?|options)\b", transcript or "", re.IGNORECASE):
        offer_risk.append("Equity expectations raised — align with comp band before offer.")

    # Panel debrief packet
    debrief = []
    for s in submitted:
        debrief.append({
            "interviewer_name": s.interviewer_name,
            "overall_rating": s.overall_rating,
            "rating_label": RATING_SCALE.get(s.overall_rating or -1, "—"),
            "confidence": s.interviewer_confidence,
            "headline_competency": (
                max(s.competencies, key=lambda c: (c.final_rating or 0)).competency
                if s.competencies else None
            ),
        })

    next_actions: list[str] = []
    if recommendation == "advance":
        next_actions.append("Schedule next round (onsite or final).")
    elif recommendation == "advance_with_caveats":
        next_actions.append("Add one targeted interviewer on the weakest competency.")
    elif recommendation == "hold":
        next_actions.append("Park in talent pool with a 90-day follow-up.")
    else:
        next_actions.append("Send polite decline. Update ATS stage to rejected.")
    if calibration.get("dissenters"):
        next_actions.append("Resolve panel dissent before the next round.")
    if calibration["evidence_gap_count"]:
        next_actions.append("Backfill transcript evidence on flagged ratings before debrief.")

    fairness_note = (
        "This summary is generated by an AI synthesis layer over a transparent, evidence-cited scorecard. "
        "It is intended to support — not replace — human hiring judgement. Calibrate against the rubric; "
        "review for bias before any final decision."
    )

    return {
        "ready": True,
        "candidate_name": candidate_name,
        "job_title": job_title,
        "overall_score": overall,
        "band": band,
        "recommendation": recommendation,
        "narrative": narrative,
        "strengths": strengths,
        "concerns": concerns,
        "competency_scores": competency_scores,
        "panel_debrief": debrief,
        "next_actions": next_actions,
        "candidate_feedback_draft": feedback,
        "offer_risk_notes": offer_risk,
        "calibration": calibration,
        "fairness_note": fairness_note,
        "insights_recorded": len(insights),
    }
