"""Pay Equity router — EU Pay Transparency Directive readiness.

Org-scoped, deterministic, fail-soft. Mounted at /api/pay-equity.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import Actor, require_org
from app.services import pay_equity_service as svc


router = APIRouter(prefix="/pay-equity", tags=["pay-equity"])

# Pay data is sensitive — restrict to comp/HR leadership.
_ALLOWED = ("owner", "admin", "hr")


def _guard(actor: Actor) -> None:
    if actor.role not in _ALLOWED:
        raise HTTPException(status_code=403, detail="Not allowed — pay-equity data is restricted to HR/admin")


def _threshold(v) -> float:
    try:
        t = float(v)
    except (TypeError, ValueError):
        return svc.DEFAULT_THRESHOLD
    if t <= 0 or t >= 1:
        return svc.DEFAULT_THRESHOLD
    return t


@router.get("/analysis")
async def analysis(
    attribute: str = "gender",
    threshold: float | None = None,
    actor: Actor = Depends(require_org),
):
    _guard(actor)
    return svc.org_analysis(actor.org_id, attr=attribute, threshold=_threshold(threshold))


@router.get("/employee/{employee_id}")
async def employee(employee_id: str, attribute: str = "gender", actor: Actor = Depends(require_org)):
    _guard(actor)
    out = svc.org_employee_position(actor.org_id, employee_id, attr=attribute)
    if not out:
        raise HTTPException(status_code=404, detail="Employee not found in pay-equity dataset")
    return out


@router.post("/remediation-plan")
async def remediation(payload: dict | None = None, actor: Actor = Depends(require_org)):
    _guard(actor)
    payload = payload or {}
    return svc.org_remediation(
        actor.org_id,
        attr=str(payload.get("attribute") or "gender"),
        threshold=_threshold(payload.get("threshold")),
    )


@router.get("/report")
async def report(
    attribute: str = "gender",
    threshold: float | None = None,
    actor: Actor = Depends(require_org),
):
    _guard(actor)
    return svc.compliance_report(actor.org_id, attr=attribute, threshold=_threshold(threshold))


@router.get("/employees")
async def employees(actor: Actor = Depends(require_org)):
    """Underlying dataset (for the frontend table)."""
    _guard(actor)
    return {"items": [e.to_dict() for e in svc.list_employees(actor.org_id)]}
