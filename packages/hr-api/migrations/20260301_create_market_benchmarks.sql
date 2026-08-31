create extension if not exists pgcrypto;

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
);

alter table public.market_benchmarks
    alter column id set default gen_random_uuid();

create index if not exists idx_market_benchmarks_org_id
    on public.market_benchmarks(org_id);

create index if not exists idx_market_benchmarks_org_title
    on public.market_benchmarks(org_id, job_title);

create index if not exists idx_market_benchmarks_captured_at
    on public.market_benchmarks(captured_at desc);
