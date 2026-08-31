from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Try the LLM helper; if openai/config isn't importable, fall back to a
# deterministic, evidence-only draft (same pattern the AI Interviewer uses).
try:
    from app.services.llm import llm_complete, LLMError
except Exception:  # pragma: no cover
    llm_complete = None

    class LLMError(Exception):
        pass


def detect_manager_bias(reviews):
    return []


def _deterministic_narrative(self_review: str, manager_review: str, flags: Any) -> str:
    """Grounded fallback when no LLM is configured. Summarizes ONLY what was
    provided — never invents accomplishments, metrics, or ratings."""
    parts = []
    if manager_review:
        parts.append(f"Manager assessment: {manager_review.strip()}")
    if self_review:
        parts.append(f"Self-assessment: {self_review.strip()}")
    if flags:
        flag_text = flags if isinstance(flags, str) else ", ".join(map(str, flags))
        parts.append(f"To reconcile in the 1:1: {flag_text}")
    if not parts:
        return "No review content is available yet to summarize."
    return "Draft summary (edit before sharing):\n" + "\n".join(f"- {p}" for p in parts)


def write_performance_narrative(
    data: Dict[str, Any],
    *,
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    """Draft a balanced performance summary GROUNDED in this review's own
    content. Human-in-the-loop: returns a DRAFT for the manager to edit — it
    never auto-submits. Uses the LLM when configured (metered via the gateway
    when org context is threaded), else a deterministic evidence-only summary."""
    data = data or {}
    self_review = (data.get("self_review") or "").strip()
    manager_review = (data.get("manager_review") or "").strip()
    flags = data.get("ai_flags")

    if not (self_review or manager_review):
        return "No review content is available yet to summarize."

    if llm_complete is not None:
        try:
            prompt = (
                "Write a concise, balanced performance-review summary for a manager to EDIT before "
                "sharing. Ground every statement ONLY in the material below — do not invent "
                "accomplishments, metrics, or ratings. Cover strengths, growth areas, and one suggested "
                "next step. Keep it neutral, specific, and bias-free.\n\n"
                f"SELF-ASSESSMENT:\n{self_review or '(none provided)'}\n\n"
                f"MANAGER ASSESSMENT:\n{manager_review or '(none provided)'}\n\n"
                f"DISCREPANCY / BIAS FLAGS:\n{flags or '(none)'}\n"
            )
            draft = llm_complete(
                prompt,
                system=(
                    "You are a calibrated HR partner. Produce an evidence-based draft grounded only in "
                    "the provided review content; never fabricate. The manager reviews and edits before "
                    "anything is shared."
                ),
                org_id=org_id,
                user_id=user_id,
            )
            if draft and draft.strip():
                return draft.strip()
        except LLMError as exc:
            logger.info("perf narrative: LLM unavailable (%s) — using deterministic draft", exc)
        except Exception as exc:  # pragma: no cover
            logger.warning("perf narrative: LLM call failed (%s) — using deterministic draft", exc)

    return _deterministic_narrative(self_review, manager_review, flags)
