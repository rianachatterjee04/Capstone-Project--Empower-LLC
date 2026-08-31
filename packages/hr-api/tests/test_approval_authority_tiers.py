"""P0.3 — amount-tier approval authority + router wiring.

Proves, WITHOUT a live Postgres:
  1. The orgs + comp_cycle routers are now mounted on the API router.
  2. The approval_authority tier-resolution SQL (same predicate as
     app/api/routers/approvals._check_authority) authorizes a spend by amount
     tier and fails closed when no tier covers the amount — including the
     $50M spend-approval path the audit flagged as dead.
  3. A per-user override tier wins over the role tier.

The tier SQL is exercised against an in-memory SQLite table with the same
columns as the migration, so no external DB is required.
"""
import sqlite3

import pytest


# ---- 1. Routers are mounted ------------------------------------------------

def test_orgs_and_comp_cycle_routers_mounted():
    import app.api.router as r
    paths = [getattr(rt, "path", "") for rt in r.api_router.routes]
    assert any(p.startswith("/orgs") for p in paths), "orgs router not mounted"
    assert any(p.startswith("/compcycle") for p in paths), "comp_cycle router not mounted"


def test_approvals_router_mounted():
    import app.api.router as r
    paths = [getattr(rt, "path", "") for rt in r.api_router.routes]
    assert any(p.startswith("/approvals") for p in paths)


def test_userprofile_model_maps_user_profiles_table():
    from app.db.models import UserProfile
    assert UserProfile.__tablename__ == "user_profiles"


# ---- 2/3. Amount-tier authority resolution (SQLite mirror of the SQL) ------
# Same predicate as approvals._check_authority:
#   active, amount in [min_amount, max_amount], and (per-user override OR role),
#   preferring a per-user override.
_TIER_SQL = """
    select max_amount
    from approval_authority
    where org_id = :org_id
      and active = 1
      and :amount >= min_amount
      and :amount <= max_amount
      and (
            (user_id is not null and user_id = :user_id)
         or (user_id is null and role = :role)
      )
    order by (user_id is not null) desc
    limit 1
"""


@pytest.fixture()
def authdb():
    con = sqlite3.connect(":memory:")
    con.execute("""
        create table approval_authority(
            id integer primary key,
            org_id text not null,
            role text,
            user_id text,
            min_amount real not null default 0,
            max_amount real not null,
            active integer not null default 1
        )
    """)
    org = "org1"
    # Default tier ladder that orgs.py seeds (min defaults to 0 -> each role can
    # approve up to its ceiling).
    tiers = [
        ("manager", None, 0, 5_000),
        ("director", None, 0, 25_000),
        ("vp", None, 0, 100_000),
        ("cfo", None, 0, 1_000_000),
        ("owner", None, 0, 999_999_999),
    ]
    for role, uid, lo, hi in tiers:
        con.execute("insert into approval_authority(org_id, role, user_id, min_amount, max_amount)"
                    " values (?,?,?,?,?)", (org, role, uid, lo, hi))
    con.commit()
    yield con, org
    con.close()


def _authorized(con, org, role, amount, user_id=None):
    row = con.execute(_TIER_SQL, {"org_id": org, "role": role,
                                  "amount": float(amount), "user_id": user_id}).fetchone()
    return row is not None


def test_manager_can_approve_within_ceiling(authdb):
    con, org = authdb
    assert _authorized(con, org, "manager", 4_999) is True
    assert _authorized(con, org, "manager", 5_000) is True   # inclusive ceiling


def test_manager_cannot_approve_above_ceiling(authdb):
    con, org = authdb
    assert _authorized(con, org, "manager", 5_001) is False
    assert _authorized(con, org, "manager", 50_000) is False


def test_cfo_authorizes_large_spend_but_not_beyond_ceiling(authdb):
    con, org = authdb
    assert _authorized(con, org, "cfo", 1_000_000) is True
    assert _authorized(con, org, "cfo", 1_000_001) is False


def test_owner_authorizes_50m_spend(authdb):
    """The $50M spend-approval path the audit flagged as dead: owner tier
    (ceiling 999,999,999) authorizes a $50,000,000 request."""
    con, org = authdb
    assert _authorized(con, org, "owner", 50_000_000) is True


def test_unknown_role_fails_closed(authdb):
    con, org = authdb
    assert _authorized(con, org, "intern", 100) is False


def test_no_tier_covering_amount_fails_closed(authdb):
    con, org = authdb
    # Above every ceiling -> not authorized for anyone.
    assert _authorized(con, org, "owner", 2_000_000_000) is False


def test_per_user_override_wins_over_role(authdb):
    con, org = authdb
    # Give a specific manager user a raised personal ceiling of $250k.
    con.execute("insert into approval_authority(org_id, role, user_id, min_amount, max_amount)"
                " values (?,?,?,?,?)", (org, None, "user-super", 0, 250_000))
    con.commit()
    # That user can approve $200k even though the 'manager' role tops out at $5k.
    assert _authorized(con, org, "manager", 200_000, user_id="user-super") is True
    # A different manager user with no override still fails above the role ceiling.
    assert _authorized(con, org, "manager", 200_000, user_id="user-plain") is False


def test_inactive_tier_ignored(authdb):
    con, org = authdb
    con.execute("update approval_authority set active=0 where role='owner'")
    con.commit()
    assert _authorized(con, org, "owner", 50_000_000) is False
