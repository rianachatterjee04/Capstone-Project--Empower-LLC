"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function MarketPage() {
  const qc = useQueryClient();
  const providersQ = useQuery({ queryKey: ["market_providers"], queryFn: () => apiFetch<{ providers: string[] }>("/market/providers") });
  const listQ = useQuery({ queryKey: ["benchmarks"], queryFn: () => apiFetch<any[]>("/market/benchmarks") });

  const [provider, setProvider] = useState("mock");
  const [jobTitle, setJobTitle] = useState("Software Engineer");
  const [location, setLocation] = useState("Austin, TX");

  async function capture() {
    await apiPost("/market/capture", { provider, job_title: jobTitle, location });
    await qc.invalidateQueries({ queryKey: ["benchmarks"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Market Benchmarking</div>
        <div className="text-sm text-black/60">Provider pattern (mock works now; Salary.com stub included for wiring).</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="text-sm font-semibold">Capture benchmark</div>
        <Input label="Provider" value={provider} onChange={(e) => setProvider(e.target.value)} />
        <div className="text-xs text-black/50">Available: {(providersQ.data?.providers ?? []).join(", ")}</div>
        <Input label="Job title" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
        <Input label="Location" value={location} onChange={(e) => setLocation(e.target.value)} />
        <Button onClick={capture}>Capture</Button>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Recent benchmarks</div>
        <div className="mt-4 space-y-2">
          {(listQ.data ?? []).map((b) => (
            <div key={b.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{b.source} • {b.job_title}</div>
              <div className="text-xs text-black/60">{b.location ?? "—"} • {b.currency}</div>
              <div className="text-xs text-black/60">p25 {b.p25 ?? "—"} • p50 {b.p50 ?? "—"} • p75 {b.p75 ?? "—"}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
