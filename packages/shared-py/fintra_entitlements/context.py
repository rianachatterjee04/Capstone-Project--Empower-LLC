"""
Request context bridge.

Each module backend resolves identity its own way (accounting
`get_current_user_company`, HR `require_org`, compliance `get_current_user`).
After it resolves identity it calls `set_fintra_context(request, ...)`, and the
entitlement dependencies read it back. This keeps the shared lib agnostic to how
each module authenticates.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from starlette.requests import Request


@dataclass
class FintraContext:
    org_id: str
    user_id: str
    email: Optional[str] = None
    platform_role: Optional[str] = None
    module_roles: dict = field(default_factory=dict)


def set_fintra_context(
    request: Request,
    *,
    org_id: str,
    user_id: str,
    email: Optional[str] = None,
    platform_role: Optional[str] = None,
    module_roles: Optional[dict] = None,
) -> FintraContext:
    ctx = FintraContext(
        org_id=str(org_id),
        user_id=str(user_id),
        email=email,
        platform_role=platform_role,
        module_roles=module_roles or {},
    )
    request.state.fintra = ctx
    # Also publish ambient AI context so AI utilities (no request param) can meter.
    try:
        from .aicontext import set_ai_context
        set_ai_context(org_id, user_id)
    except Exception:
        pass
    return ctx


def get_fintra_context(request: Request) -> Optional[FintraContext]:
    return getattr(request.state, "fintra", None)
