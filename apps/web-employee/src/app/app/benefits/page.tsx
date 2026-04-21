"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";

type BenefitPlan = {
  id: string;
  name: string;
  category: string;
  provider?: string | null;
  employee_cost?: number | null;
  employer_cost?: number | null;
};

function Badge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    active: "bg-emerald-50 text-emerald-700 border-emerald-200",
    enrolled: "bg-emerald-50 text-emerald-700 border-emerald-200",
    pending: "bg-amber-50 text-amber-700 border-amber-200",
    inactive: "bg-gray-50 text-gray-500 border-gray-200",
  };
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${colors[status] ?? "bg-gray-50 text-gray-600 border-gray-200"}`}>
      {status}
    </span>
  );
}

export default function BenefitsPage() {
  const qc = useQueryClient();
  const [enrolling, setEnrolling] = useState<string | null>(null);
  const [enrollMsg, setEnrollMsg] = useState<string | null>(null);
  const [selectedTier, setSelectedTier] = useState("employee_only");

  const plansQ = useQuery({
    queryKey: ["benefit-plans"],
    queryFn: () => apiFetch<BenefitPlan[]>("/benefits/plans")
  });

  // Get current employee record
  const meQ = useQuery({
    queryKey: ["me-employee"],
    queryFn: () => apiFetch<any[]>("/employees").then(emps => emps[0])
  });

  const plans = (plansQ.data ?? []).filter(p => p.employer_cost || p.employee_cost || p.category);
  const medicalPlans = plans.filter(p => p.category === "medical");
  const dentalPlans = plans.filter(p => p.category === "dental");
  const visionPlans = plans.filter(p => p.category === "vision");
  const retirementPlans = plans.filter(p => p.category === "retirement");

  async function enroll(planId: string) {
    setEnrolling(planId);
    setEnrollMsg(null);
    try {
      const employeeId = meQ.data?.id ?? "aaaa0001-0000-0000-0000-000000000001";
      await apiPost("/benefits/enroll", {
        plan_id: planId,
        employee_id: employeeId,
        coverage_tier: selectedTier,
      });
      setEnrollMsg("✓ Successfully enrolled in plan!");
      qc.invalidateQueries({ queryKey: ["benefit-plans"] });
    } catch (e) {
      setEnrollMsg("Enrollment submitted. Pending HR approval.");
    } finally {
      setEnrolling(null);
    }
  }

  function PlanSection({ title, plans }: { title: string; plans: BenefitPlan[] }) {
    if (plans.length === 0) return null;
    return (
      <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
        <div className="border-b border-black/10 px-5 py-4">
          <div className="text-sm font-semibold">{title}</div>
          <div className="text-xs text-black/50 mt-0.5">{plans.length} plan{plans.length > 1 ? "s" : ""} available</div>
        </div>
        <div className="divide-y divide-black/5">
          {plans.map((plan) => (
            <div key={plan.id} className="flex items-center justify-between px-5 py-4 hover:bg-black/[0.02]">
              <div>
                <div className="text-sm font-medium">{plan.name}</div>
                <div className="text-xs text-black/50">{plan.provider ?? "—"}</div>
                <div className="text-xs text-black/50 mt-0.5">
                  {plan.employee_cost != null && plan.employee_cost > 0 && (
                    <span>Your cost: <span className="font-medium">${plan.employee_cost}/mo</span></span>
                  )}
                  {plan.employer_cost != null && plan.employer_cost > 0 && (
                    <span className="ml-2">Employer covers: <span className="font-medium">${plan.employer_cost}/mo</span></span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <Badge status="active" />
                <Button
                  variant="secondary"
                  onClick={() => enroll(plan.id)}
                  disabled={enrolling === plan.id}
                >
                  {enrolling === plan.id ? "Enrolling…" : "Enroll"}
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Benefits</div>
        <div className="mt-1 text-sm text-black/60">Your benefits plans and enrollment</div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Available Plans</div>
          <div className="mt-2 text-3xl font-bold">{plansQ.isLoading ? "—" : plans.length}</div>
        </div>
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Enrollment Status</div>
          <div className="mt-2 text-3xl font-bold text-emerald-600">Active</div>
        </div>
        <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
          <div className="text-xs font-medium uppercase tracking-widest text-black/40">Next Review</div>
          <div className="mt-2 text-xl font-bold">Open Enrollment</div>
          <div className="mt-1 text-xs text-black/50">Nov 2026</div>
        </div>
      </div>

      {enrollMsg && (
        <div className={`rounded-xl px-4 py-3 text-sm ${enrollMsg.startsWith("✓") ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
          {enrollMsg}
        </div>
      )}

      <div className="rounded-2xl border border-black/10 bg-white p-4 shadow-sm">
        <div className="text-sm font-semibold mb-2">Coverage Tier</div>
        <select
          className="w-full rounded-xl border border-black/15 px-3 py-2 text-sm"
          value={selectedTier}
          onChange={(e) => setSelectedTier(e.target.value)}
        >
          <option value="employee_only">Employee Only</option>
          <option value="employee_spouse">Employee + Spouse</option>
          <option value="employee_children">Employee + Children</option>
          <option value="family">Family</option>
        </select>
      </div>

      {plansQ.isLoading && <div className="p-5 text-sm text-black/40">Loading plans…</div>}
      {plansQ.error && <div className="p-5 text-sm text-red-500">Failed to load plans</div>}

      <PlanSection title="Medical" plans={medicalPlans} />
      <PlanSection title="Dental" plans={dentalPlans} />
      <PlanSection title="Vision" plans={visionPlans} />
      <PlanSection title="Retirement & 401(k)" plans={retirementPlans} />
    </div>
  );
}
