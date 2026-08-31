"""Sync -> async persistence bridge for the flagship HR modules.

goals / 1:1s / recognition / engagement / 9-box calibration used to be in-process
``_store`` dicts, so every deploy or restart wiped the data. Their service
functions are **synchronous** and their routers call them without a ``db``
session — and per the contract neither routers nor frontend may change. To back
these services with Postgres WITHOUT touching a single public signature, we run
async SQLAlchemy on a dedicated background event loop and bridge each sync call
through it (``q`` for reads, ``tx`` for writes).

Why a private engine on its own loop:
  * A dedicated ``NullPool`` engine hands out one connection per operation,
    created on the background loop — so an asyncpg connection is never shared
    with (or created on) the request event loop. That sidesteps the classic
    "got Future attached to a different loop" asyncpg failure.
  * ``db_available()`` probes once per process and caches the verdict. When
    DATABASE_URL is unset or the database is unreachable it returns False and
    each service transparently falls back to its in-process store — fail-soft,
    so the app still boots and every route still serves even with no DB.

Nothing here connects at import time; the engine and loop are created lazily on
first real use.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Optional

_log = logging.getLogger("hr.persistence")


def note_fallback(where: str, exc: BaseException) -> None:
    """Record that a DB op failed and the caller fell back to its in-memory
    store. Fail-soft keeps the app serving, but the write will not survive a
    restart — so surface it rather than swallowing it silently."""
    _log.warning("hr-persistence: falling back to memory in %s: %r", where, exc)

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

# ---------------------------------------------------------------------------
# Lazy engine (private, NullPool) + background event loop
# ---------------------------------------------------------------------------
_engine = None
_Session: Optional[async_sessionmaker] = None
_engine_lock = threading.Lock()

_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_bg_lock = threading.Lock()

_db_ok: Optional[bool] = None


def _connect_args(url: str) -> dict:
    low = (url or "").lower()
    # Supabase's transaction pooler (pgBouncer) cannot cache prepared statements.
    if "supabase.co" in low or "supabase.com" in low:
        return {"statement_cache_size": 0}
    return {}


def _ensure_engine():
    global _engine, _Session
    if _engine is not None:
        return _engine
    with _engine_lock:
        if _engine is None and settings.database_url:
            _engine = create_async_engine(
                settings.database_url,
                poolclass=NullPool,
                connect_args=_connect_args(settings.database_url),
            )
            _Session = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop
    if _bg_loop is not None:
        return _bg_loop
    with _bg_lock:
        if _bg_loop is None:
            loop = asyncio.new_event_loop()
            t = threading.Thread(
                target=loop.run_forever, name="hr-persist-loop", daemon=True
            )
            t.start()
            _bg_loop = loop
    return _bg_loop


def run(coro: Awaitable[Any]) -> Any:
    """Run a coroutine on the background loop and block for its result.

    Safe to call from the request event-loop thread: the coroutine executes on a
    *different* loop/thread, so ``.result()`` blocks the caller (matching the
    services' existing synchronous behaviour) without deadlocking.
    """
    loop = _ensure_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result()


@asynccontextmanager
async def session() -> AsyncSession:
    if _Session is None:
        _ensure_engine()
    if _Session is None:
        raise RuntimeError("DATABASE_URL is not configured")
    async with _Session() as s:  # type: ignore[misc]
        yield s


def db_available() -> bool:
    """Probe the database once per process; cache the verdict.

    False => the configured DB is unset/unreachable and callers must use their
    in-memory fallback.
    """
    global _db_ok
    if _db_ok is not None:
        return _db_ok
    if _ensure_engine() is None:
        _db_ok = False
        return _db_ok

    async def _probe() -> None:
        async with session() as s:
            await s.execute(text("select 1"))

    try:
        run(_probe())
        _db_ok = True
    except Exception:
        _db_ok = False
    return _db_ok


def reset_cache() -> None:
    """Test hook: drop the cached availability verdict (e.g. after the
    DATABASE_URL env changed) so the next ``db_available()`` re-probes."""
    global _db_ok
    _db_ok = None


# ---------------------------------------------------------------------------
# Sync query helpers
# ---------------------------------------------------------------------------
def q(sql: str, **params) -> list[dict]:
    """Run a SELECT and return rows as plain dicts (synchronously)."""

    async def _op() -> list[dict]:
        async with session() as s:
            res = await s.execute(text(sql), params)
            return [dict(r._mapping) for r in res]

    return run(_op())


def tx(async_fn: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
    """Run ``async_fn(session)`` inside one session, commit, return its result.

    Use for writes and any read-after-write that must share a transaction.
    """

    async def _op() -> Any:
        async with session() as s:
            result = await async_fn(s)
            await s.commit()
            return result

    return run(_op())


async def afetchall(s: AsyncSession, sql: str, **params) -> list[dict]:
    """Async SELECT helper for use inside a ``tx`` closure."""
    res = await s.execute(text(sql), params)
    return [dict(r._mapping) for r in res]


# ---------------------------------------------------------------------------
# JSON(b) round-tripping. asyncpg does not auto-encode dict/list for jsonb, and
# returns jsonb as a raw string, so we dump on write (with a ::jsonb cast in SQL)
# and load on read.
# ---------------------------------------------------------------------------
def json_dump(value: Any) -> str:
    return json.dumps(value if value is not None else None)


def json_load(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value
