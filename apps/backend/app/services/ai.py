"""AI service stub.

This module is intentionally minimal and safe-by-default.
Replace implementations with your LLM provider + retrieval (per-tenant vector store).

Design principle:
- Deterministic rules where possible
- LLM for interpretation + summarization
- Everything logged + explainable
"""

from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ResumeScreenResult:
    score: int
    summary: str
    reasons: list[str]

async def screen_resume(job_criteria: dict, resume_text: str | None) -> ResumeScreenResult:
    # Placeholder: in production, use RAG against job criteria + company hiring rubric
    if not resume_text:
        return ResumeScreenResult(score=0, summary="No resume provided.", reasons=["missing_resume"])
    # naive heuristic placeholder
    keywords = [k.lower() for k in job_criteria.get("must_have_keywords", [])]
    hits = sum(1 for k in keywords if k in resume_text.lower())
    score = min(100, hits * 20)
    return ResumeScreenResult(
        score=score,
        summary=f"Matched {hits} must-have keywords.",
        reasons=[f"keyword_hit:{k}" for k in keywords if k in resume_text.lower()],
    )

async def performance_discrepancy_flags(self_review: dict, manager_review: dict) -> dict:
    # Placeholder for bias/discrepancy detection
    flags = {}
    if self_review and manager_review:
        if self_review.get("overall") and manager_review.get("overall") and self_review["overall"] != manager_review["overall"]:
            flags["overall_mismatch"] = {"self": self_review["overall"], "manager": manager_review["overall"]}
    return flags


async def rescore_candidate_ai(resume_text: str | None) -> tuple[float, str]:
    """Re-score a candidate based on their resume text. Stub implementation."""
    if not resume_text:
        return 0.5, "No resume text available for rescoring."
    # In production: call LLM with job criteria + resume
    score = min(1.0, len(resume_text) / 5000)  # stub: longer resume = higher score
    return round(score, 2), "Auto-rescored by AI orchestrator (stub)."