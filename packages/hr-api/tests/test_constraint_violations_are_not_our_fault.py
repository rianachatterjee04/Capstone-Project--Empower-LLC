"""
A database constraint violation is a 4xx, and says which field.

WHY THIS IS A TEST
A sweep of all 143 parameterless write endpoints found six that answered a
perfectly ordinary bad request with:

    500  {"message": "Internal Server Error"}

Creating a time-off policy whose name already existed, posting a benefit plan
without a name, referencing a job posting that does not exist -- each hit a
constraint, raised IntegrityError, fell through the global handler, and told
the caller our software had broken. It had not. Their request had, and we knew
exactly which column was at fault and did not say.

That is worse than rude. An integrator who sees 500 retries, escalates, or
concludes the API is unstable. A 409 "that record already exists" or a 422
"'name' is required" ends the conversation in one round trip.

THE SUBTLE PART
SQLAlchemy's asyncpg dialect wraps the driver error in its OWN IntegrityError,
so the asyncpg exception carrying column_name and constraint_name sits one
__cause__ deeper. The first implementation read exc.orig, found a dialect
wrapper every time, and classified nothing -- every violation came back as the
generic fallback. The control below fails if that unwrapping regresses.
"""
from __future__ import annotations

import asyncpg.exceptions as ae
import pytest
from sqlalchemy.exc import IntegrityError

from app.main import _violation_response


def _wrapped(asyncpg_exc):
    """Reproduce the two-layer shape SQLAlchemy actually delivers:
    IntegrityError.orig -> dialect wrapper -> __cause__ -> asyncpg error."""
    dialect_wrapper = Exception("(sqlalchemy.dialects.postgresql.asyncpg.IntegrityError)")
    dialect_wrapper.__cause__ = asyncpg_exc
    return IntegrityError("INSERT ...", {}, dialect_wrapper)


def _unique(constraint="time_off_policies_org_name_unique"):
    e = ae.UniqueViolationError("duplicate key value violates unique constraint")
    e.constraint_name = constraint
    return e


def _not_null(column="name", table="benefit_plans"):
    e = ae.NotNullViolationError(f'null value in column "{column}"')
    e.column_name = column
    e.table_name = table
    return e


def _fk(column="job_posting_id"):
    e = ae.ForeignKeyViolationError("insert or update violates foreign key constraint")
    e.column_name = column
    return e


def test_a_duplicate_is_a_conflict_not_a_crash():
    status, message = _violation_response(_wrapped(_unique()))
    assert status == 409, f"a duplicate should be 409 Conflict, got {status}"
    assert "already exists" in message
    assert "time_off_policies_org_name_unique" in message, (
        "naming the constraint is how the caller learns WHICH uniqueness they "
        f"violated; got {message!r}"
    )


def test_a_missing_column_names_the_column():
    status, message = _violation_response(_wrapped(_not_null()))
    assert status == 422, f"a missing required value should be 422, got {status}"
    assert message == "'name' is required", message


def test_a_bad_reference_names_the_column():
    status, message = _violation_response(_wrapped(_fk()))
    assert status == 422
    assert "job_posting_id" in message and "does not exist" in message, message


@pytest.mark.parametrize(
    "exc,expected",
    [
        (ae.CheckViolationError("check"), 422),
        (ae.ExclusionViolationError("exclusion"), 409),
    ],
)
def test_other_violations_are_still_client_errors(exc, expected):
    status, _ = _violation_response(_wrapped(exc))
    assert status == expected


def test_an_unclassified_violation_does_not_invent_a_reason():
    """We would rather say "the database rejected this write" than guess. It is
    still a 4xx -- the database refused it -- but the message must not claim a
    cause we did not establish."""
    status, message = _violation_response(_wrapped(ae.IntegrityConstraintViolationError("?")))
    assert status == 422
    assert "rejected" in message
    for invented in ("already exists", "is required", "does not exist"):
        assert invented not in message, (
            f"unclassified violation claimed {invented!r} without evidence: {message!r}"
        )


def test_reading_orig_alone_classifies_nothing(monkeypatch):
    """MUTATION CONTROL. The pre-fix implementation looked only at exc.orig.
    Confirm that shape really does fail to classify -- otherwise these tests
    would pass without the unwrapping and prove nothing."""
    wrapped = _wrapped(_not_null())
    surface = type(wrapped.orig).__name__
    assert surface not in (
        "NotNullViolationError", "UniqueViolationError", "ForeignKeyViolationError",
    ), (
        f"exc.orig is now {surface} directly, so the dialect no longer double-wraps "
        "and this control no longer proves the unwrapping is needed"
    )


def test_a_violation_never_returns_500():
    """The whole point. Every shape above must be a client error."""
    for exc in (_unique(), _not_null(), _fk(), ae.CheckViolationError("c"),
                ae.IntegrityConstraintViolationError("?")):
        status, _ = _violation_response(_wrapped(exc))
        assert 400 <= status < 500, (
            f"{type(exc).__name__} came back {status}; a constraint violation is "
            "the database refusing the request, never an internal failure"
        )
