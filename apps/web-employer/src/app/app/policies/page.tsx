"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

type Policy = { id: string; name: string; body: string; status: string; version: number; dsl: any; created_at: string };

export default function PoliciesPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("Harassment response SLA");
  const [body, setBody] = useState("All harassment complaints must be reviewed within 48 hours. High severity escalates to legal.");

  const q = useQuery({ queryKey: ["policies"], queryFn: () => apiFetch<Policy[]>("/policies") });

  async function create() {
    await apiPost("/policies", { name, body });
    await qc.invalidateQueries({ queryKey: ["policies"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Policies</div>
        <div className="text-sm text-black/60">English → executable DSL (heuristic compiler v1).</div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4 space-y-3">
        <div className="text-sm font-semibold">Create policy</div>
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Textarea label="Policy text" rows={5} value={body} onChange={(e) => setBody(e.target.value)} />
        <Button onClick={create}>Create policy</Button>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Active policies</div>
        {q.isLoading ? <div className="mt-3">Loading…</div> : null}
        {q.error ? <div className="mt-3 text-red-600">{(q.error as Error).message}</div> : null}
        <div className="mt-4 space-y-3">
          {(q.data ?? []).map((p) => (
            <div key={p.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{p.name} <span className="text-xs text-black/50">v{p.version}</span></div>
              <div className="mt-1 text-sm text-black/70">{p.body}</div>
              <details className="mt-2">
                <summary className="cursor-pointer text-sm text-black/60">View compiled DSL</summary>
                <pre className="mt-2 overflow-auto rounded-xl bg-black/5 p-3 text-xs">{JSON.stringify(p.dsl, null, 2)}</pre>
              </details>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
