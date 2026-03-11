import asyncio
from sqlalchemy import text

from app.db.session import engine
from app.db.models import Base
import app.db.models  # ensures all models are registered


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(text("create extension if not exists pgcrypto"))

        await conn.execute(text("""
            create table if not exists public.market_benchmarks (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                provider text not null,
                job_title text not null,
                location text,
                currency text not null default 'USD',
                p50 numeric,
                p75 numeric,
                p90 numeric,
                raw_payload jsonb,
                captured_at timestamptz not null default now(),
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            alter table public.market_benchmarks
            alter column id set default gen_random_uuid()
        """))

        await conn.execute(text("""
            create index if not exists idx_market_benchmarks_org_id
            on public.market_benchmarks(org_id)
        """))

        await conn.execute(text("""
            create index if not exists idx_market_benchmarks_org_title
            on public.market_benchmarks(org_id, job_title)
        """))

        await conn.execute(text("""
            create index if not exists idx_market_benchmarks_captured_at
            on public.market_benchmarks(captured_at desc)
        """))

    print("✅ Database tables created successfully!")


if __name__ == "__main__":
    asyncio.run(init_models())
