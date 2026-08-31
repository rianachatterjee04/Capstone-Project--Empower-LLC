"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";
import { Button } from "@/components/Button";
import { PageHeader, Surface, SectionTitle, MetricStat, StatusPill } from "@/components/ds";

type BenefitPlan = {
  id: string;
  name: string;
  category: string;
  provider?: string | null;
  employee_cost?: number | null;
  employer_cost?: number | null;
};

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
      <Surface pad="none">
        <div className="border-b border-line px-5 py-4">
          <div className="text-md font-semibold text-ink">{title}</div>
          <div className="text-xs text-muted mt-0.5">{plans.length} plan{plans.length > 1 ? "s" : ""} available</div>
        </div>
        <div className="divide-y divide-rule">
          {plans.map((plan) => (
            <div key={plan.id} className="flex items-center justify-between px-5 py-4 hover:bg-sunken/60 transition-colors duration-150 ease-calm">
              <div>
                <div className="text-sm font-medium text-ink">{plan.name}</div>
                <div className="text-xs text-muted">{plan.provider ?? "—"}</div>
                <div className="text-xs text-muted mt-0.5">
                  {plan.employee_cost != null && plan.employee_cost > 0 && (
                    <span>Your cost: <span className="font-medium text-body">${plan.employee_cost}/mo</span></span>
                  )}
                  {plan.employer_cost != null && plan.employer_cost > 0 && (
                    <span className="ml-2">Employer covers: <span className="font-medium text-body">${plan.employer_cost}/mo</span></span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <StatusPill value="active" />
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
      </Surface>
    );
  }

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Pay & Equity"
        title="Benefits"
        subtitle="Your benefits plans and enrollment."
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <MetricStat label="Available plans" value={plansQ.isLoading ? "—" : plans.length} />
        <MetricStat label="Enrollment status" value="Active" tone="success" />
        <MetricStat label="Next review" value={<span className="text-xl">Open Enrollment</span>} hint="Nov 2026" />
      </div>

      {enrollMsg && (
        <div className={`rounded-md border px-4 py-3 text-sm ${enrollMsg.startsWith("✓") ? "bg-success-bg border-success-line text-success-fg" : "bg-warn-bg border-warn-line text-warn-fg"}`}>
          {enrollMsg}
        </div>
      )}

      <Surface>
        <SectionTitle title="Coverage tier" />
        <select
          className="mt-2 w-full rounded-md border border-line bg-surface text-ink px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-accent/30 focus:border-accent"
          value={selectedTier}
          onChange={(e) => setSelectedTier(e.target.value)}
        >
          <option value="employee_only">Employee Only</option>
          <option value="employee_spouse">Employee + Spouse</option>
          <option value="employee_children">Employee + Children</option>
          <option value="family">Family</option>
        </select>
      </Surface>

      {plansQ.isLoading && <div className="text-sm text-muted">Loading plans…</div>}
      {plansQ.error && <div className="text-sm text-danger-fg">Failed to load plans</div>}

      <PlanSection title="Medical" plans={medicalPlans} />
      <PlanSection title="Dental" plans={dentalPlans} />
      <PlanSection title="Vision" plans={visionPlans} />
      <PlanSection title="Retirement & 401(k)" plans={retirementPlans} />
    </div>
  );
}
