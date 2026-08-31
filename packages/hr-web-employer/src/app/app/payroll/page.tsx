"use client";
/**
 * Payroll dashboard — the employer home of the payroll bridge.
 *
 * Architecture: HR (hr-api) is the source of truth for people and pushes
 * employees/timesheets INTO the standalone payroll service; this workspace
 * reads payroll through the allow-listed /api/payroll proxy (fail-soft) and
 * the "Sync from HR" button triggers hr-api's POST /payroll-sync/employees.
 */
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricStat, PageHeader, SectionTitle, StatusPill, Surface } from "@/components/ds";
import { apiPost } from "@/lib/api";
import { fmtCents, payrollGet, type PayRunSummary } from "@/lib/payroll";
import { PayrollGate } from "./PayrollGate";

type RunsPayload = { runs: PayRunSummary[] };

export default function PayrollDashboardPage() {
  const qc = useQueryClient();
  const [syncMsg, setSyncMsg] = useState<string>("");
  const [syncing, setSyncing] = useState(false);

  const runsQ = useQuery({
    queryKey: ["payroll-runs"],
    queryFn: () => payrollGet<RunsPayload>("runs"),
    refetchInterval: 30_000,
  });

  const result = runsQ.data ?? null;
  const runs = result?.data?.runs ?? [];
  const latest = runs[0] ?? null;
  const needingReview = runs.filter((r) => r.status === "submitted").length;

  async function syncFromHr() {
    setSyncing(true);
    setSyncMsg("");
    try {
      const res = await apiPost<any>("/payroll-sync/employees", {});
      if (res?.error) {
        setSyncMsg(`Sync failed: ${res.error}`);
      } else {
        setSyncMsg(
          `Synced ${res?.synced ?? 0} employee(s) from HR — ` +
            `${res?.created ?? 0} created, ${res?.updated ?? 0} updated, ${res?.unchanged ?? 0} unchanged.`,
        );
      }
    } catch (e: any) {
      setSyncMsg(`Sync failed: ${e?.message ?? "hr-api unreachable"}`);
    } finally {
      setSyncing(false);
      qc.invalidateQueries({ queryKey: ["payroll-runs"] });
      qc.invalidateQueries({ queryKey: ["payroll-employees"] });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Payroll"
        title="Payroll dashboard"
        subtitle="Runs, statuses and money at a glance. People data flows HR → payroll; finance reads payroll's outputs downstream."
        actions={
          <div className="flex items-center gap-2">
            <Link
              href="/app/payroll/employees"
              className="inline-flex h-9 items-center rounded-md border border-line bg-surface px-3 text-sm font-medium text-ink hover:bg-sunken"
            >
              Payroll employees
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
            <MetricStat label="Pay runs" value={String(runs.length)} hint={`${needingReview} awaiting approval`} />
            <MetricStat
              label="Latest net pay"
              value={latest ? fmtCents(latest.totals?.net_cents ?? 0) : "—"}
              hint={latest ? `pay date ${latest.pay_date}` : "no runs yet"}
            />
            <MetricStat
              label="Latest cash required"
              value={latest ? fmtCents(latest.totals?.total_cash_required_cents ?? 0) : "—"}
              hint="net + taxes + garnishments"
            />
            <MetricStat
              label="Employees on latest run"
              value={latest ? String(latest.totals?.employees ?? 0) : "—"}
              hint={latest ? `${(latest.totals?.anomaly_flags ?? []).length} anomaly flag(s)` : ""}
            />
          </div>

          <Surface pad="none">
            <div className="p-5 pb-3">
              <SectionTitle
                title="Pay runs"
                description="Newest first. Open a run to review per-employee amounts, diffs and anomaly flags, then approve or reject."
              />
            </div>
            {runs.length === 0 ? (
              <div className="px-5 pb-6 text-sm text-muted">
                No pay runs yet. Sync employees from HR, assign them a pay schedule in payroll, then create the
                first run (or let the auto-payroll agent prepare it).
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                      <th className="px-5 py-2 font-medium">Period</th>
                      <th className="px-5 py-2 font-medium">Pay date</th>
                      <th className="px-5 py-2 font-medium">Type</th>
                      <th className="px-5 py-2 font-medium">Status</th>
                      <th className="px-5 py-2 font-medium text-right">Employees</th>
                      <th className="px-5 py-2 font-medium text-right">Gross</th>
                      <th className="px-5 py-2 font-medium text-right">Net</th>
                      <th className="px-5 py-2 font-medium text-right">Flags</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((run) => (
                      <tr key={run.id} className="border-t border-line hover:bg-sunken">
                        <td className="px-5 py-2.5">
                          <Link href={`/app/payroll/runs/${run.id}`} className="font-medium text-ink hover:underline">
                            {run.period_start} → {run.period_end}
                          </Link>
                        </td>
                        <td className="px-5 py-2.5">{run.pay_date}</td>
                        <td className="px-5 py-2.5 text-muted">{run.run_type}</td>
                        <td className="px-5 py-2.5">
                          <StatusPill value={run.status} />
                        </td>
                        <td className="px-5 py-2.5 text-right">{run.totals?.employees ?? "—"}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(run.totals?.gross_cents)}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(run.totals?.net_cents)}</td>
                        <td className="px-5 py-2.5 text-right">{(run.totals?.anomaly_flags ?? []).length || "—"}</td>
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
