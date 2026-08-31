"""
Core entitlement logic — the cross-module generalization of accounting's
`license_gate` (enabled / require → 402). Adds seats, AI on/off, and AI token
quota metering against the control plane.
"""
from __future__ import annotations
from datetime import datetime, timezone

from . import client
from .cache import cache
from .errors import ModuleNotLicensed, SeatRequired, AINotEnabled, AIQuotaExceeded

_ACTIVE_SUB_STATUSES = {"trial", "active", "past_due"}  # past_due still works (grace)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


class Entitlements:
    # -- MODULE ACCESS ------------------------------------------------------
    def module_enabled(self, org_id: str, module_key: str) -> bool:
        sub = cache.get_or_set(
            f"sub:{org_id}:{module_key}", lambda: client.get_subscription(org_id, module_key)
        )
        if not sub or sub.get("status") not in _ACTIVE_SUB_STATUSES:
            return False
        end = _parse_ts(sub.get("term_end"))
        if end and end < _now():
            return False
        return True

    def require_module(self, org_id: str, module_key: str) -> None:
        if not self.module_enabled(org_id, module_key):
            raise ModuleNotLicensed(
                f"This workspace is not licensed for '{module_key}'. "
                f"Enable it in Settings → Modules, or contact your administrator.",
                code="module_not_licensed",
                detail={"module": module_key},
            )

    # -- SEATS --------------------------------------------------------------
    def has_seat(self, org_id: str, module_key: str, user_id: str) -> bool:
        sub = cache.get_or_set(
            f"sub:{org_id}:{module_key}", lambda: client.get_subscription(org_id, module_key)
        )
        if not sub:
            return False
        # seat_limit == 0 → unlimited: every org member may use the module.
        if int(sub.get("seat_limit") or 0) == 0:
            return True
        seat = cache.get_or_set(
            f"seat:{org_id}:{module_key}:{user_id}",
            lambda: client.get_seat(org_id, module_key, user_id),
        )
        return seat is not None

    def require_seat(self, org_id: str, module_key: str, user_id: str) -> None:
        if not self.has_seat(org_id, module_key, user_id):
            raise SeatRequired(
                f"You don't have a seat for '{module_key}'. "
                f"Ask an administrator to assign you a seat in Settings → Members.",
                code="seat_required",
                detail={"module": module_key},
            )

    def can_assign_seat(self, org_id: str, module_key: str) -> tuple[bool, int, int]:
        """Returns (ok, used, limit). limit 0 = unlimited."""
        sub = client.get_subscription(org_id, module_key)
        if not sub:
            return (False, 0, 0)
        limit = int(sub.get("seat_limit") or 0)
        used = client.count_seats(org_id, module_key)
        if limit == 0:
            return (True, used, 0)
        return (used < limit, used, limit)

    # -- ORG USER CAP -------------------------------------------------------
    def org_user_count(self, org_id: str) -> int:
        return client.count_members(org_id)

    def can_add_user(self, org_id: str) -> tuple[bool, int, int]:
        """Returns (ok, used, cap). cap 0 = unlimited."""
        org = client.get_org(org_id) or {}
        cap = int(org.get("max_users") or 0)
        used = client.count_members(org_id)
        if cap == 0:
            return (True, used, 0)
        return (used < cap, used, cap)

    def require_user_capacity(self, org_id: str) -> None:
        ok, used, cap = self.can_add_user(org_id)
        if not ok:
            raise SeatRequired(
                f"This workspace has reached its user limit ({used}/{cap}). "
                f"Upgrade the plan or remove an inactive member to add more.",
                code="org_user_limit_reached",
                detail={"org_id": org_id, "used": used, "cap": cap},
            )

    # -- PER-SEAT AI BUDGET -------------------------------------------------
    def _seat_ai_row(self, org_id: str, module_key: str, user_id: str) -> dict | None:
        seat = client.get_seat_full(org_id, module_key, user_id)
        if not seat:
            return None
        # roll the monthly per-seat window
        start = _parse_ts(seat.get("ai_period_start"))
        now = _now()
        if start and (start.year, start.month) != (now.year, now.month):
            new_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
            client.update_seat_ai(org_id, module_key, user_id, ai_tokens_used=0, ai_period_start=new_start)
            seat["ai_tokens_used"] = 0
            seat["ai_period_start"] = new_start
        return seat

    def seat_ai_budget(self, org_id: str, module_key: str, user_id: str) -> int:
        """Per-seat monthly AI budget. 0 = no per-seat cap (org pool governs)."""
        seat = self._seat_ai_row(org_id, module_key, user_id)
        if not seat:
            return 0
        override = int(seat.get("ai_token_limit") or 0)
        if override > 0:
            return override
        sub = cache.get_or_set(
            f"sub:{org_id}:{module_key}", lambda: client.get_subscription(org_id, module_key)
        ) or {}
        return int(sub.get("ai_tokens_per_seat") or 0)

    def seat_ai_remaining(self, org_id: str, module_key: str, user_id: str) -> int | None:
        """Remaining per-seat tokens; None = no per-seat cap (unlimited per seat)."""
        budget = self.seat_ai_budget(org_id, module_key, user_id)
        if budget <= 0:
            return None
        seat = self._seat_ai_row(org_id, module_key, user_id) or {}
        used = int(seat.get("ai_tokens_used") or 0)
        return max(0, budget - used)

    # -- AI ON/OFF ----------------------------------------------------------
    def ai_enabled(self, org_id: str, app_key: str) -> bool:
        sub = cache.get_or_set(
            f"sub:{org_id}:{app_key}", lambda: client.get_subscription(org_id, app_key)
        )
        return bool(sub and sub.get("ai_enabled"))

    def require_ai(self, org_id: str, app_key: str) -> None:
        if not self.ai_enabled(org_id, app_key):
            raise AINotEnabled(
                f"AI features are turned off for '{app_key}' on this plan. "
                f"Enable AI in Settings → AI, or upgrade your plan.",
                code="ai_not_enabled",
                detail={"app": app_key},
            )

    # -- AI TOKEN QUOTA (metered) ------------------------------------------
    def _quota_row(self, org_id: str, app_key: str) -> dict:
        row = client.get_quota(org_id, app_key)
        if not row:
            return {
                "org_id": org_id, "app_key": app_key, "period": "monthly",
                "token_budget": 0, "tokens_used": 0,
                "period_start": _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat(),
            }
        # roll over the monthly window if stale
        start = _parse_ts(row.get("period_start"))
        if row.get("period", "monthly") == "monthly" and start:
            now = _now()
            if (start.year, start.month) != (now.year, now.month):
                row["tokens_used"] = 0
                row["period_start"] = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
                client.upsert_quota({
                    "org_id": org_id, "app_key": app_key,
                    "tokens_used": 0, "period_start": row["period_start"],
                })
        return row

    def remaining_tokens(self, org_id: str, app_key: str) -> int:
        row = self._quota_row(org_id, app_key)
        budget = int(row.get("token_budget") or 0)
        used = int(row.get("tokens_used") or 0)
        return max(0, budget - used)

    def check_ai_quota(self, org_id: str, app_key: str, est_tokens: int = 0,
                       user_id: str | None = None) -> None:
        """Raise 429 if the (estimated) call would exceed the org pool OR the
        caller's per-seat budget. Enforcing both gives an org ceiling plus a
        per-user guardrail (one user can't drain the whole pool)."""
        est = max(0, int(est_tokens))
        # 1) org-wide pool
        row = self._quota_row(org_id, app_key)
        budget = int(row.get("token_budget") or 0)
        used = int(row.get("tokens_used") or 0)
        if budget <= 0:
            raise AIQuotaExceeded(
                f"No AI token budget allocated for '{app_key}'. Contact your administrator.",
                code="ai_quota_exceeded",
                detail={"app": app_key, "scope": "org", "budget": budget, "used": used},
            )
        if used + est > budget:
            raise AIQuotaExceeded(
                f"Monthly AI token budget exhausted for '{app_key}' "
                f"({used:,}/{budget:,}). Upgrade your plan or wait for the next cycle.",
                code="ai_quota_exceeded",
                detail={"app": app_key, "scope": "org", "budget": budget, "used": used},
            )
        # 2) per-seat budget (only if this seat has a cap configured)
        if user_id:
            seat_budget = self.seat_ai_budget(org_id, app_key, user_id)
            if seat_budget > 0:
                seat = self._seat_ai_row(org_id, app_key, user_id) or {}
                seat_used = int(seat.get("ai_tokens_used") or 0)
                if seat_used + est > seat_budget:
                    raise AIQuotaExceeded(
                        f"Your personal AI allowance for '{app_key}' is used up "
                        f"({seat_used:,}/{seat_budget:,}). Ask an administrator to raise your seat's limit.",
                        code="ai_seat_quota_exceeded",
                        detail={"app": app_key, "scope": "seat", "budget": seat_budget, "used": seat_used},
                    )

    def record_ai_usage(
        self, org_id: str, app_key: str, *, total_tokens: int,
        user_id: str | None = None, provider: str | None = None, model: str | None = None,
        prompt_tokens: int = 0, completion_tokens: int = 0,
        request_id: str | None = None, meta: dict | None = None,
    ) -> None:
        """Append an immutable ledger row and bump the fast-path counter."""
        client.insert_ledger({
            "org_id": org_id, "app_key": app_key, "user_id": user_id,
            "provider": provider, "model": model,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "total_tokens": total_tokens, "request_id": request_id, "meta": meta or {},
        })
        row = self._quota_row(org_id, app_key)
        client.upsert_quota({
            "org_id": org_id, "app_key": app_key,
            "token_budget": int(row.get("token_budget") or 0),
            "tokens_used": int(row.get("tokens_used") or 0) + max(0, int(total_tokens)),
            "period": row.get("period", "monthly"),
            "period_start": row.get("period_start"),
        })
        # per-seat meter (only if the caller occupies a seat)
        if user_id:
            seat = self._seat_ai_row(org_id, app_key, user_id)
            if seat:
                client.update_seat_ai(
                    org_id, app_key, user_id,
                    ai_tokens_used=int(seat.get("ai_tokens_used") or 0) + max(0, int(total_tokens)),
                )


entitlements = Entitlements()
