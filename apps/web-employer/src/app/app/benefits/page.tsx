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

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Benefits Optimization</div>
        <div className="text-sm text-black/60">Manage benefit plans and run budget optimizer.</div>
      </div>

      {msg && (
        <div className={`rounded-xl px-4 py-3 text-sm ${msg.startsWith("✓") ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
          {msg}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Create plan</div>
          <Input label="Name" value={planName} onChange={(e: any) => setPlanName(e.target.value)} />
          <div>
            <label className="text-xs text-black/60 mb-1 block">Category</label>
            <select
              className="w-full rounded-xl border border-black/15 px-3 py-2 text-sm"
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
        </div>

        <div className="rounded-2xl border border-black/10 p-4 space-y-3">
          <div className="text-sm font-semibold">Run optimizer</div>
          <Input label="Fiscal year" type="number" value={fy} onChange={(e: any) => setFy(parseInt(e.target.value || "0"))} />
          <Input label="Annual budget ($)" type="number" value={budget} onChange={(e: any) => setBudget(parseFloat(e.target.value || "0"))} />
          <Button onClick={optimize}>Optimize</Button>
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold mb-3">Active Plans ({plans.length})</div>
        <div className="space-y-2">
          {plansQ.isLoading && <div className="text-sm text-black/40">Loading…</div>}
          {plans.length === 0 && !plansQ.isLoading && <div className="text-sm text-black/40">No plans yet.</div>}
          {plans.map((p: any) => (
            <div key={p.id} className="rounded-xl border border-black/10 p-3 flex justify-between items-center">
              <div>
                <div className="font-medium text-sm">{p.name}</div>
                <div className="text-xs text-black/60 capitalize">{p.category ?? "—"} {p.provider ? `· ${p.provider}` : ""}</div>
                <div className="text-xs text-black/50 mt-0.5">
                  {p.employer_cost != null && <span>Employer: <strong>${p.employer_cost}/mo</strong></span>}
                  {p.employee_cost != null && <span className="ml-2">Employee: <strong>${p.employee_cost}/mo</strong></span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 p-4">
        <div className="text-sm font-semibold mb-3">Optimization runs</div>
        <div className="space-y-2">
          {(runsQ.data ?? []).map((r: any) => (
            <div key={r.id} className="rounded-xl border border-black/10 p-3">
              <div className="font-medium text-sm">FY {r.fiscal_year} • Budget ${r.budget?.toLocaleString()}</div>
              <details className="mt-2">
                <summary className="cursor-pointer text-sm text-black/60">View result</summary>
                <pre className="mt-2 overflow-auto rounded-xl bg-black/5 p-3 text-xs">{JSON.stringify(r.result, null, 2)}</pre>
              </details>
            </div>
          ))}
          {(runsQ.data ?? []).length === 0 && !runsQ.isLoading && <div className="text-sm text-black/40">No optimization runs yet.</div>}
        </div>
      </div>
    </div>
  );
}
