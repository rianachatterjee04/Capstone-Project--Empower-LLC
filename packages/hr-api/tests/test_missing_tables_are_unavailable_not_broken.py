"""
A table this deployment never got is 503 and says which one.

WHY THIS IS A TEST
Several routers already check for their table and answer

    503  "documents table is not available yet. Run the documents migration first."

That is the right answer. The feature was never installed here, the operator
knows exactly what to run, and nobody is told our software broke.

Routers without that check answered the identical situation with 500 "Internal
Server Error". The sweep of parameterless writes found five, on tables
including ai_decisions and expo_push_tokens -- so whether a customer saw an
honest "not provisioned" or an alarming "internal error" depended only on
whether that particular router's author had remembered to write the check.

THE LINE THIS DRAWS
A missing TABLE is a feature that was never installed: operator-fixable, 503.
A missing COLUMN means the code and the schema disagree about a table that does
exist. That is our bug, it stays a 500, and it stays loud. Blurring the two
would let real schema drift hide behind a reassuring "not provisioned yet".
"""
from __future__ import annotations

import asyncpg.exceptions as ae
from sqlalchemy.exc import ProgrammingError

from app.main import _missing_table


def _wrapped(asyncpg_exc):
    """The two-layer shape SQLAlchemy's asyncpg dialect actually delivers."""
    dialect_wrapper = Exception("(sqlalchemy.dialects.postgresql.asyncpg.ProgrammingError)")
    dialect_wrapper.__cause__ = asyncpg_exc
    return ProgrammingError("SELECT ...", {}, dialect_wrapper)


def test_a_missing_table_is_named():
    exc = _wrapped(ae.UndefinedTableError('relation "public.ai_decisions" does not exist'))
    assert _missing_table(exc) == "public.ai_decisions", (
        "the response must name the table, or the operator has to read our logs "
        "to find out which migration to run"
    )


def test_a_missing_column_is_not_treated_as_a_missing_table():
    """The important negative. A column that does not exist is schema drift --
    our defect -- and must not be dressed up as an unprovisioned feature."""
    exc = _wrapped(ae.UndefinedColumnError('column "hire_date" does not exist'))
    assert _missing_table(exc) is None, (
        "an UndefinedColumnError was classified as a missing table. Real schema "
        "drift would then answer 503 'not available in this deployment', which "
        "is false and sends the operator to run a migration that will not help."
    )


def test_an_ordinary_bad_statement_is_not_a_missing_table():
    exc = _wrapped(ae.PostgresSyntaxError('syntax error at or near ":"'))
    assert _missing_table(exc) is None


def test_an_unwrapped_error_is_still_recognised():
    """Not every path double-wraps; the unwrap loop must cope with either."""
    direct = ProgrammingError("SELECT ...", {},
                              ae.UndefinedTableError('relation "public.expo_push_tokens" does not exist'))
    assert _missing_table(direct) == "public.expo_push_tokens"


def test_an_unparseable_message_still_reports_unavailable():
    """We would rather say "a required table" than crash inside the handler that
    exists to stop crashes."""
    exc = _wrapped(ae.UndefinedTableError("something we did not anticipate"))
    assert _missing_table(exc) == "a required table"


def test_the_classifier_is_not_matching_on_message_text_alone():
    """MUTATION CONTROL. A classifier that just grepped for 'does not exist'
    would also catch UndefinedColumnError and UndefinedFunctionError, which is
    exactly the confusion this guard exists to prevent."""
    for wrong in (
        ae.UndefinedColumnError('column "x" does not exist'),
        ae.UndefinedFunctionError('function f() does not exist'),
        ae.UndefinedObjectError('type "t" does not exist'),
    ):
        assert _missing_table(_wrapped(wrong)) is None, (
            f"{type(wrong).__name__} was classified as a missing table -- the "
            "check is reading the message rather than the exception type"
        )
