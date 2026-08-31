"""
fintra_entitlements — shared control-plane gating for every Fintra module backend.

Generalizes accounting's `lib/addons/license_gate.py` into a cross-module library:

    from fintra_entitlements import entitlements, set_fintra_context
    from fintra_entitlements.fastapi import require_module, require_seat, require_ai

    # in a module's auth dependency, after resolving identity:
    set_fintra_context(request, org_id=..., user_id=..., email=...)

    # then protect routes:
    @router.get("/x", dependencies=[Depends(require_module("hr")), Depends(require_seat("hr"))])

The control plane (cp_* tables) is the system of record; reads are short-TTL cached.
"""
from .gate import Entitlements, entitlements
from .context import set_fintra_context, get_fintra_context, FintraContext
from .aicontext import set_ai_context, get_ai_context, clear_ai_context
from .errors import (
    ModuleNotLicensed,
    SeatRequired,
    AINotEnabled,
    AIQuotaExceeded,
)

__all__ = [
    "Entitlements",
    "entitlements",
    "set_fintra_context",
    "get_fintra_context",
    "FintraContext",
    "set_ai_context",
    "get_ai_context",
    "clear_ai_context",
    "ModuleNotLicensed",
    "SeatRequired",
    "AINotEnabled",
    "AIQuotaExceeded",
]
