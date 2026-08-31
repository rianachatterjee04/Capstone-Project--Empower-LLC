"""
HR ↔ Fintra control-plane bridge.

Adds module/seat/AI enforcement to HR routes without disturbing the existing
auth path. Composes the existing `require_org` (which yields an Actor with
org_id + user_id), publishes the Fintra context, and — only when enforcement is
switched on — checks the org's `hr` license + the user's seat.

Safe by default: with FINTRA_ENFORCE unset/0 this is a pass-through that just
publishes context, so HR keeps working even before the control plane is wired.
Flip FINTRA_ENFORCE=1 in production once cp_* is provisioned.

Usage in a router:
    from app.api.entitlements import require_hr_access
    @router.get("/x", dependencies=[Depends(require_hr_access)])
"""
from __future__ import annotations
import logging
import os
from fastapi import Depends, Request, HTTPException
from app.api.deps import require_org, Actor

log = logging.getLogger("fintra.entitlements")


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _enforce_on() -> bool:
    # Enforcement ON by default; see require_accounting_access for the full model.
    return _flag("FINTRA_ENFORCE", "1")


def _fail_open() -> bool:
    # Fail-open on control-plane UNREACHABILITY by default (dev/test/outage safe).
    # Production hardening: set FINTRA_FAIL_OPEN=0 to fail closed (503).
    return _flag("FINTRA_FAIL_OPEN", "1")


MODULE = "hr"

try:
    from fintra_entitlements import set_fintra_context, entitlements
    from fintra_entitlements.errors import EntitlementError
    _AVAILABLE = True
except Exception:  # lib not installed yet → no-op
    _AVAILABLE = False


def _enforce_module_and_seat(org_id: str, user_id: str) -> None:
    try:
        entitlements.require_module(org_id, MODULE)
        entitlements.require_seat(org_id, MODULE, user_id)
    except EntitlementError as e:
        raise HTTPException(status_code=e.status_code,
                            detail={"message": e.message, "code": e.code, **e.detail})
    except HTTPException:
        raise
    except Exception as e:  # control plane unreachable / misconfigured
        if _fail_open():
            log.warning("entitlement check unavailable for org=%s module=%s; "
                        "failing open (FINTRA_FAIL_OPEN): %s", org_id, MODULE, e)
            return
        raise HTTPException(status_code=503,
                            detail={"message": "Entitlement service unavailable.",
                                    "code": "entitlement_unavailable"})


async def require_hr_access(request: Request, actor: Actor = Depends(require_org)) -> Actor:
    if _AVAILABLE and actor.org_id:
        set_fintra_context(request, org_id=actor.org_id, user_id=actor.user_id,
                           email=actor.claims.get("email"), platform_role=actor.role)
        if _enforce_on():
            _enforce_module_and_seat(actor.org_id, actor.user_id)
    return actor


async def require_hr_ai(request: Request, actor: Actor = Depends(require_org)) -> Actor:
    """Gate AI-powered HR routes on the org's AI entitlement."""
    if _AVAILABLE and _enforce_on() and actor.org_id:
        try:
            entitlements.require_ai(actor.org_id, MODULE)
        except EntitlementError as e:
            raise HTTPException(status_code=e.status_code,
                                detail={"message": e.message, "code": e.code, **e.detail})
        except HTTPException:
            raise
        except Exception as e:
            if _fail_open():
                log.warning("AI entitlement check unavailable for org=%s; failing open: %s", actor.org_id, e)
                return actor
            raise HTTPException(status_code=503,
                                detail={"message": "Entitlement service unavailable.",
                                        "code": "entitlement_unavailable"})
    return actor
