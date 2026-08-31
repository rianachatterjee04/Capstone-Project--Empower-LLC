"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, apiPost } from "@/lib/api";

import { PageHeader, Surface, SectionTitle, Pill, Action, EmptyState, Divider, MetricStat } from "@/components/ds";

type GroupGap = {
  group: string;
  raw_gap_pct: number;
  raw_gap_abs: number;
  adjusted_gap_pct: number;
  adjusted_gap_abs: number;
  explained_pct: number;
  reference_mean: number;
  group_mean: number;
  reference_n: number;
  group_n: number;
  exceeds_threshold: boolean;
};

type Category = {
  job_category: string;
  headcount: number;
  raw_gap_pct: number;
  adjusted_gap_pct: number;
  adjusted_gap_abs: number;
  exceeds_threshold: boolean;
  controls_applied: string[];
};

type Analysis = {
  available: boolean;
  reason?: string;
  reference_group?: string;
  threshold: number;
  controls_applied: string[];
  headcount: number;
  groups: GroupGap[];
  job_categories: Category[];
  n_flagged_categories: number;
  directive_ready: boolean;
  cohort?: { is_sample: boolean; source: string; note: string; needs: string[] };
};

type Adjustment = {
  employee_id: string;
  name: string;
  group: string;
  cohort: Record<string, string>;
  current_salary: number;
  cohort_reference_mean: number;
  target_floor: number;
  suggested_adjustment: number;
  new_salary: number;
  pct_increase: number;
};

type Remediation = {
  available: boolean;
  reference_group?: string;
  threshold: number;
  n_employees_adjusted: number;
  total_budget: number;
  adjustments: Adjustment[];
};

type Report = {
  framework: string;
  reporting_threshold: number;
  directive_ready: boolean;
  n_flagged_categories: number;
  remediation_budget: number;
  employees_requiring_adjustment: number;
  controls_applied: string[];
  generated_note: string;
  disclaimer: string;
  flagged_categories: Category[];
};

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const usd = (v: number) => `$${Math.round(v).toLocaleString()}`;

