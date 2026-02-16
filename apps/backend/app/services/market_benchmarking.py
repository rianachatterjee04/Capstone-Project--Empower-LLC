from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

@dataclass
class Benchmark:
    source: str
    job_title: str
    location: str | None
    currency: str
    p25: float | None
    p50: float | None
    p75: float | None

class MarketProvider:
    name: str = "base"
    async def fetch(self, job_title: str, location: str | None, currency: str = "USD") -> Benchmark:
        raise NotImplementedError

class SalaryDotComProvider(MarketProvider):
    name = "salary.com"
    async def fetch(self, job_title: str, location: str | None, currency: str = "USD") -> Benchmark:
        # TODO: Wire Salary.com with an API key / partner feed
        return Benchmark(source=self.name, job_title=job_title, location=location, currency=currency, p25=None, p50=None, p75=None)

class MockProvider(MarketProvider):
    name = "mock"
    async def fetch(self, job_title: str, location: str | None, currency: str = "USD") -> Benchmark:
        base = float(abs(hash((job_title, location, currency))) % 150000 + 50000)
        return Benchmark(source=self.name, job_title=job_title, location=location, currency=currency, p25=base*0.85, p50=base, p75=base*1.15)

PROVIDERS: Dict[str, MarketProvider] = {"salary.com": SalaryDotComProvider(), "mock": MockProvider()}

async def capture_benchmark(db: AsyncSession, org_id: UUID, provider: str, job_title: str, location: str | None, currency: str = "USD") -> Dict[str, Any]:
    prov = PROVIDERS.get(provider)
    if not prov:
        raise ValueError("Unknown provider")
    b = await prov.fetch(job_title, location, currency)
    res = await db.execute(text("""
        insert into public.market_benchmarks(org_id, source, job_title, location, currency, p25, p50, p75, captured_at)
        values (:org_id, :source, :job_title, :location, :currency, :p25, :p50, :p75, now())
        returning id
    """), {
        "org_id": str(org_id), "source": b.source, "job_title": b.job_title, "location": b.location,
        "currency": b.currency, "p25": b.p25, "p50": b.p50, "p75": b.p75
    })
    bid = res.first()[0]
    return {"id": str(bid), **b.__dict__}
