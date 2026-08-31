from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = None
AsyncSessionLocal = None


def _engine_kwargs(url: str) -> dict:
    """Build create_async_engine kwargs, adapting to Supabase's pooler.

    Supabase exposes three connection modes:
      - Direct           db.<ref>.supabase.co:5432       (IPv6, no pooler)
      - Session pooler   aws-0-<region>.pooler.supabase.com:5432
      - Transaction pool aws-0-<region>.pooler.supabase.com:6543

    asyncpg caches prepared statements by default, which the *transaction*
    pooler (pgBouncer) cannot support — it raises
    `prepared statement "__asyncpg_..." does not exist`. Disabling the
    statement cache fixes it and is harmless on the other modes. We also
    disable SQLAlchemy's own pooling when talking to a server-side pooler to
    avoid double-pooling.
    """
    kwargs: dict = {"pool_pre_ping": True}
    lowered = (url or "").lower()
    is_supabase = "supabase.co" in lowered or "supabase.com" in lowered
    is_server_pooler = "pooler.supabase.com" in lowered

    if is_supabase:
        # asyncpg-specific: turn off the prepared-statement cache so the
        # transaction pooler works. (SQLAlchemy passes connect_args to the
        # asyncpg driver.)
        kwargs["connect_args"] = {"statement_cache_size": 0}

    if is_server_pooler:
        # The server already pools; use NullPool client-side.
        from sqlalchemy.pool import NullPool
        kwargs["poolclass"] = NullPool
        kwargs.pop("pool_pre_ping", None)

    return kwargs


if settings.database_url:
    engine = create_async_engine(settings.database_url, **_engine_kwargs(settings.database_url))
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured. Database session is unavailable.")

    async with AsyncSessionLocal() as session:
        yield session

from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_session_internal():
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured.")
    async with AsyncSessionLocal() as session:
        yield session
