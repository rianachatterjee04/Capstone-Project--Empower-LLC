"""
Launch-gate logic tests — prove the entitlement decisions without live Supabase.
We fake the thin client accessors (the seam) and exercise the real gate logic.

Run: cd packages/shared-py && python -m pytest tests/ -q   (or: python tests/test_gate.py)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fintra_entitlements import client as cp
from fintra_entitlements.gate import Entitlements
from fintra_entitlements.cache import cache
from fintra_entitlements.errors import (
    ModuleNotLicensed, SeatRequired, AINotEnabled, AIQuotaExceeded,
)

ORG = "org-1"
USER = "user-1"


class FakeStore:
    def __init__(self):
        self.subs = {}      # (org,module) -> dict
        self.seats = set()  # (org,module,user)
        self.quota = {}     # (org,app) -> dict
        self.ledger = []

    def install(self):
        cp.get_subscription = lambda o, m: self.subs.get((o, m))
        cp.get_seat = lambda o, m, u: ({"user_id": u} if (o, m, u) in self.seats else None)
        cp.count_seats = lambda o, m: sum(1 for (a, b, _) in self.seats if a == o and b == m)
        cp.get_quota = lambda o, a: self.quota.get((o, a))
        cp.upsert_quota = lambda row: self.quota.__setitem__((row["org_id"], row["app_key"]), {**self.quota.get((row["org_id"], row["app_key"]), {}), **row})
        cp.insert_ledger = lambda row: self.ledger.append(row)
        cache.clear()


def check(label, fn, expect_exc=None):
    try:
        fn()
        ok = expect_exc is None
    except Exception as e:
        ok = expect_exc is not None and isinstance(e, expect_exc)
        if not ok:
            print(f"  ✗ {label}: unexpected {type(e).__name__}: {e}")
            return False
    status = "✓" if ok else "✗"
    print(f"  {status} {label}")
    return ok


def main():
    store = FakeStore()
    store.install()
    ent = Entitlements()
    results = []

    print("1) No subscription → module blocked (402)")
    results.append(check("require_module raises ModuleNotLicensed", lambda: ent.require_module(ORG, "hr"), ModuleNotLicensed))

    print("2) Licensed (seat_limit=1), no seat → 403")
    store.subs[(ORG, "hr")] = {"status": "active", "seat_limit": 1, "ai_enabled": False, "term_end": None}
    cache.clear()
    results.append(check("require_module passes", lambda: ent.require_module(ORG, "hr")))
    results.append(check("require_seat raises SeatRequired", lambda: ent.require_seat(ORG, "hr", USER), SeatRequired))

    print("3) Assign seat → access granted")
    store.seats.add((ORG, "hr", USER)); cache.clear()
    results.append(check("require_seat passes", lambda: ent.require_seat(ORG, "hr", USER)))

    print("4) Seat limit reached → can_assign_seat false for 2nd user")
    ok, used, limit = ent.can_assign_seat(ORG, "hr")
    results.append(check(f"limit reached (used={used}, limit={limit})", lambda: None if not ok else (_ for _ in ()).throw(AssertionError())))

    print("5) AI disabled → 402; enable → ok")
    results.append(check("require_ai raises AINotEnabled", lambda: ent.require_ai(ORG, "hr"), AINotEnabled))
    store.subs[(ORG, "hr")]["ai_enabled"] = True; cache.clear()
    results.append(check("require_ai passes", lambda: ent.require_ai(ORG, "hr")))

    print("6) AI quota: budget 1000, use 900 ok, then exceed → 429")
    store.quota[(ORG, "hr")] = {"org_id": ORG, "app_key": "hr", "period": "monthly", "token_budget": 1000, "tokens_used": 0, "period_start": "2999-01-01T00:00:00+00:00"}
    results.append(check("check_ai_quota(900) ok", lambda: ent.check_ai_quota(ORG, "hr", 900)))
    ent.record_ai_usage(ORG, "hr", total_tokens=900, provider="openai", model="gpt", prompt_tokens=600, completion_tokens=300)
    results.append(check("ledger appended", lambda: None if store.ledger else (_ for _ in ()).throw(AssertionError())))
    results.append(check("check_ai_quota(200) over budget → 429", lambda: ent.check_ai_quota(ORG, "hr", 200), AIQuotaExceeded))

    print("7) Unlimited seats (seat_limit=0) → any member seated")
    store.subs[(ORG, "accounting")] = {"status": "active", "seat_limit": 0, "ai_enabled": True, "term_end": None}
    cache.clear()
    results.append(check("has_seat true under unlimited", lambda: None if ent.has_seat(ORG, "accounting", "random") else (_ for _ in ()).throw(AssertionError())))

    print("8) Expired term → blocked")
    store.subs[(ORG, "compliance")] = {"status": "active", "seat_limit": 5, "ai_enabled": True, "term_end": "2000-01-01T00:00:00+00:00"}
    cache.clear()
    results.append(check("expired → ModuleNotLicensed", lambda: ent.require_module(ORG, "compliance"), ModuleNotLicensed))

    passed = sum(1 for r in results if r)
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
