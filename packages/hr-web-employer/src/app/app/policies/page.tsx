"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";
import { PageHeader, Surface, SectionTitle, Pill, EmptyState } from "@/components/ds";

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

  const policies = q.data ?? [];

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Compliance"
        title="Policies"
        subtitle="English → executable DSL (heuristic compiler v1)."
      />

      <Surface className="space-y-3">
        <SectionTitle title="Create policy" />
        <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Textarea label="Policy text" rows={5} value={body} onChange={(e) => setBody(e.target.value)} />
        <Button onClick={create}>Create policy</Button>
      </Surface>

      <Surface>
        <SectionTitle title="Active policies" description={`${policies.length} total`} />
        {q.isLoading ? <div className="mt-3 text-sm text-muted">Loading…</div> : null}
        {q.error ? <div className="mt-3 text-sm text-danger-fg">{(q.error as Error).message}</div> : null}
        {!q.isLoading && policies.length === 0 ? (
          <EmptyState title="No policies yet" description="Create one above to compile it into executable DSL." />
        ) : (
          <div className="mt-4 space-y-3">
            {policies.map((p) => (
              <div key={p.id} className="rounded-md border border-line bg-canvas p-3">
                <div className="flex items-center gap-2">
                  <div className="font-medium text-sm text-ink">{p.name}</div>
                  <Pill tone="neutral">v{p.version}</Pill>
                </div>
                <div className="mt-1 text-sm text-body">{p.body}</div>
                <details className="mt-2">
                  <summary className="cursor-pointer text-sm text-muted hover:text-ink">View compiled DSL</summary>
                  <pre className="mt-2 overflow-auto rounded-md bg-sunken p-3 text-xs text-body">{JSON.stringify(p.dsl, null, 2)}</pre>
                </details>
              </div>
            ))}
          </div>
        )}
      </Surface>
    </div>
  );
}
