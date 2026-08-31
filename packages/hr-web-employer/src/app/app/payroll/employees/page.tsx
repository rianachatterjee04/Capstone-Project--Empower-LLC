"use client";
/**
 * Payroll-side employee list. These are payroll's records (SSN masked by
 * the service; full SSN never leaves it) — kept in sync from HR via the
 * internal bridge. "Sync from HR" pushes the HR directory into payroll.
 */
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricStat, PageHeader, Pill, SectionTitle, StatusPill, Surface } from "@/components/ds";
import { apiPost } from "@/lib/api";
import { fmtCents, payrollGet, type PayrollEmployee } from "@/lib/payroll";
import { PayrollGate } from "../PayrollGate";

type EmployeesPayload = { employees: PayrollEmployee[] };

const PAY_METHOD_LABEL: Record<string, string> = {
  direct_deposit: "Direct deposit",
  manual_check: "Manual check",
};

function payBasisLabel(e: PayrollEmployee): string {
  if (e.pay_basis === "hourly") return `${fmtCents(e.basis_amount_cents)}/hr`;
  return `${fmtCents(e.basis_amount_cents)} ${e.pay_basis}`;
}

export default function PayrollEmployeesPage() {
  const qc = useQueryClient();
  const [syncMsg, setSyncMsg] = useState("");
  const [syncing, setSyncing] = useState(false);

  const empQ = useQuery({
    queryKey: ["payroll-employees"],
    queryFn: () => payrollGet<EmployeesPayload>("employees"),
  });

  const result = empQ.data ?? null;
  const employees = result?.data?.employees ?? [];
  const missingSsn = employees.filter((e) => !e.has_valid_ssn).length;
  const portalActive = employees.filter((e) => e.portal_active).length;
  const fromHr = employees.filter((e) => e.hr_employee_id).length;

  async function syncFromHr() {
    setSyncing(true);
    setSyncMsg("");
    try {
      const res = await apiPost<any>("/payroll-sync/employees", {});
      setSyncMsg(
        res?.error
          ? `Sync failed: ${res.error}`
          : `Synced ${res?.synced ?? 0} employee(s) — ${res?.created ?? 0} created, ${res?.updated ?? 0} updated.`,
      );
    } catch (e: any) {
      setSyncMsg(`Sync failed: ${e?.message ?? "hr-api unreachable"}`);
    } finally {
      setSyncing(false);
      qc.invalidateQueries({ queryKey: ["payroll-employees"] });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Payroll"
        title="Payroll employees"
        subtitle="Payroll's employee records (SSNs stay masked and encrypted in the payroll service). HR is the source of truth — sync pushes the HR directory in."
        actions={
          <div className="flex items-center gap-2">
            <Link
              href="/app/payroll"
              className="inline-flex h-9 items-center rounded-md border border-line bg-surface px-3 text-sm font-medium text-ink hover:bg-sunken"
            >
              ← Dashboard
            </Link>
            <button
              onClick={syncFromHr}
              disabled={syncing}
              className="inline-flex h-9 items-center rounded-md bg-accent px-3 text-sm font-medium text-accent-fg hover:opacity-90 disabled:opacity-60"
            >
              {syncing ? "Syncing…" : "Sync from HR"}
            </button>
          </div>
        }
      />

      {syncMsg && (
        <Surface pad="sm" className="text-sm text-ink">
          {syncMsg}
        </Surface>
      )}

      <PayrollGate result={result} />

      {result?.data && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <MetricStat label="Employees" value={String(employees.length)} hint={`${fromHr} linked to HR records`} />
            <MetricStat
              label="Missing SSN"
              value={String(missingSsn)}
              tone={missingSsn ? "warn" : "success"}
              hint={missingSsn ? "blocks pay runs (SSN gate)" : "run-ready"}
            />
            <MetricStat label="Portal invites accepted" value={String(portalActive)} hint="employee self-service portal" />
            <MetricStat
              label="Contractors"
              value={String(employees.filter((e) => e.is_contractor).length)}
              hint="paid without withholding (1099)"
            />
          </div>

          <Surface pad="none">
            <div className="p-5 pb-3">
              <SectionTitle title="Directory" description="SSNs are masked by the payroll API; the full value never reaches this app." />
            </div>
            {employees.length === 0 ? (
              <div className="px-5 pb-6 text-sm text-muted">
                No payroll employees yet — click “Sync from HR” to push the HR directory into payroll.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                      <th className="px-5 py-2 font-medium">Name</th>
                      <th className="px-5 py-2 font-medium">Email</th>
                      <th className="px-5 py-2 font-medium">SSN</th>
                      <th className="px-5 py-2 font-medium">Department</th>
                      <th className="px-5 py-2 font-medium">Compensation</th>
                      <th className="px-5 py-2 font-medium">Pay method</th>
                      <th className="px-5 py-2 font-medium">Portal</th>
                      <th className="px-5 py-2 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {employees.map((e) => (
                      <tr key={e.id} className="border-t border-line hover:bg-sunken">
                        <td className="px-5 py-2.5 font-medium text-ink">
                          {e.first_name} {e.last_name}
                          {e.hr_employee_id && (
                            <Pill tone="info" className="ml-2">
                              HR-linked
                            </Pill>
                          )}
                        </td>
                        <td className="px-5 py-2.5 text-muted">{e.email}</td>
                        <td className="px-5 py-2.5 font-mono text-xs">
                          {e.has_valid_ssn ? e.ssn : <Pill tone="warn">missing</Pill>}
                        </td>
                        <td className="px-5 py-2.5">{e.department ?? "—"}</td>
                        <td className="px-5 py-2.5 tabular-nums">{payBasisLabel(e)}</td>
                        <td className="px-5 py-2.5">{PAY_METHOD_LABEL[e.pay_method] ?? e.pay_method}</td>
                        <td className="px-5 py-2.5">
                          {e.portal_active ? <Pill tone="success">active</Pill> : <Pill tone="neutral">not invited</Pill>}
                        </td>
                        <td className="px-5 py-2.5">
                          <StatusPill value={e.status} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Surface>
        </>
      )}
    </div>
  );
}
