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

  async function create() {
    await apiPost("/bonuses/pools", { name, total_amount: total, currency: "USD" });
    await qc.invalidateQueries({ queryKey: ["bonus_pools"] });
  }

  async function calc(id: string) {
    await apiPost(`/bonuses/pools/${id}/calculate`, {});
    await qc.invalidateQueries({ queryKey: ["bonus_pools"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Bonus Pools</div>
        <div className="text-sm text-black/60">Payout calculator based on performance rating weights (extendable).</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="text-sm font-semibold">Create pool</div>
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Input label="Total amount" type="number" value={total} onChange={(e) => setTotal(parseFloat(e.target.value || "0"))} />
        <Button onClick={create}>Create</Button>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Pools</div>
        <div className="mt-4 space-y-2">
          {(poolsQ.data ?? []).map((p) => (
            <div key={p.id} className="rounded-xl border border-black/10 p-3 flex items-center justify-between">
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-black/60">Total: {p.total_amount} • Status: {p.status}</div>
              </div>
              <Button onClick={() => calc(p.id)}>Calculate</Button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
