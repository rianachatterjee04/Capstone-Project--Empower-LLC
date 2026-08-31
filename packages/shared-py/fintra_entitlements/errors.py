"""Typed entitlement errors. Map cleanly to HTTP status codes in fastapi.py."""
from __future__ import annotations


class EntitlementError(Exception):
    """Base class. `status_code` mirrors the intended HTTP response."""
    status_code = 403

    def __init__(self, message: str, *, code: str | None = None, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__
        self.detail = detail or {}


class ModuleNotLicensed(EntitlementError):
    """Org has no active subscription for the module → 402 Payment Required."""
    status_code = 402


class SeatRequired(EntitlementError):
    """Org is licensed but this user holds no seat (or seat limit reached) → 403."""
    status_code = 403


class AINotEnabled(EntitlementError):
    """AI is turned off for this org/module → 402 Payment Required."""
    status_code = 402


class AIQuotaExceeded(EntitlementError):
    """Monthly AI token budget exhausted → 429 Too Many Requests."""
    status_code = 429
