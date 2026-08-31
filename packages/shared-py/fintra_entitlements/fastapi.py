"""
FastAPI dependency factories. Mirror accounting's `require_min_role` ergonomics.

Wiring in a module backend (one line in the auth dependency + decorators on routes):

    from fintra_entitlements import set_fintra_context
    from fintra_entitlements.fastapi import require_module, require_seat, require_ai

    async def auth(request: Request, ...):
        ...                                     # module's own identity resolution
        set_fintra_context(request, org_id=org_id, user_id=user_id, email=email)
        return user

    @router.get("/things", dependencies=[
        Depends(require_module("hr")),
        Depends(require_seat("hr")),
    ])
"""
from __future__ import annotations
from fastapi import Request, HTTPException, Depends

from .gate import entitlements
from .context import get_fintra_context
from .errors import EntitlementError


def _ctx(request: Request):
    ctx = get_fintra_context(request)
    if ctx is None:
        # Misconfiguration: the module forgot to call set_fintra_context in its auth dep.
        raise HTTPException(
            status_code=401,
            detail="Unauthenticated (no Fintra entitlement context on request).",
        )
    return ctx


def _as_http(err: EntitlementError) -> HTTPException:
    return HTTPException(
        status_code=err.status_code,
        detail={"message": err.message, "code": err.code, **err.detail},
    )


def require_module(module_key: str):
    """402 if the org isn't licensed for `module_key`."""
    async def _dep(request: Request):
        ctx = _ctx(request)
        try:
            entitlements.require_module(ctx.org_id, module_key)
        except EntitlementError as e:
            raise _as_http(e)
        return True
    return _dep


def require_seat(module_key: str):
    """403 if the current user holds no seat in `module_key` (unless unlimited)."""
    async def _dep(request: Request):
        ctx = _ctx(request)
        try:
            entitlements.require_seat(ctx.org_id, module_key, ctx.user_id)
        except EntitlementError as e:
            raise _as_http(e)
        return True
    return _dep


def require_ai(app_key: str):
    """402 if AI is disabled for the org/app."""
    async def _dep(request: Request):
        ctx = _ctx(request)
        try:
            entitlements.require_ai(ctx.org_id, app_key)
        except EntitlementError as e:
            raise _as_http(e)
        return True
    return _dep


def require_module_access(module_key: str):
    """Convenience: module licensed AND user seated (the common pair)."""
    mod = require_module(module_key)
    seat = require_seat(module_key)

    async def _dep(request: Request, _m=Depends(mod), _s=Depends(seat)):
        return True
    return _dep
