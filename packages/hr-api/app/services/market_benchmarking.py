from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
from uuid import UUID
from decimal import Decimal
from datetime import datetime
import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


@dataclass
class Benchmark:
    provider: str
    job_title: str
    location: str | None
    currency: str
    p50: float | None
    p75: float | None
    p90: float | None


class MarketProvider:
    name: str = "base"

    async def fetch(self, job_title: str, location: str | None, currency: str = "USD") -> Benchmark:
        raise NotImplementedError


class SalaryDotComProvider(MarketProvider):
    name = "salary.com"

    async def fetch(self, job_title: str, location: str | None, currency: str = "USD") -> Benchmark:
        return Benchmark(
            provider=self.name,
            job_title=job_title,
            location=location,
            currency=currency,
            p50=None,
            p75=None,
            p90=None,
        )


class MockProvider(MarketProvider):
    name = "mock"

    async def fetch(self, job_title: str, location: str | None, currency: str = "USD") -> Benchmark:
        base = float(abs(hash((job_title, location, currency))) % 150000 + 50000)
        return Benchmark(
            provider=self.name,
            job_title=job_title,
            location=location,
            currency=currency,
            p50=base,
            p75=base * 1.15,
            p90=base * 1.30,
        )


PROVIDERS: Dict[str, MarketProvider] = {
    "salary.com": SalaryDotComProvider(),
    "mock": MockProvider(),
}


def json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value


async def capture_benchmark(
    db: AsyncSession,
    org_id: UUID,
    provider: str,
    job_title: str,
    location: str | None,
    currency: str = "USD",
) -> Dict[str, Any]:
    prov = PROVIDERS.get(provider)
    if not prov:
        raise ValueError("Unknown provider")

    b = await prov.fetch(job_title, location, currency)

    raw_payload = {
        "provider": b.provider,
        "job_title": b.job_title,
        "location": b.location,
        "currency": b.currency,
        "benchmark_data": {
            "p50": b.p50,
            "p75": b.p75,
            "p90": b.p90,
        },
        "generated_at": datetime.utcnow().isoformat(),
    }

    res = await db.execute(
        text("""
            insert into public.market_benchmarks(
                id,
                org_id,
                provider,
                job_title,
                location,
                currency,
                p50,
                p75,
                p90,
                raw_payload,
                captured_at,
                created_at
            )
            values (
                gen_random_uuid(),
                :org_id,
                :provider,
                :job_title,
                :location,
                :currency,
                :p50,
                :p75,
                :p90,
                cast(:raw_payload as jsonb),
                now(),
                now()
            )
            returning
                id,
                org_id,
                provider,
                job_title,
                location,
                currency,
                p50,
                p75,
                p90,
                raw_payload,
                captured_at,
                created_at
        """),
        {
            "org_id": org_id,
            "provider": b.provider,
            "job_title": b.job_title,
            "location": b.location,
            "currency": b.currency,
            "p50": b.p50,
            "p75": b.p75,
            "p90": b.p90,
            "raw_payload": json.dumps(raw_payload),
        },
    )

    row = res.mappings().first()
    if not row:
        raise RuntimeError("Failed to insert market benchmark")

    return json_safe(dict(row))
