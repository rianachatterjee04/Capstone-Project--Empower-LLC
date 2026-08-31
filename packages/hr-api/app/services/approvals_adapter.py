"""Adapter seam: HR approvals -> platform approvals inbox.

TODO(platform-approvals): when the unified platform approvals inbox lands,
implement `emit_approval_request` to POST the event to the platform service
(same fail-soft pattern as app/integrations/internal_payroll.py — HR flows
must never block on the inbox being unavailable).

Today this is an intentional no-op stub so the time-off (and future) approval
flows already call through a single seam. Callers pass a normalized payload:

    emit_approval_request(
        org_id=...,
        kind="timeoff.request",          # namespaced approval kind
        entity_id=str(request.id),
        requested_by_user_id=...,
        summary="PTO 2026-07-10 → 2026-07-14 (Jane Doe)",
        payload={...},                    # kind-specific details
    )
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def emit_approval_request(
    *,
    org_id: str,
    kind: str,
    entity_id: str,
    requested_by_user_id: str | None = None,
    summary: str = "",
    payload: dict | None = None,
) -> None:
    """No-op stub. Never raises — approval emission is best-effort."""
    try:
        logger.debug(
            "approvals_adapter stub: org=%s kind=%s entity=%s summary=%s",
            org_id, kind, entity_id, summary,
        )
    except Exception:  # pragma: no cover — logging must never break the flow
        pass
