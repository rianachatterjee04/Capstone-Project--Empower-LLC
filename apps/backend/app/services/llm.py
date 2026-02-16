from __future__ import annotations
from typing import Optional, Dict, Any
from app.core.config import settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None

class LLMError(Exception):
    pass

def _openai_client():
    if not settings.openai_api_key:
        raise LLMError("OPENAI_API_KEY missing")
    if OpenAI is None:
        raise LLMError("openai library missing")
    return OpenAI(api_key=settings.openai_api_key)

def llm_complete(prompt: str, system: str = "You are an expert HR copilot.", model: Optional[str] = None) -> str:
    if settings.llm_provider != "openai":
        raise LLMError("Only openai provider implemented")
    client = _openai_client()
    resp = client.chat.completions.create(
        model=model or settings.llm_model,
        messages=[{"role":"system","content":system},{"role":"user","content":prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""
