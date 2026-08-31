"""
Ambient AI context (contextvar) so module AI utilities — which often don't
receive the request/org as a parameter — can still tag gateway calls with the
right org. The per-module auth bridge sets this; AI utils read it.
"""
from __future__ import annotations
import contextvars
from typing import Optional

_ai_ctx: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("fintra_ai_ctx", default=None)


def set_ai_context(org_id: str, user_id: Optional[str] = None) -> None:
    _ai_ctx.set({"org_id": str(org_id), "user_id": str(user_id) if user_id else None})


def get_ai_context() -> Optional[dict]:
    return _ai_ctx.get()


def clear_ai_context() -> None:
    _ai_ctx.set(None)
