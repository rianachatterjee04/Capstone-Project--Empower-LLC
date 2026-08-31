"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";
import { PageHeader, Surface, SectionTitle, EmptyState } from "@/components/ds";

export default function BenefitsPage() {
  const qc = useQueryClient();
  const plansQ = useQuery({ queryKey: ["benefit_plans"], queryFn: () => apiFetch<any[]>("/benefits/plans") });
  const runsQ = useQuery({ queryKey: ["benefit_runs"], queryFn: () => apiFetch<any[]>("/benefits/optimization-runs") });

  const [planName, setPlanName] = useState("Standard Medical");
  const [planCategory, setPlanCategory] = useState("medical");
  const [employer, setEmployer] = useState(400);
  const [employee, setEmployee] = useState(200);
  const [fy, setFy] = useState(new Date().getFullYear());
  const [budget, setBudget] = useState(50000);
  const [msg, setMsg] = useState<string | null>(null);

  async function addPlan() {
    try {
      await apiPost("/benefits/plans", {
        name: planName,
        category: planCategory,
        employer_cost: employer,
        employee_cost: employee,
      });
      setMsg("✓ Plan added successfully!");
      await qc.invalidateQueries({ queryKey: ["benefit_plans"] });
    } catch (e) {
      setMsg("Failed to add plan.");
    }
  }

  async function optimize() {
    try {
      await apiPost("/benefits/optimize", { fiscal_year: fy, budget });
      setMsg("✓ Optimization run complete!");
      await qc.invalidateQueries({ queryKey: ["benefit_runs"] });
    } catch (e) {
      setMsg("Optimization failed.");
    }
  }

  const plans = (plansQ.data ?? []).filter((p: any) => p.employer_cost > 0 || p.employee_cost > 0 || p.category);
  const runs = runsQ.data ?? [];

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Compensation"
        title="Benefits optimization"
        subtitle="Manage benefit plans and run the budget optimizer."
      />

      {msg && (
        <div className={`rounded-md border px-4 py-3 text-sm ${msg.startsWith("✓") ? "bg-success-bg border-success-line text-success-fg" : "bg-danger-bg border-danger-line text-danger-fg"}`}>
          {msg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Surface className="space-y-3">
          <SectionTitle title="Create plan" />
          <Input label="Name" value={planName} onChange={(e: any) => setPlanName(e.target.value)} />
          <div>
            <label className="text-sm font-medium text-ink mb-1 block">Category</label>
            <select
              className="w-full rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
              value={planCategory}
              onChange={(e) => setPlanCategory(e.target.value)}
            >
              <option value="medical">Medical</option>
              <option value="dental">Dental</option>
              <option value="vision">Vision</option>
              <option value="retirement">Retirement</option>
            </select>
          </div>
          <Input label="Employer monthly cost ($)" type="number" value={employer} onChange={(e: any) => setEmployer(parseFloat(e.target.value || "0"))} />
          <Input label="Employee monthly cost ($)" type="number" value={employee} onChange={(e: any) => setEmployee(parseFloat(e.target.value || "0"))} />
          <Button onClick={addPlan}>Add plan</Button>
        </Surface>

        <Surface className="space-y-3">
          <SectionTitle title="Run optimizer" />
          <Input label="Fiscal year" type="number" value={fy} onChange={(e: any) => setFy(parseInt(e.target.value || "0"))} />
          <Input label="Annual budget ($)" type="number" value={budget} onChange={(e: any) => setBudget(parseFloat(e.target.value || "0"))} />
          <Button onClick={optimize}>Optimize</Button>
        </Surface>
      </div>

      <Surface>
        <SectionTitle title={`Active plans (${plans.length})`} />
        <div className="mt-3 space-y-2">
          {plansQ.isLoading && <div className="text-sm text-muted">Loading…</div>}
          {plans.length === 0 && !plansQ.isLoading && <div className="text-sm text-muted">No plans yet.</div>}
          {plans.map((p: any) => (
            <div key={p.id} className="rounded-md border border-line bg-canvas p-3 flex justify-between items-center">
              <div>
                <div className="font-medium text-sm text-ink">{p.name}</div>
                <div className="text-xs text-muted capitalize">{p.category ?? "—"} {p.provider ? `· ${p.provider}` : ""}</div>
                <div className="text-xs text-muted mt-0.5">
                  {p.employer_cost != null && <span>Employer: <strong className="text-body">${p.employer_cost}/mo</strong></span>}
                  {p.employee_cost != null && <span className="ml-2">Employee: <strong className="text-body">${p.employee_cost}/mo</strong></span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Surface>

      <Surface>
        <SectionTitle title="Optimization runs" />
        <div className="mt-3 space-y-2">
          {runs.map((r: any) => (
            <div key={r.id} className="rounded-md border border-line bg-canvas p-3">
              <div className="font-medium text-sm text-ink">FY {r.fiscal_year} · Budget ${r.budget?.toLocaleString()}</div>
              <details className="mt-2">
                <summary className="cursor-pointer text-sm text-muted hover:text-ink">View result</summary>
                <pre className="mt-2 overflow-auto rounded-md bg-sunken p-3 text-xs text-body">{JSON.stringify(r.result, null, 2)}</pre>
              </details>
            </div>
          ))}
          {runs.length === 0 && !runsQ.isLoading && (
            <EmptyState title="No optimization runs yet" description="Run the optimizer above to model a benefits budget." />
          )}
        </div>
      </Surface>
    </div>
  );
}
