"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function BonusesPage() {
  const qc = useQueryClient();
  const poolsQ = useQuery({ queryKey: ["bonus_pools"], queryFn: () => apiFetch<any[]>("/bonuses/pools") });

  const [name, setName] = useState("Annual Bonus Pool");
  const [total, setTotal] = useState(100000);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    setError(null);
    try {
      await apiPost("/bonuses/pools", { name, total_amount: total, currency: "USD" });
      await qc.invalidateQueries({ queryKey: ["bonus_pools"] });
    } catch (e) {
      setError((e as Error).message || "Create failed");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Bonus Pools</div>
        <div className="text-sm text-black/60">Create and list bonus pools. Allocation is handled outside this page for now.</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="text-sm font-semibold">Create pool</div>
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Input label="Total amount" type="number" value={total} onChange={(e) => setTotal(parseFloat(e.target.value || "0"))} />
        <Button onClick={create}>Create</Button>
      </div>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">{error}</div>
      ) : null}

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Pools</div>
        <div className="mt-4 space-y-2">
          {(poolsQ.data ?? []).map((p) => (
            <div key={p.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{p.name}</div>
              <div className="text-xs text-black/60">Total: {p.total_amount} • Status: {p.status}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
