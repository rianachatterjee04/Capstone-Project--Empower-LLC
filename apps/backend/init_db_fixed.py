import asyncio
from sqlalchemy import text

from app.db.session import engine
from app.db.models import Base
import app.db.models


async def init_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(text("create extension if not exists pgcrypto"))

        # =========================================================
        # MARKET BENCHMARKS
        # =========================================================
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
            add column if not exists provider text
        """))
        await conn.execute(text("""
            alter table public.market_benchmarks
            add column if not exists p90 numeric
        """))
        await conn.execute(text("""
            alter table public.market_benchmarks
            add column if not exists raw_payload jsonb
        """))
        await conn.execute(text("""
            alter table public.market_benchmarks
            add column if not exists created_at timestamptz not null default now()
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

        # =========================================================
        # BONUS POOLS
        # =========================================================
        await conn.execute(text("""
            create table if not exists public.bonus_pools (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                name text not null,
                cycle_id uuid null,
                currency text not null default 'USD',
                total_amount numeric not null,
                status text not null default 'draft',
                finalized_at timestamptz null,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.bonus_allocations (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                pool_id uuid not null,
                employee_id uuid not null,
                amount numeric null,
                basis jsonb null,
                adjusted boolean not null default false,
                adjusted_reason text null,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            alter table public.bonus_allocations
            add column if not exists amount numeric
        """))
        await conn.execute(text("""
            alter table public.bonus_allocations
            add column if not exists basis jsonb
        """))
        await conn.execute(text("""
            alter table public.bonus_allocations
            add column if not exists adjusted boolean not null default false
        """))
        await conn.execute(text("""
            alter table public.bonus_allocations
            add column if not exists adjusted_reason text
        """))
        await conn.execute(text("""
            alter table public.bonus_allocations
            add column if not exists created_at timestamptz not null default now()
        """))

        await conn.execute(text("""
            create index if not exists idx_bonus_pools_org_id
            on public.bonus_pools(org_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_bonus_allocations_org_id
            on public.bonus_allocations(org_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_bonus_allocations_pool_id
            on public.bonus_allocations(pool_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_bonus_allocations_employee_id
            on public.bonus_allocations(employee_id)
        """))

        # =========================================================
        # BENEFITS
        # =========================================================
        await conn.execute(text("""
            create table if not exists public.benefit_plans (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                name text not null,
                provider text,
                category text,
                employer_cost numeric not null default 0,
                employee_cost numeric not null default 0,
                metadata jsonb,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.benefit_enrollment_windows (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                start_date date not null,
                end_date date not null,
                fiscal_year integer,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.employee_benefit_elections (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                employee_id uuid not null,
                plan_id uuid not null,
                elected_on date,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.benefit_life_events (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                employee_id uuid not null,
                event_type text not null,
                event_date date not null,
                metadata jsonb,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.benefit_optimization_runs (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                fiscal_year integer,
                budget numeric,
                result jsonb,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create index if not exists idx_benefit_plans_org_id
            on public.benefit_plans(org_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_benefit_enrollment_windows_org_id
            on public.benefit_enrollment_windows(org_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_employee_benefit_elections_org_id
            on public.employee_benefit_elections(org_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_benefit_life_events_org_id
            on public.benefit_life_events(org_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_benefit_optimization_runs_org_id
            on public.benefit_optimization_runs(org_id)
        """))

        # =========================================================
        # POLICY VERSIONS / RULES / EXECUTIONS
        # =========================================================
        await conn.execute(text("""
            create table if not exists public.policy_versions (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                policy_id uuid not null references public.policies(id) on delete cascade,
                version integer not null default 1,
                policy_text text not null,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.policy_rules (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                policy_version_id uuid not null references public.policy_versions(id) on delete cascade,
                rule jsonb not null,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create table if not exists public.policy_executions (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                policy_version_id uuid not null,
                context jsonb,
                results jsonb,
                executed_at timestamptz not null default now(),
                executed_by uuid null
            )
        """))

        await conn.execute(text("""
            create index if not exists idx_policy_versions_policy_id
            on public.policy_versions(policy_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_policy_rules_policy_version_id
            on public.policy_rules(policy_version_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_policy_executions_org_id
            on public.policy_executions(org_id)
        """))

        # =========================================================
        # INTEGRATIONS
        # =========================================================
        await conn.execute(text("""
            create table if not exists public.integration_connections (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                provider text not null,
                status text not null default 'pending',
                token_ciphertext text null,
                refresh_ciphertext text null,
                webhook_secret text null,
                scopes jsonb null,
                external_account_id text null,
                created_at timestamptz not null default now(),
                updated_at timestamptz not null default now(),
                unique (org_id, provider)
            )
        """))

        await conn.execute(text("""
            create table if not exists public.integration_events (
                id uuid primary key default gen_random_uuid(),
                org_id uuid not null,
                provider text not null,
                event_type text null,
                external_id text null,
                payload jsonb null,
                created_at timestamptz not null default now()
            )
        """))

        await conn.execute(text("""
            create index if not exists idx_integration_connections_org_id
            on public.integration_connections(org_id)
        """))
        await conn.execute(text("""
            create index if not exists idx_integration_events_org_id
            on public.integration_events(org_id)
        """))

    print("✅ Database tables created successfully!")


if __name__ == "__main__":
    asyncio.run(init_models())