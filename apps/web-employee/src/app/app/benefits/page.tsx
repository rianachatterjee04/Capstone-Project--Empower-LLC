"use client";
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

type BenefitPlan = {
  id: string;
  name: string;
  plan_type: string;
  provider?: string | null;
  employee_cost_monthly?: number | null;
  employer_cost_monthly?: number | null;
};

type Enrollment = {
  id: string;
  plan_id: string;
  status: string;
  coverage_tier?: string | null;
  effective_date?: string | null;
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
  const plansQ = useQuery({ queryKey: ["benefit-plans"], queryFn: () => apiFetch<BenefitPlan[]>("/benefits/plans") });
  const plans = plansQ.data ?? [];

  return (
    <div className="space-y-6">
      <div>
        <div className="text-2xl font-semibold">Benefits</div>
        <div className="mt-1 text-sm text-black/60">Your benefits plans and enrollment status</div>
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
          <div className="mt-2 text-3xl font-bold">Open Enrollment</div>
          <div className="mt-1 text-xs text-black/50">Nov 2026</div>
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white shadow-sm">
        <div className="border-b border-black/10 px-5 py-4">
          <div className="text-sm font-semibold">Available Plans</div>
          <div className="text-xs text-black/50 mt-0.5">Medical, dental, vision and more</div>
        </div>
        <div className="divide-y divide-black/5">
          {plansQ.isLoading && <div className="p-5 text-sm text-black/40">Loading plans…</div>}
          {plansQ.error && <div className="p-5 text-sm text-red-500">Failed to load plans</div>}
          {!plansQ.isLoading && plans.length === 0 && (
            <div className="p-5 text-sm text-black/40">No benefits plans configured yet</div>
          )}
          {plans.map((plan) => (
            <div key={plan.id} className="flex items-center justify-between px-5 py-4 hover:bg-black/[0.02]">
              <div>
                <div className="text-sm font-medium">{plan.name}</div>
                <div className="text-xs text-black/50 capitalize">{plan.plan_type} {plan.provider ? `· ${plan.provider}` : ""}</div>
                {plan.employee_cost_monthly && (
                  <div className="text-xs text-black/50 mt-0.5">
                    Employee cost: <span className="font-medium">${plan.employee_cost_monthly}/mo</span>
                    {plan.employer_cost_monthly ? ` · Employer covers: $${plan.employer_cost_monthly}/mo` : ""}
                  </div>
                )}
              </div>
              <Badge status="active" />
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-2xl border border-black/10 bg-white p-5 shadow-sm">
        <div className="text-sm font-semibold mb-3">401(k) & Retirement</div>
        <div className="rounded-xl bg-black/5 p-4 text-sm text-black/60 text-center">
          401(k) provider integration coming soon. Connect via Benefits Admin settings.
        </div>
      </div>
    </div>
  );
}
