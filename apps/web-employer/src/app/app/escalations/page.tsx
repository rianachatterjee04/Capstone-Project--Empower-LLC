"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { Textarea } from "@/components/Textarea";

type Rule = { id: string; name: string; entity_type: string; sla_minutes: number; severity_floor?: string | null; condition_dsl: any; route: any; is_active: boolean; created_at: string };
type Esc = { id: string; entity_type: string; entity_id: string; rule_id: string; level: number; status: string; due_at: string; last_notified_at?: string | null };

export default function EscalationsPage() {
  const qc = useQueryClient();
  const [name, setName] = useState("Harassment SLA 48h");
  const [sla, setSla] = useState(48 * 60);
  const [severity, setSeverity] = useState("high");
  const [condition, setCondition] = useState(JSON.stringify({ category_in: ["harassment"] }, null, 2));

  const rulesQ = useQuery({ queryKey: ["esc_rules"], queryFn: () => apiFetch<Rule[]>("/escalations/rules") });
  const escQ = useQuery({ queryKey: ["escalations"], queryFn: () => apiFetch<Esc[]>("/escalations") });

  async function createRule() {
    const condition_dsl = JSON.parse(condition);
    await apiPost("/escalations/rules", { name, entity_type: "case", sla_minutes: sla, severity_floor: severity, condition_dsl, route: { roles: ["manager","hr","legal","exec"] }, is_active: true });
    await qc.invalidateQueries({ queryKey: ["esc_rules"] });
  }

  const [runLoading, setRunLoading] = useState(false);
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  async function run() {
    setRunLoading(true);
    setRunError(null);
    setRunMessage(null);
    try {
      await apiPost("/escalations/run", {});
      await qc.invalidateQueries({ queryKey: ["escalations"] });
      setRunMessage("Evaluator completed. Refresh the list below if counts changed.");
    } catch (e) {
      setRunError((e as Error).message || "Request failed");
    } finally {
      setRunLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Escalations</div>
        <div className="text-sm text-black/60">SLA timers + auto escalation evaluator (run manually for now; wire to cron/Temporal).</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Create escalation rule</div>
          <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input label="SLA minutes" type="number" value={sla} onChange={(e) => setSla(parseInt(e.target.value || "0"))} />
          <Input label="Severity floor" value={severity} onChange={(e) => setSeverity(e.target.value)} />
          <Textarea label="Condition DSL (JSON)" rows={6} value={condition} onChange={(e) => setCondition(e.target.value)} />
          <Button onClick={createRule}>Create rule</Button>
        </div>

        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold">Run evaluator</div>
            <Button onClick={run} disabled={runLoading}>
              {runLoading ? "Running…" : "Run"}
            </Button>
          </div>
          <div className="text-xs text-black/60">
            The evaluator creates escalations for open cases and bumps level when overdue. Notification routing is stubbed.
          </div>
          {runError ? <div className="text-xs text-red-600">{runError}</div> : null}
          {runMessage ? <div className="text-xs text-green-700">{runMessage}</div> : null}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Rules</div>
        {rulesQ.isLoading ? <div className="mt-3">Loading…</div> : null}
        {rulesQ.error ? <div className="mt-3 text-red-600">{(rulesQ.error as Error).message}</div> : null}
        <div className="mt-4 space-y-2">
          {(rulesQ.data ?? []).map((r) => (
            <div key={r.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{r.name}</div>
              <div className="text-sm text-black/60">SLA: {r.sla_minutes} min • Severity ≥ {r.severity_floor ?? "any"}</div>
              <details className="mt-2">
                <summary className="cursor-pointer text-sm text-black/60">View DSL</summary>
                <pre className="mt-2 overflow-auto rounded-xl bg-black/5 p-3 text-xs">{JSON.stringify({ condition: r.condition_dsl, route: r.route }, null, 2)}</pre>
              </details>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Open escalations</div>
        {escQ.isLoading ? <div className="mt-3">Loading…</div> : null}
        {escQ.error ? <div className="mt-3 text-red-600">{(escQ.error as Error).message}</div> : null}
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
          {(escQ.data ?? []).map((e) => (
            <div key={e.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{e.entity_type} • {e.status}</div>
              <div className="text-xs text-black/60">Level: {e.level} • Due: {new Date(e.due_at).toLocaleString()}</div>
              <div className="mt-1 text-xs text-black/60">Entity: {e.entity_id}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
