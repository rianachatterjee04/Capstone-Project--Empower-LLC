"""Stub notifications service."""
from __future__ import annotations
from typing import Any
import uuid


async def enqueue_notification(
    db: Any,
    org_id: Any,
    employee_id: Any,
    notification_type: str,
    payload: dict | None = None,
) -> None:
    """Stub: enqueue a notification. Replace with real push/email logic."""
    pass