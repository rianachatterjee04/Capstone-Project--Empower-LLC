from __future__ import annotations
import os
from typing import Optional, Dict, Any
from app.core.config import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

class LLMError(Exception):
    pass


# When AI_GATEWAY_URL is set and an org_id is supplied, HR routes its LLM calls
# through the Fintra AI Gateway, which enforces AI on/off + token quota and meters
# usage to cp_ai_usage_ledger. Otherwise it calls OpenAI directly (legacy path),
# so existing behavior is preserved until callers thread org context through.
AI_GATEWAY_URL = os.getenv("AI_GATEWAY_URL")
INTERNAL_SECRET = os.getenv("INTERNAL_AI_SHARED_SECRET", "dev-internal-secret")


def _direct_client():
    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY missing")
    if OpenAI is None:
        raise LLMError("openai library missing")
    return OpenAI(api_key=settings.openai_api_key)


def _gateway_client():
    if OpenAI is None:
        raise LLMError("openai library missing")
    return OpenAI(api_key=INTERNAL_SECRET, base_url=AI_GATEWAY_URL.rstrip("/") + "/v1")


def llm_complete(
    prompt: str,
    system: str = "You are an expert HR copilot.",
    model: Optional[str] = None,
    *,
    org_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> str:
    if settings.llm_provider != "openai":
        raise LLMError("Only openai provider implemented")

    # AI safety — crisis screen the user's prompt BEFORE spending a call. On the
    # metered path the gateway also screens, but the direct path bypasses it, so we
    # screen here too. If it's a crisis we short-circuit with a compassionate response
    # and never call the model. Fail-soft: any safety error falls through to normal flow.
    try:
        from fintra_safety import screen_input
        _verdict = screen_input(prompt or "")
        if getattr(_verdict, "crisis", False) and getattr(_verdict, "safe_response", None):
            return _verdict.safe_response
    except Exception:
        pass

    use_gateway = bool(AI_GATEWAY_URL and org_id)
    client = _gateway_client() if use_gateway else _direct_client()
    extra_headers = (
        {"X-Fintra-Org": org_id, "X-Fintra-App": "hr", "X-Fintra-User": user_id or ""}
        if use_gateway else None
    )
    resp = client.chat.completions.create(
        model=model or settings.llm_model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        temperature=0.2,
        extra_headers=extra_headers,
    )
    content = resp.choices[0].message.content or ""

    # AI safety — annotate advice-like output with the right disclaimer. Idempotent,
    # so it's a no-op if the gateway already stamped it; fail-soft on any error.
    try:
        from fintra_safety import annotate_output
        content = annotate_output(content)
    except Exception:
        pass
    return content
