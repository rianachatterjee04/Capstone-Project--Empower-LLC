"use client";
/**
 * Remittances / EFTPS liabilities — surfaces the built-but-unlinked payroll
 * remittances engine (packages/payroll app/api/routers/remittances.py):
 *   - GET  /api/payroll/remittances            (tax liabilities rollup)
 *   - POST /api/payroll/remittances/{id}/mark-paid
 *   - GET  /api/payroll/compliance/calendar     (upcoming deposit/filing dates)
 * through the allow-listed /api/payroll proxy (fail-soft via PayrollGate).
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { MetricStat, PageHeader, SectionTitle, Surface, Pill, Action } from "@/components/ds";
import { fmtCents, payrollGet, payrollPost } from "@/lib/payroll";
import { PayrollGate } from "../PayrollGate";

type Liability = {
  id: string;
  run_id: string | null;
  jurisdiction: string;
  level: string;
  agency: string;
  portal_url: string | null;
  amount: string;
  amount_cents: number;
  due_date: string | null;
  status: string;
  paid_at: string | null;
};
type RemittancesPayload = { remittances: Liability[]; total_open_cents: number };
type CalItem = {
  kind: string;
  jurisdiction: string;
  agency: string;
  amount?: string;
  due_date: string | null;
  portal_url?: string | null;
};
type CalendarPayload = { items?: CalItem[] };

export default function RemittancesPage() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState("");

  const remQ = useQuery({
    queryKey: ["payroll-remittances"],
    queryFn: () => payrollGet<RemittancesPayload>("remittances"),
    refetchInterval: 60_000,
  });
  const calQ = useQuery({
    queryKey: ["payroll-compliance-cal"],
    queryFn: () => payrollGet<CalendarPayload>("compliance/calendar"),
  });

  const result = remQ.data ?? null;
  const liabilities = result?.data?.remittances ?? [];
  const openCount = liabilities.filter((l) => l.status === "open").length;
  const cal = calQ.data?.data?.items ?? [];

  async function markPaid(id: string) {
    setBusy(id);
    setMsg("");
    const res = await payrollPost(`remittances/${id}/mark-paid`, {});
    setMsg(res.error ? `Could not mark paid: ${res.error}` : "Liability marked deposited.");
    setBusy(null);
    qc.invalidateQueries({ queryKey: ["payroll-remittances"] });
    qc.invalidateQueries({ queryKey: ["payroll-compliance-cal"] });
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        eyebrow="Payroll · Compliance"
        title="Tax remittances"
        subtitle="Federal (EFTPS) and state/local tax liabilities from every payroll run — track what's owed, where to deposit, and mark deposits made."
      />

      {msg && (
        <Surface pad="sm" className="text-sm text-ink">
          {msg}
        </Surface>
      )}

      <PayrollGate result={result} />

      {result?.data && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
            <MetricStat label="Open liabilities" value={String(openCount)} hint="not yet deposited" />
            <MetricStat label="Total open" value={fmtCents(result.data.total_open_cents)} tone="accent" />
            <MetricStat label="Upcoming due dates" value={String(cal.length)} hint="deposits + filings" />
          </div>

          <Surface pad="none">
            <div className="p-5 pb-3">
              <SectionTitle title="Tax liabilities" description="Sorted by due date. Mark a liability deposited once you've paid the agency." />
            </div>
            {liabilities.length === 0 ? (
              <div className="px-5 pb-6 text-sm text-muted">No tax liabilities yet. They are created when a payroll run is processed.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                      <th className="px-5 py-2 font-medium">Agency</th>
                      <th className="px-5 py-2 font-medium">Jurisdiction</th>
                      <th className="px-5 py-2 font-medium">Due</th>
                      <th className="px-5 py-2 font-medium text-right">Amount</th>
                      <th className="px-5 py-2 font-medium">Status</th>
                      <th className="px-5 py-2 font-medium text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {liabilities.map((l) => (
                      <tr key={l.id} className="border-t border-line hover:bg-sunken">
                        <td className="px-5 py-2.5">
                          {l.portal_url ? (
                            <a href={l.portal_url} target="_blank" rel="noreferrer" className="font-medium text-ink hover:underline">
                              {l.agency}
                            </a>
                          ) : (
                            <span className="font-medium text-ink">{l.agency}</span>
                          )}
                        </td>
                        <td className="px-5 py-2.5 text-muted">
                          {l.jurisdiction} <span className="text-xs">({l.level})</span>
                        </td>
                        <td className="px-5 py-2.5 text-muted">{l.due_date ?? "—"}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{fmtCents(l.amount_cents)}</td>
                        <td className="px-5 py-2.5">
                          <Pill tone={l.status === "paid" ? "success" : "warn"}>{l.status}</Pill>
                        </td>
                        <td className="px-5 py-2.5 text-right">
                          {l.status !== "paid" && (
                            <Action size="sm" disabled={busy === l.id} onClick={() => markPaid(l.id)}>
                              {busy === l.id ? "…" : "Mark deposited"}
                            </Action>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Surface>

          {cal.length > 0 && (
            <Surface pad="none">
              <div className="p-5 pb-3">
                <SectionTitle title="Compliance calendar" description="Upcoming deposit deadlines and standard 941/940 filing dates." />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-t border-line text-left text-xs uppercase tracking-wide text-muted">
                      <th className="px-5 py-2 font-medium">Type</th>
                      <th className="px-5 py-2 font-medium">Agency</th>
                      <th className="px-5 py-2 font-medium">Jurisdiction</th>
                      <th className="px-5 py-2 font-medium">Due</th>
                      <th className="px-5 py-2 font-medium text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {cal.map((c, i) => (
                      <tr key={i} className="border-t border-line">
                        <td className="px-5 py-2.5">
                          <Pill tone={c.kind === "filing" ? "info" : "neutral"}>{c.kind}</Pill>
                        </td>
                        <td className="px-5 py-2.5 text-ink">{c.agency}</td>
                        <td className="px-5 py-2.5 text-muted">{c.jurisdiction}</td>
                        <td className="px-5 py-2.5 text-muted">{c.due_date ?? "—"}</td>
                        <td className="px-5 py-2.5 text-right tabular-nums">{c.amount ? `$${c.amount}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Surface>
          )}
        </>
      )}
    </div>
  );
}
