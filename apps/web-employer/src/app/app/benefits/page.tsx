"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { Input } from "@/components/Input";

export default function BenefitsPage() {
  const qc = useQueryClient();
  const plansQ = useQuery({ queryKey: ["benefit_plans"], queryFn: () => apiFetch<any[]>("/benefits/plans") });
  const runsQ = useQuery({ queryKey: ["benefit_runs"], queryFn: () => apiFetch<any[]>("/benefits/optimization-runs") });

  const [planName, setPlanName] = useState("Standard Medical");
  const [planType, setPlanType] = useState("medical");
  const [employer, setEmployer] = useState(400);
  const [fy, setFy] = useState(new Date().getFullYear());
  const [budget, setBudget] = useState(50000);

  async function addPlan() {
    await apiPost("/benefits/plans", { name: planName, type: planType, employer_monthly_cost: employer, employee_monthly_cost: 0 });
    await qc.invalidateQueries({ queryKey: ["benefit_plans"] });
  }

  async function optimize() {
    await apiPost("/benefits/optimize", { fiscal_year: fy, budget });
    await qc.invalidateQueries({ queryKey: ["benefit_runs"] });
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Benefits Optimization</div>
        <div className="text-sm text-black/60">Greedy optimizer MVP (upgradeable to ILP/knapsack).</div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Create plan</div>
          <Input label="Name" value={planName} onChange={(e) => setPlanName(e.target.value)} />
          <Input label="Type" value={planType} onChange={(e) => setPlanType(e.target.value)} />
          <Input label="Employer monthly cost" type="number" value={employer} onChange={(e) => setEmployer(parseFloat(e.target.value || "0"))} />
          <Button onClick={addPlan}>Add plan</Button>
        </div>

        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Run optimizer</div>
          <Input label="Fiscal year" type="number" value={fy} onChange={(e) => setFy(parseInt(e.target.value || "0"))} />
          <Input label="Annual budget" type="number" value={budget} onChange={(e) => setBudget(parseFloat(e.target.value || "0"))} />
          <Button onClick={optimize}>Optimize</Button>
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Plans</div>
        <div className="mt-3 space-y-2">
          {(plansQ.data ?? []).map((p) => (
            <div key={p.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">{p.name}</div>
              <div className="text-xs text-black/60">{p.type} • employer/mo: {p.employer_monthly_cost}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold">Optimization runs</div>
        <div className="mt-3 space-y-2">
          {(runsQ.data ?? []).map((r) => (
            <div key={r.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium">FY {r.fiscal_year} • Budget {r.budget}</div>
              <details className="mt-2">
                <summary className="cursor-pointer text-sm text-black/60">View result</summary>
                <pre className="mt-2 overflow-auto rounded-xl bg-black/5 p-3 text-xs">{JSON.stringify(r.result, null, 2)}</pre>
              </details>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
