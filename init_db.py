import asyncio
from sqlalchemy import text

from app.db.session import engine
from app.db.models import Base
import app.db.models


async def init_all():
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
                p50 numeric, p75 numeric, p90 numeric,
                raw_payload jsonb,
                captured_at timestamptz not null default now(),
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create index if not exists idx_market_benchmarks_org_id on public.market_benchmarks(org_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_market_benchmarks_org_title on public.market_benchmarks(org_id, job_title)
        """))
        await conn.execute(text("""
            create index if not exists idx_market_benchmarks_captured_at on public.market_benchmarks(captured_at desc)
        """))

        await conn.execute(text("""
            create table if not exists public.pto_requests (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                employee_id uuid,
                start_date date not null,
                end_date date not null,
                reason text,
                status text default 'pending',
                reviewed_by_user_id uuid,
                reviewed_at timestamptz,
                review_note text,
                created_at timestamptz default now(),
                updated_at timestamptz default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.performance_cycles (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                name text not null,
                status text default 'open',
                start_date date,
                end_date date,
                opened_at timestamptz default now(),
                closed_at timestamptz,
                created_at timestamptz default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.performance_reviews (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                employee_id uuid,
                cycle text,
                cycle_id uuid,
                self_review jsonb default '{}',
                manager_review jsonb default '{}',
                ai_flags jsonb default '{}',
                ai_decision text,
                calibrated_rating numeric,
                outcome text,
                status text default 'draft',
                self_submitted_at timestamptz,
                manager_submitted_at timestamptz,
                finalized_at timestamptz,
                created_at timestamptz default now()
            )
        """))

        await conn.execute(text("""
            insert into public.pto_requests
                (org_id, employee_id, start_date, end_date, reason, status)
            values
                ('11111111-1111-1111-1111-111111111111','aaaa0001-0000-0000-0000-000000000002','2026-05-01','2026-05-03','Family vacation','pending'),
                ('11111111-1111-1111-1111-111111111111','aaaa0001-0000-0000-0000-000000000003','2026-04-20','2026-04-21','Medical appointment','approved'),
                ('11111111-1111-1111-1111-111111111111','aaaa0001-0000-0000-0000-000000000004','2026-04-10','2026-04-11','Personal day','denied'),
                ('11111111-1111-1111-1111-111111111111','aaaa0001-0000-0000-0000-000000000005','2026-06-01','2026-06-05','Summer vacation','pending')
            on conflict do nothing
        """))

        await conn.execute(text("""
            insert into public.performance_reviews
                (org_id, employee_id, cycle, status, ai_decision, self_review, manager_review)
            values
                ('11111111-1111-1111-1111-111111111111','aaaa0001-0000-0000-0000-000000000002',
                 'Q1 2026','finalized','normal',
                 '{"highlights":"Delivered auth service on time","growth":"Want to lead a project"}'::jsonb,
                 '{"rating":4,"notes":"Strong contributor, good communication"}'::jsonb),
                ('11111111-1111-1111-1111-111111111111','aaaa0001-0000-0000-0000-000000000003',
                 'Q1 2026','finalized','promotion',
                 '{"highlights":"Improved onboarding process","growth":"Ready for senior role"}'::jsonb,
                 '{"rating":5,"notes":"Exceptional performance, recommend promotion"}'::jsonb),
                ('11111111-1111-1111-1111-111111111111','aaaa0001-0000-0000-0000-000000000004',
                 'Q1 2026','draft',null,'{}','{}')
            on conflict do nothing
        """))

        print("✅ All tables created and seeded!")


if __name__ == "__main__":
    asyncio.run(init_all())
