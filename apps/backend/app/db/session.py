from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

engine = None
AsyncSessionLocal = None

if settings.database_url:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    if AsyncSessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured. Database session is unavailable.")

    async with AsyncSessionLocal() as session:
        yield session