export default function PayEquityPage() {
  const [threshold] = useState(0.05);

  const analysis = useQuery({
    queryKey: ["pay-equity", "analysis"],
    queryFn: () => apiFetch<Analysis>(`/pay-equity/analysis?threshold=${threshold}`),
  });
  const report = useQuery({
    queryKey: ["pay-equity", "report"],
    queryFn: () => apiFetch<Report>(`/pay-equity/report?threshold=${threshold}`),
  });
  const remediation = useQuery({
    queryKey: ["pay-equity", "remediation", threshold],
    queryFn: () => apiPost<Remediation>(`/pay-equity/remediation-plan`, { threshold }),
  });

  const a = analysis.data;

  return (
    <div className="space-y-7 fp-fade-in">
      <PageHeader
        eyebrow="Compensation · Regulatory"
        title="Pay Equity"
        subtitle="Raw and adjusted pay gaps with explainable controls, EU Pay Transparency Directive readiness, and a costed remediation plan."
        actions={<Pill tone={a?.directive_ready ? "success" : "danger"}>{a?.directive_ready ? "Directive-ready" : `${a?.n_flagged_categories ?? "—"} flagged`}</Pill>}
      />

      {analysis.isLoading ? (
        <Surface><EmptyState title="Analysing pay…" /></Surface>
      ) : !a?.available ? (
        <Surface><EmptyState title="Not enough data" description={a?.reason ?? "Need at least two groups to compute a gap."} /></Surface>
      ) : (
        <>
          {/* A gender pay gap is a regulatory claim. This page showed "headcount
              analysed 16", a 16.2% raw gap and a $32,825 remediation budget for
              an organisation with one employee — all of it from the cohort the
              product ships to demonstrate the maths. */}
          {a.cohort?.is_sample && (
            <Surface pad="md">
              <div className="fp-eyebrow">Worked example, not your pay data</div>
              <p className="mt-1 text-sm text-body">{a.cohort.note}</p>
              {a.cohort.needs.length > 0 && (
                <p className="mt-2 text-xs text-muted">
                  To run this on your own people it needs: {a.cohort.needs.join("; ")}.
                </p>
              )}
            </Surface>
          )}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricStat
              label="Headcount analysed"
              value={a.headcount}
              hint={a.cohort?.is_sample ? "sample cohort" : undefined}
            />
            <MetricStat label="Reference group" value={a.reference_group} hint="highest-paid group" />
            <MetricStat label="Flagged categories" value={a.n_flagged_categories} tone={a.n_flagged_categories > 0 ? "danger" : "success"} hint={`> ${pct(a.threshold)} adjusted`} />
            <MetricStat label="Remediation budget" value={remediation.data ? usd(remediation.data.total_budget) : "—"} tone={(remediation.data?.total_budget ?? 0) > 0 ? "warn" : "success"} />
          </div>

          {/* Gap by protected group */}
          <Surface>
            <SectionTitle eyebrow="By protected group" title="Raw vs adjusted pay gap" description={`Adjusted gap controls for ${a.controls_applied.join(", ")}. The adjusted gap is the "unexplained" residual the directive cares about.`} />
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-2xs uppercase tracking-eyebrow text-muted border-b border-line">
                    <th className="py-2 pr-3">Group</th>
                    <th className="py-2 pr-3">Headcount</th>
                    <th className="py-2 pr-3">Raw gap</th>
                    <th className="py-2 pr-3">Adjusted gap</th>
                    <th className="py-2 pr-3">Explained by controls</th>
                    <th className="py-2 pr-3">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {a.groups.map((g) => (
                    <tr key={g.group} className="border-b border-rule last:border-0">
                      <td className="py-2 pr-3 font-medium text-ink capitalize">{g.group} <span className="text-muted">vs {a.reference_group}</span></td>
                      <td className="py-2 pr-3 tabular-nums text-body">{g.group_n}</td>
                      <td className="py-2 pr-3 tabular-nums text-body">{pct(g.raw_gap_pct)}</td>
                      <td className="py-2 pr-3 tabular-nums font-semibold text-ink">{pct(g.adjusted_gap_pct)}</td>
                      <td className="py-2 pr-3 tabular-nums text-muted">{pct(g.explained_pct)}</td>
                      <td className="py-2 pr-3">
                        <Pill tone={g.exceeds_threshold ? "danger" : "success"}>{g.exceeds_threshold ? "Over threshold" : "Within threshold"}</Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Surface>

          {/* By job category */}
          <Surface>
            <SectionTitle eyebrow="By job category" title="Segment breakdown (job-family × level)" description="Each category's adjusted gap flags a required joint pay assessment above the 5% directive threshold." />
            <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
              {a.job_categories.map((c) => (
                <div key={c.job_category} className={`rounded-md border p-3 ${c.exceeds_threshold ? "border-danger-line bg-danger-bg/30" : "border-line bg-canvas"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-ink">{c.job_category}</div>
                    <Pill tone={c.exceeds_threshold ? "danger" : "success"}>{pct(c.adjusted_gap_pct)}</Pill>
                  </div>
                  <div className="text-2xs uppercase tracking-eyebrow text-muted mt-1">
                    {c.headcount} people · raw {pct(c.raw_gap_pct)} · adjusted {pct(c.adjusted_gap_pct)}
                  </div>
                </div>
              ))}
            </div>
          </Surface>

          {/* Remediation plan */}
          <Surface>
            <SectionTitle
              eyebrow="Remediation"
              title="Costed plan to close every cohort to threshold"
              description={remediation.data ? `${remediation.data.n_employees_adjusted} employees · ${usd(remediation.data.total_budget)} total budget to reach ${pct(remediation.data.threshold)}.` : "Computing…"}
            />
            {remediation.data && remediation.data.adjustments.length > 0 ? (
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-2xs uppercase tracking-eyebrow text-muted border-b border-line">
                      <th className="py-2 pr-3">Employee</th>
                      <th className="py-2 pr-3">Cohort</th>
                      <th className="py-2 pr-3">Current</th>
                      <th className="py-2 pr-3">Peer ref mean</th>
                      <th className="py-2 pr-3">Suggested +</th>
                      <th className="py-2 pr-3">New salary</th>
                    </tr>
                  </thead>
                  <tbody>
                    {remediation.data.adjustments.map((r) => (
                      <tr key={r.employee_id} className="border-b border-rule last:border-0">
                        <td className="py-2 pr-3 font-medium text-ink">{r.name} <span className="text-muted capitalize">· {r.group}</span></td>
                        <td className="py-2 pr-3 text-2xs text-muted">{Object.values(r.cohort).join(" · ")}</td>
                        <td className="py-2 pr-3 tabular-nums text-body">{usd(r.current_salary)}</td>
                        <td className="py-2 pr-3 tabular-nums text-muted">{usd(r.cohort_reference_mean)}</td>
                        <td className="py-2 pr-3 tabular-nums font-semibold text-warn-fg">{usd(r.suggested_adjustment)}</td>
                        <td className="py-2 pr-3 tabular-nums text-ink">{usd(r.new_salary)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="mt-3"><EmptyState title="No adjustments needed" description="Every comparable cohort is already within the threshold." /></div>
            )}
          </Surface>

          {/* Compliance report */}
          {report.data && (
            <Surface>
              <SectionTitle eyebrow="Compliance" title={report.data.framework} />
              <Divider className="my-3" />
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <MetricStat label="Directive ready" value={report.data.directive_ready ? "Yes" : "No"} tone={report.data.directive_ready ? "success" : "danger"} />
                <MetricStat label="Reporting threshold" value={pct(report.data.reporting_threshold)} />
                <MetricStat label="Employees to adjust" value={report.data.employees_requiring_adjustment} />
                <MetricStat label="Budget" value={usd(report.data.remediation_budget)} />
              </div>
              <p className="mt-3 text-sm text-body">{report.data.generated_note}</p>
              <p className="mt-2 text-xs text-muted">Controls applied: {report.data.controls_applied.join(", ")}.</p>
              <p className="mt-1 text-xs text-muted italic">{report.data.disclaimer}</p>
            </Surface>
          )}
        </>
      )}
    </div>
  );
}
